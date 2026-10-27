from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Event
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.evidence_contracts.common import EvidenceRevisionReference, ReasonCode, VerificationPurpose
from app.evidence_contracts.evidence import EvidenceRecord, EvidenceSnapshot, EvidenceKind, Quantity, ValueState
from app.evidence_store.repository import EvidenceRepository
from app.evidence_store.verification import VerificationRecord, VerificationStatus
from app.evidence_store.legacy import prepare_legacy
from app.evidence_store.migration import install
from tests.contracts.factories import record_data, scope, NOW, POLICY, denial_data, eligible_assessment_data
from app.evidence_contracts.decisions import ReliabilityAssessment, DecisionEligibility
from app.data_reliability.models import ReliabilityState
from app.data_reliability.reliability import EvidenceConfidence

pytestmark = pytest.mark.postgres


def observation(store, **overrides):
    data = record_data()
    data.update(reference=EvidenceRevisionReference(restaurant_id=store.restaurant_id,
        evidence_id=uuid4(), revision=1), scope=scope(restaurant_id=store.restaurant_id))
    data.update(overrides)
    return EvidenceRecord(**data)


def insert(store, record):
    with store.transaction() as tx:
        return tx.append('evidence', record)


def sealed(store, record, refs=()):
    with store.transaction() as tx:
        return tx.assemble_snapshot(scope=record.scope, policy=POLICY, created_at=NOW,
            evidence_refs=(record.reference,), verification_refs=refs)


def correction(record, quantity='1'):
    return EvidenceRecord(**{**record.model_dump(), 'reference': EvidenceRevisionReference(
        restaurant_id=record.scope.restaurant_id, evidence_id=record.reference.evidence_id,
        revision=record.reference.revision+1), 'supersedes': record.reference,
        'quantity': Quantity(state=ValueState.OBSERVED, value=Decimal(quantity))})


def verification(record, purpose=VerificationPurpose.COUNT, issuer='verifier'):
    return VerificationRecord(schema_version='1.0.0', verification_id=uuid4(), revision=1,
        evidence=record.reference, issuer_id=issuer, purpose=purpose, method='independent-count',
        supporting_refs=('artifact-1',), verified_at=NOW, scope_description='item-period',
        limitations=(), status=VerificationStatus.VERIFIED)


def test_migration_is_explicit_idempotent_and_runtime_cannot_install(stores):
    writer, _, _, admin = stores
    install(admin)
    with pytest.raises(DBAPIError):
        install(writer.engine)
    with pytest.raises(PermissionError):
        with EvidenceRepository(admin, writer.restaurant_id).transaction():
            pytest.fail('Owner runtime accepted')


@pytest.mark.parametrize('operation', ['UPDATE', 'DELETE', 'TRUNCATE'])
def test_database_immutable_even_owner_dml(stores, operation):
    writer, _, _, admin = stores
    insert(writer, observation(writer))
    query = {'UPDATE': "UPDATE rori_evidence.objects SET payload=payload",
             'DELETE': 'DELETE FROM rori_evidence.objects',
             'TRUNCATE': 'TRUNCATE rori_evidence.objects CASCADE'}[operation]
    with pytest.raises(DBAPIError, match='APPEND_ONLY_VIOLATION'):
        with admin.begin() as conn:
            conn.execute(text(query))


@pytest.mark.parametrize('table', ['objects', 'links', 'revocations', 'audit_events'])
def test_runtime_has_no_direct_write_privileges(stores, table):
    writer, _, _, _ = stores
    with pytest.raises(DBAPIError, match='permission denied'):
        with writer.engine.begin() as conn:
            conn.execute(text(f'DELETE FROM rori_evidence.{table}'))


