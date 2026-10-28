"""Explicit, transactional persistence boundary; never an authorization gateway.

Use separately provisioned, non-owner PostgreSQL logins. No application settings,
.env loading, tenant self-registration, or production startup side effects.
"""
from contextlib import contextmanager
import json
from uuid import UUID

from sqlalchemy import text

from app.evidence_contracts.evidence import EvidenceRecord, EvidenceSnapshot
from app.evidence_contracts.decisions import ReliabilityAssessment, DecisionEligibility
from app.evidence_contracts.audit import AuditEvent, validate_audit_chain
from app.evidence_contracts.common import Scope, ReasonCode
from .verification import VerificationRecord
from .legacy import LegacyClaim

_REPOSITORY_ORIGIN = object()

MODELS = {'evidence': EvidenceRecord, 'snapshot': EvidenceSnapshot,
          'assessment': ReliabilityAssessment, 'eligibility': DecisionEligibility,
          'verification': VerificationRecord, 'legacy_claim': LegacyClaim}


def validated(model, value):
    # Revalidate even frozen model instances: model_copy/model_construct bypass validation.
    return model.model_validate_json(value.model_dump_json() if isinstance(value, model)
                                     else json.dumps(value))


class EvidenceRepository:
    def __init__(self, engine, restaurant_id):
        if engine.dialect.name != 'postgresql':
            raise ValueError('PostgreSQL required')
        self.engine = engine
        self.restaurant_id = Scope(restaurant_id=restaurant_id).restaurant_id

    @contextmanager
    def transaction(self):
        with self.engine.begin() as connection:
            privileged = connection.scalar(text("""SELECT rolsuper OR rolbypassrls OR
                pg_has_role(session_user, n.nspowner, 'MEMBER') FROM pg_roles r,
                pg_namespace n WHERE r.rolname=session_user AND n.nspname='rori_evidence'"""))
            if privileged is not False:
                raise PermissionError('Runtime requires a non-owner, non-bypass database login')
            connection.execute(text('SELECT rori_evidence.lock_scope(:t)'), {'t': self.restaurant_id})
            yield EvidenceTransaction(connection, self.restaurant_id, _origin=_REPOSITORY_ORIGIN)


class EvidenceTransaction:
    def __init__(self, connection, restaurant_id, *, _origin=None):
        self.connection, self.restaurant_id = connection, restaurant_id
        self._repository_origin = _origin

    def require_repository_origin(self):
        if self._repository_origin is not _REPOSITORY_ORIGIN or not self.connection.in_transaction():
            raise PermissionError("Active EvidenceRepository transaction required")

    def append(self, kind, value, *, expected_revision=0):
        if kind not in MODELS:
            raise ValueError('Unknown evidence object kind')
        value = validated(MODELS[kind], value)
        if kind == 'evidence':
            identity, revision = value.reference.evidence_id, value.reference.revision
        elif kind == 'verification':
            identity, revision = value.verification_id, value.revision
        else:
            identity = getattr(value, {'snapshot': 'snapshot_id', 'assessment': 'assessment_id',
                'eligibility': 'eligibility_id', 'legacy_claim': 'claim_id'}[kind])
            revision = 1
        # No trusted policy registry exists. Never persist a positive authorization
        # or an assessment that could be mistaken for operational permission.
        if kind == 'assessment' and value.decision_eligible:
            raise ValueError('POLICY_UNAVAILABLE: positive assessments cannot be persisted yet')
        self.connection.execute(text('''SELECT rori_evidence.append_object(
            :t,:k,CAST(:i AS uuid),:r,CAST(:p AS jsonb),:expected)'''),
            {'t': self.restaurant_id, 'k': kind, 'i': str(identity), 'r': revision,
             'p': value.model_dump_json(), 'expected': expected_revision})
        # Return the persisted version (idempotent import may preserve an earlier batch).
        return self.get(kind, identity, revision)

    def get(self, kind, identity, revision=1):
        if kind not in MODELS or not isinstance(identity, UUID) or type(revision) is not int or revision < 1:
            raise ValueError('Invalid object reference')
        row = self.connection.execute(text('''SELECT payload,
            transport_digest=encode(sha256(convert_to(payload::text,'UTF8')),'hex') AS intact
            FROM rori_evidence.objects WHERE restaurant_id=:t AND kind=:k
            AND object_id=CAST(:i AS uuid) AND revision=:r'''),
            {'t': self.restaurant_id, 'k': kind, 'i': str(identity), 'r': revision}).first()
        if row is None:
            raise LookupError('MISSING_EVIDENCE')
        if not row.intact:
            raise ValueError('STORAGE_INTEGRITY_MISMATCH')
        return validated(MODELS[kind], row.payload)

    def assemble_snapshot(self, *, scope, policy, created_at, evidence_refs, verification_refs=()):
        if scope.restaurant_id != self.restaurant_id:
            raise ValueError('TENANT_MISMATCH')
        for ref in evidence_refs:
            if ref.restaurant_id != self.restaurant_id:
                raise ValueError('TENANT_MISMATCH')
        records = tuple(self.get('evidence', ref.evidence_id, ref.revision) for ref in evidence_refs)
        verifications = tuple(self.get('verification', ref.verification_id, ref.revision).reference()
                              for ref in verification_refs)
        # Compare requested references, not just IDs: don't silently replace a forged scope.
        if verifications != tuple(verification_refs):
            raise ValueError('VERIFICATION_BINDING_MISMATCH')
        snapshot = EvidenceSnapshot(schema_version='1.0.0', scope=scope, policy=policy,
            created_at=created_at, records=records, verification_refs=verifications)
        return self.append('snapshot', snapshot)

    def resolve_snapshot(self, reference):
        if reference.restaurant_id != self.restaurant_id:
            raise ValueError('TENANT_MISMATCH')
        payload = self.connection.scalar(text('''SELECT rori_evidence.resolve_snapshot(
            :t,CAST(:i AS uuid),:d)'''), {'t': self.restaurant_id,
            'i': str(reference.snapshot_id), 'd': reference.digest})
        return validated(EvidenceSnapshot, payload)

    def revoke(self, kind, identity, revision, reason=ReasonCode.REVOKED_EVIDENCE):
        if kind not in MODELS or not isinstance(identity, UUID):
            raise ValueError('Invalid object reference')
        self.connection.execute(text('''SELECT rori_evidence.revoke_object(
            :t,:k,CAST(:i AS uuid),:r,:reason)'''), {'t': self.restaurant_id,
            'k': kind, 'i': str(identity), 'r': revision, 'reason': ReasonCode(reason).value})

    def stage_claims(self, claims):
        """One transaction per caller-selected batch; any failed row rolls back all.

        Retrying an identical raw row is idempotent across migration batch IDs.
        Nothing reads or updates operational tables, or promotes claims to evidence.
        """
        return tuple(self.append('legacy_claim', claim) for claim in claims)

    def audit_events(self):
        rows = self.connection.execute(text('''SELECT payload FROM rori_evidence.audit_events
            WHERE restaurant_id=:t ORDER BY sequence'''), {'t': self.restaurant_id})
        events = tuple(validated(AuditEvent, row.payload) for row in rows)
        validate_audit_chain(events)
        return events
