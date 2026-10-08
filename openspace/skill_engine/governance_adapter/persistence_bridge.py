"""Persist governance output through OpenSpace's existing EvidenceStore."""

from __future__ import annotations

from typing import Any


def persist_governance_result(
    evidence_store: Any,
    result: Any,
    *,
    request_id: str,
    decision_id: str = "",
    admission_id: str = "",
    authoring_id: str = "",
    validation_id: str = "",
) -> None:
    persist = getattr(evidence_store, "persist_governance_result", None)
    if not callable(persist):
        raise RuntimeError("EvidenceStore does not support governance persistence")
    persist(
        result,
        request_id=request_id,
        decision_id=decision_id,
        admission_id=admission_id,
        authoring_id=authoring_id,
        validation_id=validation_id,
    )
