"""Migration and role probes restricted to disposable local PostgreSQL."""
from uuid import uuid4

import pytest
from psycopg2.errors import DuplicateTable
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.evidence_store.migration import install, install_assessments
from tests.postgres.test_inventory_assessment import assessment_stores, bundle, assess

pytestmark = pytest.mark.postgres


@pytest.fixture
def migration_database(pg_admin):
    name = 'rori_review_'+uuid4().hex
    with pg_admin.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
        conn.execute(text(f'CREATE DATABASE {name}'))
    engine = create_engine(pg_admin.url.set(database=name), hide_parameters=True)
    try:
        yield engine
    finally:
        engine.dispose()
        with pg_admin.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
            conn.execute(text(f'DROP DATABASE {name}'))


def test_v1_v2_explicit_upgrade_and_repeat_installation(migration_database):
    engine = migration_database
    install(engine)
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM rori_evidence.schema_versions')) == 1
        assert conn.scalar(text("SELECT to_regclass('rori_evidence.assessment_runs')")) is None
    install_assessments(engine)
    install_assessments(engine)
    install(engine)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT version FROM rori_evidence.schema_versions ORDER BY version')).scalars().all() == [1, 2]
        assert conn.scalar(text("SELECT to_regclass('rori_evidence.assessment_runs') IS NOT NULL"))


@pytest.mark.parametrize('defect', ['v1_checksum', 'v2_checksum', 'unknown_version', 'missing_v1'])
def test_unknown_or_modified_migration_ledgers_rejected(migration_database, defect):
    engine = migration_database
    install_assessments(engine)
    with engine.begin() as conn:
        if defect.endswith('checksum'):
            conn.execute(text('UPDATE rori_evidence.schema_versions SET checksum=:bad WHERE version=:v'),
                         {'bad': '0'*64, 'v': 1 if defect.startswith('v1') else 2})
        elif defect == 'unknown_version':
            conn.execute(text("INSERT INTO rori_evidence.schema_versions VALUES(3,'unreviewed')"))
        else:
            conn.execute(text('DELETE FROM rori_evidence.schema_versions WHERE version=1'))
    with pytest.raises(ValueError, match='Unknown or changed'):
        install_assessments(engine)


def test_unversioned_partial_schema_is_not_adopted(migration_database):
    with migration_database.begin() as conn:
        conn.execute(text('CREATE SCHEMA rori_evidence'))
    with pytest.raises(ValueError, match='Unversioned'):
        install_assessments(migration_database)


def test_partial_v2_objects_roll_back_failed_upgrade(migration_database):
    engine = migration_database
    install(engine)
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE rori_evidence.inventory_manifests(unexpected integer)'))
    with pytest.raises(DuplicateTable, match='already exists'):
        install_assessments(engine)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT version FROM rori_evidence.schema_versions')).scalars().all() == [1]
        assert conn.scalar(text("SELECT to_regclass('rori_evidence.inventory_profiles')")) is None


@pytest.mark.parametrize('object_ddl', [
    'TABLE rori_evidence.inventory_profiles',
    'TABLE rori_evidence.inventory_manifests',
    'TABLE rori_evidence.assessment_runs',
    'FUNCTION rori_evidence.assessment_context(bigint)',
    'FUNCTION rori_evidence.current_verification(bigint,uuid,integer)',
    'FUNCTION rori_evidence.put_inventory_manifest(bigint,jsonb)',
    'FUNCTION rori_evidence.save_assessment_run(bigint,text,text,jsonb)',
])
def test_matching_ledger_does_not_adopt_missing_required_objects(migration_database, object_ddl):
    engine = migration_database
    install_assessments(engine)
    with engine.begin() as conn:
        conn.execute(text('DROP '+object_ddl))
    with pytest.raises(ValueError, match='Incomplete assessment schema'):
        install_assessments(engine)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT version FROM rori_evidence.schema_versions ORDER BY version')).scalars().all() == [1, 2]


