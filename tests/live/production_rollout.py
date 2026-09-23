"""Collect deterministic production-rollout evidence without changing runtime defaults."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_ENGINE_REVISION = "0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _objects(root: Path, case: str, *, action_type: str = "FIX", validation: str = "approve", contract: dict[str, object] | None = None, identity: str | None = None):
    source = root / "source"
    candidate = root / "staging" / "proposed" / source.name
    source.mkdir(parents=True, exist_ok=True)
    candidate.mkdir(parents=True, exist_ok=True)
    (source / "SKILL.md").write_text(
        f"---\nname: rollout-{case}\ndescription: source {case}\n---\n",
        encoding="utf-8",
    )
    (candidate / "SKILL.md").write_text(
        f"---\nname: rollout-{case}\ndescription: candidate {case}\n---\n",
        encoding="utf-8",
    )
    prefix = identity or f"rollout-{case}-{uuid4().hex[:8]}"
    decision = SimpleNamespace(
        decision_id=f"{prefix}-decision",
        trigger_job_id=f"{prefix}-job",
        proposed_action=action_type,
        target_skill_ids=[f"rollout-{case}"],
        reason_summary=f"Production rollout case {case}",
        reason_tags=["production-rollout", case],
        proposal_contract=contract or {"coverage_status": "COMPLETE"},
    )
    admission = SimpleNamespace(
        admission_id=f"{prefix}-admission",
        outcome="direct",
        required_refs_checked=[],
    )
    staged = SimpleNamespace(
        action_type=action_type,
        staging_dir=str(root / "staging"),
        target_dir=str(source),
        target_skill_ids=[f"rollout-{case}"],
        parent_skill_ids=[f"rollout-{case}"],
        evidence_refs=[f"evidence:{prefix}"],
    )
    authoring = SimpleNamespace(
        authoring_id=f"{prefix}-authoring",
        status="staged",
        staged_edit=staged,
    )
    validation_obj = SimpleNamespace(
        validation_id=f"{prefix}-validation",
        outcome=validation,
        provenance_refs=[f"validation:{prefix}"],
        deterministic_failures=[] if validation == "approve" else [f"failure:{case}"],
        semantic_warnings=[],
    )
    behavior = SimpleNamespace(eval_id=f"{prefix}-behavior")
    return decision, admission, authoring, validation_obj, behavior


def _percentiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        return {"p50": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "p50": round(statistics.median(ordered), 6),
        "p95": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 6),
        "max": round(max(ordered), 6),
    }


def _evaluate(root: Path, mode: str, case: str, *, contract: dict[str, object] | None = None, validation: str = "approve", action_type: str = "FIX", providers=(), identity: str | None = None) -> dict[str, object]:
    from openspace.skill_engine.evidence import EvidenceStore
    from openspace.skill_engine.governance_adapter import GovernanceAdapter

    store = EvidenceStore(root / "evidence.db")
    try:
        decision, admission, authoring, validation_obj, behavior = _objects(
            root,
            case,
            action_type=action_type,
            validation=validation,
            contract=contract,
            identity=identity,
        )
        adapter = GovernanceAdapter(evidence_store=store, mode=mode)
        started = time.perf_counter()
        result = adapter.evaluate(
            decision=decision,
            admission=admission,
            authoring=authoring,
            validation=validation_obj,
            behavior_eval=behavior,
            providers=providers,
        )
        elapsed = time.perf_counter() - started
        persisted = store.list_governance_results(limit=20)
        payload = {
            "mode": mode,
            "case": case,
            "duration_seconds": round(elapsed, 6),
            "invocation_count": 0 if mode == "off" else 1,
            "provider_invocation_count": 0,
            "persisted_count": len(persisted),
            "db_bytes": (root / "evidence.db").stat().st_size if (root / "evidence.db").exists() else 0,
            "engine_revision": getattr(adapter.engine, "engine_revision", ""),
            "governance_id": getattr(result, "governance_id", None),
            "gate_status": getattr(getattr(result, "gate_status", None), "value", None),
            "publish_authorized": getattr(result, "publish_authorized", None),
            "reason_codes": list(getattr(result, "reason_codes", ()) or ()),
        }
        if mode == "off" and (result is not None or persisted):
            raise RuntimeError(f"off mode invoked or persisted governance: {payload}")
        if mode != "off" and result is None:
            raise RuntimeError(f"{mode} mode returned no GovernanceResult")
        return payload
    finally:
        store.close()


def _provider_observation(status: str):
    from engine import ProviderObservation

    return (
        ProviderObservation(
            provider_id="rollout.provider",
            capability="DELIVERABLE_CONTRACT",
            available=status != "UNAVAILABLE",
            selected=status != "UNAVAILABLE",
            executed=status == "TIMEOUT",
            status=status,
            evidence_valid=False,
            evidence_refs=(f"provider:{status.lower()}",),
            reason_codes=(f"provider_{status.lower()}",),
        ),
    )


def _run(root: Path) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    required_fail = {
        "coverage_status": "COMPLETE",
        "required_capabilities": ["DELIVERABLE_CONTRACT"],
        "applicability": {"deliverable_contract": "required"},
        "deliverable_contract": {"status": "FAIL"},
    }
    required_incomplete = {
        "coverage_status": "INCOMPLETE",
        "required_capabilities": ["DELIVERABLE_CONTRACT"],
        "applicability": {"deliverable_contract": "required"},
    }
    results: dict[str, object] = {"engine_revision": "", "modes": {}, "concurrency": {}, "idempotency": {}, "evidence_growth": {}, "performance": {}}

    for mode in ("off", "shadow", "enforced"):
        cases = {
            "valid": _evaluate(root / mode / "valid", mode, "valid"),
            "invalid": _evaluate(root / mode / "invalid", mode, "invalid", contract=required_fail),
            "provider_error": _evaluate(root / mode / "provider_error", mode, "provider_error", contract=required_incomplete, providers=_provider_observation("ERROR")),
            "provider_unavailable": _evaluate(root / mode / "provider_unavailable", mode, "provider_unavailable", contract=required_incomplete, providers=_provider_observation("UNAVAILABLE")),
            "provider_timeout": _evaluate(root / mode / "provider_timeout", mode, "provider_timeout", contract=required_incomplete, providers=_provider_observation("TIMEOUT")),
            "audit_only": _evaluate(root / mode / "audit_only", mode, "audit_only", action_type="AUDIT_ONLY"),
        }
        results["modes"][mode] = cases
        results["engine_revision"] = cases["valid"]["engine_revision"]

    for count in (2, 4):
        with ThreadPoolExecutor(max_workers=count) as pool:
            items = list(
                pool.map(
                    lambda index: _evaluate(
                        root / "concurrent" / str(count) / str(index),
                        "shadow",
                        f"concurrent-{count}-{index}",
                    ),
                    range(count),
                )
            )
        ids = [item["governance_id"] for item in items]
        results["concurrency"][str(count)] = {
            "runs": len(items),
            "unique_governance_ids": len(set(ids)),
            "persisted_counts": [item["persisted_count"] for item in items],
            "isolated": len(set(ids)) == count and all(item["persisted_count"] == 1 for item in items),
            "durations": [item["duration_seconds"] for item in items],
        }

    same_root = root / "idempotency"
    first = _evaluate(same_root, "shadow", "same-request", identity="same-request")
    second = _evaluate(same_root, "shadow", "same-request", identity="same-request")
    results["idempotency"] = {
        "first_governance_id": first["governance_id"],
        "second_governance_id": second["governance_id"],
        "same_governance_id": first["governance_id"] == second["governance_id"],
        "persisted_count_after_retry": second["persisted_count"],
        "safe": first["governance_id"] == second["governance_id"] and second["persisted_count"] == 1,
    }

    growth_root = root / "evidence-growth"
    growth_runs = [_evaluate(growth_root / str(index), "shadow", f"growth-{index}") for index in range(10)]
    db_path = growth_root / "9" / "evidence.db"
    results["evidence_growth"] = {
        "run_count": len(growth_runs),
        "record_counts": [item["persisted_count"] for item in growth_runs],
        "largest_db_bytes": max(item["db_bytes"] for item in growth_runs),
        "average_db_bytes": round(statistics.mean(item["db_bytes"] for item in growth_runs), 2),
        "bounded": all(item["persisted_count"] == 1 for item in growth_runs),
        "shared_store_note": "Per-run stores are isolated; no repository snapshot is persisted by this harness.",
        "last_db_exists": db_path.exists(),
    }

    for mode in ("off", "shadow", "enforced"):
        durations: list[float] = []
        for index in range(20):
            item = _evaluate(root / "performance" / mode / str(index), mode, f"perf-{index}")
            durations.append(float(item["duration_seconds"]))
        results["performance"][mode] = {"runs": len(durations), **_percentiles(durations)}

    if results["engine_revision"] != EXPECTED_ENGINE_REVISION:
        raise RuntimeError(
            f"unexpected engine revision: {results['engine_revision']} != {EXPECTED_ENGINE_REVISION}"
        )
    results["cleanup"] = {
        "temporary_roots": str(root),
        "provider_processes_spawned": 0,
        "orphan_processes_observed": 0,
        "status": "NOT_APPLICABLE_FOR_SYNTHETIC_HARNESS",
    }
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    payload = _run(Path(args.root).expanduser().resolve())
    output = Path(args.root).expanduser().resolve() / "production-rollout-results.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"RESULT_PATH={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
