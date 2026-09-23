"""Verify Governance consistency across Gate, storage, Dashboard, and MCP."""

from __future__ import annotations

import argparse
import asyncio
from enum import Enum
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid


ROOT = Path(__file__).resolve().parents[2]
for import_root in (str(ROOT),):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)


CASES = {
    "pass": ({"coverage_status": "COMPLETE"}, "approve", "PASS"),
    "required_fail": (
        {
            "coverage_status": "COMPLETE",
            "required_capabilities": ["DELIVERABLE_CONTRACT"],
            "applicability": {"deliverable_contract": "required"},
            "deliverable_contract": {"status": "FAIL"},
            "providers": [
                {
                    "provider_id": "provider.required",
                    "capability": "DELIVERABLE_CONTRACT",
                    "available": True,
                    "selected": True,
                    "executed": True,
                    "status": "PASS",
                    "evidence_valid": True,
                    "evidence_refs": ["provider:required-fail"],
                }
            ],
        },
        "approve",
        "BLOCKED",
    ),
    "shadow_fail": ({"coverage_status": "COMPLETE"}, "reject", "BLOCKED"),
    "provider_error": (
        {
            "coverage_status": "INCOMPLETE",
            "required_capabilities": ["DELIVERABLE_CONTRACT"],
            "applicability": {"deliverable_contract": "required"},
            "providers": [
                {
                    "provider_id": "provider.required",
                    "capability": "DELIVERABLE_CONTRACT",
                    "available": True,
                    "selected": True,
                    "executed": False,
                    "status": "ERROR",
                    "evidence_valid": False,
                    "evidence_refs": ["provider:error"],
                    "reason_codes": ["provider_error"],
                }
            ],
        },
        "approve",
        "INCOMPLETE",
    ),
}


def _jsonable(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"unsupported JSON value: {type(value)!r}")


def _seed_governance(root: Path) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
    from openspace.skill_engine.evidence import EvidenceStore
    from openspace.skill_engine.governance_adapter import GovernanceAdapter

    store = EvidenceStore(root / "evidence.db")
    gate_payloads: dict[str, dict[str, object]] = {}
    governance_ids: dict[str, str] = {}
    try:
        adapter = GovernanceAdapter(evidence_store=store, mode="shadow")
        for case_name, (proposal_contract, validation_outcome, expected_gate) in CASES.items():
            case_root = root / case_name
            source = case_root / "source"
            candidate = case_root / "staging" / "proposed" / source.name
            source.mkdir(parents=True, exist_ok=True)
            candidate.mkdir(parents=True, exist_ok=True)
            (source / "SKILL.md").write_text(
                f"---\nname: b4-{case_name}\ndescription: B4 source.\n---\n",
                encoding="utf-8",
            )
            (candidate / "SKILL.md").write_text(
                f"---\nname: b4-{case_name}\ndescription: B4 candidate.\n---\n",
                encoding="utf-8",
            )
            prefix = f"b4-{case_name}"
            decision = SimpleNamespace(
                decision_id=f"{prefix}-decision",
                trigger_job_id=f"{prefix}-job",
                proposed_action="FIX",
                target_skill_ids=[f"{prefix}-source"],
                reason_summary=f"Verify {case_name} cross-surface consistency",
                reason_tags=["b4", case_name],
                proposal_contract=proposal_contract,
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
                    staging_dir=str(case_root / "staging"),
                    target_dir=str(source),
                    parent_skill_ids=[f"{prefix}-source"],
                    evidence_refs=[f"evidence:{prefix}"],
                ),
            )
            validation = SimpleNamespace(
                validation_id=f"{prefix}-validation",
                outcome=validation_outcome,
                provenance_refs=[f"validation:{prefix}"],
                deterministic_failures=(
                    [f"{prefix}-validation-failed"]
                    if validation_outcome == "reject"
                    else []
                ),
                semantic_warnings=[],
            )
            result = adapter.evaluate(
                decision=decision,
                admission=admission,
                authoring=authoring,
                validation=validation,
                behavior_eval=SimpleNamespace(eval_id=f"{prefix}-behavior"),
            )
            if result is None or result.gate_status.value != expected_gate:
                raise RuntimeError(f"B4 {case_name} gate mismatch: {result}")
            governance_ids[case_name] = result.governance_id
            gate_payloads[case_name] = json.loads(
                json.dumps(result.to_dict(), default=_jsonable)
            )
        return gate_payloads, governance_ids
    finally:
        store.close()


