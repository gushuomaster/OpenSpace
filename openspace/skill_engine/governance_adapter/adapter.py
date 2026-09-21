"""Thin runtime bridge to the independent skill-engineering engine."""

from __future__ import annotations

import os
from typing import Any

from engine import GovernanceEngine, GovernanceMode, GovernanceResult, ProviderObservation

from .mapping import _artifact_digest, _candidate_dir, build_governance_request
from .persistence_bridge import persist_governance_result


class GovernanceAdapter:
    """Translate lifecycle facts, invoke governance, and persist its result."""

    def __init__(
        self,
        *,
        evidence_store: Any | None = None,
        engine: GovernanceEngine | None = None,
        mode: GovernanceMode | str | None = None,
    ) -> None:
        resolved_mode = mode or os.environ.get("OPENSPACE_GOVERNANCE_MODE", "shadow")
        self.engine = engine or GovernanceEngine(mode=resolved_mode)
        self.evidence_store = evidence_store

    @property
    def mode(self) -> GovernanceMode:
        return self.engine.mode

    @property
    def enforced(self) -> bool:
        return self.mode is GovernanceMode.ENFORCED

    @property
    def enabled(self) -> bool:
        """Whether this adapter should invoke the governance engine."""
        return self.mode is not GovernanceMode.OFF

    def evaluate(
        self,
        *,
        decision: Any,
        admission: Any,
        authoring: Any | None = None,
        validation: Any | None = None,
        behavior_eval: Any | None = None,
        action_packet: Any | None = None,
        job: Any | None = None,
        providers: tuple[ProviderObservation, ...] = (),
    ) -> GovernanceResult | None:
        if not self.enabled:
            return None
        request = build_governance_request(
            decision=decision,
            admission=admission,
            authoring=authoring,
            validation=validation,
            behavior_eval=behavior_eval,
            action_packet=action_packet,
            job=job,
            providers=providers,
        )
        result = self.engine.evaluate(request)
        if self.evidence_store is not None and self.mode is not GovernanceMode.OFF:
            persist_governance_result(
                self.evidence_store,
                result,
                request_id=request.request_id,
                decision_id=request.decision_id,
                admission_id=request.admission_id,
                authoring_id=request.authoring_id,
                validation_id=request.validation_id,
            )
        return result

    def verify_result_integrity(self, result: GovernanceResult, authoring: Any) -> tuple[str, ...]:
        staged = getattr(authoring, "staged_edit", None)
        target_dir = str(getattr(staged, "target_dir", "") or "")
        staging_dir = str(getattr(staged, "staging_dir", "") or "")
        candidate_dir = _candidate_dir(staging_dir or None, target_dir or None)
        current_source = _artifact_digest(target_dir or None)
        current_candidate = _artifact_digest(candidate_dir)
        reasons: list[str] = []
        if not result.source_digest or current_source != result.source_digest:
            reasons.append("source_digest_mismatch")
        if not result.candidate_digest or current_candidate != result.candidate_digest:
            reasons.append("candidate_digest_mismatch")
        return tuple(reasons)
