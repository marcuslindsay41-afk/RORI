"""Assessment/eligibility records, not a gateway or caller-held capability.

No operational policies are registered in Increment 1. Consequently an ALLOW
record cannot be issued here. A future server-side resolver must authenticate
references, implement policy checks and enforce all recommendation paths.
"""
from decimal import Decimal
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import model_validator

from app.data_reliability.models import ReliabilityState
from app.data_reliability.reliability import EvidenceConfidence
from app.economic_engine.models import DecisionType
from .common import (Contract, VersionedRecord, VersionReference, Scope, Timestamp, TenantId, Identifier,
                     SnapshotReference, VerificationReference, ReasonCode,
                     VerificationAction, VerificationPurpose, same_tenant, unique)
from .evidence import EvidenceDomain


class CheckKind(str, Enum):
    SOURCE_VERIFIED = 'source_verified'
    COUNT_VERIFIED = 'count_verified'
    COVERAGE_COMPLETE = 'coverage_complete'
    EVIDENCE_CURRENT = 'evidence_current'
    IDENTITY_RESOLVED = 'identity_resolved'
    UNITS_RESOLVED = 'units_resolved'
    REVISION_CURRENT = 'revision_current'
    POLICY_AVAILABLE = 'policy_available'


class CheckStatus(str, Enum):
    PASSED = 'passed'
    FAILED = 'failed'
    UNKNOWN = 'unknown'
    NOT_APPLICABLE = 'not_applicable'


class EvidenceCheck(Contract):
    kind: CheckKind
    status: CheckStatus
    verification_refs: tuple[VerificationReference, ...] = ()
    rule: VersionReference | None = None
    reasons: tuple[ReasonCode, ...] = ()

    @model_validator(mode='after')
    def check_support(self):
        if self.status in (CheckStatus.FAILED, CheckStatus.UNKNOWN) and not self.reasons:
            raise ValueError('failed/unknown checks require structured reasons')
        if self.status == CheckStatus.PASSED and self.reasons:
            raise ValueError('a passing check cannot include blocking reasons')
        if self.status == CheckStatus.NOT_APPLICABLE:
            if self.rule is None:
                raise ValueError('not-applicable checks require a documented versioned rule')
        elif self.rule is not None:
            raise ValueError('rule applies only to a not-applicable check')
        if (self.status == CheckStatus.PASSED
                and self.kind in (CheckKind.SOURCE_VERIFIED, CheckKind.COUNT_VERIFIED, CheckKind.COVERAGE_COMPLETE)
                and not self.verification_refs):
            raise ValueError('verification checks require separate verification references')
        purpose = {CheckKind.SOURCE_VERIFIED: VerificationPurpose.SOURCE,
                   CheckKind.COUNT_VERIFIED: VerificationPurpose.COUNT,
                   CheckKind.COVERAGE_COMPLETE: VerificationPurpose.COVERAGE}.get(self.kind)
        if purpose is not None and any(v.purpose != purpose for v in self.verification_refs):
            raise ValueError('verification reference purpose does not match the check')
        unique(((v.verification_id, v.revision) for v in self.verification_refs), 'check verification references')
        return self


