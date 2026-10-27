"""Synthetic contract data; no verification references here are production trust."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.evidence_contracts.common import (Scope, VersionReference, EvidenceRevisionReference,
    VerificationReference, VerificationPurpose, ReasonCode, VerificationAction)
from app.evidence_contracts.evidence import (EvidenceRecord, EvidenceSnapshot, EvidenceDomain,
    EvidenceKind, Quantity, ValueState, SourceReference)
from app.evidence_contracts.decisions import (ReliabilityAssessment, DecisionEligibility,
    CheckKind, CheckStatus, EvidenceCheck, DecisionOperation, EligibilityOutcome)
from app.evidence_contracts.audit import AuditEvent, AuditAction, SubjectType, ActorKind
from app.data_reliability.models import ReliabilityState
from app.data_reliability.reliability import EvidenceConfidence
from app.economic_engine.models import DecisionType

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
POLICY = VersionReference(identifier='test-policy', version='1.0.0')


def scope(**kwargs):
    return Scope(**{'restaurant_id': 101, 'item_id': 'ingredient-1', 'unit': 'kg', **kwargs})


def record_data(**kwargs):
    return dict(schema_version='1.0.0', reference=EvidenceRevisionReference(
        restaurant_id=101, evidence_id=uuid4(), revision=1), scope=scope(),
        domain=EvidenceDomain.INVENTORY, kind=EvidenceKind.PHYSICAL_COUNT,
        quantity=Quantity(state=ValueState.OBSERVED, value=Decimal('0')),
        source=SourceReference(system='test-source', record_id='row-1'),
        ingested_at=NOW, effective_at=NOW, **kwargs)


def record():
    return EvidenceRecord(**record_data())


def snapshot_data(records=None):
    return dict(schema_version='1.0.0', scope=scope(), policy=POLICY,
                created_at=NOW, records=(record(),) if records is None else records)


def snapshot():
    return EvidenceSnapshot(**snapshot_data())


def verification(reference, purpose=VerificationPurpose.SOURCE):
    return VerificationReference(verification_id=uuid4(), revision=1, evidence=reference,
                                 issuer_id='test-verifier', purpose=purpose)


def eligible_assessment_data():
    rec = record()
    checks = []
    purposes = {CheckKind.SOURCE_VERIFIED: VerificationPurpose.SOURCE,
                CheckKind.COUNT_VERIFIED: VerificationPurpose.COUNT,
                CheckKind.COVERAGE_COMPLETE: VerificationPurpose.COVERAGE}
    for kind in CheckKind:
        refs = (verification(rec.reference, purposes[kind]),) if kind in purposes else ()
        checks.append(EvidenceCheck(kind=kind, status=CheckStatus.PASSED, verification_refs=refs))
    snap = EvidenceSnapshot(**{**snapshot_data((rec,)),
        'verification_refs': tuple(v for check in checks for v in check.verification_refs)})
    return dict(schema_version='1.0.0', assessment_id=uuid4(), assessor_id='test-assessor', scope=scope(),
                domain=EvidenceDomain.INVENTORY, snapshots=(snap.reference(),), policy=POLICY,
                assessed_at=NOW, state=ReliabilityState.RELIABLE, confidence=EvidenceConfidence.HIGH,
                decision_eligible=True, verification_required=False, checks=tuple(checks),
                expected_inventory=Decimal('0'), actual_inventory=Decimal('0'),
                unexplained_variance=Decimal('0'))


def denial_data():
    return dict(schema_version='1.0.0', eligibility_id=uuid4(), issuer_id='test-gateway', scope=scope(), decision_id=uuid4(),
                decision_type=DecisionType.INVENTORY, operation=DecisionOperation.GENERATE,
                dependency_manifest=VersionReference(identifier='test-manifest', version='1.0.0'),
                snapshots=(), assessments=(), policy=POLICY, evaluated_at=NOW,
                outcome=EligibilityOutcome.DENY, reasons=(ReasonCode.POLICY_UNAVAILABLE,),
                required_actions=(VerificationAction.DEFINE_POLICY,),
                invalidation_conditions=(ReasonCode.REVISION_MISMATCH, ReasonCode.REVOKED_EVIDENCE))


def event_data():
    rec = record()
    return dict(schema_version='1.0.0', event_id=uuid4(), stream_id=uuid4(), sequence=1,
                restaurant_id=101, actor_id='test-actor', actor_kind=ActorKind.SYSTEM, action=AuditAction.SUBMIT,
                subject_type=SubjectType.EVIDENCE, subject_id=rec.reference.evidence_id,
                occurred_at=NOW, evidence_refs=(rec.reference,))
