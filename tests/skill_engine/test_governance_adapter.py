from pathlib import Path
from types import SimpleNamespace

from openspace.skill_engine.evidence.store import EvidenceStore
from openspace.skill_engine.governance_adapter import GovernanceAdapter
from openspace.skill_engine.governance_adapter.errors import GovernanceBlockedError
from openspace.skill_engine.evolution.engine import EvolutionCommitter


def _objects(tmp_path: Path, proposal_contract=None):
    source = tmp_path / "source"
    candidate = tmp_path / "staging" / "proposed" / "source"
    source.mkdir(parents=True)
    candidate.mkdir(parents=True)
    (source / "SKILL.md").write_text("source", encoding="utf-8")
    (candidate / "SKILL.md").write_text("candidate", encoding="utf-8")
    decision = SimpleNamespace(
        decision_id="dec-1",
        trigger_job_id="job-1",
        proposed_action="FIX",
        target_skill_ids=["skill"],
        reason_summary="repair",
        reason_tags=[],
        proposal_contract=proposal_contract or {},
    )
    admission = SimpleNamespace(admission_id="adm-1", required_refs_checked=[])
    staged = SimpleNamespace(
        action_type="FIX",
        staging_dir=str(tmp_path / "staging"),
        target_dir=str(source),
        target_skill_ids=["skill"],
        parent_skill_ids=["skill"],
        evidence_refs=["evidence:source"],
    )
    authoring = SimpleNamespace(authoring_id="auth-1", staged_edit=staged)
    validation = SimpleNamespace(
        validation_id="val-1",
        outcome="approve",
        provenance_refs=["validation:val-1"],
        deterministic_failures=[],
        semantic_warnings=[],
    )
    behavior = SimpleNamespace(eval_id="eval-1")
    return decision, admission, authoring, validation, behavior


def test_shadow_adapter_persists_to_existing_evidence_store(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "evidence.db")
    adapter = GovernanceAdapter(evidence_store=store, mode="shadow")
    objects = _objects(tmp_path)

    result = adapter.evaluate(
        decision=objects[0],
        admission=objects[1],
        authoring=objects[2],
        validation=objects[3],
        behavior_eval=objects[4],
    )

    assert result.gate_status == "PASS"
    assert result.publish_authorized is False
    assert store.load_governance_result(result.governance_id)["engine_name"] == "skill-engineering"


def test_off_adapter_does_not_invoke_or_persist_governance(tmp_path: Path) -> None:
    from engine import GovernanceMode

    class ExplodingEngine:
        mode = GovernanceMode.OFF

        def evaluate(self, _request):
            raise AssertionError("off mode must not invoke GovernanceEngine")

    store = EvidenceStore(tmp_path / "evidence.db")
    adapter = GovernanceAdapter(
        evidence_store=store,
        engine=ExplodingEngine(),
        mode="off",
    )

    objects = _objects(tmp_path)
    result = adapter.evaluate(
        decision=objects[0],
        admission=objects[1],
        authoring=objects[2],
        validation=objects[3],
        behavior_eval=objects[4],
    )

    assert adapter.enabled is False
    assert result is None
    assert store.list_governance_results() == []


def test_enforced_adapter_blocks_required_unexecuted_capability(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "evidence.db")
    adapter = GovernanceAdapter(evidence_store=store, mode="enforced")
    objects = _objects(
        tmp_path,
        proposal_contract={
            "required_capabilities": ["DELIVERABLE_CONTRACT"],
            "applicability": {"deliverable_contract": "required"},
        },
    )

    result = adapter.evaluate(
        decision=objects[0],
        admission=objects[1],
        authoring=objects[2],
        validation=objects[3],
        behavior_eval=objects[4],
    )

    assert result.gate_status == "INCOMPLETE"
    assert result.publish_authorized is False
    assert "provider_not_selected" in result.reason_codes


