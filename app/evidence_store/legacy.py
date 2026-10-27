"""Pure dry-run preparation of quarantined claims; never constructs InventoryRecord."""
from datetime import date, datetime
from enum import Enum
from uuid import UUID, uuid5, NAMESPACE_URL
import math

from pydantic import model_validator

from app.evidence_contracts.common import (Contract, VersionedRecord, TenantId, Identifier,
    Timestamp, Digest, ReasonCode, integrity_digest)


class RawType(str, Enum):
    NULL = 'null'
    INTEGER = 'integer'
    FLOAT = 'float'
    TEXT = 'text'
    DATE = 'date'
    DATETIME = 'datetime'
    BOOLEAN = 'boolean'


class RawField(Contract):
    name: Identifier
    value_type: RawType
    value: str | None

    @model_validator(mode='after')
    def raw_missing_semantics(self):
        if (self.value_type == RawType.NULL) != (self.value is None):
            raise ValueError('only a raw NULL may omit its value; NULL cannot contain zero')
        return self


class LegacyClaim(VersionedRecord):
    claim_id: UUID
    restaurant_id: TenantId
    batch_id: UUID
    source_table: Identifier
    source_primary_key: str
    source_digest: Digest
    ingested_at: Timestamp
    fields: tuple[RawField, ...]
    quality_flags: tuple[ReasonCode, ...]
    quarantine_reason: ReasonCode

    @model_validator(mode='after')
    def claim_only(self):
        if self.source_table not in ('sales', 'inventory', 'labor') or not self.source_primary_key:
            raise ValueError('explicit original table and primary key are required')
        required = {ReasonCode.LEGACY_CLAIM, ReasonCode.UNVERIFIED_EVIDENCE,
                    ReasonCode.UNKNOWN_OBSERVATION_TIME, ReasonCode.UNRESOLVED_ITEM,
                    ReasonCode.UNRESOLVED_UNIT, ReasonCode.MISSING_MOVEMENT_COVERAGE}
        names = tuple(field.name for field in self.fields)
        if names != tuple(sorted(set(names))):
            raise ValueError('raw fields require unique, sorted original column names')
        fields = {field.name: field for field in self.fields}
        if ('restaurant_id' not in fields or fields['restaurant_id'].value_type != RawType.INTEGER
                or fields['restaurant_id'].value != str(self.restaurant_id)):
            raise ValueError('raw tenant must match the authorized import tenant')
        if 'id' not in fields or fields['id'].value != self.source_primary_key:
            raise ValueError('raw primary key must match original lineage')
        if any(field.value_type == RawType.FLOAT for field in self.fields):
            required.add(ReasonCode.PRECISION_UNCERTAIN)
        if any(field.value_type == RawType.FLOAT and field.value in ('nan', 'inf', '-inf')
               for field in self.fields):
            required.add(ReasonCode.INVALID_QUANTITY)
        if not required.issubset(self.quality_flags) or self.quarantine_reason != ReasonCode.MISSING_EVIDENCE:
            raise ValueError('legacy claims must remain unverified and quarantined with all uncertainty flags')
        body = {'restaurant_id': self.restaurant_id, 'table': self.source_table,
                'primary_key': self.source_primary_key, 'fields': self.fields}
        digest = integrity_digest(body)
        identity = uuid5(NAMESPACE_URL, 'rori:legacy-claim:1.0.0:' + digest)
        if self.source_digest != digest or self.claim_id != identity:
            raise ValueError('legacy claim digest or identity mismatch')
        return self


def prepare_legacy(table, row, *, restaurant_id, batch_id, ingested_at):
    """Preserve supplied raw rows. Caller chooses a consistent read-only export.

    No mapping, observation-time, quantity-completeness, or verification inference
    occurs. Different source contents create a different quarantined claim.
    """
    if table not in ('inventory', 'sales', 'labor') or 'id' not in row or row['id'] is None:
        raise ValueError('known table and original primary key required')
    if type(restaurant_id) is not int or restaurant_id <= 0 or type(row.get('restaurant_id')) is not int or row['restaurant_id'] != restaurant_id:
        raise ValueError('TENANT_MISMATCH')
    fields = []
    flags = {ReasonCode.LEGACY_CLAIM, ReasonCode.UNVERIFIED_EVIDENCE,
             ReasonCode.UNKNOWN_OBSERVATION_TIME, ReasonCode.UNRESOLVED_UNIT,
             ReasonCode.UNRESOLVED_ITEM, ReasonCode.MISSING_MOVEMENT_COVERAGE}
    for key, value in sorted(row.items()):
        if value is None:
            kind, encoded = RawType.NULL, None
        elif type(value) is bool:
            kind, encoded = RawType.BOOLEAN, str(value)
        elif type(value) is int:
            kind, encoded = RawType.INTEGER, str(value)
        elif type(value) is float:
            kind, encoded = RawType.FLOAT, repr(value)
            flags.add(ReasonCode.PRECISION_UNCERTAIN)
            if not math.isfinite(value): flags.add(ReasonCode.INVALID_QUANTITY)
        elif isinstance(value, datetime):
            kind, encoded = RawType.DATETIME, value.isoformat()
        elif isinstance(value, date):
            kind, encoded = RawType.DATE, value.isoformat()
        elif isinstance(value, str):
            kind, encoded = RawType.TEXT, value
        else:
            raise ValueError(f'Unsupported raw field type: {key}; preserve in a reviewed source artifact')
        fields.append(RawField(name=key, value_type=kind, value=encoded))
    body = {'restaurant_id': restaurant_id, 'table': table, 'primary_key': str(row['id']), 'fields': tuple(fields)}
    digest = integrity_digest(body)
    return LegacyClaim(schema_version='1.0.0', claim_id=uuid5(NAMESPACE_URL, 'rori:legacy-claim:1.0.0:'+digest),
        restaurant_id=restaurant_id, batch_id=batch_id, source_table=table, source_primary_key=str(row['id']),
        source_digest=digest, ingested_at=ingested_at, fields=tuple(fields),
        quality_flags=tuple(sorted(flags, key=lambda f:f.value)), quarantine_reason=ReasonCode.MISSING_EVIDENCE)
