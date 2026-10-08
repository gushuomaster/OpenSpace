import asyncio
import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openspace.application import OpenSpaceConfig
from openspace.llm.client import LLMClient
from openspace.llm.types import ModelResponse, TokenUsage
from openspace.recording import RecordingManager
from openspace.services.conversation.messages import (
    build_assistant_api_error_message,
)
from openspace.skill_engine.evolver import (
    EvolutionContext,
    EvolutionTrigger,
    SkillEvolver,
)
from openspace.skill_engine.patch import SkillEditResult, stage_create_skill
from openspace.skill_engine.types import EvolutionSuggestion, EvolutionType


class FakeLLMClient:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.model = "test-model"
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def call_model_with_fallback(self, **kwargs) -> ModelResponse:
        self.calls.append(
            {
                "messages": copy.deepcopy(kwargs["messages"]),
                "tools": kwargs.get("tools"),
                "model": kwargs.get("model"),
                "max_tokens": kwargs.get("max_tokens"),
            }
        )
        return self._responses.pop(0)

    @staticmethod
    def get_model_response_followup_messages(
        response: ModelResponse,
    ) -> list[dict]:
        return LLMClient.get_model_response_followup_messages(response)

    @staticmethod
    def model_response_has_api_error(response: ModelResponse) -> bool:
        return LLMClient.model_response_has_api_error(response)


def _response(
    content: str,
    *,
    stop_reason: str = "stop",
    output_tokens: int = 100,
) -> ModelResponse:
    assistant_message = {"role": "assistant", "content": content}
    messages = [assistant_message]
    if stop_reason == "length":
        messages.append(
            build_assistant_api_error_message(
                "Response reached the maximum output token limit.",
                error_details="stop_reason=length, model=test-model",
            )
        )
    elif stop_reason in {"refusal", "content_filter"}:
        messages.append(
            build_assistant_api_error_message(
                "The model declined the request.",
                error_details=f"stop_reason={stop_reason}, model=test-model",
            )
        )
    return ModelResponse(
        assistant_message=assistant_message,
        tool_calls=[],
        tool_map={},
        stop_reason=stop_reason,
        usage=TokenUsage(
            input_tokens=200,
            output_tokens=output_tokens,
            total_tokens=200 + output_tokens,
        ),
        messages=messages,
        effective_model="test-model",
    )


def _complete_response() -> str:
    return (
        "---\n"
        "name: concise-workflow\n"
        "description: Apply a reusable workflow.\n"
        "---\n\n"
        "# Concise workflow\n\n"
        "1. Inspect the relevant state.\n"
        "2. Apply the smallest verified change.\n\n"
        "*** Begin Evolution Finalization\n"
        '{"status":"complete","change_summary":"Captured the workflow",'
        '"intent_spec":{"goal":"Apply the verified workflow"},'
        '"eval_plan":{"checks":["Confirm the expected result"]}}\n'
        "*** End Evolution Finalization"
    )


def _context() -> EvolutionContext:
    return EvolutionContext(
        trigger=EvolutionTrigger.ANALYSIS,
        suggestion=EvolutionSuggestion(
            evolution_type=EvolutionType.CAPTURED,
            direction="Capture a reusable verified workflow.",
        ),
        source_task_id="task_test",
        available_tools=[object()],
    )


def _evolver(
    client: FakeLLMClient,
    *,
    max_tokens: int | None = None,
) -> SkillEvolver:
    return SkillEvolver(
        store=SimpleNamespace(),
        registry=SimpleNamespace(),
        llm_client=client,
        max_tokens=max_tokens,
    )


def test_length_response_keeps_remaining_rounds_tool_free_until_finalization(
    monkeypatch,
) -> None:
    setup_recorder = AsyncMock()
    iteration_recorder = AsyncMock()
    monkeypatch.setattr(
        RecordingManager,
        "record_conversation_setup",
        setup_recorder,
    )
    monkeypatch.setattr(
        RecordingManager,
        "record_iteration_context",
        iteration_recorder,
    )
    client = FakeLLMClient(
        [
            _response(
                "partial skill content", stop_reason="length", output_tokens=4096
            ),
            _response("I will now provide the concise replacement."),
            _response(_complete_response()),
        ]
    )

    result = asyncio.run(
        _evolver(client, max_tokens=8192)._run_evolution_loop(
            "Author a skill.",
            _context(),
        )
    )

    assert result is not None
    assert result.change_summary == "Captured the workflow"
    assert len(client.calls) == 3
    assert client.calls[0]["tools"] is not None
    assert client.calls[1]["tools"] is None
    assert client.calls[2]["tools"] is None
    assert {call["max_tokens"] for call in client.calls} == {8192}
    assert any(
        message.get("_meta", {}).get("type") == "evolution_max_output_tokens_recovery"
        for message in client.calls[1]["messages"]
    )

    first_metadata = iteration_recorder.await_args_list[0].kwargs["response_metadata"]
    assert first_metadata["stop_reason"] == "length"
    assert first_metadata["output_tokens"] == 4096
    assert first_metadata["content_length"] == len("partial skill content")
    assert first_metadata["has_api_error"] is True
    assert first_metadata["length_recovery_attempt"] == 1


def test_repeated_length_response_stops_after_one_recovery(monkeypatch) -> None:
    monkeypatch.setattr(
        RecordingManager,
        "record_conversation_setup",
        AsyncMock(),
    )
    monkeypatch.setattr(
        RecordingManager,
        "record_iteration_context",
        AsyncMock(),
    )
    client = FakeLLMClient(
        [
            _response("first partial", stop_reason="length", output_tokens=4096),
            _response("second partial", stop_reason="length", output_tokens=4096),
        ]
    )

    result = asyncio.run(
        _evolver(client)._run_evolution_loop("Author a skill.", _context())
    )

    assert result is None
    assert len(client.calls) == 2


