from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.evidence_contracts import (EvidenceRecord, EvidenceSnapshot, ReliabilityAssessment,
                                  DecisionEligibility, AuditEvent)
from app.evidence_contracts.audit import validate_audit_chain, AuditAction
from app.evidence_contracts.common import VersionReference
from .factories import (event_data, record_data, snapshot_data, eligible_assessment_data,
                        denial_data, verification)

FACTORIES = [(EvidenceRecord, record_data), (EvidenceSnapshot, snapshot_data),
             (ReliabilityAssessment, eligible_assessment_data), (DecisionEligibility, denial_data),
             (AuditEvent, event_data)]


@pytest.mark.parametrize('model,factory', FACTORIES)
@pytest.mark.parametrize('version', [None, '0.0.0', '2.0.0', 1])
def test_every_record_rejects_unknown_schema_versions(model, factory, version):
    with pytest.raises(ValidationError):
        model(**{**factory(), 'schema_version': version})


@pytest.mark.parametrize('model,factory', FACTORIES)
def test_version_is_required_extra_fields_rejected_and_records_round_trip(model, factory):
    data = factory()
    value = model(**data)
    assert model.model_validate_json(value.model_dump_json()) == value
    with pytest.raises(ValidationError):
        model(**{k: v for k, v in data.items() if k != 'schema_version'})
    with pytest.raises(ValidationError):
        model(**{**data, 'trusted': True})


@pytest.mark.parametrize('model,factory,field', [(EvidenceRecord, record_data, 'ingested_at'),
    (EvidenceSnapshot, snapshot_data, 'created_at'), (ReliabilityAssessment, eligible_assessment_data, 'assessed_at'),
    (DecisionEligibility, denial_data, 'evaluated_at'), (AuditEvent, event_data, 'occurred_at')])
def test_naive_timestamps_never_acquire_an_invented_timezone(model, factory, field):
    data = factory()
    data[field] = data[field].replace(tzinfo=None)
    with pytest.raises(ValidationError, match='timezone'):
        model(**data)


@pytest.mark.parametrize('version', ['', 'latest', '0.1.0', '1', '1.0', '1.0.0-extra'])
def test_policy_and_manifest_version_references_require_explicit_version_syntax(version):
    with pytest.raises(ValidationError):
        VersionReference(identifier='test', version=version)


def test_append_only_audit_records_validate_order_and_integrity():
    first = AuditEvent(**event_data())
    second = AuditEvent(**{**event_data(), 'stream_id': first.stream_id, 'sequence': 2,
                          'previous_digest': first.digest})
    validate_audit_chain((first, second))
    assert first.digest != second.digest
    with pytest.raises(ValidationError, match='frozen'):
        first.actor_id = 'rewritten-actor'
    with pytest.raises(ValidationError, match='digest mismatch'):
        AuditEvent.model_validate({**first.model_dump(), 'actor_id': 'rewritten-actor'})
    for events in [(second, first), (first, first), (second,)]:
        with pytest.raises(ValueError):
            validate_audit_chain(events)


def test_audit_predecessor_scope_cannot_be_substituted():
    first = AuditEvent(**event_data())
    data = {**event_data(), 'stream_id': first.stream_id, 'sequence': 2, 'previous_digest': first.digest}
    wrong_stream = AuditEvent(**{**data, 'stream_id': uuid4()})
    with pytest.raises(ValueError, match='scope'):
        validate_audit_chain((first, wrong_stream))
    with pytest.raises(ValidationError, match='predecessor'):
        AuditEvent(**{**data, 'previous_digest': None})


@pytest.mark.parametrize('action', [AuditAction.DENY, AuditAction.REVOKE, AuditAction.INVALIDATE])
def test_negative_audit_events_require_structured_reasons(action):
    with pytest.raises(ValidationError, match='reasons'):
        AuditEvent(**{**event_data(), 'action': action})


def test_verification_is_a_separate_traceable_record_not_an_observation_flag():
    data = event_data()
    with pytest.raises(ValidationError, match='separate verification'):
        AuditEvent(**{**data, 'action': AuditAction.VERIFY})
    event = AuditEvent(**{**data, 'action': AuditAction.VERIFY,
                         'verification_ref': verification(data['evidence_refs'][0])})
    assert event.verification_ref.evidence == event.evidence_refs[0]


def test_unsafe_pydantic_copy_is_not_treated_as_valid_audit_history():
    event = AuditEvent(**event_data())
    forged = event.model_copy(update={'actor_id': 'changed-without-validation'})
    with pytest.raises(ValidationError, match='digest mismatch'):
        validate_audit_chain((forged,))


def test_audit_chain_cannot_repeat_an_event_identity():
    first = AuditEvent(**event_data())
    second = AuditEvent(**{**event_data(), 'event_id': first.event_id,
                          'stream_id': first.stream_id, 'sequence': 2, 'previous_digest': first.digest})
    with pytest.raises(ValueError, match='duplicate audit event IDs'):
        validate_audit_chain((first, second))