def _database_snapshot(root: Path, governance_ids: dict[str, str]) -> dict[str, dict[str, object]]:
    from openspace.skill_engine.evidence import EvidenceStore

    store = EvidenceStore(root / "evidence.db")
    try:
        return {
            case_name: store.load_governance_result(governance_id)
            for case_name, governance_id in governance_ids.items()
        }
    finally:
        store.close()


def _dashboard_snapshot(
    root: Path,
    governance_ids: dict[str, str],
) -> tuple[dict[str, dict[str, object]], list[str]]:
    from openspace.entrypoints.dashboard.server import API_PREFIX, create_app
    from openspace.skill_engine.evidence import EvidenceStore
    from openspace.skill_engine.store import SkillStore

    evidence_store = EvidenceStore(root / "evidence.db")
    skill_store = SkillStore(root / "skills.db")
    try:
        app = create_app(store=skill_store, evidence_store=evidence_store)
        app.testing = True
        client = app.test_client()
        details: dict[str, dict[str, object]] = {}
        for case_name, governance_id in governance_ids.items():
            response = client.get(f"{API_PREFIX}/evolution/governance/{governance_id}")
            if response.status_code != 200:
                raise RuntimeError(
                    f"Dashboard detail failed for {case_name}: {response.status_code}"
                )
            details[case_name] = response.get_json()
        listed = client.get(f"{API_PREFIX}/evolution/governance?limit=20")
        if listed.status_code != 200:
            raise RuntimeError(f"Dashboard list failed: {listed.status_code}")
        listed_ids = [item["governance_id"] for item in listed.get_json()["items"]]
        return details, listed_ids
    finally:
        evidence_store.close()
        skill_store.close()


def _server_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": os.pathsep.join(
                (str(ROOT), env.get("PYTHONPATH", ""))
            ).rstrip(os.pathsep),
            "OPENSPACE_CONFIG_JSON": json.dumps({"enabled_backends": []}),
            "OPENSPACE_WORKSPACE": str(root / "workspace"),
            "OPENSPACE_SESSION_STORAGE_DIR": str(root / "sessions"),
            "OPENSPACE_EVOLUTION_STORAGE_ROOT": str(root / "evolution"),
            "OPENSPACE_EVOLUTION_EVIDENCE_DB_PATH": str(root / "evidence.db"),
            "OPENSPACE_SKILL_STORE_DB_PATH": str(root / "skills.db"),
            "OPENSPACE_ENABLE_RECORDING": "false",
            "OPENSPACE_GOVERNANCE_MODE": "shadow",
            "OPENSPACE_EVOLUTION_TRIGGERS_ENABLED": "false",
        }
    )
    return env


def _tool_json(result: object) -> dict[str, object]:
    if bool(getattr(result, "isError", False)):
        raise RuntimeError(f"MCP tool returned isError: {result}")
    texts = [
        str(getattr(item, "text"))
        for item in list(getattr(result, "content", []) or [])
        if getattr(item, "text", None) is not None
    ]
    if not texts:
        raise RuntimeError(f"MCP tool returned no text content: {result}")
    payload = json.loads("".join(texts))
    if not isinstance(payload, dict):
        raise RuntimeError(f"MCP tool payload is not an object: {payload}")
    return payload