def test_tenant_isolation_uses_database_login_not_requested_tenant(stores):
    writer, _, other, _ = stores
    rec = insert(writer, observation(writer))
    with other.transaction() as tx:
        with pytest.raises(LookupError):
            tx.get('evidence', rec.reference.evidence_id)
        count = tx.connection.scalar(text('SELECT count(*) FROM rori_evidence.objects WHERE restaurant_id=:t'),
                                     {'t': writer.restaurant_id})
        assert count == 0
    with pytest.raises(DBAPIError, match='TENANT_OR_CAPABILITY_DENIED'):
        with EvidenceRepository(other.engine, writer.restaurant_id).transaction():
            pytest.fail('Cross-tenant database principal accepted')
    with pytest.raises(DBAPIError, match='TENANT_MISMATCH'):
        insert(other, rec)


def test_exact_revisions_and_optimistic_concurrency(stores):
    writer, _, _, _ = stores
    rec = insert(writer, observation(writer))
    revised = correction(rec)
    def update():
        try:
            with writer.transaction() as tx:
                tx.append('evidence', revised, expected_revision=1)
            return 'committed'
        except DBAPIError as exc:
            assert 'REVISION_CONFLICT' in str(exc.orig)
            return 'conflict'
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: update(), range(2)))
    assert sorted(results) == ['committed', 'conflict']
    with writer.transaction() as tx:
        assert tx.get('evidence', rec.reference.evidence_id, 1) == rec
        assert tx.get('evidence', rec.reference.evidence_id, 2) == revised
        events = tx.audit_events()
        assert [e.action.value for e in events] == ['submit', 'correct']
        assert [e.sequence for e in events] == [1, 2]


def test_snapshot_reproducible_and_tampering_rejected(stores):
    writer, _, _, _ = stores
    rec = insert(writer, observation(writer))
    snap = sealed(writer, rec)
    assert EvidenceSnapshot(**snap.model_dump()).digest == snap.digest
    with writer.transaction() as tx:
        assert tx.resolve_snapshot(snap.reference()) == snap
    forged = snap.model_copy(update={'digest': 'a'*64})
    with pytest.raises(ValidationError, match='digest'):
        with writer.transaction() as tx:
            tx.append('snapshot', forged)
    altered = correction(rec).model_copy(update={'reference': rec.reference, 'supersedes': None})
    fresh = EvidenceSnapshot(schema_version='1.0.0', scope=rec.scope, policy=POLICY,
        created_at=NOW+timedelta(seconds=1), records=(altered,))
    with pytest.raises(DBAPIError, match='SNAPSHOT_CONTENT_MISMATCH'):
        with writer.transaction() as tx:
            tx.append('snapshot', fresh)


@pytest.mark.parametrize('action', ['correct', 'revoke'])
def test_old_snapshot_retained_but_not_resolvable(stores, action):
    writer, _, _, _ = stores
    rec = insert(writer, observation(writer))
    snap = sealed(writer, rec)
    with writer.transaction() as tx:
        if action == 'correct':
            tx.append('evidence', correction(rec), expected_revision=1)
        else:
            tx.revoke('evidence', rec.reference.evidence_id, 1)
    with writer.transaction() as tx:
        assert tx.get('snapshot', snap.snapshot_id) == snap
    with pytest.raises(DBAPIError, match='STALE_OR_REVOKED_EVIDENCE'):
        with writer.transaction() as tx:
            tx.resolve_snapshot(snap.reference())
    with pytest.raises(DBAPIError, match='STALE_OR_REVOKED_EVIDENCE'):
        with writer.transaction() as tx:
            tx.assemble_snapshot(scope=rec.scope, policy=POLICY,
                created_at=NOW+timedelta(seconds=1), evidence_refs=(rec.reference,))


def test_verifier_authority_and_revocation(stores):
    writer, verifier, _, _ = stores
    rec = insert(writer, observation(writer))
    ver = verification(rec)
    with pytest.raises(DBAPIError, match='TENANT_OR_CAPABILITY_DENIED'):
        with writer.transaction() as tx:
            tx.append('verification', ver)
    with pytest.raises(DBAPIError, match='VERIFIER_IDENTITY_MISMATCH'):
        with verifier.transaction() as tx:
            tx.append('verification', ver.model_copy(update={'issuer_id': 'imposter'}))
    with verifier.transaction() as tx:
        assert tx.append('verification', ver) == ver
        assert tx.audit_events()[-1].verification_ref == ver.reference()
    snap = sealed(writer, rec, (ver.reference(),))
    with verifier.transaction() as tx:
        tx.revoke('verification', ver.verification_id, 1)
    with pytest.raises(DBAPIError, match='STALE_OR_REVOKED_EVIDENCE'):
        with writer.transaction() as tx:
            tx.resolve_snapshot(snap.reference())


