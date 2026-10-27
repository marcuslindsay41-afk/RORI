from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.evidence_store.legacy import prepare_legacy, LegacyClaim, RawType
from app.evidence_store.verification import VerificationRecord, VerificationStatus
from app.evidence_store.repository import validated
from app.evidence_contracts.common import ReasonCode, VerificationPurpose
from app.evidence_contracts.decisions import ReliabilityAssessment
from app.evidence_contracts.evidence import EvidenceRecord
from tests.contracts.factories import NOW, record, eligible_assessment_data


def prepare(**row):
    return prepare_legacy('inventory', {'id': 1, 'restaurant_id': 101, **row},
        restaurant_id=101, batch_id=uuid4(), ingested_at=NOW)


def test_null_zero_and_raw_timestamp_preserved_without_inference():
    naive = datetime(2020, 1, 1)
    claim = prepare(physical_count=None, usage=0, receipts=0.0, date=naive,
                    item='unmapped external label')
    fields = {field.name: field for field in claim.fields}
    assert fields['physical_count'].value is None
    assert fields['physical_count'].value_type == RawType.NULL
    assert fields['usage'].value == '0'
    assert fields['receipts'].value == '0.0'
    assert fields['date'].value == '2020-01-01T00:00:00'
    assert fields['item'].value == 'unmapped external label'
    assert {ReasonCode.UNKNOWN_OBSERVATION_TIME, ReasonCode.UNRESOLVED_ITEM,
            ReasonCode.UNRESOLVED_UNIT, ReasonCode.PRECISION_UNCERTAIN,
            ReasonCode.UNVERIFIED_EVIDENCE}.issubset(claim.quality_flags)
    assert claim.quarantine_reason == ReasonCode.MISSING_EVIDENCE
    assert 'effective_at' not in LegacyClaim.model_fields


@pytest.mark.parametrize('value', [0.1, float('nan'), float('inf'), -float('inf')])
def test_float_original_representation_and_precision_warning(value):
    claim = prepare(quantity=value)
    assert next(f for f in claim.fields if f.name == 'quantity').value == repr(value)
    assert ReasonCode.PRECISION_UNCERTAIN in claim.quality_flags
    if repr(value) in ('nan', 'inf', '-inf'):
        assert ReasonCode.INVALID_QUANTITY in claim.quality_flags


def test_claim_identity_is_repeatable_but_changes_preserve_history():
    a, b = prepare(quantity=None), prepare(quantity=None)
    assert a.claim_id == b.claim_id and a.source_digest == b.source_digest
    assert a.batch_id != b.batch_id
    assert prepare(quantity=0).claim_id != a.claim_id
    forged = a.model_copy(update={'source_digest': '0'*64})
    with pytest.raises(ValidationError, match='digest'):
        validated(LegacyClaim, forged)


@pytest.mark.parametrize('row', [{'id': None}, {'restaurant_id': 202},
    {'restaurant_id': True}, {'quantity': Decimal('1.1')}])
def test_invalid_export_fails_without_mutating_original(row):
    original = dict(row)
    with pytest.raises(ValueError):
        prepare(**row)
    assert row == original


def test_unknown_schema_version_fails():
    claim = prepare(quantity=0)
    with pytest.raises(ValidationError):
        validated(LegacyClaim, claim.model_copy(update={'schema_version': '2.0.0'}))


@pytest.mark.parametrize('purpose', list(VerificationPurpose))
def test_verification_requires_separate_authority_and_support(purpose):
    data = dict(schema_version='1.0.0', verification_id=uuid4(), revision=1,
        evidence=record().reference, issuer_id='verifier', purpose=purpose, method='count',
        supporting_refs=('source-artifact',), verified_at=NOW, scope_description='item-period',
        limitations=(), status=VerificationStatus.VERIFIED)
    ver = VerificationRecord(**data)
    assert ver.reference().purpose == purpose
    with pytest.raises(ValidationError, match='supporting'):
        VerificationRecord(**{**data, 'supporting_refs': ()})
    with pytest.raises(ValidationError, match='timezone'):
        VerificationRecord(**{**data, 'verified_at': datetime(2020, 1, 1)})


@pytest.mark.parametrize('axis', ['forecast', 'decision', 'universal'])
def test_assessment_confidence_cannot_be_relabelled(axis):
    with pytest.raises(ValidationError):
        ReliabilityAssessment(**{**eligible_assessment_data(), 'confidence_axis': axis})


def test_boundary_revalidates_unsafe_model_copy():
    original = record()
    with pytest.raises(ValidationError):
        validated(EvidenceRecord, original.model_copy(update={'verification_status': 'verified'}))
    assert original.verification_status.value == 'unverified'


def test_raw_null_cannot_be_relabelled_as_observed_zero():
    from app.evidence_store.legacy import RawField
    with pytest.raises(ValidationError, match='NULL'):
        RawField(name='quantity', value_type=RawType.NULL, value='0')
    with pytest.raises(ValidationError, match='NULL'):
        RawField(name='quantity', value_type=RawType.INTEGER, value=None)


def test_precision_and_quarantine_flags_cannot_be_removed():
    claim = prepare(quantity=0.1)
    forged = claim.model_copy(update={'quality_flags': tuple(
        flag for flag in claim.quality_flags if flag != ReasonCode.PRECISION_UNCERTAIN)})
    with pytest.raises(ValidationError, match='quarantined'):
        validated(LegacyClaim, forged)