class ReliabilityAssessment(VersionedRecord):
    assessment_id: UUID
    assessor_id: Identifier
    scope: Scope
    domain: EvidenceDomain
    snapshots: tuple[SnapshotReference, ...]
    policy: VersionReference
    assessed_at: Timestamp
    state: ReliabilityState
    confidence: EvidenceConfidence
    confidence_axis: Literal['state'] = 'state'
    decision_eligible: bool
    verification_required: bool
    checks: tuple[EvidenceCheck, ...]
    reasons: tuple[ReasonCode, ...] = ()
    required_actions: tuple[VerificationAction, ...] = ()
    expected_inventory: Decimal | None = None
    actual_inventory: Decimal | None = None
    unexplained_variance: Decimal | None = None

    @model_validator(mode='after')
    def coherent_assessment(self):
        if not self.snapshots:
            raise ValueError('assessment must reference a snapshot, including an explicitly empty snapshot')
        same_tenant(self.scope.restaurant_id, self.snapshots)
        unique((s.snapshot_id for s in self.snapshots), 'snapshot references')
        unique((c.kind for c in self.checks), 'assessment checks')
        for check in self.checks:
            same_tenant(self.scope.restaurant_id, (v.evidence for v in check.verification_refs))
        for value in (self.expected_inventory, self.actual_inventory, self.unexplained_variance):
            if value is not None and not value.is_finite():
                raise ValueError('assessment quantities must be finite Decimals')
        expected_confidence = {
            ReliabilityState.INCOMPLETE: EvidenceConfidence.UNKNOWN,
            ReliabilityState.UNRELIABLE: EvidenceConfidence.LOW,
            ReliabilityState.REVIEW_REQUIRED: EvidenceConfidence.LOW,
        }.get(self.state)
        if expected_confidence is not None and self.confidence != expected_confidence:
            raise ValueError('confidence contradicts the reliability state')
        if not self.decision_eligible:
            if not self.reasons or not self.required_actions or not self.verification_required:
                raise ValueError('ineligible assessments require reasons, verification and required actions')
        else:
            if self.domain != EvidenceDomain.INVENTORY:
                raise ValueError('only inventory assessment eligibility is defined in Increment 1')
            if (self.state != ReliabilityState.RELIABLE or self.confidence != EvidenceConfidence.HIGH
                    or self.verification_required or self.reasons or self.required_actions):
                raise ValueError('eligible assessment must be reliable, high-confidence and free of blockers')
            passed = {c.kind for c in self.checks if c.status == CheckStatus.PASSED}
            if passed != set(CheckKind):
                raise ValueError('eligibility requires every mandatory check to pass')
            if self.domain == EvidenceDomain.INVENTORY:
                if (any(v is None for v in (self.expected_inventory, self.actual_inventory, self.unexplained_variance))
                        or self.expected_inventory < 0 or self.actual_inventory < 0
                        or self.actual_inventory != self.expected_inventory
                        or self.actual_inventory - self.expected_inventory != self.unexplained_variance
                        or self.unexplained_variance != 0):
                    raise ValueError('inventory eligibility requires independently consistent zero variance and a physical count')
        return self

    def reference(self):
        return AssessmentReference(assessment_id=self.assessment_id,
                                   restaurant_id=self.scope.restaurant_id,
                                   snapshots=self.snapshots, policy=self.policy)


class AssessmentReference(Contract):
    assessment_id: UUID
    restaurant_id: TenantId
    snapshots: tuple[SnapshotReference, ...]
    policy: VersionReference

    @model_validator(mode='after')
    def valid_scope(self):
        if not self.snapshots:
            raise ValueError('assessment reference requires its snapshot bindings')
        same_tenant(self.restaurant_id, self.snapshots)
        unique((s.snapshot_id for s in self.snapshots), 'assessment snapshot bindings')
        return self


class DecisionOperation(str, Enum):
    GENERATE = 'generate'
    PUBLISH = 'publish'
    RETRIEVE = 'retrieve'
    ACCEPT = 'accept'
    EXECUTE = 'execute'
    VERIFY_OUTCOME = 'verify_outcome'


class EligibilityOutcome(str, Enum):
    ALLOW = 'allow'
    DENY = 'deny'


class DecisionEligibility(VersionedRecord):
    eligibility_id: UUID
    issuer_id: Identifier
    scope: Scope
    decision_id: UUID
    decision_type: DecisionType
    operation: DecisionOperation
    dependency_manifest: VersionReference
    snapshots: tuple[SnapshotReference, ...]
    assessments: tuple[AssessmentReference, ...]
    policy: VersionReference
    evaluated_at: Timestamp
    valid_until: Timestamp | None = None
    outcome: EligibilityOutcome
    reasons: tuple[ReasonCode, ...]
    required_actions: tuple[VerificationAction, ...]
    invalidation_conditions: tuple[ReasonCode, ...]

    @model_validator(mode='after')
    def scoped_denial(self):
        same_tenant(self.scope.restaurant_id, self.snapshots)
        same_tenant(self.scope.restaurant_id, self.assessments)
        unique((s.snapshot_id for s in self.snapshots), 'eligibility snapshot references')
        unique((a.assessment_id for a in self.assessments), 'assessment references')
        snapshot_set = set(self.snapshots)
        for assessment in self.assessments:
            if assessment.policy != self.policy or not set(assessment.snapshots).issubset(snapshot_set):
                raise ValueError('assessment policy and exact snapshot bindings must match eligibility')
        if self.valid_until is not None and self.valid_until <= self.evaluated_at:
            raise ValueError('valid_until must follow evaluated_at')
        if self.outcome == EligibilityOutcome.ALLOW:
            raise ValueError('no operational policies or trusted gateway exist in Increment 1; authorization is blocked')
        if not self.reasons or not self.required_actions:
            raise ValueError('denial requires structured reasons and verification actions')
        if not {ReasonCode.REVISION_MISMATCH, ReasonCode.REVOKED_EVIDENCE}.issubset(self.invalidation_conditions):
            raise ValueError('eligibility must bind invalidation to corrections and revocations')
        return self
