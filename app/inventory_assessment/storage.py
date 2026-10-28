"""Trusted resolution and additive receipt persistence on explicit repository transactions."""
from contextlib import contextmanager
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.evidence_store.repository import EvidenceTransaction, validated
from app.evidence_store.verification import VerificationRecord
from .contracts import AssessmentProfile, InventoryManifest, TrustedAssessmentReceipt, ProfileStatus
from .errors import (AssessmentIntegrityError, AssessmentSecurityError, AssessmentUnavailable,
                     IdempotencyConflict)


@contextmanager
def failures():
    try:
        yield
    except (ValidationError, LookupError) as exc:
        raise AssessmentIntegrityError('INVALID_OR_MISSING_PERSISTED_CONTRACT') from exc
    except PermissionError as exc:
        raise AssessmentSecurityError('UNTRUSTED_TRANSACTION') from exc
    except ValueError as exc:
        raise AssessmentIntegrityError('INVALID_PERSISTED_CONTRACT_OR_DIGEST') from exc
    except DBAPIError as exc:
        code = getattr(exc.orig, 'pgcode', None)
        if code == '42501':
            raise AssessmentSecurityError('DATABASE_PRINCIPAL_DENIED') from exc
        message = str(exc.orig).splitlines()[0]
        if message in ('STALE_OR_REVOKED_EVIDENCE', 'STALE_OR_REVOKED_VERIFICATION',
                       'SNAPSHOT_BINDING_MISMATCH', 'MISSING_VERIFICATION',
                       'VERIFICATION_PAYLOAD_INVALID', 'VERIFICATION_NOT_VERIFIED',
                       'ASSESSMENT_RECEIPT_BINDING_INVALID'):
            raise AssessmentIntegrityError(message) from exc
        if message == 'IDEMPOTENCY_CONFLICT':
            raise IdempotencyConflict(message) from exc
        raise AssessmentUnavailable('DATABASE_OR_AUDIT_UNAVAILABLE') from exc
    except SQLAlchemyError as exc:
        raise AssessmentUnavailable('DATABASE_OR_AUDIT_UNAVAILABLE') from exc


def context(tx):
    if not isinstance(tx, EvidenceTransaction):
        raise AssessmentSecurityError('TRUSTED_REPOSITORY_TRANSACTION_REQUIRED')
    tx.require_repository_origin()
    return tx.connection.scalar(text('SELECT rori_evidence.assessment_context(:t)'), {'t': tx.restaurant_id})


def store_manifest(tx, manifest):
    with failures():
        tx.require_repository_origin()
        manifest = validated(InventoryManifest, manifest)
        if manifest.scope.restaurant_id != tx.restaurant_id:
            raise AssessmentSecurityError('TENANT_MISMATCH')
        tx.connection.execute(text('SELECT rori_evidence.put_inventory_manifest(:t,CAST(:p AS jsonb))'),
                              {'t': tx.restaurant_id, 'p': manifest.model_dump_json()})
        return manifest


def provision_profile(connection, restaurant_id, profile):
    """Explicit schema-admin provisioning. Never called by the adapter or app startup."""
    profile = validated(AssessmentProfile, profile)
    database = connection.scalar(text('SELECT current_database()'))
    if profile.status == ProfileStatus.SYNTHETIC_TEST_APPROVED and database != 'rori_evidence_test':
        raise AssessmentSecurityError('SYNTHETIC_PROFILE_REQUIRES_DISPOSABLE_TEST_DATABASE')
    connection.execute(text('''INSERT INTO rori_evidence.inventory_profiles
        (restaurant_id,identifier,version,digest,payload) VALUES(:t,:i,:v,:d,CAST(:p AS jsonb))'''),
        {'t': restaurant_id, 'i': profile.identifier, 'v': profile.version,
         'd': profile.digest, 'p': profile.model_dump_json()})


def profile(tx, reference):
    row = tx.connection.execute(text('''SELECT payload,digest FROM rori_evidence.inventory_profiles
        WHERE restaurant_id=:t AND identifier=:i AND version=:v'''),
        {'t': tx.restaurant_id, 'i': reference.identifier, 'v': reference.version}).first()
    if row is None:
        return None
    value = validated(AssessmentProfile, row.payload)
    if value.digest != reference.digest or row.digest != reference.digest or value.reference() != reference:
        raise AssessmentIntegrityError('PROFILE_BINDING_MISMATCH')
    return value


def manifest(tx, identity, digest):
    row = tx.connection.execute(text('''SELECT payload,digest FROM rori_evidence.inventory_manifests
        WHERE restaurant_id=:t AND manifest_id=CAST(:i AS uuid)'''),
        {'t': tx.restaurant_id, 'i': str(identity)}).first()
    if row is None:
        return None
    value = validated(InventoryManifest, row.payload)
    if value.digest != digest or row.digest != digest or value.manifest_id != identity:
        raise AssessmentIntegrityError('MANIFEST_BINDING_MISMATCH')
    return value


def verification(tx, reference):
    payload = tx.connection.scalar(text('SELECT rori_evidence.current_verification(:t,CAST(:i AS uuid),:r)'),
        {'t': tx.restaurant_id, 'i': str(reference.verification_id), 'r': reference.revision})
    value = validated(VerificationRecord, payload)
    if value.reference() != reference:
        raise AssessmentIntegrityError('VERIFICATION_REFERENCE_MISMATCH')
    return value


def previous(tx, key, request_digest):
    row = tx.connection.execute(text('''SELECT request_digest,receipt FROM rori_evidence.assessment_runs
        WHERE restaurant_id=:t AND idempotency_key=:k'''), {'t': tx.restaurant_id, 'k': key}).first()
    if row is None:
        return None
    if row.request_digest != request_digest:
        raise IdempotencyConflict('IDEMPOTENCY_KEY_REUSED_WITH_CHANGED_REQUEST')
    receipt = validated(TrustedAssessmentReceipt, row.receipt)
    historical = tx.get('assessment', receipt.assessment.assessment_id)
    if historical != receipt.assessment:
        raise AssessmentIntegrityError('ASSESSMENT_RECEIPT_MISMATCH')
    return receipt


def save(tx, key, request_digest, receipt):
    receipt = validated(TrustedAssessmentReceipt, receipt)
    tx.append('assessment', receipt.assessment)
    tx.connection.execute(text('SELECT rori_evidence.save_assessment_run(:t,:k,:d,CAST(:p AS jsonb))'),
        {'t': tx.restaurant_id, 'k': key, 'd': request_digest, 'p': receipt.model_dump_json()})
    return receipt
