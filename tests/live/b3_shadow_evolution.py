"""Run full production EvolutionEngine mutations with shadow governance."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import uuid


ROOT = Path(__file__).resolve().parents[2]
for import_root in (str(ROOT),):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)


class StaticAuthoringBackend:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls = 0

    async def author_from_action_packet(self, _packet: object) -> object:
        self.calls += 1
        return self.result


class StaticValidator:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls = 0

    async def validate(self, *_args: object) -> object:
        self.calls += 1
        return self.result


CASES = {
    "valid": ({"coverage_status": "COMPLETE"}, "PASS"),
    "required_fail": (
        {
            "coverage_status": "COMPLETE",
            "required_capabilities": ["DELIVERABLE_CONTRACT"],
            "applicability": {"deliverable_contract": "required"},
            "deliverable_contract": {"status": "FAIL"},
        },
        "BLOCKED",
    ),
    "provider_incomplete": (
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
        "INCOMPLETE",
    ),
}


async def _run_case(
    root: Path,
    *,
    case_name: str,
    proposal_contract: dict[str, object],
    expected_gate: str,
) -> dict[str, object]:
    from engine import GovernanceEngine
    from openspace.skill_engine.evidence import EvidenceStore
    from openspace.skill_engine.evolution.behavior_eval import SkillBehaviorEvaluator
    from openspace.skill_engine.evolution.engine import EvolutionCommitter, EvolutionEngine
    from openspace.skill_engine.governance_adapter import GovernanceAdapter
    from openspace.skill_engine.registry import SkillRegistry
    from openspace.skill_engine.store import SkillStore

    active_root = root / "active"
    source = active_root / f"shadow-{case_name}"
    source.mkdir(parents=True, exist_ok=True)
    (source / "SKILL.md").write_text(
        f"---\nname: shadow-{case_name}\ndescription: Active before {case_name}.\n---\n",
        encoding="utf-8",
    )
    registry = SkillRegistry([active_root])
    metas = registry.discover()
    if len(metas) != 1:
        raise RuntimeError(f"expected one source Skill, found {len(metas)}")
    parent_skill_id = metas[0].skill_id

    staging = root / "staging"
    candidate = staging / "proposed" / source.name
    shutil.copytree(source, candidate)
    applied_description = f"Applied despite shadow {expected_gate}."
    (candidate / "SKILL.md").write_text(
        f"---\nname: shadow-{case_name}\ndescription: {applied_description}\n---\n",
        encoding="utf-8",
    )

    evidence_store = EvidenceStore(root / "evidence.db")
    skill_store = SkillStore(root / "skills.db")
    try:
        await skill_store.sync_from_registry(metas)
        prefix = f"b3-{case_name}"
        admission = SimpleNamespace(
            admission_id=f"{prefix}-admission",
            outcome="direct",
            required_refs_checked=[],
            source_validation_passed=False,
        )
        decision = SimpleNamespace(
            decision_id=f"{prefix}-decision",
            trigger_job_id=f"{prefix}-job",
            proposed_action="FIX",
            target_skill_ids=[parent_skill_id],
            reason_summary=f"Verify shadow {case_name} publication semantics",
            reason_tags=["b3", "shadow", case_name],
            proposal_contract=proposal_contract,
            admission=admission,
        )
        staged = SimpleNamespace(
            action_type="FIX",
            staging_dir=str(staging),
            target_dir=str(source),
            target_skill_ids=[parent_skill_id],
            parent_skill_ids=[parent_skill_id],
            evidence_refs=[f"evidence:{prefix}"],
            changed_files=["SKILL.md"],
            proposed_name=f"shadow-{case_name}",
            proposed_description=applied_description,
            tool_dependencies=[],
            critical_tools=[],
            apply_metadata={},
            intent_spec={
                "capability": f"Verify shadow {case_name}",
                "trigger_contexts": [f"Governance returns {expected_gate}."],
                "non_trigger_contexts": ["Governance mode is enforced."],
                "success_criteria": ["The existing commit path remains authoritative."],
            },
            eval_plan={
                "positive_trigger_queries": [f"Run shadow {case_name}."],
                "negative_trigger_queries": ["Run enforced governance."],
                "replay_tasks": [
                    {
                        "prompt": "Confirm the candidate is evaluated before publication.",
                        "judge_policy": "deterministic",
                    }
                ],
                "success_criteria": ["Behavior evaluation approves the candidate."],
                "judge_policy": "deterministic",
            },
        )
        authoring = SimpleNamespace(
            authoring_id=f"{prefix}-authoring",
            decision_id=decision.decision_id,
            status="staged",
            model="b3-live-harness",
            staged_edit=staged,
        )
        validation = SimpleNamespace(
            validation_id=f"{prefix}-validation",
            outcome="approve",
            provenance_refs=[f"validation:{prefix}"],
            deterministic_failures=[],
            semantic_warnings=[],
            changed_files=["SKILL.md"],
        )
        packet = SimpleNamespace(
            packet_id=f"{prefix}-packet",
            packet_type="action",
            trigger_job_id=decision.trigger_job_id,
            decisions=[decision],
            scope=SimpleNamespace(
                session_id=f"{prefix}-session",
                task_id=f"{prefix}-task",
                source_task_ids=(f"{prefix}-task",),
            ),
        )
        job = SimpleNamespace(job_id=decision.trigger_job_id, status="running", packet=packet)
        authoring_backend = StaticAuthoringBackend(authoring)
        validator = StaticValidator(validation)
        governance_adapter = GovernanceAdapter(evidence_store=evidence_store, mode="shadow")
        behavior_evaluator = SkillBehaviorEvaluator(
            evidence_store=evidence_store,
            registry=registry,
            skill_store=skill_store,
            enable_routing_eval=False,
            require_routing_eval=False,
            replay_runner=None,
            require_replay_runner=False,
            checked_by="b3-live-behavior",
        )
        committer = EvolutionCommitter(
            evidence_store=evidence_store,
            skill_store=skill_store,
            registry=registry,
            governance_adapter=governance_adapter,
            backup_root=root / "backups",
        )
        engine = EvolutionEngine(
            authoring_backend=authoring_backend,
            validator=validator,
            behavior_evaluator=behavior_evaluator,
            committer=committer,
            governance_adapter=governance_adapter,
            evolution_mode="autonomous",
        )

        source_digest_before = GovernanceEngine.artifact_digest(source)
        result = await engine.process_job(job)
        governance_results = evidence_store.list_governance_results()
        actions = evidence_store.list_actions()
        records = skill_store.load_all(active_only=False)
        if isinstance(records, dict):
            records = list(records.values())
        active_records = [record for record in records if record.is_active]
        if len(active_records) != 1:
            raise RuntimeError(f"expected one active SkillRecord, found {len(active_records)}")
        latest = active_records[0]
        applied_dir = Path(latest.path).parent
        source_digest_after = GovernanceEngine.artifact_digest(applied_dir)
        governance = result.governance_results[0]
        output = {
            "run_status": result.status,
            "errors": list(result.errors),
            "authoring_calls": authoring_backend.calls,
            "validator_calls": validator.calls,
            "governance_count": len(result.governance_results),
            "governance_id": governance.governance_id,
            "governance_gate": governance.gate_status.value,
            "governance_publish_authorized": governance.publish_authorized,
            "governance_reason_codes": list(governance.reason_codes),
            "persisted_governance_count": len(governance_results),
            "action_statuses": [action.commit_status for action in actions],
            "source_digest_changed": source_digest_before != source_digest_after,
            "active_description_applied": applied_description
            in (applied_dir / "SKILL.md").read_text(encoding="utf-8"),
            "latest_trust_state": latest.trust_state.value,
        }
        if not all(
            (
                output["run_status"] == "completed",
                output["errors"] == [],
                output["authoring_calls"] == 1,
                output["validator_calls"] == 1,
                output["governance_count"] == 1,
                output["governance_gate"] == expected_gate,
                output["governance_publish_authorized"] is False,
                output["persisted_governance_count"] == 1,
                output["action_statuses"] == ["committed"],
                output["source_digest_changed"],
                output["active_description_applied"],
                output["latest_trust_state"] == "provisional",
            )
        ):
            raise RuntimeError(f"B3 {case_name} invariant failed: {output}")
        return output
    finally:
        evidence_store.close()
        skill_store.close()


async def _run(root: Path) -> dict[str, object]:
    results: dict[str, object] = {}
    for case_name, (proposal_contract, expected_gate) in CASES.items():
        results[case_name] = await _run_case(
            root / case_name,
            case_name=case_name,
            proposal_contract=proposal_contract,
            expected_gate=expected_gate,
        )
    return results


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    args = parser.parse_args()
    root = (
        Path(args.root).expanduser().resolve()
        if args.root
        else ROOT.parent / f"openspace-b3-shadow-{uuid.uuid4().hex[:10]}"
    )
    root.mkdir(parents=True, exist_ok=True)
    payload = {"root": str(root), "cases": asyncio.run(_run(root))}
    output = root / "b3-shadow-results.json"
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"RESULT_PATH={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