def test_function_privileges_owners_search_paths_and_rls(assessment_stores):
    writer, verifier, other, admin = assessment_stores
    with admin.connect() as conn:
        rows = conn.execute(text("""SELECT p.proname,p.prosecdef,p.proconfig,
            pg_get_userbyid(p.proowner) AS owner,
            EXISTS(SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE') AS public_exec
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname='rori_evidence' AND p.proname IN
            ('assessment_context','current_verification','put_inventory_manifest','save_assessment_run')""")).mappings().all()
        assert len(rows) == 4
        for row in rows:
            assert row.prosecdef and row.proconfig == ['search_path=pg_catalog, rori_evidence']
            assert row.owner == conn.scalar(text('SELECT current_user'))
            assert not row.public_exec
        tables = conn.execute(text("""SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class
            WHERE relnamespace='rori_evidence'::regnamespace
            AND relname IN ('inventory_profiles','inventory_manifests','assessment_runs')""")).all()
        assert len(tables) == 3 and all(row.relrowsecurity and row.relforcerowsecurity for row in tables)
    with writer.transaction() as tx:
        assert tx.connection.scalar(text('SELECT session_user')) == writer.engine.url.username
        for table in ('inventory_profiles','inventory_manifests','assessment_runs'):
            assert tx.connection.scalar(text("SELECT has_table_privilege(session_user,:table,'SELECT')"),
                                        {'table': 'rori_evidence.'+table})
            assert not tx.connection.scalar(text("SELECT has_table_privilege(session_user,:table,'INSERT')"),
                                            {'table': 'rori_evidence.'+table})


def test_set_role_does_not_switch_authenticated_tenant(assessment_stores):
    writer, verifier, other, admin = assessment_stores
    quote = admin.dialect.identifier_preparer.quote
    with admin.begin() as conn:
        conn.execute(text(f'GRANT {quote(other.engine.url.username)} TO {quote(writer.engine.url.username)}'))
    with writer.transaction() as tx:
        tx.connection.execute(text(f'SET LOCAL ROLE {quote(other.engine.url.username)}'))
        assert tx.connection.scalar(text('SELECT session_user')) == writer.engine.url.username
        assert tx.connection.scalar(text('SELECT current_user')) == other.engine.url.username
        assert not tx.connection.scalar(text('SELECT rori_evidence.allowed(:t)'), {'t': other.restaurant_id})
        assert tx.connection.scalar(text('SELECT rori_evidence.allowed(:t)'), {'t': writer.restaurant_id})


def test_authorized_sql_can_store_opaque_manifest_but_adapter_revalidates(bundle):
    from app.inventory_assessment.errors import AssessmentIntegrityError
    data = bundle()
    payload = data.manifest.model_dump(mode='json')
    identity = uuid4()
    payload['manifest_id'] = str(identity)
    payload['claims'] = 'invalid-not-an-array'
    import json
    with data.writer.transaction() as tx:
        tx.connection.execute(text('SELECT rori_evidence.put_inventory_manifest(:t,CAST(:p AS jsonb))'),
                              {'t': data.scope.restaurant_id, 'p': json.dumps(payload)})
    with pytest.raises(AssessmentIntegrityError):
        assess(data, manifest_id=identity)


def test_old_audit_subject_enum_cannot_parse_new_subjects(bundle):
    # Frozen v1 reader values from preservation HEAD, without depending on a Git
    # checkout (or the current branch's evolving enum) at test runtime.
    from enum import Enum
    old_enum = Enum('OldSubjectType', {v.upper(): v for v in
        ('evidence', 'verification', 'snapshot', 'assessment', 'eligibility', 'decision', 'legacy_claim')})
    data = bundle()
    assess(data)
    with data.writer.transaction() as tx:
        events = [e for e in tx.audit_events() if e.subject_type.value in ('inventory_manifest', 'assessment_run')]
    assert {e.subject_type.value for e in events} == {'inventory_manifest', 'assessment_run'}
    for event in events:
        with pytest.raises(ValueError):
            old_enum(event.subject_type.value)
