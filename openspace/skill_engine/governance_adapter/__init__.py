"""Evolution-only OpenSpace-to-skill-engineering governance bridge.

Candidate Governance uses its dedicated candidate lifecycle integration and does
not pass through this adapter.
"""

from .adapter import GovernanceAdapter
from .errors import GovernanceBlockedError, GovernanceAdapterError
from .mapping import build_governance_request

__all__ = [
    "GovernanceAdapter",
    "GovernanceAdapterError",
    "GovernanceBlockedError",
    "build_governance_request",
]
