"""Adversarial review of 3B. All identities, sources and quantities are synthetic."""
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.postgres.test_inventory_assessment import (
    assessment_stores, bundle, assess, codes, INGEST, EvidenceKind,
    AssessmentProfile, InventoryManifest, VerificationRecord, VerificationPurpose,
    VersionReference, ReliabilityState, store_manifest, provision_profile,
    AssessmentIntegrityError, AssessmentSecurityError,
)
from app.evidence_contracts.decisions import CheckKind, CheckStatus
from app.evidence_contracts.evidence import EvidenceRecord, SourceReference
from app.evidence_contracts.common import EvidenceRevisionReference
from app.inventory_assessment.contracts import CoverageClaim

pytestmark = pytest.mark.postgres


def rebind(data, *, profile_changes=None, replace_verification=None, remove=()):
    """Append new immutable inputs; never rewrite previously persisted history."""
    profile = data.profile
    if profile_changes:
        profile = AssessmentProfile(**{**profile.model_dump(exclude={'digest'}),
            'identifier': 'review-'+uuid4().hex, **profile_changes})
        with data.admin.begin() as conn:
            provision_profile(conn, data.scope.restaurant_id, profile)
    verifications = list(data.verifications)
    claims = data.manifest.claims
    if replace_verification:
        old, changes = replace_verification
        new = VerificationRecord(**{**old.model_dump(), 'verification_id': uuid4(), **changes})
        with data.verifier.transaction() as tx:
            tx.append('verification', new)
        verifications[verifications.index(old)] = new
        claims = tuple(CoverageClaim(statement=c.statement,
            verification=new.reference() if c.verification == old.reference() else c.verification)
            for c in claims)
    verifications = [v for v in verifications if v.purpose not in remove]
    with data.writer.transaction() as tx:
        snap = tx.assemble_snapshot(scope=data.scope,
            policy=VersionReference(identifier=profile.identifier, version=profile.version),
            created_at=INGEST, evidence_refs=tuple(r.reference for r in data.records),
            verification_refs=tuple(v.reference() for v in verifications))
        manifest = InventoryManifest(schema_version='1.0.0', scope=data.scope,
            snapshot=snap.reference(), claims=claims)
        store_manifest(tx, manifest)
    data.profile, data.snapshot, data.manifest = profile, snap, manifest
    data.verifications = verifications
    return data


def assert_incomplete_without_passes(receipt):
    assert receipt.assessment.state == ReliabilityState.INCOMPLETE
    assert not receipt.assessment.decision_eligible
    assert not [c for c in receipt.assessment.checks if c.status == CheckStatus.PASSED]


def test_missing_closing_count_cannot_claim_complete_verification(bundle):
    receipt = assess(bundle(missing=(EvidenceKind.PHYSICAL_COUNT,)))
    assert receipt.assessment.expected_inventory == 85  # Permitted opening/movement diagnostic.
    assert_incomplete_without_passes(receipt)


@pytest.mark.parametrize('change', [
    {'verification_issuers': ('unapproved-verifier',)},
    {'verification_methods': ('unapproved-method',)},
])
def test_unapproved_verification_never_produces_passed_checks(bundle, change):
    receipt = assess(rebind(bundle(), profile_changes=change))
    assert 'verification_method_or_issuer_unapproved' in codes(receipt)
    assert receipt.assessment.expected_inventory is None
    assert_incomplete_without_passes(receipt)


@pytest.mark.parametrize('purpose', [VerificationPurpose.SOURCE, VerificationPurpose.COUNT])
def test_missing_verification_purpose_has_no_complete_result(bundle, purpose):
    receipt = assess(bundle(missing_purpose=purpose))
    assert receipt.assessment.expected_inventory is None
    assert_incomplete_without_passes(receipt)


def test_missing_snapshot_coverage_proof_is_integrity_failure(bundle):
    data = rebind(bundle(), remove=(VerificationPurpose.COVERAGE,))
    with pytest.raises(AssessmentIntegrityError, match='COVERAGE_VERIFICATION_NOT_BOUND'):
        assess(data)


def test_mixed_valid_and_unapproved_methods_fail_closed(bundle):
    data = bundle()
    source = next(v for v in data.verifications if v.purpose == VerificationPurpose.SOURCE)
    receipt = assess(rebind(data, replace_verification=(source, {'method': 'not-approved'})))
    assert_incomplete_without_passes(receipt)
    assert 'verification_method_or_issuer_unapproved' in codes(receipt)


@pytest.mark.parametrize('state_input', [{}, {'values': {EvidenceKind.PHYSICAL_COUNT: 84}},
    {'values': {EvidenceKind.THEORETICAL_USAGE: 200}}])
@pytest.mark.parametrize('purpose', [VerificationPurpose.SOURCE, VerificationPurpose.COUNT, VerificationPurpose.COVERAGE])
def test_qualified_verification_cannot_certify_quantities(bundle, state_input, purpose):
    from decimal import Decimal
    state_input = {k: {r: Decimal(v) for r, v in values.items()} for k, values in state_input.items()}
    data = bundle(**state_input)
    source = next(v for v in data.verifications if v.purpose == purpose)
    receipt = assess(rebind(data, replace_verification=(source, {'limitations': ('quantity-not-verified',)})))
    assert_incomplete_without_passes(receipt)
    assert receipt.assessment.expected_inventory is None
    assert 'verification_limitations_unresolved' in codes(receipt)


