"""Explicit additive migration using the existing SQLAlchemy dependency.

Never reads DATABASE_URL/.env and never runs during application startup. The
caller must deliberately supply a schema-admin engine for the intended database.
"""
from hashlib import sha256
from pathlib import Path

from sqlalchemy import text


def _require_assessment_objects(connection):
    """Reject incomplete v2 provisioning; never auto-repair a checksummed schema.

    Presence is not a full catalog-definition/privilege attestation. Those still
    require deployment review; migration digests attest the reviewed SQL bytes.
    """
    for name in ('inventory_profiles', 'inventory_manifests', 'assessment_runs'):
        if connection.scalar(text('SELECT to_regclass(:name)'), {'name': 'rori_evidence.'+name}) is None:
            raise ValueError('Incomplete assessment schema; explicit administrative review required')
    for signature in ('assessment_context(bigint)', 'current_verification(bigint,uuid,integer)',
                      'put_inventory_manifest(bigint,jsonb)', 'save_assessment_run(bigint,text,text,jsonb)'):
        if connection.scalar(text('SELECT to_regprocedure(:name)'), {'name': 'rori_evidence.'+signature}) is None:
            raise ValueError('Incomplete assessment schema; explicit administrative review required')


def install(engine):
    if engine.dialect.name != 'postgresql':
        raise ValueError('PostgreSQL is required; SQLite cannot establish these guarantees')
    script = Path(__file__).with_name('sql').joinpath('001_evidence.sql').read_text()
    checksum = sha256(script.encode()).hexdigest()
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('rori-evidence-schema',0))"))
        exists = connection.scalar(text("SELECT to_regclass('rori_evidence.schema_versions') IS NOT NULL"))
        if exists:
            rows = connection.execute(text('SELECT version,checksum FROM rori_evidence.schema_versions ORDER BY version')).all()
            second = Path(__file__).with_name('sql').joinpath('002_inventory_assessments.sql')
            accepted = [(1, checksum), (2, sha256(second.read_bytes()).hexdigest())]
            if rows not in (accepted[:1], accepted):
                raise ValueError('Unknown or changed evidence schema migration; explicit upgrade required')
            if rows == accepted:
                _require_assessment_objects(connection)
            return
        # A pre-existing unversioned schema is deliberately not adopted.
        if connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='rori_evidence')")):
            raise ValueError('Unversioned evidence schema already exists')
        cursor = connection.connection.cursor()
        try:
            cursor.execute(script)
        finally:
            cursor.close()
        connection.execute(text('INSERT INTO rori_evidence.schema_versions VALUES(1,:checksum)'), {'checksum': checksum})


def grant_runtime(connection, login_role):
    """Schema-admin provisioning, not runtime self-registration or tenant grants."""
    role = connection.dialect.identifier_preparer.quote(login_role)
    connection.execute(text(f'GRANT USAGE ON SCHEMA rori_evidence TO {role}'))
    for table in ('objects', 'links', 'revocations', 'audit_events'):
        connection.execute(text(f'GRANT SELECT ON rori_evidence.{table} TO {role}'))
    for signature in ('allowed(bigint)', 'lock_scope(bigint)',
                      'append_object(bigint,text,uuid,integer,jsonb,integer)',
                      'revoke_object(bigint,text,uuid,integer,text)',
                      'resolve_snapshot(bigint,uuid,text)'):
        connection.execute(text(f'GRANT EXECUTE ON FUNCTION rori_evidence.{signature} TO {role}'))


def install_assessments(engine):
    """Explicit additive upgrade; old install() remains a version-1 initializer."""
    install(engine)
    script = Path(__file__).with_name('sql').joinpath('002_inventory_assessments.sql').read_text()
    checksum = sha256(script.encode()).hexdigest()
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('rori-evidence-schema',0))"))
        previous = connection.scalar(text('SELECT checksum FROM rori_evidence.schema_versions WHERE version=2'))
        if previous is not None:
            if previous != checksum:
                raise ValueError('Changed assessment migration; explicit upgrade required')
            _require_assessment_objects(connection)
            return
        cursor = connection.connection.cursor()
        try:
            cursor.execute(script)
        finally:
            cursor.close()
        _require_assessment_objects(connection)
        connection.execute(text('INSERT INTO rori_evidence.schema_versions VALUES(2,:checksum)'), {'checksum': checksum})


def grant_assessment_runtime(connection, login_role):
    """Admin-only additional grants for provisioned assessment service logins."""
    role = connection.dialect.identifier_preparer.quote(login_role)
    for table in ('inventory_profiles', 'inventory_manifests', 'assessment_runs'):
        connection.execute(text(f'GRANT SELECT ON rori_evidence.{table} TO {role}'))
    for signature in ('assessment_context(bigint)', 'current_verification(bigint,uuid,integer)',
                      'put_inventory_manifest(bigint,jsonb)', 'save_assessment_run(bigint,text,text,jsonb)'):
        connection.execute(text(f'GRANT EXECUTE ON FUNCTION rori_evidence.{signature} TO {role}'))
