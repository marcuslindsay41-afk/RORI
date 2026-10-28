"""Additive adapter contracts. Existing assessment/history payloads are unchanged."""
from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID, uuid5, NAMESPACE_URL

from pydantic import model_validator

from app.evidence_contracts.common import (Contract, VersionedRecord, Scope, Identifier, Digest,
    Timestamp, VersionReference, VerificationReference, EvidenceRevisionReference,
    SnapshotReference, ReasonCode, integrity_digest)
from app.evidence_contracts.evidence import EvidenceKind
from app.evidence_contracts.decisions import ReliabilityAssessment as AssessmentEnvelope
from app.data_reliability.models import ReliabilityState
from .arithmetic import ARITHMETIC_VERSION, exact_arithmetic

ROLES = tuple(kind for kind in EvidenceKind if kind not in
              (EvidenceKind.SOURCE_OBSERVATION, EvidenceKind.LEGACY_CLAIM))
COUNTS = (EvidenceKind.OPENING_COUNT, EvidenceKind.PHYSICAL_COUNT)


class ProfileReference(VersionReference):
    digest: Digest


class ProfileStatus(str, Enum):
    DRAFT = 'draft'
    SYNTHETIC_TEST_APPROVED = 'synthetic_test_approved'


class AssessmentProfile(VersionedRecord):
    identifier: Identifier
    version: Literal['1.0.0']
    status: ProfileStatus
    approval_reference: Identifier
    algorithm: Literal['dr01-adapter-1.0.0'] = 'dr01-adapter-1.0.0'
    arithmetic: Literal['exact-decimal-1.0.0'] = ARITHMETIC_VERSION
    interval: Literal['movements_start_inclusive_end_exclusive_counts_at_boundaries']
    timezone: Literal['UTC']
    location_scope: Literal['restaurant_aggregate_only']
    unit: Identifier
    unit_basis: Literal['native_canonical_no_conversion']
    usage_basis: Literal['excludes_recorded_waste']
    dependency_roles: tuple[EvidenceKind, ...]
    cardinality: Literal['one_stream_per_role_one_count_at_each_boundary']
    verification_issuers: tuple[Identifier, ...]
    verification_methods: tuple[Identifier, ...]
    source_systems: tuple[Identifier, ...]
    evaluation_as_of: Timestamp | None
    digest: Digest | None = None

    @model_validator(mode='after')
    def seal(self):
        if set(self.dependency_roles) != set(ROLES) or len(self.dependency_roles) != len(ROLES):
            raise ValueError('every inventory dependency role is mandatory')
        if not self.verification_issuers or not self.verification_methods or not self.source_systems:
            raise ValueError('explicit source and verifier authority required')
        if self.status == ProfileStatus.SYNTHETIC_TEST_APPROVED and self.evaluation_as_of is None:
            raise ValueError('synthetic test profiles require a fixed trusted evaluation time')
        digest = integrity_digest(self.model_dump(exclude={'digest'}))
        if self.digest is not None and self.digest != digest:
            raise ValueError('profile digest mismatch')
        object.__setattr__(self, 'digest', digest)
        return self

    def reference(self):
        return ProfileReference(identifier=self.identifier, version=self.version, digest=self.digest)


class Representation(str, Enum):
    EVENTS = 'events'
    AGGREGATE = 'aggregate'
    NO_MOVEMENTS = 'verified_no_movements'
    NOT_APPLICABLE = 'not_applicable'


class CoverageStatement(Contract):
    role: EvidenceKind
    stream_id: Identifier
    source_system: Identifier
    scope: Scope
    representation: Representation
    evidence: tuple[EvidenceRevisionReference, ...]
    unit_basis: Identifier
    usage_basis: Identifier | None = None
    # No hidden conversion: non-native inputs are blocked until a reviewed conversion contract exists.

    @model_validator(mode='after')
    def role_is_inventory(self):
        if self.role not in ROLES:
            raise ValueError('not an inventory dependency role')
        return self

    def artifact(self):
        return 'coverage:' + integrity_digest(self)


class CoverageClaim(Contract):
    statement: CoverageStatement
    verification: VerificationReference