def test_missing_count_retains_negative_expected_diagnostic_without_passes(bundle):
    from decimal import Decimal
    receipt = assess(bundle(missing=(EvidenceKind.PHYSICAL_COUNT,),
        values={EvidenceKind.THEORETICAL_USAGE: Decimal('200')}))
    assert receipt.assessment.state == ReliabilityState.UNRELIABLE
    assert receipt.assessment.expected_inventory == -85
    assert receipt.assessment.actual_inventory is None
    assert not [c for c in receipt.assessment.checks if c.status == CheckStatus.PASSED]
    assert not receipt.assessment.decision_eligible


@pytest.mark.parametrize('defects', [
    {'missing': (EvidenceKind.PHYSICAL_COUNT,), 'missing_purpose': VerificationPurpose.SOURCE},
    {'unknown': (EvidenceKind.RECEIPT,), 'usage_basis': 'unknown'},
    {'duplicate_source': True, 'out_of_period': True},
    {'empty': (EvidenceKind.RECEIPT,), 'unit_basis': 'unknown'},
])
def test_multiple_defects_never_cancel_each_other(bundle, defects):
    receipt = assess(bundle(**defects))
    assert_incomplete_without_passes(receipt)
    assert receipt.assessment.expected_inventory is None
    assert len(codes(receipt)) >= 3


def test_coverage_attestation_cannot_detect_an_omitted_external_transaction(bundle):
    data = bundle()
    original = next(r for r in data.records if r.kind == EvidenceKind.RECEIPT)
    # An independent synthetic source ledger has one more real transaction. Even
    # persisting it outside the snapshot does not turn the attestation into truth.
    extra = EvidenceRecord(**{**original.model_dump(),
        'reference': EvidenceRevisionReference(restaurant_id=data.scope.restaurant_id,
            evidence_id=uuid4(), revision=1),
        'source': SourceReference(system='synthetic-source', record_id='omitted-from-source-export')})
    with data.writer.transaction() as tx:
        tx.append('evidence', extra)
    receipt = assess(data)
    assert extra.reference not in receipt.provenance.evidence
    assert receipt.assessment.expected_inventory == 85
    assert receipt.assessment.state == ReliabilityState.RELIABLE  # Snapshot-relative arithmetic only.
    assert not receipt.assessment.decision_eligible
    # This is an attested closed stream, not independent external completeness.
    coverage = next(c for c in receipt.assessment.checks if c.kind == CheckKind.COVERAGE_COMPLETE)
    assert coverage.verification_refs


def test_role_loss_blocks_reassessment_but_preserves_historical_assessment(bundle):
    data = bundle()
    first = assess(data)
    with data.admin.begin() as conn:
        conn.execute(text("UPDATE rori_evidence.principal_grants SET capabilities='{}' "
                          "WHERE restaurant_id=:t AND actor_id='verifier'"), {'t': data.scope.restaurant_id})
    with pytest.raises(AssessmentSecurityError):
        assess(data)
    with data.writer.transaction() as tx:
        assert tx.get('assessment', first.assessment.assessment_id) == first.assessment
    # Restoring authority is not explicit verification revocation.
    with data.admin.begin() as conn:
        conn.execute(text("UPDATE rori_evidence.principal_grants SET capabilities="
            "ARRAY['verify:source','verify:count','verify:coverage','revoke'] "
            "WHERE restaurant_id=:t AND actor_id='verifier'"), {'t': data.scope.restaurant_id})
    assert assess(data) == first


def test_ordinary_access_loss_does_not_change_actor_wide_authority_lookup(bundle):
    data = bundle()
    # Disabling login is access loss, not an explicit revocation of issued attestations.
    role = data.admin.dialect.identifier_preparer.quote(data.verifier.engine.url.username)
    with data.admin.begin() as conn:
        conn.execute(text(f'ALTER ROLE {role} NOLOGIN'))
    assert assess(data).assessment.decision_eligible is False


def test_explicit_revocation_remains_denied_despite_current_authority(bundle):
    data = bundle()
    first = assess(data)
    verification = data.verifications[0]
    with data.verifier.transaction() as tx:
        tx.revoke('verification', verification.verification_id, verification.revision)
    with pytest.raises(AssessmentIntegrityError):
        assess(data)
    with data.writer.transaction() as tx:
        assert tx.get('assessment', first.assessment.assessment_id) == first.assessment


def test_current_authority_is_actor_wide_not_original_login_bound(bundle):
    data = bundle()
    first = assess(data)
    role = 'replacement_'+uuid4().hex[:16]
    quote = data.admin.dialect.identifier_preparer.quote
    with data.admin.begin() as conn:
        conn.execute(text("UPDATE rori_evidence.principal_grants SET capabilities='{}' "
                          "WHERE restaurant_id=:t AND actor_id='verifier'"), {'t': data.scope.restaurant_id})
        conn.execute(text(f'CREATE ROLE {quote(role)} NOLOGIN'))
        conn.execute(text('INSERT INTO rori_evidence.principal_grants VALUES(:role,:t,:actor,:caps)'),
            {'role': role, 't': data.scope.restaurant_id, 'actor': 'verifier',
             'caps': ['verify:source', 'verify:count', 'verify:coverage']})
    # Intentional probe: issuer_id is the actor identity, not the issuing login.
    assert assess(data) == first