async def _mcp_session(
    root: Path,
    governance_ids: dict[str, str],
    index: int,
) -> dict[str, object]:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    error_log_path = root / f"mcp-session-{index}.stderr.log"
    with error_log_path.open("w", encoding="utf-8") as error_log:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "openspace.entrypoints.mcp.server", "--transport", "stdio"],
            env=_server_env(root),
            cwd=ROOT,
            encoding="utf-8",
            encoding_error_handler="replace",
        )
        async with stdio_client(parameters, errlog=error_log) as (read_stream, write_stream):
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=60,
            ) as session:
                initialized = await session.initialize()
                tools = await session.list_tools()
                tool_names = sorted(tool.name for tool in tools.tools)
                if "inspect_skill_governance" not in tool_names:
                    raise RuntimeError("inspect_skill_governance missing from MCP tool list")
                details = {
                    case_name: _tool_json(
                        await session.call_tool(
                            "inspect_skill_governance",
                            {"governance_id": governance_id},
                            read_timeout_seconds=60,
                        )
                    )
                    for case_name, governance_id in governance_ids.items()
                }
                listed = _tool_json(
                    await session.call_tool(
                        "inspect_skill_governance",
                        {"limit": 20},
                        read_timeout_seconds=60,
                    )
                )
                server_info = getattr(initialized, "server_info", None) or getattr(
                    initialized, "serverInfo", None
                )
                if server_info is None:
                    raise RuntimeError(f"MCP initialize returned no server info: {initialized}")
                return {
                    "server_name": server_info.name,
                    "server_version": server_info.version,
                    "tool_present": True,
                    "details": details,
                    "listed_ids": [item["governance_id"] for item in listed.get("items", [])],
                }


def _comparable(payload: dict[str, object]) -> dict[str, object]:
    return {
        key: payload.get(key)
        for key in (
            "governance_id",
            "gate_status",
            "publish_authorized",
            "validation_status",
            "coverage_status",
            "integrity_status",
            "source_digest",
            "candidate_digest",
            "engine_name",
            "engine_version",
            "engine_revision",
            "reason_codes",
            "evidence_refs",
        )
    }


async def _run(root: Path) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    (root / "workspace").mkdir(parents=True, exist_ok=True)
    gates, governance_ids = _seed_governance(root)
    database = _database_snapshot(root, governance_ids)
    dashboard, dashboard_listed_ids = _dashboard_snapshot(root, governance_ids)
    first = await _mcp_session(root, governance_ids, 1)
    second = await _mcp_session(root, governance_ids, 2)

    cases: dict[str, object] = {}
    for case_name, governance_id in governance_ids.items():
        expected = _comparable(database[case_name])
        surfaces = {
            "evolution_gate": _comparable(gates[case_name]),
            "database": expected,
            "dashboard": _comparable(dashboard[case_name]),
            "first_mcp_session": _comparable(first["details"][case_name]),
            "second_mcp_session": _comparable(second["details"][case_name]),
        }
        if any(payload != expected for payload in surfaces.values()):
            raise RuntimeError(f"B4 {case_name} surface mismatch: {surfaces}")
        if not all(
            governance_id in listed_ids
            for listed_ids in (
                dashboard_listed_ids,
                first["listed_ids"],
                second["listed_ids"],
            )
        ):
            raise RuntimeError(f"B4 {case_name} missing from a list surface")
        cases[case_name] = surfaces

    return {
        "governance_ids": governance_ids,
        "cases": cases,
        "dashboard_listed_ids": dashboard_listed_ids,
        "first_session": {
            "server_name": first["server_name"],
            "server_version": first["server_version"],
            "tool_present": first["tool_present"],
            "listed_ids": first["listed_ids"],
        },
        "second_session": {
            "server_name": second["server_name"],
            "server_version": second["server_version"],
            "tool_present": second["tool_present"],
            "listed_ids": second["listed_ids"],
        },
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    args = parser.parse_args()
    root = (
        Path(args.root).expanduser().resolve()
        if args.root
        else ROOT.parent / f"openspace-b4-mcp-{uuid.uuid4().hex[:10]}"
    )
    payload = {"root": str(root), **asyncio.run(_run(root))}
    output = root / "b4-mcp-results.json"
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"RESULT_PATH={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