def test_import_integrity_does_not_verify_legacy_observation(stores):
    from app.evidence_contracts.evidence import MigrationReference
    writer, verifier, _, _ = stores
    rec = insert(writer, observation(writer, kind=EvidenceKind.LEGACY_CLAIM,
        migration=MigrationReference(batch_id=uuid4(), source_table='inventory', source_primary_key='1'),
        quality_flags=(ReasonCode.LEGACY_CLAIM, ReasonCode.UNVERIFIED_EVIDENCE)))
    with pytest.raises(DBAPIError, match='LEGACY_CLAIM_NOT_OBSERVATION'):
        with verifier.transaction() as tx:
            tx.append('verification', verification(rec))
    ver = verification(rec, VerificationPurpose.IMPORT_INTEGRITY)
    with verifier.transaction() as tx:
        assert tx.append('verification', ver).purpose == VerificationPurpose.IMPORT_INTEGRITY
    snap = sealed(writer, rec, (ver.reference(),))
    assert snap.records[0].verification_status.value == 'unverified'
    assert snap.verification_refs[0].purpose != VerificationPurpose.COUNT


def test_all_five_contracts_persist_but_no_positive_authorization(stores):
    writer, _, _, _ = stores
    rec = insert(writer, observation(writer))
    snap = sealed(writer, rec)
    data = eligible_assessment_data()
    data.update(assessment_id=uuid4(), assessor_id='writer', scope=rec.scope, snapshots=(snap.reference(),),
        state=ReliabilityState.INCOMPLETE, confidence=EvidenceConfidence.UNKNOWN, checks=(),
        decision_eligible=False, verification_required=True, reasons=(ReasonCode.POLICY_UNAVAILABLE,),
        required_actions=denial_data()['required_actions'])
    assessment = ReliabilityAssessment(**data)
    with writer.transaction() as tx:
        assert tx.append('assessment', assessment) == assessment
        denial = denial_data()
        denial.update(issuer_id='writer', scope=rec.scope, snapshots=(snap.reference(),),
                      assessments=(assessment.reference(),))
        result = tx.append('eligibility', DecisionEligibility(**denial))
        assert result.outcome.value == 'deny'
        assert len(tx.audit_events()) == 4
    # Bypass the Python contract intentionally to exercise the SQL deny-only boundary.
    denial = {**result.model_dump(mode='json'), 'eligibility_id': str(uuid4()), 'outcome': 'allow'}
    import json
    with pytest.raises(DBAPIError, match='check constraint'):
        with writer.transaction() as tx:
            tx.connection.execute(text('SELECT rori_evidence.append_object(:t,\'eligibility\',CAST(:i AS uuid),1,CAST(:p AS jsonb),0)'),
                {'t': writer.restaurant_id, 'i': denial['eligibility_id'], 'p': json.dumps(denial)})


def claim(writer, row_id=1, batch=None):
    return prepare_legacy('inventory', {'id': row_id, 'restaurant_id': writer.restaurant_id,
        'quantity': None, 'usage': 0.0}, restaurant_id=writer.restaurant_id,
        batch_id=batch or uuid4(), ingested_at=NOW)