def test_refusal_is_recorded_and_not_retried(monkeypatch) -> None:
    iteration_recorder = AsyncMock()
    monkeypatch.setattr(
        RecordingManager,
        "record_conversation_setup",
        AsyncMock(),
    )
    monkeypatch.setattr(
        RecordingManager,
        "record_iteration_context",
        iteration_recorder,
    )
    client = FakeLLMClient([_response("", stop_reason="refusal", output_tokens=0)])

    result = asyncio.run(
        _evolver(client)._run_evolution_loop("Author a skill.", _context())
    )

    assert result is None
    assert len(client.calls) == 1
    metadata = iteration_recorder.await_args.kwargs["response_metadata"]
    assert metadata["stop_reason"] == "refusal"
    assert metadata["has_api_error"] is True
    assert metadata["length_recovery_attempt"] == 0


def test_staged_authoring_loop_does_not_require_legacy_mutation_opt_in(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        RecordingManager,
        "record_conversation_setup",
        AsyncMock(),
    )
    monkeypatch.setattr(
        RecordingManager,
        "record_iteration_context",
        AsyncMock(),
    )
    client = FakeLLMClient([_response(_complete_response())])

    result = asyncio.run(
        _evolver(client).run_staged_authoring_loop(
            "Author a skill.",
            _context(),
        )
    )

    assert result is not None
    assert result.change_summary == "Captured the workflow"


def test_staged_authoring_retry_preserves_underlying_exception() -> None:
    class RetryFailure(RuntimeError):
        pass

    evolver = _evolver(FakeLLMClient([]))

    async def fail_retry(**_kwargs):
        raise RetryFailure("retry failed")

    evolver._apply_with_retry = fail_retry

    with pytest.raises(RetryFailure, match="retry failed"):
        asyncio.run(
            evolver.apply_staged_authoring_with_retry(
                apply_fn=lambda content: content,
                initial_content="content",
                skill_dir=SimpleNamespace(),
                ctx=_context(),
                prompt="Author a skill.",
            )
        )


def test_staged_authoring_retry_applies_corrected_content_only_in_staging(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(RecordingManager, "record_conversation_setup", AsyncMock())
    monkeypatch.setattr(RecordingManager, "record_iteration_context", AsyncMock())
    staging_dir = tmp_path / "staging"
    formal_dir = tmp_path / "formal"
    formal_dir.mkdir()
    sentinel = formal_dir / "SKILL.md"
    sentinel.write_text("formal asset", encoding="utf-8")
    client = FakeLLMClient([_response(_complete_response())])
    evolver = _evolver(client)
    attempts = []

    def apply(content: str) -> SkillEditResult:
        attempts.append(content)
        if len(attempts) == 1:
            return SkillEditResult(error="invalid first staged edit")
        return stage_create_skill(staging_dir, "retry-skill", content)

    result = asyncio.run(
        evolver.apply_staged_authoring_with_retry(
            apply_fn=apply,
            initial_content="invalid first content",
            skill_dir=staging_dir / "proposed" / "retry-skill",
            ctx=_context(),
            prompt="Author a skill.",
            cleanup_on_retry=staging_dir,
        )
    )

    assert result is not None
    assert result.ok
    assert len(attempts) == 2
    assert sentinel.read_text(encoding="utf-8") == "formal asset"
    assert (staging_dir / "proposed" / "retry-skill" / "SKILL.md").exists()


def test_staged_authoring_retry_exhaustion_cleans_staging_and_preserves_formal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(RecordingManager, "record_conversation_setup", AsyncMock())
    monkeypatch.setattr(RecordingManager, "record_iteration_context", AsyncMock())
    staging_dir = tmp_path / "staging"
    formal_dir = tmp_path / "formal"
    formal_dir.mkdir()
    sentinel = formal_dir / "SKILL.md"
    sentinel.write_text("formal asset", encoding="utf-8")
    client = FakeLLMClient(
        [_response(_complete_response()), _response(_complete_response())]
    )
    evolver = _evolver(client)
    attempts = []

    def always_fail(content: str) -> SkillEditResult:
        attempts.append(content)
        failed_dir = staging_dir / "proposed" / "retry-skill"
        failed_dir.mkdir(parents=True, exist_ok=True)
        (failed_dir / "partial.txt").write_text("partial", encoding="utf-8")
        return SkillEditResult(skill_dir=failed_dir, error="persistent staged failure")

    result = asyncio.run(
        evolver.apply_staged_authoring_with_retry(
            apply_fn=always_fail,
            initial_content="invalid first content",
            skill_dir=staging_dir / "proposed" / "retry-skill",
            ctx=_context(),
            prompt="Author a skill.",
            cleanup_on_retry=staging_dir,
        )
    )

    assert result is None
    assert len(attempts) == 3
    assert not staging_dir.exists()
    assert sentinel.read_text(encoding="utf-8") == "formal asset"


def test_legacy_direct_mutation_guard_is_closed_by_default() -> None:
    evolver = _evolver(FakeLLMClient([]))

    with pytest.raises(RuntimeError, match="direct mutation is disabled"):
        asyncio.run(evolver._execute_contexts([], "test"))


def test_skill_evolver_max_tokens_can_be_configured_from_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENSPACE_SKILL_EVOLVER_MAX_TOKENS", "12288")

    config = OpenSpaceConfig(skill_evolver_max_tokens=8192)

    assert config.skill_evolver_max_tokens == 12288
