"""Observations and sealed snapshots; no source record can verify itself."""
from decimal import Decimal
from enum import Enum
from typing import Literal
from uuid import UUID, uuid5, NAMESPACE_URL

from pydantic import model_validator

from .common import (Contract, VersionedRecord, VersionReference, Scope, Identifier,
                     Timestamp, Digest, EvidenceRevisionReference, SnapshotReference,
                     VerificationReference, ReasonCode, same_tenant, unique, integrity_digest)


class ValueState(str, Enum):
    OBSERVED = 'observed'
    UNKNOWN = 'unknown'
    NOT_APPLICABLE = 'not_applicable'


class Quantity(Contract):
    state: ValueState
    value: Decimal | None = None
    rule: VersionReference | None = None

    @model_validator(mode='after')
    def explicit_semantics(self):
        if self.state == ValueState.OBSERVED:
            if self.value is None or not self.value.is_finite():
                raise ValueError('observed quantity requires a finite Decimal')
            if self.rule is not None:
                raise ValueError('observed quantity cannot claim a not-applicable rule')
        elif self.value is not None:
            raise ValueError('unknown/not-applicable quantity cannot contain a value')
        if self.state == ValueState.NOT_APPLICABLE:
            if self.rule is None:
                raise ValueError('not-applicable requires a documented versioned rule')
        elif self.rule is not None:
            raise ValueError('rule is only applicable to not-applicable values')
        return self


class EvidenceDomain(str, Enum):
    INVENTORY = 'inventory'
    SALES = 'sales'
    COST = 'cost'
    LABOR = 'labor'
    RECIPE = 'recipe'


class EvidenceKind(str, Enum):
    OPENING_COUNT = 'opening_count'
    PHYSICAL_COUNT = 'physical_count'
    RECEIPT = 'receipt'
    THEORETICAL_USAGE = 'theoretical_usage'
    RECORDED_WASTE = 'recorded_waste'
    TRANSFER_IN = 'transfer_in'
    TRANSFER_OUT = 'transfer_out'
    ADJUSTMENT = 'adjustment'
    SOURCE_OBSERVATION = 'source_observation'
    LEGACY_CLAIM = 'legacy_claim'


class IntakeStatus(str, Enum):
    UNVERIFIED = 'unverified'


class SourceReference(Contract):
    system: Identifier
    record_id: Identifier | None = None
    revision: Identifier | None = None
    artifact_ref: Identifier | None = None


class MigrationReference(Contract):
    batch_id: UUID
    source_table: Identifier
    source_primary_key: Identifier