def test_migration_idempotency_and_partial_failure_recovery(stores):
    writer, _, other, _ = stores
    first, wrong = claim(writer), claim(other, 2)
    with pytest.raises(DBAPIError, match='TENANT_MISMATCH'):
        with writer.transaction() as tx:
            tx.stage_claims((first, wrong))
    with writer.transaction() as tx:
        assert tx.audit_events() == ()
        with pytest.raises(LookupError):
            tx.get('legacy_claim', first.claim_id)
    with writer.transaction() as tx:
        stored = tx.stage_claims((first, claim(writer, 2)))
        assert len(stored) == 2
    with writer.transaction() as tx:
        rerun = tx.stage_claims((claim(writer, 1, uuid4()), claim(writer, 2, uuid4())))
        assert rerun[0].batch_id == first.batch_id
        assert len(tx.audit_events()) == 2
        assert rerun[0].fields == first.fields
        assert ReasonCode.UNVERIFIED_EVIDENCE in rerun[0].quality_flags


def test_revocation_serializes_with_snapshot_resolution(stores):
    writer, _, _, _ = stores
    rec = insert(writer, observation(writer))
    snap = sealed(writer, rec)
    started, finished = Event(), Event()
    def revoke():
        started.set()
        with writer.transaction() as tx:
            tx.revoke('evidence', rec.reference.evidence_id, 1)
        finished.set()
    with ThreadPoolExecutor(1) as pool:
        with writer.transaction() as tx:
            assert tx.resolve_snapshot(snap.reference()) == snap
            future = pool.submit(revoke)
            assert started.wait(2)
            assert not finished.wait(.1), 'Revocation bypassed the transaction fence'
        future.result(timeout=5)
    assert finished.is_set()
    with pytest.raises(DBAPIError, match='STALE_OR_REVOKED_EVIDENCE'):
        with writer.transaction() as tx:
            tx.resolve_snapshot(snap.reference())


def test_empty_snapshot_preserves_missing_evidence(stores):
    writer, _, _, _ = stores
    with writer.transaction() as tx:
        snap = tx.assemble_snapshot(scope=scope(restaurant_id=writer.restaurant_id), policy=POLICY,
                                    created_at=NOW, evidence_refs=())
        assert tx.resolve_snapshot(snap.reference()).records == ()
        denial = denial_data()
        denial.update(issuer_id='writer', scope=snap.scope, snapshots=(snap.reference(),))
        assert tx.append('eligibility', DecisionEligibility(**denial)).outcome.value == 'deny'


@pytest.mark.parametrize('defect', ['schema_version', 'future_timestamp'])
def test_database_rejects_unknown_contract_and_future_observation(stores, defect):
    import json
    from datetime import datetime, timezone
    writer, _, _, _ = stores
    rec = observation(writer)
    data = rec.model_dump(mode='json')
    if defect == 'schema_version':
        data['schema_version'] = '9.0.0'
        error = 'UNKNOWN_CONTRACT_VERSION'
    else:
        data['ingested_at'] = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        error = 'FUTURE_TIMESTAMP'
    with pytest.raises(DBAPIError, match=error):
        with writer.transaction() as tx:
            tx.connection.execute(text("SELECT rori_evidence.append_object(:t,'evidence',CAST(:i AS uuid),1,CAST(:p AS jsonb),0)"),
                {'t': writer.restaurant_id, 'i': str(rec.reference.evidence_id), 'p': json.dumps(data)})
    with writer.transaction() as tx:
        assert tx.audit_events() == ()


def test_cross_tenant_snapshot_and_verification_reuse_denied(stores):
    writer, verifier, other, _ = stores
    rec = insert(writer, observation(writer))
    with pytest.raises(ValueError, match='TENANT_MISMATCH'):
        with other.transaction() as tx:
            tx.assemble_snapshot(scope=scope(restaurant_id=other.restaurant_id), policy=POLICY,
                created_at=NOW, evidence_refs=(rec.reference,))
    with verifier.transaction() as tx:
        ver = tx.append('verification', verification(rec))
    snap = sealed(writer, rec, (ver.reference(),))
    with pytest.raises(ValueError, match='TENANT_MISMATCH'):
        with other.transaction() as tx:
            tx.resolve_snapshot(snap.reference())
    with other.transaction() as tx:
        with pytest.raises(LookupError):
            tx.get('verification', ver.verification_id)


