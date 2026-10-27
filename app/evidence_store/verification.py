"""Verification facts may be written only by database-authorized verifier identities."""
from enum import Enum
from uuid import UUID

from pydantic import model_validator

from app.evidence_contracts.common import (VersionedRecord, EvidenceRevisionReference,
    VerificationReference, VerificationPurpose, Revision, Identifier, Timestamp)


class VerificationStatus(str, Enum):
    VERIFIED = 'verified'
    REJECTED = 'rejected'


class VerificationRecord(VersionedRecord):
    verification_id: UUID
    revision: Revision
    evidence: EvidenceRevisionReference
    issuer_id: Identifier
    purpose: VerificationPurpose
    method: Identifier
    supporting_refs: tuple[Identifier, ...]
    verified_at: Timestamp
    scope_description: Identifier
    limitations: tuple[Identifier, ...]
    status: VerificationStatus

    @model_validator(mode='after')
    def supporting_material(self):
        if not self.supporting_refs:
            raise ValueError('verification requires supporting references, not just an asserted boolean')
        return self

    def reference(self):
        return VerificationReference(verification_id=self.verification_id, revision=self.revision,
                                     evidence=self.evidence, issuer_id=self.issuer_id, purpose=self.purpose)