class EvidenceRecord(VersionedRecord):
    reference: EvidenceRevisionReference
    scope: Scope
    domain: EvidenceDomain
    kind: EvidenceKind
    quantity: Quantity
    source: SourceReference
    ingested_at: Timestamp
    effective_at: Timestamp | None = None
    recorded_at: Timestamp | None = None
    supersedes: EvidenceRevisionReference | None = None
    migration: MigrationReference | None = None
    quality_flags: tuple[ReasonCode, ...] = ()
    # Trust is resolved through separate verification records in a later increment.
    verification_status: Literal[IntakeStatus.UNVERIFIED] = IntakeStatus.UNVERIFIED

    @model_validator(mode='after')
    def observation_contract(self):
        same_tenant(self.scope.restaurant_id, (self.reference,))
        if self.reference.revision == 1:
            if self.supersedes is not None:
                raise ValueError('first revision cannot supersede another revision')
        elif self.supersedes is None:
            raise ValueError('a correction requires its previous revision reference')
        if self.supersedes is not None:
            previous = self.supersedes
            if (previous.restaurant_id != self.reference.restaurant_id
                    or previous.evidence_id != self.reference.evidence_id
                    or previous.revision + 1 != self.reference.revision):
                raise ValueError('correction must supersede the immediately preceding revision of the same evidence')
        flags = set(self.quality_flags)
        unique(self.quality_flags, 'quality flags')
        required_flags = set()
        if self.effective_at is None:
            required_flags.add(ReasonCode.UNKNOWN_OBSERVATION_TIME)
        if self.source.record_id is None and self.source.artifact_ref is None:
            required_flags.add(ReasonCode.MISSING_PROVENANCE)
        if self.quantity.state == ValueState.UNKNOWN:
            required_flags.add(ReasonCode.MISSING_QUANTITY)
        if self.domain == EvidenceDomain.INVENTORY:
            if self.scope.item_id is None:
                required_flags.add(ReasonCode.UNRESOLVED_ITEM)
            if self.scope.unit is None:
                required_flags.add(ReasonCode.UNRESOLVED_UNIT)
            if self.kind != EvidenceKind.LEGACY_CLAIM and (self.scope.item_id is None or self.scope.unit is None):
                raise ValueError('inventory observations require an explicit item and unit')
        if self.kind == EvidenceKind.LEGACY_CLAIM:
            required_flags.update((ReasonCode.LEGACY_CLAIM, ReasonCode.UNVERIFIED_EVIDENCE))
            if self.migration is None:
                raise ValueError('legacy claims require original row and migration-batch references')
        elif self.migration is not None:
            raise ValueError('migration lineage must remain a legacy claim')
        if not required_flags.issubset(flags):
            raise ValueError('missing quality flags: ' + ', '.join(sorted(f.value for f in required_flags - flags)))
        if self.domain != EvidenceDomain.INVENTORY and self.kind not in (EvidenceKind.SOURCE_OBSERVATION, EvidenceKind.LEGACY_CLAIM):
            raise ValueError('inventory movement/count kinds require the inventory domain')
        if (self.domain == EvidenceDomain.INVENTORY and self.quantity.value is not None
                and self.quantity.value < 0 and self.kind != EvidenceKind.ADJUSTMENT):
            raise ValueError('inventory quantities cannot be negative except signed adjustments')
        if self.effective_at is not None and self.effective_at > self.ingested_at:
            raise ValueError('an observation cannot occur after ingestion')
        if self.recorded_at is not None and self.recorded_at > self.ingested_at:
            raise ValueError('source recording cannot occur after ingestion')
        return self


class EvidenceSnapshot(VersionedRecord):
    scope: Scope
    policy: VersionReference
    created_at: Timestamp
    records: tuple[EvidenceRecord, ...]
    verification_refs: tuple[VerificationReference, ...] = ()
    digest: Digest | None = None
    snapshot_id: UUID | None = None

    @model_validator(mode='after')
    def seal_snapshot(self):
        # Source ordering is not part of snapshot meaning.
        records = tuple(sorted(self.records, key=lambda r: str(r.reference.evidence_id)))
        verifications = tuple(sorted(self.verification_refs, key=lambda r: (str(r.verification_id), r.revision)))
        unique((r.reference.evidence_id for r in records), 'evidence identities')
        unique(((v.verification_id, v.revision) for v in verifications), 'verification references')
        same_tenant(self.scope.restaurant_id, (r.reference for r in records))
        references = {r.reference for r in records}
        for record in records:
            if record.ingested_at > self.created_at:
                raise ValueError('snapshot cannot precede evidence ingestion')
            for field in ('item_id', 'unit'):
                expected = getattr(self.scope, field)
                if expected is not None and getattr(record.scope, field) != expected:
                    raise ValueError(f'snapshot {field} must match each evidence record')
            if self.scope.period_start is not None and record.scope.period_start is not None:
                if (record.scope.period_start < self.scope.period_start
                        or record.scope.period_end > self.scope.period_end):
                    raise ValueError('evidence period is outside snapshot scope')
        if any(v.evidence not in references for v in verifications):
            raise ValueError('verification references must bind an exact evidence revision in this snapshot')
        object.__setattr__(self, 'records', records)
        object.__setattr__(self, 'verification_refs', verifications)
        calculated = integrity_digest(self.model_dump(exclude={'digest', 'snapshot_id'}))
        identity = uuid5(NAMESPACE_URL, f'rori:evidence-snapshot:1.0.0:{calculated}')
        if self.digest is not None and self.digest != calculated:
            raise ValueError('snapshot digest mismatch')
        if self.snapshot_id is not None and self.snapshot_id != identity:
            raise ValueError('snapshot identity mismatch')
        object.__setattr__(self, 'digest', calculated)
        object.__setattr__(self, 'snapshot_id', identity)
        return self

    def reference(self) -> SnapshotReference:
        return SnapshotReference(restaurant_id=self.scope.restaurant_id,
                                 snapshot_id=self.snapshot_id, digest=self.digest)
