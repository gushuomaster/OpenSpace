"""Thin OpenSpace-to-skill-engineering governance bridge."""

from .adapter import GovernanceAdapter
from .errors import GovernanceBlockedError, GovernanceAdapterError
from .mapping import build_governance_request

__all__ = [
    "GovernanceAdapter",
    "GovernanceAdapterError",
    "GovernanceBlockedError",
    "build_governance_request",
]
