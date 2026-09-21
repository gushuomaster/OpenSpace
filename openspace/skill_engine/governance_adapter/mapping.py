"""Translate OpenSpace lifecycle objects into neutral governance contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from engine import GovernanceEngine, GovernanceRequest, ProviderObservation


def build_governance_request(
    *,
    decision: Any,
    admission: Any,
    authoring: Any | None = None,
    validation: Any | None = None,
    behavior_eval: Any | None = None,
    action_packet: Any | None = None,
    job: Any | None = None,
    providers: tuple[ProviderObservation, ...] = (),
) -> GovernanceRequest:
    staged = _get(authoring, "staged_edit")
    proposal_contract = _mapping(_get(decision, "proposal_contract"))
    action_type = _text(
        _get(decision, "proposed_action")
        or _get(staged, "action_type")
    ).upper()
    target_dir = _text(_get(staged, "target_dir")) or None
    staging_dir = _text(_get(staged, "staging_dir")) or None
    candidate_dir = _candidate_dir(staging_dir, target_dir)
    source_digest = _artifact_digest(target_dir)
    candidate_digest = _artifact_digest(candidate_dir)
    required = _capabilities(proposal_contract.get("required_capabilities"))
    optional = _capabilities(proposal_contract.get("optional_capabilities"))
    applicability = _mapping(proposal_contract.get("applicability"))
    if proposal_contract.get("deliverable_contract") is not None:
        applicability.setdefault("deliverable_contract", "required")
        if "DELIVERABLE_CONTRACT" not in required:
            required.append("DELIVERABLE_CONTRACT")
    evidence_refs = _evidence_refs(
        decision,
        admission,
        authoring,
        validation,
        behavior_eval,
        action_packet,
    )
    if not providers:
        providers = _provider_observations(proposal_contract.get("providers"))
    coverage = _text(
        proposal_contract.get("coverage_status")
        or proposal_contract.get("coverage")
        or ("COMPLETE" if not required else "UNKNOWN")
    ).upper()
    return GovernanceRequest(
        request_id=_text(_get(decision, "decision_id")) or _text(_get(job, "job_id")) or "unknown",
        trigger_job_id=_text(_get(decision, "trigger_job_id")) or _text(_get(action_packet, "trigger_job_id")),
        decision_id=_text(_get(decision, "decision_id")),
        admission_id=_text(_get(admission, "admission_id")),
        authoring_id=_text(_get(authoring, "authoring_id")),
        validation_id=_text(_get(validation, "validation_id")),
        action_type=action_type,
        target_skill_ids=tuple(_strings(_get(decision, "target_skill_ids"))),
        parent_revision_ids=tuple(_strings(_get(staged, "parent_skill_ids"))),
        intent={
            "reason_summary": _text(_get(decision, "reason_summary")),
            "reason_tags": _strings(_get(decision, "reason_tags")),
            "proposal_contract": proposal_contract,
        },
        applicability={str(key): str(value) for key, value in applicability.items()},
        required_capabilities=tuple(required),
        optional_capabilities=tuple(optional),
        source_digest=source_digest,
        candidate_digest=candidate_digest,
        source_path=target_dir,
        candidate_path=candidate_dir,
        evidence_refs=tuple(evidence_refs),
        staging_descriptor={
            "staging_dir": staging_dir or "",
            "target_dir": target_dir or "",
            "candidate_dir": candidate_dir or "",
            "behavior_eval_id": _text(_get(behavior_eval, "eval_id")),
        },
        validation_status=_validation_status(validation),
        coverage_status=coverage,
        integrity_status="PASS" if source_digest and candidate_digest else "UNKNOWN",
        validation_reasons=tuple(
            _strings(_get(validation, "deterministic_failures"))
            + _strings(_get(validation, "semantic_warnings"))
        ),
        providers=providers,
        deliverable_contract=_mapping(proposal_contract.get("deliverable_contract")) or None,
    )


def _get(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    return []


def _capabilities(value: Any) -> list[str]:
    return list(dict.fromkeys(item.upper() for item in _strings(value)))


def _provider_observations(value: Any) -> tuple[ProviderObservation, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    observations: list[ProviderObservation] = []
    for item in value:
        data = _mapping(item)
        if not data:
            continue
        observations.append(
            ProviderObservation(
                provider_id=_text(data.get("provider_id")),
                capability=_text(data.get("capability")).upper(),
                available=bool(data.get("available", data.get("provider_available", False))),
                selected=bool(data.get("selected", False)),
                executed=bool(data.get("executed", data.get("provider_execution") == "EXECUTED")),
                status=_text(data.get("status", data.get("provider_status", "UNKNOWN"))).upper(),
                evidence_valid=bool(data.get("evidence_valid", False)),
                evidence_refs=tuple(_strings(data.get("evidence_refs", data.get("evidence")))),
                reason_codes=tuple(_strings(data.get("reason_codes"))),
            )
        )
    return tuple(item for item in observations if item.provider_id and item.capability)


def _validation_status(validation: Any) -> str:
    outcome = _text(_get(validation, "outcome")).lower()
    if outcome in {"approve", "pass", "passed"}:
        return "PASS"
    if outcome in {"reject", "fail", "failed"}:
        return "FAIL"
    return "UNKNOWN"


def _candidate_dir(staging_dir: str | None, target_dir: str | None) -> str | None:
    if not staging_dir or not target_dir:
        return None
    target = Path(target_dir)
    candidate = Path(staging_dir) / "proposed" / target.name
    return str(candidate)


def _artifact_digest(path: str | None) -> str | None:
    if not path or not Path(path).is_dir():
        return None
    return GovernanceEngine.artifact_digest(path)


def _evidence_refs(*values: Any) -> list[str]:
    refs: list[str] = []
    for value in values:
        for name in (
            "evidence_refs",
            "provenance_refs",
            "required_refs_checked",
        ):
            refs.extend(_strings(_get(value, name)))
    return list(dict.fromkeys(ref for ref in refs if ref))