def test_positive_assessment_rejected_at_repository_and_database(stores):
    import json
    writer, _, _, _ = stores
    data = eligible_assessment_data()
    data.update(assessor_id='writer')
    # Deliberately bypass the data contract to probe the repository's revalidation.
    forged = ReliabilityAssessment.model_construct(**data)
    with pytest.raises(ValueError, match='POLICY_UNAVAILABLE'):
        with writer.transaction() as tx:
            tx.append('assessment', forged)
    payload = {'schema_version': '1.0.0', 'assessment_id': str(uuid4()),
               'scope': {'restaurant_id': writer.restaurant_id}, 'assessor_id': 'writer',
               'decision_eligible': True, 'assessed_at': NOW.isoformat()}
    with pytest.raises(DBAPIError, match='check constraint'):
        with writer.transaction() as tx:
            tx.connection.execute(text("SELECT rori_evidence.append_object(:t,'assessment',CAST(:i AS uuid),1,CAST(:p AS jsonb),0)"),
                {'t': writer.restaurant_id, 'i': payload['assessment_id'], 'p': json.dumps(payload)})


def test_verification_revision_supersedes_without_overwrite(stores):
    writer, verifier, _, _ = stores
    rec = insert(writer, observation(writer))
    first = verification(rec)
    with verifier.transaction() as tx:
        tx.append('verification', first)
    snap = sealed(writer, rec, (first.reference(),))
    revised = VerificationRecord(**{**first.model_dump(), 'revision': 2,
                                   'status': VerificationStatus.REJECTED})
    with verifier.transaction() as tx:
        tx.append('verification', revised, expected_revision=1)
        assert tx.get('verification', first.verification_id, 1) == first
        assert tx.get('verification', first.verification_id, 2) == revised
    with pytest.raises(DBAPIError, match='STALE_OR_REVOKED_EVIDENCE'):
        with writer.transaction() as tx:
            tx.resolve_snapshot(snap.reference())
    with pytest.raises(DBAPIError, match='VERIFICATION_BINDING_MISMATCH'):
        with writer.transaction() as tx:
            tx.assemble_snapshot(scope=rec.scope, policy=POLICY, created_at=NOW+timedelta(seconds=1),
                evidence_refs=(rec.reference,), verification_refs=(revised.reference(),))


def test_forward_baseline_is_new_observation_not_legacy_certification(stores):
    writer, verifier, _, _ = stores
    old = claim(writer)
    baseline = observation(writer, kind=EvidenceKind.OPENING_COUNT,
        quantity=Quantity(state=ValueState.OBSERVED, value=Decimal('12.5')))
    with writer.transaction() as tx:
        tx.stage_claims((old,))
        tx.append('evidence', baseline)
    with verifier.transaction() as tx:
        ver = tx.append('verification', verification(baseline))
    snapshot = sealed(writer, baseline, (ver.reference(),))
    assert snapshot.records[0].quantity.value == Decimal('12.5')
    with writer.transaction() as tx:
        assert tx.get('legacy_claim', old.claim_id) == old
        assert ReasonCode.UNVERIFIED_EVIDENCE in old.quality_flags
        assert tx.audit_events()[-1].subject_id == snapshot.snapshot_id


def test_non_read_committed_isolation_rejected(stores):
    writer, _, _, _ = stores
    serial_engine = writer.engine.execution_options(isolation_level='REPEATABLE READ')
    with pytest.raises(DBAPIError, match='READ_COMMITTED_REQUIRED'):
        with EvidenceRepository(serial_engine, writer.restaurant_id).transaction():
            pytest.fail('Unsupported isolation accepted')


def test_snapshot_resolution_requires_exact_non_null_digest(stores):
    writer, _, _, _ = stores
    rec = insert(writer, observation(writer))
    snap = sealed(writer, rec)
    for digest in (None, '0'*64):
        with pytest.raises(DBAPIError, match='SNAPSHOT_BINDING_MISMATCH'):
            with writer.transaction() as tx:
                tx.connection.execute(text('SELECT rori_evidence.resolve_snapshot(:t,CAST(:i AS uuid),:d)'),
                    {'t': writer.restaurant_id, 'i': str(snap.snapshot_id), 'd': digest})
