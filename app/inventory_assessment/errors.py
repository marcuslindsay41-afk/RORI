"""Typed failures: no misleading assessment on security/integrity/service failure."""
class AssessmentError(Exception):
    pass

class AssessmentSecurityError(AssessmentError):
    pass

class AssessmentIntegrityError(AssessmentError):
    pass

class AssessmentUnavailable(AssessmentError):
    pass

class IdempotencyConflict(AssessmentError):
    pass

class UnsupportedPrecision(AssessmentError):
    pass
