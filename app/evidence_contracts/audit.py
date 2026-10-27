"""Immutable, integrity-linked audit records; durable append-only storage is future work."""
from enum import Enum
from uuid import UUID

from pydantic import model_validator

from .common import (VersionedRecord, Identifier, TenantId, Revision, Timestamp,
                     Digest, EvidenceRevisionReference, SnapshotReference,
                     VerificationReference, ReasonCode, same_tenant, unique, integrity_digest)


class ActorKind(str, Enum):
    HUMAN = 'human'
    SERVICE = 'service'
    SYSTEM = 'system'


class AuditAction(str, Enum):
    SUBMIT = 'submit'
    CORRECT = 'correct'
    VERIFY = 'verify'
    REVOKE = 'revoke'
    ASSESS = 'assess'
    AUTHORIZE = 'authorize'
    DENY = 'deny'
    PUBLISH = 'publish'
    ACCEPT = 'accept'
    EXECUTE = 'execute'
    INVALIDATE = 'invalidate'


class SubjectType(str, Enum):
    VERIFICATION = 'verification'
    LEGACY_CLAIM = 'legacy_claim'
    EVIDENCE = 'evidence'
    SNAPSHOT = 'snapshot'
    ASSESSMENT = 'assessment'
    ELIGIBILITY = 'eligibility'
    DECISION = 'decision'


class AuditEvent(VersionedRecord):
    event_id: UUID
    stream_id: UUID
    sequence: Revision
    restaurant_id: TenantId
    actor_id: Identifier
    actor_kind: ActorKind
    action: AuditAction
    subject_type: SubjectType
    subject_id: UUID
    occurred_at: Timestamp
    evidence_refs: tuple[EvidenceRevisionReference, ...] = ()
    snapshot_refs: tuple[SnapshotReference, ...] = ()
    verification_ref: VerificationReference | None = None
    reasons: tuple[ReasonCode, ...] = ()
    previous_digest: Digest | None = None
    digest: Digest | None = None

    @model_validator(mode='after')
    def seal_event(self):
        same_tenant(self.restaurant_id, self.evidence_refs)
        same_tenant(self.restaurant_id, self.snapshot_refs)
        if self.verification_ref is not None:
            same_tenant(self.restaurant_id, (self.verification_ref.evidence,))
        if self.sequence == 1 and self.previous_digest is not None:
            raise ValueError('first event cannot have a predecessor')
        if self.sequence > 1 and self.previous_digest is None:
            raise ValueError('subsequent events require a predecessor digest')
        if self.action in (AuditAction.DENY, AuditAction.INVALIDATE, AuditAction.REVOKE) and not self.reasons:
            raise ValueError('denial/invalidation/revocation requires structured reasons')
        if self.action == AuditAction.VERIFY and self.verification_ref is None:
            raise ValueError('verification event must reference a separate verification record')
        if self.subject_type == SubjectType.EVIDENCE:
            if self.subject_id not in {ref.evidence_id for ref in self.evidence_refs}:
                raise ValueError('evidence subjects require an exact revision reference')
        if self.subject_type == SubjectType.SNAPSHOT:
            if self.subject_id not in {ref.snapshot_id for ref in self.snapshot_refs}:
                raise ValueError('snapshot subjects require an exact digest reference')
        if self.action == AuditAction.VERIFY:
            if self.verification_ref.evidence not in self.evidence_refs:
                raise ValueError('verification event must bind its evidence revision')
        calculated = integrity_digest(self.model_dump(exclude={'digest'}))
        if self.digest is not None and self.digest != calculated:
            raise ValueError('audit event digest mismatch')
        object.__setattr__(self, 'digest', calculated)
        return self


def validate_audit_chain(events: tuple[AuditEvent, ...]) -> None:
    """Validate a complete ordered stream; this does not persist or authenticate it."""
    unique((event.event_id for event in events), 'audit event IDs')
    previous = None
    for event in events:
        # Revalidate even when a caller used Pydantic's unsafe construction APIs.
        AuditEvent.model_validate(event.model_dump())
        if previous is None:
            if event.sequence != 1:
                raise ValueError('complete stream must begin at sequence 1')
        elif (event.restaurant_id != previous.restaurant_id or event.stream_id != previous.stream_id
              or event.sequence != previous.sequence + 1 or event.previous_digest != previous.digest
              or event.occurred_at < previous.occurred_at):
            raise ValueError('audit stream order, scope or predecessor mismatch')
        previous = event
