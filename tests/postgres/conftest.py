"""Real PostgreSQL tests: explicit isolated config, never DATABASE_URL or .env."""
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.evidence_store.migration import install, grant_runtime
from app.evidence_store.repository import EvidenceRepository


@pytest.fixture(scope='session')
def pg_admin():
    config_path = os.environ.get('RORI_EVIDENCE_TEST_CONFIG')
    if not config_path:
        pytest.skip('Isolated PostgreSQL not enabled: set RORI_EVIDENCE_TEST_CONFIG explicitly')
    config = json.loads(Path(config_path).read_text())
    url = make_url(config['url'])
    if url.database != 'rori_evidence_test' or url.host not in ('localhost', '127.0.0.1'):
        pytest.fail('Refusing a database outside the explicitly isolated local test target')
    admin = create_engine(url, hide_parameters=True)
    install(admin)
    yield admin
    admin.dispose()


@pytest.fixture
def stores(pg_admin):
    suffix = uuid4().hex[:16]
    roles = ['writer_'+suffix, 'verifier_'+suffix, 'other_'+suffix]
    tenant = 1000 + int(suffix, 16) % 1000000000
    password = uuid4().hex
    capabilities = [('write', 'assess', 'evaluate', 'revoke'),
                    ('verify:source', 'verify:count', 'verify:coverage', 'verify:import_integrity', 'revoke'),
                    ('write',)]
    engines = []
    with pg_admin.begin() as conn:
        for index, role in enumerate(roles):
            # Synthetic identifiers and passwords only; never print connection URLs.
            conn.execute(text(f'CREATE ROLE "{role}" LOGIN PASSWORD \'{password}\''))
            grant_runtime(conn, role)
            conn.execute(text('INSERT INTO rori_evidence.principal_grants VALUES(:role,:tenant,:actor,:caps)'),
                {'role': role, 'tenant': tenant if index < 2 else tenant+1,
                 'actor': 'verifier' if index == 1 else 'writer', 'caps': list(capabilities[index])})
            engines.append(create_engine(pg_admin.url.set(username=role, password=password), hide_parameters=True))
    result = [EvidenceRepository(engine, tenant if i < 2 else tenant+1) for i, engine in enumerate(engines)]
    yield (*result, pg_admin)
    for engine in engines:
        engine.dispose()
    # Test rows are intentionally append-only even for test cleanup; no production data touched.
    # Roles can be disabled without deleting historical actor identities.
    with pg_admin.begin() as conn:
        for role in roles:
            conn.execute(text(f'ALTER ROLE "{role}" NOLOGIN'))