class InventoryManifest(VersionedRecord):
    scope: Scope
    snapshot: SnapshotReference
    claims: tuple[CoverageClaim, ...]
    location_id: Identifier | None = None
    digest: Digest | None = None
    manifest_id: UUID | None = None

    @model_validator(mode='after')
    def seal(self):
        if self.scope.restaurant_id != self.snapshot.restaurant_id:
            raise ValueError('cross-tenant manifest')
        for claim in self.claims:
            if (claim.statement.scope.restaurant_id != self.scope.restaurant_id
                    or claim.verification.evidence.restaurant_id != self.scope.restaurant_id
                    or any(ref.restaurant_id != self.scope.restaurant_id for ref in claim.statement.evidence)):
                raise ValueError('cross-tenant coverage')
        digest = integrity_digest(self.model_dump(exclude={'digest', 'manifest_id'}))
        identity = uuid5(NAMESPACE_URL, 'rori:inventory-manifest:1.0.0:'+digest)
        if self.digest is not None and self.digest != digest:
            raise ValueError('manifest digest mismatch')
        if self.manifest_id is not None and self.manifest_id != identity:
            raise ValueError('manifest identity mismatch')
        object.__setattr__(self, 'digest', digest)
        object.__setattr__(self, 'manifest_id', identity)
        return self


class AssessmentRequest(Contract):
    snapshot: SnapshotReference
    profile: ProfileReference
    manifest_id: UUID
    manifest_digest: Digest
    scope: Scope


class BlockDetail(Contract):
    code: Identifier
    reason: ReasonCode


class CalculationProvenance(VersionedRecord):
    request: AssessmentRequest
    evaluated_at: Timestamp
    profile_available: bool
    algorithm: Literal['dr01-adapter-1.0.0'] = 'dr01-adapter-1.0.0'
    arithmetic: Literal['exact-decimal-1.0.0'] = ARITHMETIC_VERSION
    evidence: tuple[EvidenceRevisionReference, ...]
    verifications: tuple[VerificationReference, ...]
    details: tuple[BlockDetail, ...]
    assessment_digest: Digest
    computation_digest: Digest | None = None

    @model_validator(mode='after')
    def seal(self):
        digest = integrity_digest(self.model_dump(exclude={'computation_digest'}))
        if self.computation_digest is not None and self.computation_digest != digest:
            raise ValueError('computation digest mismatch')
        object.__setattr__(self, 'computation_digest', digest)
        return self


def calculation_body(assessment):
    return assessment.model_dump(exclude={'assessment_id', 'assessed_at', 'assessor_id'})


class TrustedAssessmentReceipt(VersionedRecord):
    assessment: AssessmentEnvelope
    provenance: CalculationProvenance

    @model_validator(mode='after')
    def coherent(self):
        a, p = self.assessment, self.provenance
        if a.decision_eligible or a.scope != p.request.scope or a.snapshots != (p.request.snapshot,):
            raise ValueError('trusted receipt must be blocked and bound to exact request scope/snapshot')
        if a.policy != VersionReference(identifier=p.request.profile.identifier, version=p.request.profile.version):
            raise ValueError('assessment profile binding mismatch')
        if a.assessed_at != p.evaluated_at or integrity_digest(calculation_body(a)) != p.assessment_digest:
            raise ValueError('assessment provenance mismatch')
        refs = set(p.verifications)
        if any(ref.evidence not in set(p.evidence) for ref in refs):
            raise ValueError('verification must bind resolved evidence')
        if any(ref not in refs for check in a.checks for ref in check.verification_refs):
            raise ValueError('check verification must be among resolved supporting references')
        if tuple(sorted(set(a.reasons), key=lambda r:r.value)) != a.reasons:
            raise ValueError('reasons must have stable unique ordering')
        values = tuple(v for v in (a.expected_inventory, a.actual_inventory, a.unexplained_variance) if v is not None)
        with exact_arithmetic(values):
            expected, actual, variance = a.expected_inventory, a.actual_inventory, a.unexplained_variance
            if actual is not None and actual < 0:
                raise ValueError('physical count cannot be negative')
            if a.state in (ReliabilityState.RELIABLE, ReliabilityState.REVIEW_REQUIRED):
                if expected is None or actual is None or variance is None or expected < 0 or actual < 0:
                    raise ValueError('complete states require valid quantities')
                if actual - expected != variance or ((variance == 0) != (a.state == ReliabilityState.RELIABLE)):
                    raise ValueError('contradictory assessment quantities/state')
            elif a.state == ReliabilityState.UNRELIABLE:
                if expected is None or expected >= 0 or variance is not None:
                    raise ValueError('negative expected inventory required for calculated unreliable state')
            elif variance is not None or actual is not None:
                raise ValueError('incomplete assessment cannot claim a physical result')
        return self