def test_committer_remains_the_only_publication_boundary() -> None:
    class BlockingAdapter:
        enforced = True

        async def evaluate(self, **_kwargs):
            return SimpleNamespace(
                gate_status="BLOCKED",
                publish_authorized=False,
                reason_codes=("candidate_digest_mismatch",),
            )

    committer = EvolutionCommitter(
        evidence_store=SimpleNamespace(),
        skill_store=SimpleNamespace(),
        registry=SimpleNamespace(),
        governance_adapter=BlockingAdapter(),
    )
    authoring = SimpleNamespace(
        status="staged",
        staged_edit=SimpleNamespace(action_type="FIX"),
    )

    import asyncio

    try:
        asyncio.run(
            committer.commit(
                authoring,
                SimpleNamespace(outcome="approve"),
                SimpleNamespace(proposed_action="FIX"),
                SimpleNamespace(outcome="direct"),
                SimpleNamespace(),
            )
        )
    except GovernanceBlockedError as exc:
        assert "candidate_digest_mismatch" in exc.reason_codes
    else:
        raise AssertionError("enforced governance must block before active mutation")


def test_candidate_digest_change_is_blocked_before_commit(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "evidence.db")
    adapter = GovernanceAdapter(evidence_store=store, mode="enforced")
    decision, admission, authoring, validation, behavior = _objects(tmp_path)
    result = adapter.evaluate(
        decision=decision,
        admission=admission,
        authoring=authoring,
        validation=validation,
        behavior_eval=behavior,
    )
    candidate = Path(authoring.staged_edit.staging_dir) / "proposed" / "source" / "SKILL.md"
    candidate.write_text("changed after governance", encoding="utf-8")
    committer = EvolutionCommitter(
        evidence_store=SimpleNamespace(),
        skill_store=SimpleNamespace(),
        registry=SimpleNamespace(),
        governance_adapter=adapter,
    )

    import asyncio

    try:
        asyncio.run(
            committer.commit(
                authoring,
                validation,
                decision,
                admission,
                SimpleNamespace(),
                governance_result=result,
            )
        )
    except GovernanceBlockedError as exc:
        assert "candidate_digest_mismatch" in exc.reason_codes
    else:
        raise AssertionError("candidate mutation after governance must be blocked")


def test_source_digest_change_is_blocked_before_commit(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "evidence.db")
    adapter = GovernanceAdapter(evidence_store=store, mode="enforced")
    decision, admission, authoring, validation, behavior = _objects(tmp_path)
    result = adapter.evaluate(
        decision=decision,
        admission=admission,
        authoring=authoring,
        validation=validation,
        behavior_eval=behavior,
    )
    (Path(authoring.staged_edit.target_dir) / "SKILL.md").write_text(
        "source changed after governance", encoding="utf-8"
    )
    committer = EvolutionCommitter(
        evidence_store=SimpleNamespace(),
        skill_store=SimpleNamespace(),
        registry=SimpleNamespace(),
        governance_adapter=adapter,
    )

    import asyncio

    try:
        asyncio.run(
            committer.commit(
                authoring,
                validation,
                decision,
                admission,
                SimpleNamespace(),
                governance_result=result,
            )
        )
    except GovernanceBlockedError as exc:
        assert "source_digest_mismatch" in exc.reason_codes
    else:
        raise AssertionError("source mutation after governance must be blocked")


def test_stale_governance_result_replay_is_rejected(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "evidence.db")
    adapter = GovernanceAdapter(evidence_store=store, mode="enforced")
    decision, admission, authoring, validation, behavior = _objects(tmp_path)
    stale_result = adapter.evaluate(
        decision=decision,
        admission=admission,
        authoring=authoring,
        validation=validation,
        behavior_eval=behavior,
    )
    (Path(authoring.staged_edit.staging_dir) / "proposed" / "source" / "SKILL.md").write_text(
        "new candidate revision", encoding="utf-8"
    )
    assert adapter.verify_result_integrity(stale_result, authoring) == (
        "candidate_digest_mismatch",
    )
