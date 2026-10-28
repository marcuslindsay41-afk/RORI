"""Real PostgreSQL adapter tests. All observations, verifiers and approvals are synthetic."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal, localcontext
from types import SimpleNamespace
from uuid import uuid4
import json
import time

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.evidence_contracts.common import (EvidenceRevisionReference, Scope, ReasonCode,
    VerificationPurpose, VerificationReference, integrity_digest, VersionReference)
from app.evidence_contracts.evidence import (EvidenceRecord, EvidenceSnapshot, EvidenceKind, EvidenceDomain,
    Quantity, ValueState, SourceReference, MigrationReference)
from app.evidence_store.migration import install_assessments, grant_assessment_runtime
from app.evidence_store.verification import VerificationRecord, VerificationStatus
from app.evidence_store.repository import EvidenceTransaction
from app.inventory_assessment.contracts import (AssessmentProfile, ProfileStatus, ProfileReference,
    InventoryManifest, CoverageStatement, CoverageClaim, Representation, ROLES, COUNTS,
    TrustedAssessmentReceipt)
from app.inventory_assessment.adapter import assess_inventory_snapshot
from app.inventory_assessment.storage import provision_profile, store_manifest
from app.inventory_assessment.errors import (AssessmentIntegrityError, AssessmentSecurityError,
    AssessmentUnavailable, IdempotencyConflict, UnsupportedPrecision)
from app.data_reliability.models import ReliabilityState
from tests.contracts.factories import NOW

pytestmark = pytest.mark.postgres
START, END = NOW, NOW+timedelta(days=1)
INGEST, ASOF = END+timedelta(hours=1), END+timedelta(days=1)
DEFAULT = dict(zip(ROLES, map(Decimal, ('100','85','20','30','5','5','3','-2'))))
# ROLES declaration order: opening, physical, receipts, theoretical, waste, in, out, adjustments.


@pytest.fixture
def assessment_stores(stores):
    writer, verifier, other, admin = stores
    install_assessments(admin)
    with admin.begin() as conn:
        for store in (writer, verifier, other):
            grant_assessment_runtime(conn, store.engine.url.username)
    return stores


@pytest.fixture
def bundle(assessment_stores):
    writer, verifier, other, admin = assessment_stores
    def build(*, values=None, missing=(), unknown=(), no_movements=(), empty=(), not_applicable=(),
              duplicate_source=False, competing=False, aggregate_overlap=False,
              record_period_missing=False, out_of_period=False, usage_basis='excludes_recorded_waste',
              unit_basis='native_canonical_no_conversion', missing_purpose=None,
              profile_status=ProfileStatus.SYNTHETIC_TEST_APPROVED, malformed_verification=False,
              verify_at=INGEST, legacy_ancestor=False, coverage_quantity_observed=False):
        scope = Scope(restaurant_id=writer.restaurant_id,item_id='test-ingredient',unit='kg',
                      period_start=START,period_end=END)
        profile = AssessmentProfile(schema_version='1.0.0',identifier='profile-'+uuid4().hex,
            version='1.0.0',status=profile_status,approval_reference='synthetic-fixture-only',
            interval='movements_start_inclusive_end_exclusive_counts_at_boundaries',timezone='UTC',
            location_scope='restaurant_aggregate_only',unit='kg',unit_basis='native_canonical_no_conversion',
            usage_basis='excludes_recorded_waste',dependency_roles=ROLES,
            cardinality='one_stream_per_role_one_count_at_each_boundary',
            verification_issuers=('verifier',), verification_methods=('synthetic-check',),
            source_systems=('synthetic-source',),evaluation_as_of=ASOF)
        with admin.begin() as conn:provision_profile(conn, writer.restaurant_id, profile)
        amounts = {**DEFAULT, **(values or {})}
        records, all_verifications, statements, claims = [], [], [], []
        sequence = 0
        def observation(kind, value, *, artifact=None, unknown_value=False):
            nonlocal sequence
            sequence+=1
            effective = START if kind==EvidenceKind.OPENING_COUNT else END if kind in (EvidenceKind.PHYSICAL_COUNT,EvidenceKind.SOURCE_OBSERVATION) else START+timedelta(hours=1)
            if out_of_period and kind==EvidenceKind.RECEIPT:effective=START-timedelta(seconds=1)
            row_scope = scope
            if record_period_missing and kind==EvidenceKind.RECEIPT:
                row_scope=Scope(restaurant_id=scope.restaurant_id,item_id=scope.item_id,unit=scope.unit)
            rid = 'event-'+str(sequence)
            if duplicate_source and kind in (EvidenceKind.RECEIPT,EvidenceKind.TRANSFER_IN):rid='duplicate-event'
            rec=EvidenceRecord(schema_version='1.0.0',reference=EvidenceRevisionReference(
                restaurant_id=writer.restaurant_id,evidence_id=uuid4(),revision=1),scope=row_scope,
                domain=EvidenceDomain.INVENTORY,kind=kind,
                quantity=Quantity(state=ValueState.UNKNOWN) if unknown_value else Quantity(state=ValueState.OBSERVED,value=value),
                source=SourceReference(system='synthetic-source',record_id=rid,artifact_ref=artifact),
                ingested_at=INGEST,effective_at=effective,
                quality_flags=(ReasonCode.MISSING_QUANTITY,) if unknown_value else ())
            with writer.transaction() as tx:
                if legacy_ancestor and kind==EvidenceKind.OPENING_COUNT:
                    legacy=EvidenceRecord(**{**rec.model_dump(),'kind':EvidenceKind.LEGACY_CLAIM,
                        'migration':MigrationReference(batch_id=uuid4(),source_table='inventory',source_primary_key='historical-claim'),
                        'quality_flags':(ReasonCode.LEGACY_CLAIM,ReasonCode.UNVERIFIED_EVIDENCE)})
                    tx.append('evidence',legacy)
                    rec=EvidenceRecord(**{**rec.model_dump(),'reference':EvidenceRevisionReference(
                        restaurant_id=writer.restaurant_id,evidence_id=rec.reference.evidence_id,revision=2),
                        'supersedes':legacy.reference})
                    tx.append('evidence',rec,expected_revision=1)
                else:tx.append('evidence',rec)
            records.append(rec)
            return rec
        def verify(rec,purpose,scope_description,supporting=('synthetic-artifact',)):
            ver=VerificationRecord(schema_version='1.0.0',verification_id=uuid4(),revision=1,
                evidence=rec.reference,issuer_id='verifier',purpose=purpose,method='synthetic-check',
                supporting_refs=supporting,verified_at=verify_at,scope_description=scope_description,
                limitations=(),status=VerificationStatus.VERIFIED)
            with verifier.transaction() as tx:
                if malformed_verification and not all_verifications:
                    payload=ver.model_dump(mode='json')
                    payload.pop('method')
                    payload.pop('supporting_refs')
                    tx.connection.execute(text("SELECT rori_evidence.append_object(:t,'verification',CAST(:i AS uuid),1,CAST(:p AS jsonb),0)"),
                        {'t':writer.restaurant_id,'i':str(ver.verification_id),'p':json.dumps(payload)})
                else:tx.append('verification',ver)
            all_verifications.append(ver)
            return ver.reference()
        for role in ROLES:
            if role in missing:continue
            events=[]
            representation=(Representation.NO_MOVEMENTS if role in no_movements else
                            Representation.NOT_APPLICABLE if role in not_applicable else Representation.EVENTS)
            if role not in no_movements and role not in empty and role not in not_applicable:
                rec=observation(role,amounts[role],unknown_value=role in unknown)
                events.append(rec)
                if (competing and role==EvidenceKind.PHYSICAL_COUNT) or (aggregate_overlap and role==EvidenceKind.RECEIPT):
                    events.append(observation(role,amounts[role]))
                    if aggregate_overlap and role==EvidenceKind.RECEIPT:representation=Representation.AGGREGATE
                for event in events:
                    for purpose in (VerificationPurpose.SOURCE,VerificationPurpose.COUNT) if role in COUNTS else (VerificationPurpose.SOURCE,):
                        if purpose!=missing_purpose:
                            verify(event,purpose,'scope:'+integrity_digest(scope))
            statement=CoverageStatement(role=role,stream_id=role.value+'-stream',source_system='synthetic-source',
                scope=scope,representation=representation,evidence=tuple(r.reference for r in events),
                unit_basis=unit_basis,usage_basis=usage_basis if role==EvidenceKind.THEORETICAL_USAGE else None)
            artifact=statement.artifact()
            coverage=observation(EvidenceKind.SOURCE_OBSERVATION,Decimal('999') if coverage_quantity_observed else None,
                artifact=artifact,unknown_value=not coverage_quantity_observed)
            if missing_purpose!=VerificationPurpose.SOURCE:
                verify(coverage,VerificationPurpose.SOURCE,'scope:'+integrity_digest(scope))
            ref=verify(coverage,VerificationPurpose.COVERAGE,artifact,(artifact,))
            claims.append(CoverageClaim(statement=statement,verification=ref))
        with writer.transaction() as tx:
            if malformed_verification:
                # Adversarial SQL writer bypasses repository assembly revalidation, as observed in 3A.
                snap=tx.append('snapshot',EvidenceSnapshot(schema_version='1.0.0',scope=scope,
                    policy=VersionReference(identifier=profile.identifier,version=profile.version),created_at=INGEST,
                    records=tuple(records),verification_refs=tuple(v.reference() for v in all_verifications)))
            else:
                snap=tx.assemble_snapshot(scope=scope,policy=VersionReference(identifier=profile.identifier,version=profile.version),
                    created_at=INGEST,evidence_refs=tuple(r.reference for r in records),
                    verification_refs=tuple(v.reference() for v in all_verifications))
            manifest=InventoryManifest(schema_version='1.0.0',scope=scope,snapshot=snap.reference(),claims=tuple(claims))
            store_manifest(tx,manifest)
        return SimpleNamespace(writer=writer,verifier=verifier,other=other,admin=admin,scope=scope,
            profile=profile,snapshot=snap,manifest=manifest,records=records,verifications=all_verifications)
    return build


def assess(data,key='request',**changes):
    args=dict(snapshot_reference=data.snapshot.reference(),assessment_profile_reference=data.profile.reference(),
        request_scope=data.scope,idempotency_key=key,manifest_id=data.manifest.manifest_id,manifest_digest=data.manifest.digest)
    args.update(changes)
    with data.writer.transaction() as tx:return assess_inventory_snapshot(tx,**args)


def codes(receipt):return {detail.code for detail in receipt.provenance.details}


@pytest.mark.parametrize('actual,state,variance',[(Decimal('85'),ReliabilityState.RELIABLE,Decimal('0')),
    (Decimal('84'),ReliabilityState.REVIEW_REQUIRED,Decimal('-1'))])
def test_complete_calculation_preserves_economics_and_stays_blocked(bundle,actual,state,variance):
    data=bundle(values={EvidenceKind.PHYSICAL_COUNT:actual})
    receipt=assess(data)
    a=receipt.assessment
    assert a.expected_inventory==Decimal('85') and a.actual_inventory==actual
    assert a.unexplained_variance==variance and a.state==state
    assert a.decision_eligible is False and a.verification_required
    assert ReasonCode.POLICY_UNAVAILABLE in a.reasons
    assert receipt.provenance.request.snapshot==data.snapshot.reference()
    assert set(receipt.provenance.evidence)=={r.reference for r in data.records}
    assert set(receipt.provenance.verifications)=={v.reference() for v in data.verifications}
    with data.writer.transaction() as tx:
        assert tx.get('assessment',a.assessment_id)==a
        assert tx.audit_events()[-1].subject_type.value=='assessment_run'


def test_negative_expected_preserves_domain_classification(bundle):
    data=bundle(values={EvidenceKind.THEORETICAL_USAGE:Decimal('200')})
    receipt=assess(data)
    assert receipt.assessment.state==ReliabilityState.UNRELIABLE
    assert receipt.assessment.expected_inventory==Decimal('-85')
    assert receipt.assessment.unexplained_variance is None
    assert not receipt.assessment.decision_eligible


@pytest.mark.parametrize('role',ROLES)
def test_missing_dependencies_never_become_zero(bundle,role):
    receipt=assess(bundle(missing=(role,)))
    assert receipt.assessment.state==ReliabilityState.INCOMPLETE
    assert receipt.assessment.actual_inventory is None
    if role!=EvidenceKind.PHYSICAL_COUNT:assert receipt.assessment.expected_inventory is None
    else:assert receipt.assessment.expected_inventory==Decimal('85')
    assert not receipt.assessment.decision_eligible


@pytest.mark.parametrize('variant,expected_code',[
    ({'unknown':(EvidenceKind.RECEIPT,)},'unknown_or_not_applicable_quantity'),
    ({'empty':(EvidenceKind.RECEIPT,)},'empty_stream_without_no_movement_statement'),
    ({'competing':True},'missing_or_competing_count'),
    ({'duplicate_source':True},'missing_or_duplicate_source_event'),
    ({'aggregate_overlap':True},'overlapping_aggregate_and_events'),
    ({'record_period_missing':True},'record_scope_or_period_mismatch'),
    ({'out_of_period':True},'observation_outside_role_period'),
    ({'usage_basis':'unknown'},'usage_may_double_count_waste'),
    ({'unit_basis':'unreviewed_conversion'},'unit_conversion_unresolved'),
    ({'not_applicable':(EvidenceKind.RECEIPT,)},'not_applicable_rule_unapproved'),
    ({'missing_purpose':VerificationPurpose.SOURCE},'unverified_source'),
    ({'missing_purpose':VerificationPurpose.COUNT},'unverified_count'),
])
def test_ambiguous_unverified_or_unscoped_inputs_are_incomplete(bundle,variant,expected_code):
    receipt=assess(bundle(**variant))
    assert receipt.assessment.state==ReliabilityState.INCOMPLETE
    assert receipt.assessment.expected_inventory is None
    assert expected_code in codes(receipt)


def test_certified_no_movements_is_distinct_from_empty_or_observed_zero(bundle):
    movements=tuple(r for r in ROLES if r not in COUNTS)
    amounts={r:Decimal('0') for r in movements}
    amounts.update({EvidenceKind.OPENING_COUNT:Decimal('100'),EvidenceKind.PHYSICAL_COUNT:Decimal('100')})
    explicit=assess(bundle(values=amounts))
    certified=assess(bundle(values=amounts,no_movements=movements),'certified')
    assert explicit.assessment.state==certified.assessment.state==ReliabilityState.RELIABLE
    assert explicit.assessment.expected_inventory==certified.assessment.expected_inventory==Decimal('100')
    assert explicit.provenance.computation_digest!=certified.provenance.computation_digest


def test_unapproved_profile_returns_structured_block(bundle):
    data=bundle(profile_status=ProfileStatus.DRAFT)
    result=assess(data)
    assert result.assessment.state==ReliabilityState.INCOMPLETE
    assert 'assessment_profile_unapproved_or_unavailable' in codes(result)
    assert result.assessment.expected_inventory is None


def test_missing_profile_and_manifest_are_representable_blocks(bundle):
    data=bundle()
    missing=ProfileReference(identifier='missing',version='9.0.0',digest='0'*64)
    receipt=assess(data,assessment_profile_reference=missing,manifest_id=uuid4())
    assert receipt.assessment.state==ReliabilityState.INCOMPLETE
    assert {ReasonCode.POLICY_UNAVAILABLE,ReasonCode.UNKNOWN_MANIFEST}<=set(receipt.assessment.reasons)


@pytest.mark.parametrize('field,value',[('item_id','other-item'),('unit','g'),('period_end',END+timedelta(days=1))])
def test_wrong_request_scope_is_typed_integrity_failure(bundle,field,value):
    data=bundle()
    bad=Scope(**{**data.scope.model_dump(),field:value})
    with pytest.raises(AssessmentIntegrityError,match='SCOPE_MISMATCH'):assess(data,request_scope=bad)


def test_cross_tenant_and_untrusted_context_are_security_failures(bundle):
    data=bundle()
    with data.other.transaction() as tx:
        with pytest.raises(AssessmentSecurityError):
            assess_inventory_snapshot(tx,data.snapshot.reference(),data.profile.reference(),data.scope,
                idempotency_key='x',manifest_id=data.manifest.manifest_id,manifest_digest=data.manifest.digest)
    with pytest.raises(AssessmentSecurityError,match='EVALUATION_CONTEXT'):
        assess(data,evaluation_context={'source_verified':True,'now':ASOF})
    with data.writer.transaction() as tx:
        fake=EvidenceTransaction(tx.connection,tx.restaurant_id)
        with pytest.raises(AssessmentSecurityError,match='UNTRUSTED_TRANSACTION'):
            assess_inventory_snapshot(fake,data.snapshot.reference(),data.profile.reference(),data.scope,
                idempotency_key='x',manifest_id=data.manifest.manifest_id,manifest_digest=data.manifest.digest)


@pytest.mark.parametrize('change',['evidence_revoke','evidence_correct','verification_revoke','verification_supersede'])
def test_changed_inputs_cannot_be_reused_even_on_idempotent_retry(bundle,change):
    data=bundle()
    first=assess(data)
    if change.startswith('evidence'):
        rec=next(r for r in data.records if r.kind==EvidenceKind.RECEIPT)
        with data.writer.transaction() as tx:
            if change=='evidence_revoke':tx.revoke('evidence',rec.reference.evidence_id,1)
            else:
                revised=EvidenceRecord(**{**rec.model_dump(),'reference':EvidenceRevisionReference(
                    restaurant_id=rec.scope.restaurant_id,evidence_id=rec.reference.evidence_id,revision=2),
                    'supersedes':rec.reference})
                tx.append('evidence',revised,expected_revision=1)
    else:
        ver=data.verifications[0]
        with data.verifier.transaction() as tx:
            if change=='verification_revoke':tx.revoke('verification',ver.verification_id,1)
            else:tx.append('verification',VerificationRecord(**{**ver.model_dump(),'revision':2,
                      'status':VerificationStatus.REJECTED}),expected_revision=1)
    with pytest.raises(AssessmentIntegrityError):assess(data)
    with data.writer.transaction() as tx:assert tx.get('assessment',first.assessment.assessment_id)==first.assessment


def test_current_verifier_authority_and_sql_shape_are_revalidated(bundle):
    data=bundle()
    with data.admin.begin() as c:
        c.execute(text("UPDATE rori_evidence.principal_grants SET capabilities='{}' WHERE restaurant_id=:t AND actor_id='verifier'"),{'t':data.scope.restaurant_id})
    with pytest.raises(AssessmentSecurityError):assess(data)


def test_malformed_authorized_sql_verification_is_not_trusted(bundle):
    data=bundle(malformed_verification=True)
    with pytest.raises(AssessmentIntegrityError,match='VERIFICATION_PAYLOAD_INVALID'):assess(data)


def test_determinism_and_idempotency_with_different_ambient_contexts(bundle):
    data=bundle()
    with localcontext() as c:
        c.prec=3
        first=assess(data)
    with localcontext() as c:
        c.prec=80
        replay=assess(data)
        fresh=assess(data,'different-attempt')
    assert replay==first
    assert fresh.assessment.assessment_id!=first.assessment.assessment_id
    assert fresh.provenance.computation_digest==first.provenance.computation_digest
    assert first.assessment.expected_inventory==Decimal('85')
    with data.writer.transaction() as tx:
        count=tx.connection.scalar(text('SELECT count(*) FROM rori_evidence.assessment_runs WHERE restaurant_id=:t'),{'t':data.scope.restaurant_id})
        assert count==2


def test_same_idempotency_key_changed_request_conflicts(bundle):
    first=bundle()
    assess(first)
    second=bundle(values={EvidenceKind.PHYSICAL_COUNT:Decimal('84')})
    with pytest.raises(IdempotencyConflict):assess(second)
    with first.writer.transaction() as tx:
        assert tx.connection.scalar(text('SELECT count(*) FROM rori_evidence.assessment_runs WHERE restaurant_id=:t'),{'t':first.scope.restaurant_id})==1


def test_concurrent_duplicate_requests_have_one_result(bundle):
    data=bundle()
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:assess(data),range(2)))
    assert results[0]==results[1]
    with data.writer.transaction() as tx:
        events=[e for e in tx.audit_events() if e.subject_type.value=='assessment_run']
        assert len(events)==1


def test_rollback_and_recovery_preserve_atomic_audit(bundle):
    data=bundle()
    with pytest.raises(RuntimeError,match='abort'):
        with data.writer.transaction() as tx:
            receipt=assess_inventory_snapshot(tx,data.snapshot.reference(),data.profile.reference(),data.scope,
                idempotency_key='retry',manifest_id=data.manifest.manifest_id,manifest_digest=data.manifest.digest)
            raise RuntimeError('abort')
    with data.writer.transaction() as tx:
        with pytest.raises(LookupError):tx.get('assessment',receipt.assessment.assessment_id)
        assert not [e for e in tx.audit_events() if e.subject_type.value=='assessment_run']
    recovered=assess(data,'retry')
    assert recovered.assessment.assessment_id!=receipt.assessment.assessment_id
    assert recovered.provenance.computation_digest==receipt.provenance.computation_digest


@pytest.mark.parametrize('defect',['missing','wrong_revision','unrelated'])
def test_coverage_verification_must_be_real_and_exactly_bound(bundle,defect):
    data=bundle()
    claims=list(data.manifest.claims)
    original=claims[0].verification
    if defect=='missing':
        ref=VerificationReference(**{**original.model_dump(),'verification_id':uuid4()})
    elif defect=='wrong_revision':
        ref=VerificationReference(**{**original.model_dump(),'revision':2})
    else:ref=data.verifications[0].reference()
    claims[0]=CoverageClaim(statement=claims[0].statement,verification=ref)
    manifest=InventoryManifest(schema_version='1.0.0',scope=data.scope,snapshot=data.snapshot.reference(),claims=tuple(claims))
    with data.writer.transaction() as tx:store_manifest(tx,manifest)
    with pytest.raises(AssessmentIntegrityError):
        assess(data,manifest_id=manifest.manifest_id,manifest_digest=manifest.digest)
    with data.writer.transaction() as tx:
        assert tx.connection.scalar(text('SELECT count(*) FROM rori_evidence.assessment_runs WHERE restaurant_id=:t'),{'t':data.scope.restaurant_id})==0


def test_profile_digest_and_manifest_digest_are_revalidated(bundle):
    data=bundle()
    bad=ProfileReference(**{**data.profile.reference().model_dump(),'digest':'0'*64})
    with pytest.raises(AssessmentIntegrityError,match='PROFILE_BINDING_MISMATCH'):
        assess(data,assessment_profile_reference=bad)
    with pytest.raises(AssessmentIntegrityError,match='MANIFEST_BINDING_MISMATCH'):
        assess(data,manifest_digest='0'*64)


def test_high_precision_inventory_is_exact_under_tiny_ambient_context(bundle):
    data=bundle(values={EvidenceKind.RECEIPT:Decimal('20.000000000000000000000000000001'),
                        EvidenceKind.PHYSICAL_COUNT:Decimal('85.000000000000000000000000000001')})
    with localcontext() as context:
        context.prec=3
        receipt=assess(data)
    assert receipt.assessment.expected_inventory==Decimal('85.000000000000000000000000000001')
    assert receipt.assessment.unexplained_variance==0 and receipt.assessment.state==ReliabilityState.RELIABLE


def test_unsupported_inventory_precision_does_not_persist_a_success(bundle):
    data=bundle(values={EvidenceKind.RECEIPT:Decimal('1e-5000')})
    with pytest.raises(UnsupportedPrecision):assess(data)
    with data.writer.transaction() as tx:
        assert not [e for e in tx.audit_events() if e.subject_type.value=='assessment_run']


def test_unverified_legacy_claim_is_a_blocked_archive_not_inventory(bundle):
    data=bundle()
    rec=EvidenceRecord(schema_version='1.0.0',reference=EvidenceRevisionReference(
        restaurant_id=data.scope.restaurant_id,evidence_id=uuid4(),revision=1),scope=data.scope,
        domain=EvidenceDomain.INVENTORY,kind=EvidenceKind.LEGACY_CLAIM,
        quantity=Quantity(state=ValueState.UNKNOWN),source=SourceReference(system='legacy',record_id='old-1'),
        ingested_at=INGEST,effective_at=None,
        migration=MigrationReference(batch_id=uuid4(),source_table='inventory',source_primary_key='old-1'),
        quality_flags=(ReasonCode.LEGACY_CLAIM,ReasonCode.UNVERIFIED_EVIDENCE,
                       ReasonCode.UNKNOWN_OBSERVATION_TIME,ReasonCode.MISSING_QUANTITY))
    with data.writer.transaction() as tx:
        tx.append('evidence',rec)
        snap=tx.assemble_snapshot(scope=data.scope,policy=VersionReference(identifier=data.profile.identifier,version=data.profile.version),
            created_at=INGEST,evidence_refs=(rec.reference,))
    receipt=assess(data,snapshot_reference=snap.reference(),manifest_id=uuid4())
    assert receipt.assessment.state==ReliabilityState.INCOMPLETE
    assert receipt.assessment.expected_inventory is None
    assert ReasonCode.LEGACY_CLAIM in receipt.assessment.reasons


def test_location_specific_claims_are_explicitly_blocked(bundle):
    data=bundle()
    manifest=InventoryManifest(**{**data.manifest.model_dump(exclude={'digest','manifest_id'}),'location_id':'unrepresented-location'})
    with data.writer.transaction() as tx:store_manifest(tx,manifest)
    receipt=assess(data,manifest_id=manifest.manifest_id,manifest_digest=manifest.digest)
    assert receipt.assessment.state==ReliabilityState.INCOMPLETE
    assert 'location_scope_not_supported' in codes(receipt)


def test_audit_failure_rolls_back_adapter_savepoint_even_if_caller_catches(bundle):
    data=bundle()
    suffix=uuid4().hex
    function='audit_failure_'+suffix
    trigger='audit_failure_'+suffix
    with data.admin.begin() as conn:
        conn.execute(text(f'''CREATE FUNCTION rori_evidence.{function}() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.restaurant_id={data.scope.restaurant_id} AND NEW.payload->>'subject_type'='assessment_run'
            THEN RAISE EXCEPTION 'INJECTED_AUDIT_FAILURE'; END IF; RETURN NEW; END $$'''))
        conn.execute(text(f'CREATE TRIGGER {trigger} BEFORE INSERT ON rori_evidence.audit_events FOR EACH ROW EXECUTE FUNCTION rori_evidence.{function}()'))
    try:
        with data.writer.transaction() as tx:
            before=tx.audit_events()
            with pytest.raises(AssessmentUnavailable,match='DATABASE_OR_AUDIT_UNAVAILABLE'):
                assess_inventory_snapshot(tx,data.snapshot.reference(),data.profile.reference(),data.scope,
                    idempotency_key='audit-retry',manifest_id=data.manifest.manifest_id,manifest_digest=data.manifest.digest)
            assert tx.audit_events()==before
            assert tx.connection.scalar(text("SELECT count(*) FROM rori_evidence.objects WHERE restaurant_id=:t AND kind='assessment'"),{'t':data.scope.restaurant_id})==0
            assert tx.connection.scalar(text('SELECT count(*) FROM rori_evidence.assessment_runs WHERE restaurant_id=:t'),{'t':data.scope.restaurant_id})==0
    finally:
        with data.admin.begin() as conn:
            conn.execute(text(f'DROP TRIGGER {trigger} ON rori_evidence.audit_events'))
            conn.execute(text(f'DROP FUNCTION rori_evidence.{function}()'))
    assert assess(data,'audit-retry').assessment.state==ReliabilityState.RELIABLE


def test_actual_database_disconnect_is_typed_unavailable_and_recoverable(bundle):
    data=bundle()
    with pytest.raises(AssessmentUnavailable):
        with data.writer.transaction() as tx:
            pid=tx.connection.scalar(text('SELECT pg_backend_pid()'))
            with data.admin.begin() as admin:
                assert admin.scalar(text('SELECT pg_terminate_backend(:pid)'),{'pid':pid}) is True
            assess_inventory_snapshot(tx,data.snapshot.reference(),data.profile.reference(),data.scope,
                idempotency_key='disconnect',manifest_id=data.manifest.manifest_id,manifest_digest=data.manifest.digest)
    assert assess(data,'disconnect').assessment.state==ReliabilityState.RELIABLE


@pytest.mark.parametrize('change',['revoke','correct'])
def test_assessment_fences_concurrent_changes_with_database_visible_wait(bundle,change):
    data=bundle()
    rec=next(r for r in data.records if r.kind==EvidenceKind.RECEIPT)
    def mutate():
        with data.writer.transaction() as tx:
            if change=='revoke':tx.revoke('evidence',rec.reference.evidence_id,1)
            else:
                revised=EvidenceRecord(**{**rec.model_dump(),'reference':EvidenceRevisionReference(
                    restaurant_id=rec.scope.restaurant_id,evidence_id=rec.reference.evidence_id,revision=2),
                    'supersedes':rec.reference})
                tx.append('evidence',revised,expected_revision=1)
        return True
    with ThreadPoolExecutor(1) as pool:
        with data.writer.transaction() as tx:
            receipt=assess_inventory_snapshot(tx,data.snapshot.reference(),data.profile.reference(),data.scope,
                idempotency_key='race',manifest_id=data.manifest.manifest_id,manifest_digest=data.manifest.digest)
            future=pool.submit(mutate)
            deadline=time.monotonic()+5
            observed=False
            while time.monotonic()<deadline:
                with data.admin.connect() as admin:
                    observed=admin.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE usename=:role AND wait_event='advisory')"),
                                          {'role':data.writer.engine.url.username})
                if observed:break
                time.sleep(.01)
            assert observed,'Concurrent writer did not reach the database advisory-lock wait'
            assert not future.done()
        assert future.result(timeout=5)
    with pytest.raises(AssessmentIntegrityError):assess(data,'race')
    with data.writer.transaction() as tx:assert tx.get('assessment',receipt.assessment.assessment_id)==receipt.assessment


def test_new_tables_are_tenant_isolated_and_append_only(bundle):
    data=bundle()
    assess(data)
    for table in ('inventory_profiles','inventory_manifests','assessment_runs'):
        with data.other.transaction() as tx:
            assert tx.connection.scalar(text(f'SELECT count(*) FROM rori_evidence.{table} WHERE restaurant_id=:t'),{'t':data.scope.restaurant_id})==0
        with pytest.raises(DBAPIError,match='APPEND_ONLY_VIOLATION'):
            with data.admin.begin() as conn:
                conn.execute(text(f'DELETE FROM rori_evidence.{table} WHERE restaurant_id=:t'),{'t':data.scope.restaurant_id})


def test_concurrent_changed_requests_have_one_success_and_one_conflict(bundle):
    one=bundle()
    two=bundle(values={EvidenceKind.PHYSICAL_COUNT:Decimal('84')})
    def request(data):
        try:return assess(data,'shared-key')
        except IdempotencyConflict:return 'conflict'
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(request,(one,two)))
    assert sum(isinstance(result,TrustedAssessmentReceipt) for result in results)==1
    assert results.count('conflict')==1
    with one.writer.transaction() as tx:
        assert len([e for e in tx.audit_events() if e.subject_type.value=='assessment_run'])==1


@pytest.mark.parametrize('kind',[EvidenceKind.PHYSICAL_COUNT,EvidenceKind.SOURCE_OBSERVATION])
def test_extra_competing_count_outside_manifest_cannot_be_ignored(bundle,kind):
    data=bundle()
    original=next(r for r in data.records if r.kind==EvidenceKind.PHYSICAL_COUNT)
    extra=EvidenceRecord(**{**original.model_dump(),'kind':kind,'reference':EvidenceRevisionReference(
        restaurant_id=data.scope.restaurant_id,evidence_id=uuid4(),revision=1),
        'source':SourceReference(system='synthetic-source',record_id='extra-count')})
    with data.writer.transaction() as tx:
        tx.append('evidence',extra)
        snap=tx.assemble_snapshot(scope=data.scope,policy=data.snapshot.policy,created_at=INGEST,
            evidence_refs=tuple(r.reference for r in data.records)+(extra.reference,),
            verification_refs=data.snapshot.verification_refs)
        manifest=InventoryManifest(schema_version='1.0.0',scope=data.scope,snapshot=snap.reference(),claims=data.manifest.claims)
        store_manifest(tx,manifest)
    receipt=assess(data,snapshot_reference=snap.reference(),manifest_id=manifest.manifest_id,manifest_digest=manifest.digest)
    assert receipt.assessment.state==ReliabilityState.INCOMPLETE
    assert receipt.assessment.expected_inventory is None
    assert ('unassigned_or_competing_inventory_records' if kind==EvidenceKind.PHYSICAL_COUNT
            else 'unassigned_source_observation') in codes(receipt)


def test_profile_is_admin_provisioned_not_runtime_self_approval(bundle):
    data=bundle()
    changed=AssessmentProfile(**{**data.profile.model_dump(exclude={'digest'}),'identifier':'self-approved'})
    with pytest.raises(DBAPIError,match='permission denied'):
        with data.writer.transaction() as tx:
            provision_profile(tx.connection,data.scope.restaurant_id,changed)


def test_current_verifier_grants_cannot_change_inside_assessment_transaction(bundle):
    data=bundle()
    application='rori-authority-'+uuid4().hex
    def remove_authority():
        with data.admin.begin() as admin:
            admin.execute(text("SELECT set_config('application_name',:name,true)"),{'name':application})
            admin.execute(text("UPDATE rori_evidence.principal_grants SET capabilities='{}' WHERE restaurant_id=:t AND actor_id='verifier'"),{'t':data.scope.restaurant_id})
        return True
    with ThreadPoolExecutor(1) as pool:
        with data.writer.transaction() as tx:
            receipt=assess_inventory_snapshot(tx,data.snapshot.reference(),data.profile.reference(),data.scope,
                idempotency_key='authority-race',manifest_id=data.manifest.manifest_id,manifest_digest=data.manifest.digest)
            future=pool.submit(remove_authority)
            deadline=time.monotonic()+5
            observed=False
            while time.monotonic()<deadline:
                with data.admin.connect() as admin:
                    observed=admin.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name=:name AND wait_event_type='Lock')"),{'name':application})
                if observed:break
                time.sleep(.01)
            assert observed,'Authority updater did not reach its database row-lock wait'
            assert not future.done()
        assert future.result(timeout=5)
    with pytest.raises(AssessmentSecurityError):assess(data,'authority-race')
    assert receipt.assessment.decision_eligible is False


def test_overlapping_closed_coverage_is_not_counted_twice(bundle):
    data=bundle()
    manifest=InventoryManifest(schema_version='1.0.0',scope=data.scope,snapshot=data.snapshot.reference(),
        claims=data.manifest.claims+(data.manifest.claims[0],))
    with data.writer.transaction() as tx:store_manifest(tx,manifest)
    result=assess(data,manifest_id=manifest.manifest_id,manifest_digest=manifest.digest)
    assert result.assessment.state==ReliabilityState.INCOMPLETE
    assert result.assessment.expected_inventory is None
    assert 'competing_or_overlapping_opening_count' in codes(result)


def test_verification_cannot_predate_the_observation_it_certifies(bundle):
    data=bundle(verify_at=START-timedelta(hours=1))
    with pytest.raises(AssessmentIntegrityError,match='VERIFICATION_PRECEDES_OBSERVATION'):
        assess(data)


def test_corrected_legacy_claim_cannot_be_promoted_into_a_verified_count(bundle):
    data=bundle(legacy_ancestor=True)
    result=assess(data)
    assert result.assessment.state==ReliabilityState.INCOMPLETE
    assert result.assessment.expected_inventory is None
    assert ReasonCode.LEGACY_CLAIM in result.assessment.reasons


def test_coverage_observation_cannot_hide_unclassified_inventory_quantity(bundle):
    receipt=assess(bundle(coverage_quantity_observed=True))
    assert receipt.assessment.state==ReliabilityState.INCOMPLETE
    assert receipt.assessment.expected_inventory is None
    assert 'coverage_record_carries_unclassified_quantity' in codes(receipt)
