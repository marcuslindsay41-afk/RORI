from datetime import timedelta, timezone
from decimal import Decimal, localcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.evidence_contracts.common import (EvidenceRevisionReference, Scope, ReasonCode,
                                          VerificationPurpose)
from app.evidence_contracts.evidence import (EvidenceRecord, EvidenceSnapshot, Quantity,
    ValueState, EvidenceKind, EvidenceDomain, MigrationReference, IntakeStatus)
from .factories import NOW, record_data, record, snapshot_data, verification


def test_zero_unknown_and_not_applicable_are_distinct():
    from .factories import POLICY
    zero = Quantity(state=ValueState.OBSERVED, value=Decimal('0'))
    unknown = Quantity(state=ValueState.UNKNOWN)
    na = Quantity(state=ValueState.NOT_APPLICABLE, rule=POLICY)
    assert zero.value == 0 and unknown.value is None and na.value is None
    assert zero != unknown != na
    assert len({zero, unknown, na}) == 3


@pytest.mark.parametrize('value', [None, 0, 0.0, True, '0', Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity')])
def test_observed_values_require_finite_decimal(value):
    with pytest.raises(ValidationError):
        Quantity(state=ValueState.OBSERVED, value=value)


@pytest.mark.parametrize('state', [ValueState.UNKNOWN, ValueState.NOT_APPLICABLE])
def test_missing_semantics_cannot_carry_a_fabricated_zero(state):
    with pytest.raises(ValidationError):
        Quantity(state=state, value=Decimal('0'))


def test_not_applicable_requires_a_rule_and_unknown_cannot_claim_one():
    from .factories import POLICY
    with pytest.raises(ValidationError):
        Quantity(state=ValueState.NOT_APPLICABLE)
    with pytest.raises(ValidationError):
        Quantity(state=ValueState.UNKNOWN, rule=POLICY)


@pytest.mark.parametrize('field,value', [('restaurant_id', 0), ('restaurant_id', True),
    ('restaurant_id', '101'), ('item_id', ''), ('item_id', ' '), ('unit', '')])
def test_scope_rejects_invalid_tenant_and_identity(field, value):
    with pytest.raises(ValidationError):
        Scope(**{'restaurant_id': 101, field: value})


@pytest.mark.parametrize('start,end', [(NOW, None), (None, NOW), (NOW, NOW), (NOW, NOW-timedelta(days=1))])
def test_partial_and_invalid_periods_rejected(start, end):
    with pytest.raises(ValidationError):
        Scope(restaurant_id=101, period_start=start, period_end=end)


def test_unknown_observation_time_is_not_replaced_by_ingestion():
    data = record_data()
    data['effective_at'] = None
    with pytest.raises(ValidationError, match='quality flags'):
        EvidenceRecord(**data)
    data['quality_flags'] = (ReasonCode.UNKNOWN_OBSERVATION_TIME,)
    result = EvidenceRecord(**data)
    assert result.effective_at is None and result.ingested_at == NOW


def test_unknown_quantity_requires_an_explicit_quality_flag():
    data = record_data()
    data['quantity'] = Quantity(state=ValueState.UNKNOWN)
    with pytest.raises(ValidationError, match='missing_quantity'):
        EvidenceRecord(**data)
    result = EvidenceRecord(**{**data, 'quality_flags': (ReasonCode.MISSING_QUANTITY,)})
    assert result.quantity.value is None


def test_legacy_claim_retains_missing_identity_and_original_row_without_verification():
    data = record_data()
    data.update(kind=EvidenceKind.LEGACY_CLAIM, scope=Scope(restaurant_id=101), effective_at=None,
        migration=MigrationReference(batch_id=uuid4(), source_table='inventory', source_primary_key='17'),
        quality_flags=(ReasonCode.LEGACY_CLAIM, ReasonCode.UNVERIFIED_EVIDENCE,
                       ReasonCode.UNRESOLVED_ITEM, ReasonCode.UNRESOLVED_UNIT,
                       ReasonCode.UNKNOWN_OBSERVATION_TIME))
    claim = EvidenceRecord(**data)
    assert claim.verification_status == IntakeStatus.UNVERIFIED
    assert claim.scope.item_id is None and claim.scope.unit is None
    assert claim.migration.source_primary_key == '17' and claim.effective_at is None
    with pytest.raises(ValidationError):
        EvidenceRecord(**{**data, 'verification_status': 'verified'})
    with pytest.raises(ValidationError):
        EvidenceRecord(**{**data, 'migration': None})


def test_corrections_reference_previous_immutable_revision():
    original = record()
    data = original.model_dump()
    data['reference'] = EvidenceRevisionReference(restaurant_id=101, evidence_id=original.reference.evidence_id, revision=2)
    data['supersedes'] = original.reference
    corrected = EvidenceRecord(**data)
    assert corrected.supersedes == original.reference and original.reference.revision == 1
    for previous in [None, EvidenceRevisionReference(restaurant_id=202, evidence_id=original.reference.evidence_id, revision=1),
                     EvidenceRevisionReference(restaurant_id=101, evidence_id=uuid4(), revision=1)]:
        with pytest.raises(ValidationError):
            EvidenceRecord(**{**data, 'supersedes': previous})


@pytest.mark.parametrize('kind', [EvidenceKind.PHYSICAL_COUNT, EvidenceKind.RECEIPT, EvidenceKind.RECORDED_WASTE])
def test_inventory_quantities_cannot_be_negative_except_adjustments(kind):
    data = record_data()
    data.update(kind=kind, quantity=Quantity(state=ValueState.OBSERVED, value=Decimal('-1')))
    with pytest.raises(ValidationError):
        EvidenceRecord(**data)
    data['kind'] = EvidenceKind.ADJUSTMENT
    assert EvidenceRecord(**data).quantity.value == -1


def test_snapshot_is_deterministic_under_order_units_of_decimal_representation_and_timezone():
    first, second = record(), record()
    a = EvidenceSnapshot(**snapshot_data((first, second)))
    changed = first.model_dump()
    changed['quantity'] = Quantity(state=ValueState.OBSERVED, value=Decimal('-0.000'))
    offset_time = NOW.astimezone(timezone(timedelta(hours=2)))
    b = EvidenceSnapshot(**{**snapshot_data((second, EvidenceRecord(**changed))), 'created_at': offset_time})
    assert a.digest == b.digest and a.snapshot_id == b.snapshot_id
    assert a.reference() == b.reference()
    assert EvidenceSnapshot.model_validate_json(a.model_dump_json()) == a


def test_snapshot_hash_never_rounds_high_precision_decimals():
    data = record_data()
    data['quantity'] = Quantity(state=ValueState.OBSERVED, value=Decimal('1.234567890123456789012345678901'))
    with localcontext() as context:
        context.prec = 5
        a = EvidenceSnapshot(**snapshot_data((EvidenceRecord(**data),)))
    data['quantity'] = Quantity(state=ValueState.OBSERVED, value=Decimal('1.234567890123456789012345678902'))
    b = EvidenceSnapshot(**snapshot_data((EvidenceRecord(**data),)))
    assert a.digest != b.digest


def test_changed_content_or_supplied_digest_cannot_reuse_snapshot_identity():
    snap = EvidenceSnapshot(**snapshot_data())
    for changes in [{'digest': '0'*64}, {'snapshot_id': uuid4()}, {'created_at': NOW+timedelta(seconds=1)}]:
        with pytest.raises(ValidationError, match='mismatch'):
            EvidenceSnapshot.model_validate({**snap.model_dump(), **changes})


def test_snapshot_rejects_duplicate_or_mixed_revisions_and_cross_tenant_scope():
    rec = record()
    with pytest.raises(ValidationError, match='duplicate'):
        EvidenceSnapshot(**snapshot_data((rec, rec)))
    data = rec.model_dump()
    data['reference'] = EvidenceRevisionReference(restaurant_id=101, evidence_id=rec.reference.evidence_id, revision=2)
    data['supersedes'] = rec.reference
    with pytest.raises(ValidationError, match='duplicate'):
        EvidenceSnapshot(**snapshot_data((rec, EvidenceRecord(**data))))
    with pytest.raises(ValidationError, match='cross-tenant'):
        EvidenceSnapshot(**{**snapshot_data((rec,)), 'scope': Scope(restaurant_id=202)})


def test_snapshot_verification_binds_exact_revision_not_just_evidence_id():
    rec = record()
    valid = verification(rec.reference)
    snap = EvidenceSnapshot(**{**snapshot_data((rec,)), 'verification_refs': (valid,)})
    assert snap.verification_refs == (valid,)
    wrong = verification(EvidenceRevisionReference(restaurant_id=101, evidence_id=rec.reference.evidence_id, revision=2))
    with pytest.raises(ValidationError, match='exact evidence revision'):
        EvidenceSnapshot(**{**snapshot_data((rec,)), 'verification_refs': (wrong,)})


def test_nested_snapshot_fields_are_immutable():
    snap = EvidenceSnapshot(**snapshot_data())
    for obj, field, value in [(snap, 'records', ()), (snap.scope, 'restaurant_id', 202),
                              (snap.records[0].quantity, 'value', Decimal('5'))]:
        with pytest.raises(ValidationError, match='frozen'):
            setattr(obj, field, value)
    assert isinstance(snap.records, tuple)


def test_correction_changes_snapshot_binding_without_overwriting_previous_evidence():
    rec = record()
    before = EvidenceSnapshot(**snapshot_data((rec,)))
    data = rec.model_dump()
    data['reference'] = EvidenceRevisionReference(restaurant_id=101, evidence_id=rec.reference.evidence_id, revision=2)
    data['supersedes'] = rec.reference
    after = EvidenceSnapshot(**snapshot_data((EvidenceRecord(**data),)))
    assert before.reference() != after.reference()
    assert before.records[0].reference.revision == 1
    assert after.records[0].reference.revision == 2


def test_inventory_observations_cannot_borrow_another_tenants_reference():
    data = record_data()
    data['reference'] = EvidenceRevisionReference(restaurant_id=202, evidence_id=uuid4(), revision=1)
    with pytest.raises(ValidationError, match='cross-tenant'):
        EvidenceRecord(**data)


def test_source_kind_and_domain_cannot_mislabel_inventory_movements():
    with pytest.raises(ValidationError, match='inventory domain'):
        EvidenceRecord(**{**record_data(), 'domain': EvidenceDomain.SALES})


def test_verification_reference_order_is_canonical_without_asserting_trust():
    rec = record()
    first = verification(rec.reference)
    second = verification(rec.reference, VerificationPurpose.COUNT)
    left = EvidenceSnapshot(**{**snapshot_data((rec,)), 'verification_refs': (first, second)})
    right = EvidenceSnapshot(**{**snapshot_data((rec,)), 'verification_refs': (second, first)})
    assert left.digest == right.digest and left.snapshot_id == right.snapshot_id
    assert left.records[0].verification_status == IntakeStatus.UNVERIFIED
