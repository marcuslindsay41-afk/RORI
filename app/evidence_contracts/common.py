"""Strict, immutable building blocks. References are identifiers, not proof of trust."""
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')]
TenantId = Annotated[int, Field(strict=True, gt=0)]
Revision = Annotated[int, Field(strict=True, gt=0)]
Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timestamps must include a timezone')
    return value.astimezone(timezone.utc)


Timestamp = Annotated[datetime, AfterValidator(utc)]


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra='forbid',
                              validate_default=True, revalidate_instances='always')


class VersionedRecord(Contract):
    schema_version: Literal['1.0.0']


class VersionReference(Contract):
    identifier: Identifier
    version: Annotated[str, Field(pattern=r'^[1-9][0-9]*\.[0-9]+\.[0-9]+$')]


class Scope(Contract):
    restaurant_id: TenantId
    item_id: Identifier | None = None
    unit: Identifier | None = None
    period_start: Timestamp | None = None
    period_end: Timestamp | None = None

    @model_validator(mode='after')
    def coherent_period(self):
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError('period boundaries must both be present or both be unknown')
        if self.period_start is not None and self.period_end <= self.period_start:
            raise ValueError('period_end must follow period_start')
        return self


class EvidenceRevisionReference(Contract):
    restaurant_id: TenantId
    evidence_id: UUID
    revision: Revision


class SnapshotReference(Contract):
    restaurant_id: TenantId
    snapshot_id: UUID
    digest: Digest


class VerificationPurpose(str, Enum):
    IMPORT_INTEGRITY = 'import_integrity'
    SOURCE = 'source'
    COUNT = 'count'
    COVERAGE = 'coverage'


class VerificationReference(Contract):
    verification_id: UUID
    revision: Revision
    evidence: EvidenceRevisionReference
    issuer_id: Identifier
    purpose: VerificationPurpose


class ReasonCode(str, Enum):
    MISSING_EVIDENCE = 'missing_evidence'
    MISSING_QUANTITY = 'missing_quantity'
    MISSING_COUNT = 'missing_count'
    MISSING_MOVEMENT_COVERAGE = 'missing_movement_coverage'
    UNKNOWN_OBSERVATION_TIME = 'unknown_observation_time'
    MISSING_PROVENANCE = 'missing_provenance'
    UNRESOLVED_ITEM = 'unresolved_item'
    UNRESOLVED_UNIT = 'unresolved_unit'
    UNKNOWN_PERIOD = 'unknown_period'
    PRECISION_UNCERTAIN = 'precision_uncertain'
    INVALID_QUANTITY = 'invalid_quantity'
    CONTRADICTORY_VARIANCE = 'contradictory_variance'
    UNVERIFIED_EVIDENCE = 'unverified_evidence'
    LEGACY_CLAIM = 'legacy_claim'
    STALE_EVIDENCE = 'stale_evidence'
    REVOKED_EVIDENCE = 'revoked_evidence'
    TENANT_MISMATCH = 'tenant_mismatch'
    REVISION_MISMATCH = 'revision_mismatch'
    POLICY_UNAVAILABLE = 'policy_unavailable'
    UNKNOWN_POLICY_VERSION = 'unknown_policy_version'
    UNKNOWN_MANIFEST = 'unknown_manifest'
    ASSESSMENT_FAILED = 'assessment_failed'
    REVIEW_REQUIRED = 'review_required'


class VerificationAction(str, Enum):
    PROVIDE_EVIDENCE = 'provide_evidence'
    RECOUNT = 'recount'
    VERIFY_SOURCE = 'verify_source'
    PROVIDE_MOVEMENTS = 'provide_movements'
    RESOLVE_IDENTITY = 'resolve_identity'
    RESOLVE_UNITS = 'resolve_units'
    DEFINE_POLICY = 'define_policy'
    REASSESS = 'reassess'


def same_tenant(restaurant_id: int, references) -> None:
    if any(ref.restaurant_id != restaurant_id for ref in references):
        raise ValueError('cross-tenant references are forbidden')


def unique(values, label: str) -> None:
    values = tuple(values)
    if len(set(values)) != len(values):
        raise ValueError(f'duplicate {label}')


def _canonical(value):
    if isinstance(value, BaseModel):
        return _canonical(value.model_dump(mode='python'))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        # Avoid normalize(), which can round under the active decimal context.
        if not value.is_finite():
            raise ValueError('nonfinite numbers cannot be hashed')
        sign, digits, exponent = value.as_tuple()
        digits = list(digits)
        if not any(digits):
            return {'decimal': '0'}
        while digits[-1] == 0:
            digits.pop()
            exponent += 1
        coefficient = ''.join(str(d) for d in digits)
        return {'decimal': f'{"-" if sign else ""}{coefficient}e{exponent}'}
    if isinstance(value, datetime):
        return utc(value).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def integrity_digest(value) -> str:
    encoded = json.dumps(_canonical(value), sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True, allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()
