"""Run isolated rollback and shared EvidenceStore operational drills."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace


SCRIPT_ROOT = Path(__file__).resolve().parents[2]


def _runtime_root() -> Path:
    return Path(os.environ.get("OPENSPACE_RUNTIME_ROOT", str(SCRIPT_ROOT))).resolve()


def _configure_imports() -> None:
    runtime_root = _runtime_root()
    sys.path[:] = [item for item in sys.path if Path(item or ".").resolve() != SCRIPT_ROOT]
    if str(runtime_root) not in sys.path:
        sys.path.insert(0, str(runtime_root))


def _objects(root: Path, name: str, *, invalid: bool = False):
    source = root / name / "source"
    candidate = root / name / "staging" / "proposed" / source.name
    source.mkdir(parents=True, exist_ok=True)
    candidate.mkdir(parents=True, exist_ok=True)
    (source / "SKILL.md").write_text(
        f"---\nname: rollback-{name}\ndescription: source\n---\n",
        encoding="utf-8",
    )
    (candidate / "SKILL.md").write_text(
        f"---\nname: rollback-{name}\ndescription: candidate\n---\n",
        encoding="utf-8",
    )
    prefix = f"rollback-{name}"
    contract = (
        {
            "coverage_status": "COMPLETE",
            "required_capabilities": ["DELIVERABLE_CONTRACT"],
            "applicability": {"deliverable_contract": "required"},
            "deliverable_contract": {"status": "FAIL"},
        }
        if invalid
        else {"coverage_status": "COMPLETE"}
    )
    decision = SimpleNamespace(
        decision_id=f"{prefix}-decision",
        trigger_job_id=f"{prefix}-job",
        proposed_action="FIX",
        target_skill_ids=[f"rollback-{name}"],
        reason_summary=f"Rollback drill {name}",
        reason_tags=["rollback-drill", name],
        proposal_contract=contract,
    )
    admission = SimpleNamespace(
        admission_id=f"{prefix}-admission",
        outcome="direct",
        required_refs_checked=[],
    )
    authoring = SimpleNamespace(
        authoring_id=f"{prefix}-authoring",
        status="staged",
        staged_edit=SimpleNamespace(
            action_type="FIX",
            staging_dir=str(root / name / "staging"),
            target_dir=str(source),
            target_skill_ids=[f"rollback-{name}"],
            parent_skill_ids=[f"rollback-{name}"],
            evidence_refs=[f"evidence:{prefix}"],
        ),
    )
    validation = SimpleNamespace(
        validation_id=f"{prefix}-validation",
        outcome="approve",
        provenance_refs=[f"validation:{prefix}"],
        deterministic_failures=[],
        semantic_warnings=[],
    )
    return decision, admission, authoring, validation, SimpleNamespace(eval_id=f"{prefix}-behavior")


def _evaluate(store, root: Path, name: str, *, mode: str, invalid: bool = False):
    from openspace.skill_engine.governance_adapter import GovernanceAdapter

    decision, admission, authoring, validation, behavior = _objects(root, name, invalid=invalid)
    result = GovernanceAdapter(evidence_store=store, mode=mode).evaluate(
        decision=decision,
        admission=admission,
        authoring=authoring,
        validation=validation,
        behavior_eval=behavior,
    )
    return result


def _dashboard_query(root: Path, governance_id: str) -> dict[str, object]:
    from openspace.entrypoints.dashboard.server import API_PREFIX, create_app
    from openspace.skill_engine.evidence import EvidenceStore
    from openspace.skill_engine.store import SkillStore

    evidence = EvidenceStore(root / "evidence.db")
    skills = SkillStore(root / "skills.db")
    try:
        app = create_app(store=skills, evidence_store=evidence)
        app.testing = True
        response = app.test_client().get(f"{API_PREFIX}/evolution/governance/{governance_id}")
        return {"status_code": response.status_code, "payload": response.get_json()}
    finally:
        evidence.close()
        skills.close()


async def _mcp_query(root: Path, governance_id: str) -> dict[str, object]:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    env = os.environ.copy()
    env.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": str(_runtime_root()),
            "OPENSPACE_CONFIG_JSON": json.dumps({"enabled_backends": []}),
            "OPENSPACE_WORKSPACE": str(root / "workspace"),
            "OPENSPACE_SESSION_STORAGE_DIR": str(root / "sessions"),
            "OPENSPACE_EVOLUTION_EVIDENCE_DB_PATH": str(root / "evidence.db"),
            "OPENSPACE_SKILL_STORE_DB_PATH": str(root / "skills.db"),
            "OPENSPACE_ENABLE_RECORDING": "false",
            "OPENSPACE_GOVERNANCE_MODE": "enforced",
            "OPENSPACE_EVOLUTION_TRIGGERS_ENABLED": "false",
        }
    )
    error_log = root / "rollback-mcp.stderr.log"
    with error_log.open("w", encoding="utf-8") as log:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "openspace.entrypoints.mcp.server", "--transport", "stdio"],
            env=env,
            cwd=_runtime_root(),
            encoding="utf-8",
            encoding_error_handler="replace",
        )
        async with stdio_client(parameters, errlog=log) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream, read_timeout_seconds=60) as session:
                await session.initialize()
                response = await session.call_tool(
                    "inspect_skill_governance",
                    {"governance_id": governance_id},
                    read_timeout_seconds=60,
                )
                text = "".join(
                    str(item.text)
                    for item in list(getattr(response, "content", []) or [])
                    if getattr(item, "text", None) is not None
                )
                return json.loads(text)


def seed(root: Path) -> dict[str, object]:
    _configure_imports()
    from engine import GovernanceEngine
    from openspace.skill_engine.evidence import EvidenceStore

    root.mkdir(parents=True, exist_ok=True)
    store = EvidenceStore(root / "evidence.db")
    try:
        result = _evaluate(store, root, "historical", mode="shadow")
        payload = {
            "governance_id": result.governance_id,
            "engine_revision": result.engine_revision,
            "engine_version": result.engine_version,
            "gate_status": result.gate_status.value,
            "record_count": len(store.list_governance_results()),
            "db_bytes": (root / "evidence.db").stat().st_size,
            "expected_revision": GovernanceEngine(mode="shadow").engine_revision,
        }
        (root / "seed.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    finally:
        store.close()


def verify(root: Path) -> dict[str, object]:
    _configure_imports()
    from engine import GovernanceEngine
    from openspace.skill_engine.evidence import EvidenceStore

    seed_payload = json.loads((root / "seed.json").read_text(encoding="utf-8"))
    store = EvidenceStore(root / "evidence.db")
    try:
        historical = store.load_governance_result(seed_payload["governance_id"])
        valid = _evaluate(store, root, "post-valid", mode="enforced")
        invalid = _evaluate(store, root, "post-invalid", mode="enforced", invalid=True)
        dashboard = _dashboard_query(root, seed_payload["governance_id"])
        mcp = asyncio.run(_mcp_query(root, seed_payload["governance_id"]))
        payload = {
            "runtime_revision": GovernanceEngine(mode="enforced").engine_revision,
            "historical_readable": historical is not None,
            "historical_governance_id": historical.get("governance_id") if historical else None,
            "historical_gate": historical.get("gate_status") if historical else None,
            "dashboard_status": dashboard["status_code"],
            "mcp_governance_id": mcp.get("governance_id"),
            "post_valid_gate": valid.gate_status.value,
            "post_valid_authorized": valid.publish_authorized,
            "post_invalid_gate": invalid.gate_status.value,
            "post_invalid_authorized": invalid.publish_authorized,
            "record_count": len(store.list_governance_results()),
            "source_integrity": valid.integrity_status.value,
            "safe": all(
                (
                    historical is not None,
                    dashboard["status_code"] == 200,
                    mcp.get("governance_id") == seed_payload["governance_id"],
                    valid.gate_status.value == "PASS",
                    valid.publish_authorized,
                    invalid.gate_status.value == "BLOCKED",
                    not invalid.publish_authorized,
                    valid.integrity_status.value == "PASS",
                )
            ),
        }
        (root / "verify.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    finally:
        store.close()


def shared_growth(root: Path, runs: int = 24) -> dict[str, object]:
    _configure_imports()
    from openspace.skill_engine.evidence import EvidenceStore

    root.mkdir(parents=True, exist_ok=True)
    store = EvidenceStore(root / "evidence.db")
    try:
        initial_size = (root / "evidence.db").stat().st_size if (root / "evidence.db").exists() else 0
        initial_count = len(store.list_governance_results())
        samples: list[dict[str, object]] = []
        durations: list[float] = []
        for index in range(runs):
            started = time.perf_counter()
            result = _evaluate(store, root, f"shared-{index:03d}", mode="shadow")
            durations.append(time.perf_counter() - started)
            if index in {0, runs // 2, runs - 1}:
                samples.append(
                    {
                        "run": index + 1,
                        "governance_id": result.governance_id,
                        "gate_status": result.gate_status.value,
                        "readable": store.load_governance_result(result.governance_id) is not None,
                        "db_bytes": (root / "evidence.db").stat().st_size,
                        "record_count": len(store.list_governance_results()),
                    }
                )
        final_size = (root / "evidence.db").stat().st_size
        final_count = len(store.list_governance_results())
        payload = {
            "runs": runs,
            "initial_size": initial_size,
            "final_size": final_size,
            "initial_count": initial_count,
            "final_count": final_count,
            "average_growth_per_run": round((final_size - initial_size) / max(1, runs), 2),
            "largest_growth": max(
                samples[index]["db_bytes"] - samples[index - 1]["db_bytes"]
                for index in range(1, len(samples))
            ) if len(samples) > 1 else final_size - initial_size,
            "query_p50_seconds": round(statistics.median(durations), 6),
            "samples": samples,
            "old_readable": bool(samples and samples[0]["readable"]),
            "latest_readable": bool(samples and samples[-1]["readable"]),
            "record_count_matches_runs": final_count - initial_count == runs,
        }
        (root / "shared-growth.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("seed", "verify", "shared-growth"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--runs", type=int, default=24)
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    if args.phase == "seed":
        payload = seed(root)
    elif args.phase == "verify":
        payload = verify(root)
    else:
        payload = shared_growth(root, runs=args.runs)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
