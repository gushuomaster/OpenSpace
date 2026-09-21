"""Typed failures for the governance boundary."""


class GovernanceAdapterError(RuntimeError):
    """Raised when OpenSpace data cannot be translated safely."""


class GovernanceBlockedError(GovernanceAdapterError):
    """Raised when enforced governance denies publication."""

    def __init__(self, reason_codes: tuple[str, ...] = ()) -> None:
        self.reason_codes = reason_codes
        detail = ", ".join(reason_codes) if reason_codes else "unknown governance reason"
        super().__init__(f"governance publication blocked: {detail}")
