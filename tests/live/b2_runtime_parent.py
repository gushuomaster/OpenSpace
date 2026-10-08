"""Child process entrypoints for B2 live crash/restart probes."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace


OPENSPACE_ROOT = Path(__file__).resolve().parents[2]
SKILL_ENGINEERING_ROOT = Path(os.environ["SKILL_ENGINEERING_REPO_ROOT"]).resolve()
DOCUMENT_SKILL = Path(os.environ["GOVERNANCE_TARGET_SKILL_PATH"]).resolve()

for import_root in (str(OPENSPACE_ROOT),):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _runtime_config(root: Path, *, governance_mode: str):
    from openspace.application import OpenSpaceConfig

    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    grounding = root / "grounding.json"
    grounding.write_text(
        json.dumps({"enabled_backends": []}),
        encoding="utf-8",
    )
    return OpenSpaceConfig(
        grounding_config_path=str(grounding),
        workspace_dir=str(workspace),
        session_storage_dir=str(root / "sessions"),
        evidence_db_path=str(root / "evidence.db"),
        evolution_storage_root=str(root / "evolution"),
        skill_store_db_path=str(root / "skills.db"),
        governance_mode=governance_mode,
        enable_recording=False,
        lsp_sync_start=False,
        scheduler_sync_start=False,
        scheduler_execute_sync_start=False,
        skill_store_sync_start=False,
        execution_analysis_sync_start=False,
        evolution_triggers_enabled=False,
        quality_signal_detector_enabled=False,
        quality_signal_trigger_enabled=False,
        quality_signal_reconciliation_enabled=False,
    )


async def _initialize_runtime(root: Path, *, governance_mode: str):
    from openspace.application import OpenSpace

    app = OpenSpace(_runtime_config(root, governance_mode=governance_mode))
    await app.initialize()
    if app.runtime.state.evidence_store is None:
        raise RuntimeError("OpenSpace runtime did not initialize EvidenceStore")
    return app


def _governance_objects(root: Path, *, request_id: str):
    source = root / "governance-source"
    candidate = root / "governance-staging" / "proposed" / source.name
    source.mkdir(parents=True, exist_ok=True)
    candidate.mkdir(parents=True, exist_ok=True)
    (source / "SKILL.md").write_text(
        "---\nname: governance-source\ndescription: Active source.\n---\n",
        encoding="utf-8",
    )
    (candidate / "SKILL.md").write_text(
        "---\nname: governance-source\ndescription: Candidate source.\n---\n",
        encoding="utf-8",
    )
    decision = SimpleNamespace(
        decision_id=request_id,
        trigger_job_id=f"job-{request_id}",
        proposed_action="FIX",
        target_skill_ids=["governance-source"],
        reason_summary="B2 crash-boundary verification",
        reason_tags=["b2"],
        proposal_contract={"coverage_status": "COMPLETE"},
    )
    admission = SimpleNamespace(
        admission_id=f"adm-{request_id}",
        outcome="direct",
        required_refs_checked=[],
    )
    staged = SimpleNamespace(
        action_type="FIX",
        staging_dir=str(root / "governance-staging"),
        target_dir=str(source),
        target_skill_ids=["governance-source"],
        parent_skill_ids=["governance-source"],
        evidence_refs=[f"evidence:{request_id}"],
    )
    authoring = SimpleNamespace(
        authoring_id=f"auth-{request_id}",
        status="staged",
        staged_edit=staged,
    )
    validation = SimpleNamespace(
        validation_id=f"val-{request_id}",
        outcome="approve",
        provenance_refs=[f"validation:{request_id}"],
        deterministic_failures=[],
        semantic_warnings=[],
    )
    behavior = SimpleNamespace(eval_id=f"eval-{request_id}")
    return decision, admission, authoring, validation, behavior


async def _kr02(root: Path, marker: Path) -> None:
    from engine import GovernanceEngine, ProviderObservation
    from engine.deliverable_contract import validate_deliverable_contract
    from engine.host_adapters import build_default_provider_adapters
    from engine.models import ArtifactManifest, Intent
    from engine.providers import ProviderGateway
    from openspace.skill_engine.governance_adapter.mapping import (
        build_governance_request,
    )

    app = await _initialize_runtime(root, governance_mode="enforced")
    try:
        adapters = build_default_provider_adapters(
            SKILL_ENGINEERING_ROOT,
            timeout_seconds=300,
        )
        adapter = next(
            item
            for item in adapters
            if item.descriptor.capability == "DELIVERABLE_CONTRACT"
        )
        _write_json(
            marker,
            {"phase": "provider_invoking", "pid": os.getpid()},
        )
        provider_target_digest = GovernanceEngine.artifact_digest(DOCUMENT_SKILL)
        result = ProviderGateway([adapter]).invoke(
            "DELIVERABLE_CONTRACT",
            {
                "target_path": str(DOCUMENT_SKILL),
                "mode": "AUDIT",
                "inspection_id": "b2-kr02",
                "inspection_nonce": "b2-kr02-nonce",
                "target_digest": provider_target_digest,
                "artifact_role": "BASELINE",
                "deliverable_contract_applicability": "REQUIRED",
            },
            formal_run=True,
        )
        decision, admission, authoring, validation, behavior = _governance_objects(
            root,
            request_id="b2-kr02",
        )
        if result.deliverable_contract is None:
            raise RuntimeError("KR-02 Provider returned no deliverable contract")
        manifest = ArtifactManifest(
            intent=Intent.AUDIT,
            artifact_root=str(DOCUMENT_SKILL),
            skill_name=DOCUMENT_SKILL.name,
            source_revision=None,
            source_digest=None,
            files=tuple(
                child.relative_to(DOCUMENT_SKILL).as_posix()
                for child in DOCUMENT_SKILL.rglob("*")
                if child.is_file()
            ),
            executable_assets=(),
            required_references=(),
            test_inventory=(),
            content_digest=provider_target_digest,
        )
        contract_check = validate_deliverable_contract(
            result.deliverable_contract,
            manifest,
            inspection_id="b2-kr02",
            inspection_nonce="b2-kr02-nonce",
            provider_id=result.provider_id,
            provider_execution=result.provider_execution,
            required=True,
        )
        _write_json(
            root / "kr02-provider-result.json",
            {
                "provider_id": result.provider_id,
                "provider_execution": result.provider_execution.value,
                "provider_status": result.provider_status.value,
                "provider_evidence_valid": result.evidence_valid,
                "provider_evidence": list(result.evidence),
                "deliverable_contract": asdict(result.deliverable_contract),
                "contract_check_status": contract_check.status.value,
                "contract_check_evidence": list(contract_check.evidence),
            },
        )
        decision.proposal_contract = {
            "coverage_status": "COMPLETE",
            "required_capabilities": ["DELIVERABLE_CONTRACT"],
            "applicability": {"deliverable_contract": "required"},
            "deliverable_contract": {
                "status": contract_check.status.value,
                "provider_contract": asdict(result.deliverable_contract),
                "evidence": list(contract_check.evidence),
            },
        }
        observation = ProviderObservation(
            provider_id=result.provider_id,
            capability=result.capability,
            available=result.provider_available,
            selected=True,
            executed=result.provider_execution.value == "EXECUTED",
            status="PASS",
            evidence_valid=result.evidence_valid,
            evidence_refs=tuple(result.evidence),
        )
        governance_adapter = app.runtime.state.evolution_engine.governance_adapter
        request = build_governance_request(
            decision=decision,
            admission=admission,
            authoring=authoring,
            validation=validation,
            behavior_eval=behavior,
            providers=(observation,),
        )
        governance_result = governance_adapter.engine.evaluate(request)
        if governance_result.gate_status.value != "PASS":
            raise RuntimeError(
                "KR-02 governance did not reach PASS: "
                f"contract_status={contract_check.status.value}; "
                f"contract_evidence={list(contract_check.evidence)}; "
                f"governance={governance_result.to_dict()}"
            )
        _write_json(
            root / "kr02-state.json",
            {
                "governance_id": governance_result.governance_id,
                "source_digest": governance_result.source_digest,
                "candidate_digest": governance_result.candidate_digest,
                "provider_id": result.provider_id,
                "provider_execution": result.provider_execution.value,
                "deliverable_contract_status": contract_check.status.value,
                "gate_status": governance_result.gate_status.value,
                "publish_authorized": governance_result.publish_authorized,
            },
        )
        _write_json(
            marker,
            {
                "phase": "governance_ready_before_persistence",
                "pid": os.getpid(),
                "governance_id": governance_result.governance_id,
            },
        )
        while True:
            await asyncio.sleep(1)
    finally:
        await app.cleanup()


async def _kr03(root: Path, marker: Path) -> None:
    app = await _initialize_runtime(root, governance_mode="enforced")
    try:
        decision, admission, authoring, validation, behavior = _governance_objects(
            root,
            request_id="b2-kr03",
        )
        governance_adapter = app.runtime.state.evolution_engine.governance_adapter
        result = governance_adapter.evaluate(
            decision=decision,
            admission=admission,
            authoring=authoring,
            validation=validation,
            behavior_eval=behavior,
        )
        if result is None or result.gate_status.value != "PASS":
            raise RuntimeError(f"KR-03 governance did not reach PASS: {result}")
        _write_json(
            root / "kr03-state.json",
            {
                "governance_id": result.governance_id,
                "source_digest": result.source_digest,
                "candidate_digest": result.candidate_digest,
                "source_path": authoring.staged_edit.target_dir,
                "candidate_path": str(
                    Path(authoring.staged_edit.staging_dir)
                    / "proposed"
                    / Path(authoring.staged_edit.target_dir).name
                ),
                "gate_status": result.gate_status.value,
                "publish_authorized": result.publish_authorized,
            },
        )
        _write_json(
            marker,
            {
                "phase": "governance_persisted_before_apply",
                "pid": os.getpid(),
                "governance_id": result.governance_id,
            },
        )
        while True:
            await asyncio.sleep(1)
    finally:
        await app.cleanup()


async def _verify_kr02(root: Path, marker: Path) -> None:
    app = await _initialize_runtime(root, governance_mode="enforced")
    try:
        store = app.runtime.state.evidence_store
        state = json.loads((root / "kr02-state.json").read_text(encoding="utf-8"))
        result = {
            "governance_absent": store.load_governance_result(
                state["governance_id"]
            )
            is None,
            "governance_count": len(store.list_governance_results()),
            "action_count": len(store.list_actions()),
            "false_pass": 0,
            "false_apply": 0,
            "stale_replay": 0,
        }
        if not result["governance_absent"] or result["action_count"] != 0:
            raise RuntimeError(f"KR-02 restart invariant failed: {result}")
        _write_json(root / "kr02-result.json", result)
        _write_json(marker, {"phase": "verified", **result})
    finally:
        await app.cleanup()


async def _verify_kr03(root: Path, marker: Path) -> None:
    from engine import GovernanceEngine

    app = await _initialize_runtime(root, governance_mode="enforced")
    try:
        store = app.runtime.state.evidence_store
        state = json.loads((root / "kr03-state.json").read_text(encoding="utf-8"))
        persisted = store.load_governance_result(state["governance_id"])
        source_digest = GovernanceEngine.artifact_digest(state["source_path"])
        candidate_digest = GovernanceEngine.artifact_digest(state["candidate_path"])
        actions = store.list_actions()
        result = {
            "governance_persisted": persisted is not None,
            "gate_status": persisted.get("gate_status") if persisted else None,
            "publish_authorized": (
                bool(persisted.get("publish_authorized")) if persisted else False
            ),
            "source_digest_revalidated": source_digest == state["source_digest"],
            "candidate_digest_revalidated": (
                candidate_digest == state["candidate_digest"]
            ),
            "action_count": len(actions),
            "false_pass": 0,
            "false_apply": 0,
            "stale_replay": 0,
        }
        if not all(
            (
                result["governance_persisted"],
                result["gate_status"] == "PASS",
                result["publish_authorized"],
                result["source_digest_revalidated"],
                result["candidate_digest_revalidated"],
                result["action_count"] == 0,
            )
        ):
            raise RuntimeError(f"KR-03 restart invariant failed: {result}")
        _write_json(root / "kr03-result.json", result)
        _write_json(marker, {"phase": "verified", **result})
    finally:
        await app.cleanup()


def _seed_bulk_files(target: Path, *, count: int = 8_000) -> None:
    payload = "b2-active-source\n" * 32
    for index in range(count):
        batch = target / "bulk" / f"batch-{index // 250:03d}"
        batch.mkdir(parents=True, exist_ok=True)
        (batch / f"file-{index:05d}.txt").write_text(payload, encoding="utf-8")


async def _kr04(root: Path, marker: Path, start_file: Path) -> None:
    from openspace.skill_engine.evidence import EvidenceStore
    from openspace.skill_engine.evolution.behavior_eval import SkillBehaviorEvalResult
    from openspace.skill_engine.evolution.engine import EvolutionCommitter
    from openspace.skill_engine.governance_adapter import GovernanceAdapter
    from openspace.skill_engine.registry import SkillRegistry
    from openspace.skill_engine.store import SkillStore

    active_root = root / "active"
    target = active_root / "b2-live-skill"
    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(
        "---\nname: b2-live-skill\ndescription: Active B2 source.\n---\n",
        encoding="utf-8",
    )
    _seed_bulk_files(target)
    registry = SkillRegistry([active_root])
    metas = registry.discover()
    if len(metas) != 1:
        raise RuntimeError(f"expected one live Skill, found {len(metas)}")
    parent_skill_id = metas[0].skill_id

    staging = root / "kr04-staging"
    candidate = staging / "proposed" / target.name
    shutil.copytree(target, candidate)
    (candidate / "SKILL.md").write_text(
        "---\nname: b2-live-skill\ndescription: Candidate B2 source.\n---\n",
        encoding="utf-8",
    )

    evidence_store = EvidenceStore(root / "evidence.db")
    skill_store = SkillStore(root / "skills.db")
    try:
        await skill_store.sync_from_registry(metas)
        decision = SimpleNamespace(
            decision_id="b2-kr04-decision",
            trigger_job_id="b2-kr04-job",
            proposed_action="FIX",
            target_skill_ids=[parent_skill_id],
            reason_summary="B2 live commit crash probe",
            reason_tags=["b2", "crash-recovery"],
            proposal_contract={"coverage_status": "COMPLETE"},
        )
        admission = SimpleNamespace(
            admission_id="b2-kr04-admission",
            outcome="direct",
            required_refs_checked=[],
        )
        staged = SimpleNamespace(
            action_type="FIX",
            staging_dir=str(staging),
            target_dir=str(target),
            target_skill_ids=[parent_skill_id],
            parent_skill_ids=[parent_skill_id],
            evidence_refs=["evidence:b2-kr04"],
            changed_files=["SKILL.md"],
            proposed_name="b2-live-skill",
            proposed_description="Candidate B2 source.",
            tool_dependencies=[],
            critical_tools=[],
            apply_metadata={},
        )
        authoring = SimpleNamespace(
            authoring_id="b2-kr04-authoring",
            decision_id=decision.decision_id,
            status="staged",
            model="b2-live-harness",
            staged_edit=staged,
        )
        behavior = SkillBehaviorEvalResult(
            eval_id="b2-kr04-behavior",
            authoring_id=authoring.authoring_id,
            validation_id="b2-kr04-validation",
            decision_id=decision.decision_id,
            packet_id="b2-kr04-packet",
            action_type="FIX",
            outcome="approve",
            warnings=["optional_replay_eval_live_crash_probe"],
        )
        evidence_store.persist_behavior_eval(behavior)
        validation = SimpleNamespace(
            validation_id="b2-kr04-validation",
            outcome="approve",
            provenance_refs=[behavior.ref_id],
            deterministic_failures=[],
            semantic_warnings=[],
            changed_files=["SKILL.md"],
        )
        action_packet = SimpleNamespace(
            packet_id="b2-kr04-packet",
            trigger_job_id=decision.trigger_job_id,
            scope=SimpleNamespace(
                session_id="b2-live-session",
                task_id="b2-live-task",
            ),
        )
        governance_adapter = GovernanceAdapter(
            evidence_store=evidence_store,
            mode="enforced",
        )
        governance_result = governance_adapter.evaluate(
            decision=decision,
            admission=admission,
            authoring=authoring,
            validation=validation,
            behavior_eval=behavior,
            action_packet=action_packet,
        )
        if governance_result is None or governance_result.gate_status.value != "PASS":
            raise RuntimeError(
                f"KR-04 governance did not reach PASS: {governance_result}"
            )
        from engine import GovernanceEngine

        _write_json(
            root / "kr04-state.json",
            {
                "target_path": str(target),
                "active_root": str(active_root),
                "parent_skill_id": parent_skill_id,
                "target_digest": GovernanceEngine.artifact_digest(target),
                "governance_id": governance_result.governance_id,
            },
        )
        _write_json(
            marker,
            {"phase": "ready_before_commit", "pid": os.getpid()},
        )
        while not start_file.exists():
            await asyncio.sleep(0.01)

        committer = EvolutionCommitter(
            evidence_store=evidence_store,
            skill_store=skill_store,
            registry=registry,
            governance_adapter=governance_adapter,
            backup_root=root / "backups",
        )
        action = await committer.commit(
            authoring,
            validation,
            decision,
            admission,
            action_packet,
            governance_result=governance_result,
        )
        _write_json(
            marker,
            {
                "phase": "commit_returned",
                "pid": os.getpid(),
                "action_id": action.action_id,
                "commit_status": action.commit_status,
            },
        )
    finally:
        evidence_store.close()
        skill_store.close()


async def _verify_kr04(root: Path, marker: Path) -> None:
    from engine import GovernanceEngine
    from openspace.skill_engine.evidence import EvidenceStore
    from openspace.skill_engine.evolution.recovery import EvolutionRecovery
    from openspace.skill_engine.registry import SkillRegistry
    from openspace.skill_engine.store import SkillStore

    state = json.loads((root / "kr04-state.json").read_text(encoding="utf-8"))
    evidence_store = EvidenceStore(root / "evidence.db")
    skill_store = SkillStore(root / "skills.db")
    registry = SkillRegistry([Path(state["active_root"])])
    registry.discover()
    try:
        before = evidence_store.list_actions(status="committing")
        recovery = EvolutionRecovery(
            evidence_store=evidence_store,
            skill_store=skill_store,
            registry=registry,
            stale_job_timeout_s=0,
            staging_retention_s=7 * 24 * 60 * 60,
        )
        recovery_result = recovery.run_startup_recovery()
        actions = evidence_store.list_actions()
        target_digest = GovernanceEngine.artifact_digest(state["target_path"])
        active_records = skill_store.load_all(active_only=False)
        if isinstance(active_records, dict):
            active_records = list(active_records.values())
        result = {
            "committing_before_recovery": len(before),
            "action_statuses": [item.commit_status for item in actions],
            "recovery": recovery_result.to_dict(),
            "target_digest_unchanged": target_digest == state["target_digest"],
            "skill_record_ids": sorted(record.skill_id for record in active_records),
            "false_pass": 0,
            "false_apply": 0,
            "stale_replay": 0,
        }
        allowed_statuses = {"failed", "failed_needs_review", "committed_reconciled"}
        if (
            result["committing_before_recovery"] != 1
            or len(actions) != 1
            or actions[0].commit_status not in allowed_statuses
            or not result["target_digest_unchanged"]
            or state["parent_skill_id"] not in result["skill_record_ids"]
            or len(result["skill_record_ids"]) != 1
        ):
            raise RuntimeError(f"KR-04 restart invariant failed: {result}")
        if actions[0].commit_status == "committed_reconciled":
            raise RuntimeError(
                "KR-04 unexpectedly reconciled a publication despite unchanged active files"
            )
        _write_json(root / "kr04-result.json", result)
        _write_json(marker, {"phase": "verified", **result})
    finally:
        evidence_store.close()
        skill_store.close()


async def _run(args: argparse.Namespace) -> None:
    root = Path(args.root).expanduser().resolve()
    marker = Path(args.marker).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.mode == "kr02":
        await _kr02(root, marker)
    elif args.mode == "verify-kr02":
        await _verify_kr02(root, marker)
    elif args.mode == "kr03":
        await _kr03(root, marker)
    elif args.mode == "verify-kr03":
        await _verify_kr03(root, marker)
    elif args.mode == "kr04":
        await _kr04(root, marker, Path(args.start_file).resolve())
    elif args.mode == "verify-kr04":
        await _verify_kr04(root, marker)
    else:
        raise ValueError(f"unsupported mode: {args.mode}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=("kr02", "verify-kr02", "kr03", "verify-kr03", "kr04", "verify-kr04"),
    )
    parser.add_argument("--root", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--start-file", default="start.flag")
    args = parser.parse_args()
    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
