"""Explicit additive migration using the existing SQLAlchemy dependency.

Never reads DATABASE_URL/.env and never runs during application startup. The
caller must deliberately supply a schema-admin engine for the intended database.
"""
from hashlib import sha256
from pathlib import Path

from sqlalchemy import text


def install(engine):
    if engine.dialect.name != 'postgresql':
        raise ValueError('PostgreSQL is required; SQLite cannot establish these guarantees')
    script = Path(__file__).with_name('sql').joinpath('001_evidence.sql').read_text()
    checksum = sha256(script.encode()).hexdigest()
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('rori-evidence-schema',0))"))
        exists = connection.scalar(text("SELECT to_regclass('rori_evidence.schema_versions') IS NOT NULL"))
        if exists:
            rows = connection.execute(text('SELECT version,checksum FROM rori_evidence.schema_versions')).all()
            if rows != [(1, checksum)]:
                raise ValueError('Unknown or changed evidence schema migration; explicit upgrade required')
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
