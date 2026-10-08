"""Run bounded real bundled-provider workload samples and record reliability."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import statistics
import subprocess
import time
from uuid import uuid4


def _process_count(image_name: str) -> int:
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return sum(1 for line in result.stdout.splitlines() if image_name.lower() in line.lower())


def _target_info(path: Path) -> dict[str, object]:
    files = [item for item in path.rglob("*") if item.is_file()]
    return {
        "path": str(path),
        "file_count": len(files),
        "input_bytes": sum(item.stat().st_size for item in files),
    }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if percentile == 50:
        return statistics.median(ordered)
    index = max(0, min(len(ordered) - 1, int((percentile / 100) * len(ordered)) - 1))
    return ordered[index]


def run_workload(engine_root: Path, targets: list[tuple[str, Path]], runs: int, timeout: int) -> dict[str, object]:
    from engine import GovernanceEngine
    from engine.host_adapters import build_default_provider_adapters
    from engine.providers import ProviderGateway

    adapters = build_default_provider_adapters(engine_root, timeout_seconds=timeout)
    selected = next(
        adapter
        for adapter in adapters
        if adapter.descriptor.capability == "DELIVERABLE_CONTRACT"
    )
    gateway = ProviderGateway([selected])
    results: list[dict[str, object]] = []
    for index in range(runs):
        target_class, target = targets[index % len(targets)]
        target_digest = GovernanceEngine.artifact_digest(target)
        inspection_id = f"operational-{index:03d}-{uuid4().hex[:8]}"
        payload = {
            "target_path": str(target),
            "mode": "AUDIT",
            "inspection_id": inspection_id,
            "inspection_nonce": uuid4().hex,
            "target_digest": target_digest,
            "artifact_role": "BASELINE",
            "deliverable_contract_applicability": "REQUIRED",
        }
        before_codex = _process_count("codex.exe")
        started = time.perf_counter()
        error = ""
        result = None
        try:
            result = gateway.invoke("DELIVERABLE_CONTRACT", payload, formal_run=True)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        duration = time.perf_counter() - started
        after_codex = _process_count("codex.exe")
        provider_status = getattr(getattr(result, "provider_status", None), "value", None)
        provider_execution = getattr(getattr(result, "provider_execution", None), "value", None)
        evidence_valid = bool(getattr(result, "evidence_valid", False))
        semantic_result = (
            "PASS"
            if result is not None and provider_execution == "EXECUTED" and evidence_valid
            else "FAIL"
            if result is not None and provider_execution == "EXECUTED"
            else "ERROR"
        )
        item = {
            "run_id": inspection_id,
            "target_class": target_class,
            **_target_info(target),
            "provider_started": result is not None or bool(error),
            "provider_completed": result is not None,
            "provider_status": provider_status,
            "provider_execution": provider_execution,
            "semantic_result": semantic_result,
            "evidence_valid": evidence_valid,
            "provider_duration_seconds": round(duration, 6),
            "governance_duration_seconds": round(duration, 6),
            "error": error,
            "codex_process_before": before_codex,
            "codex_process_after": after_codex,
            "orphan_process_delta": after_codex - before_codex,
        }
        if result is not None and getattr(result, "deliverable_contract", None) is not None:
            item["deliverable_contract"] = asdict(result.deliverable_contract)
        results.append(item)

    durations = sorted(item["provider_duration_seconds"] for item in results)
    successful = sum(item["provider_completed"] and item["provider_execution"] == "EXECUTED" for item in results)
    semantic_pass = sum(item["semantic_result"] == "PASS" for item in results)
    errors = sum(item["semantic_result"] == "ERROR" for item in results)
    timeouts = sum(str(item["provider_status"]).upper() == "TIMEOUT" for item in results)
    unavailable = sum(str(item["provider_status"]).upper() == "UNAVAILABLE" for item in results)
    return {
        "engine_revision": GovernanceEngine(mode="shadow").engine_revision,
        "runs": len(results),
        "successful_completions": successful,
        "semantic_pass": semantic_pass,
        "provider_errors": errors,
        "provider_timeouts": timeouts,
        "provider_unavailable": unavailable,
        "completion_rate": round(successful / max(1, len(results)), 6),
        "error_rate": round(errors / max(1, len(results)), 6),
        "timeout_rate": round(timeouts / max(1, len(results)), 6),
        "provider_latency_seconds": {
            "p50": round(_percentile(durations, 50), 6),
            "p95": round(_percentile(durations, 95), 6),
            "max": round(max(durations), 6) if durations else 0.0,
        },
        "resource_leak_runs": sum(item["orphan_process_delta"] > 0 for item in results),
        "targets": [_target_info(path) | {"target_class": label} for label, path in targets],
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--small", required=True)
    parser.add_argument("--medium")
    parser.add_argument("--large")
    args = parser.parse_args()
    targets = [("small", Path(args.small).expanduser().resolve())]
    if args.medium:
        targets.append(("medium", Path(args.medium).expanduser().resolve()))
    if args.large:
        targets.append(("large", Path(args.large).expanduser().resolve()))
    payload = run_workload(Path(args.engine_root).expanduser().resolve(), targets, args.runs, args.timeout)
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    print(f"RESULT_PATH={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
