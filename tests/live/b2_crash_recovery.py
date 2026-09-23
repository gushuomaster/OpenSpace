"""Orchestrate the B2 live crash/restart probes from outside the runtime."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[2]
CHILD = Path(__file__).with_name("b2_runtime_parent.py")


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.pathsep.join(
        (
            str(ROOT),
            env.get("PYTHONPATH", ""),
        )
    ).rstrip(os.pathsep)
    return env


def _spawn(mode: str, root: Path, marker: Path, *, start_file: Path | None = None):
    command = [
        sys.executable,
        str(CHILD),
        mode,
        "--root",
        str(root),
        "--marker",
        str(marker),
    ]
    if start_file is not None:
        command.extend(("--start-file", str(start_file)))
    stdout_path = root / f"{mode}.stdout.log"
    stderr_path = root / f"{mode}.stderr.log"
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=_env(),
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    process._b2_stdout_handle = stdout_handle
    process._b2_stderr_handle = stderr_handle
    process._b2_stdout_path = stdout_path
    process._b2_stderr_path = stderr_path
    return process


def _process_logs(process: subprocess.Popen[str]) -> tuple[str, str]:
    for name in ("_b2_stdout_handle", "_b2_stderr_handle"):
        handle = getattr(process, name, None)
        if handle is not None and not handle.closed:
            handle.close()
    stdout_path = getattr(process, "_b2_stdout_path")
    stderr_path = getattr(process, "_b2_stderr_path")
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    return stdout, stderr


def _wait_marker(
    process: subprocess.Popen[str],
    marker: Path,
    phase: str,
    *,
    timeout: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_payload: dict[str, object] = {}
    while time.monotonic() < deadline:
        if marker.is_file():
            try:
                last_payload = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                last_payload = {}
            if last_payload.get("phase") == phase:
                return last_payload
        if process.poll() is not None:
            process.wait()
            stdout, stderr = _process_logs(process)
            raise RuntimeError(
                f"child {process.pid} exited before {phase}: rc={process.returncode}\n"
                f"stdout:\n{stdout}\nstderr:\n{stderr}"
            )
        time.sleep(0.05)
    raise TimeoutError(
        f"timed out waiting for {phase}; pid={process.pid}; marker={last_payload}"
    )


def _kill(process: subprocess.Popen[str]) -> dict[str, object]:
    process.kill()
    process.wait(timeout=30)
    stdout, stderr = _process_logs(process)
    return {
        "pid": process.pid,
        "returncode": process.returncode,
        "stdout_tail": stdout[-4_000:],
        "stderr_tail": stderr[-4_000:],
    }


def _run_verifier(mode: str, root: Path, marker: Path) -> dict[str, object]:
    process = _spawn(mode, root, marker)
    payload = _wait_marker(process, marker, "verified", timeout=180)
    process.wait(timeout=30)
    stdout, stderr = _process_logs(process)
    if process.returncode != 0:
        raise RuntimeError(
            f"verifier {mode} failed: rc={process.returncode}\n"
            f"stdout:\n{stdout}\nstderr:\n{stderr}"
        )
    payload["stdout_tail"] = stdout[-4_000:]
    payload["stderr_tail"] = stderr[-4_000:]
    return payload


def _run_kr02(root: Path) -> dict[str, object]:
    marker = root / "kr02-marker.json"
    process = _spawn("kr02", root, marker)
    before_kill = _wait_marker(
        process,
        marker,
        "governance_ready_before_persistence",
        timeout=420,
    )
    killed = _kill(process)
    marker.unlink(missing_ok=True)
    verified = _run_verifier("verify-kr02", root, marker)
    return {"before_kill": before_kill, "killed": killed, "verified": verified}


def _run_kr03(root: Path) -> dict[str, object]:
    marker = root / "kr03-marker.json"
    process = _spawn("kr03", root, marker)
    before_kill = _wait_marker(
        process,
        marker,
        "governance_persisted_before_apply",
        timeout=180,
    )
    killed = _kill(process)
    marker.unlink(missing_ok=True)
    verified = _run_verifier("verify-kr03", root, marker)
    return {"before_kill": before_kill, "killed": killed, "verified": verified}


def _wait_committing(
    process: subprocess.Popen[str],
    db_path: Path,
    *,
    timeout: float,
) -> dict[str, str]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if db_path.is_file():
            try:
                with sqlite3.connect(db_path, timeout=0.05) as connection:
                    row = connection.execute(
                        "SELECT action_id, commit_status FROM evolution_actions "
                        "ORDER BY created_at DESC LIMIT 1"
                    ).fetchone()
            except sqlite3.Error:
                row = None
            if row is not None:
                if row[1] != "committing":
                    raise RuntimeError(
                        f"commit escaped kill window with status={row[1]}"
                    )
                return {"action_id": str(row[0]), "commit_status": str(row[1])}
        if process.poll() is not None:
            process.wait()
            stdout, stderr = _process_logs(process)
            raise RuntimeError(
                f"KR-04 child exited before committing state: rc={process.returncode}\n"
                f"stdout:\n{stdout}\nstderr:\n{stderr}"
            )
        time.sleep(0.001)
    raise TimeoutError("timed out waiting for evolution_actions.committing")


def _run_kr04(root: Path) -> dict[str, object]:
    marker = root / "kr04-marker.json"
    start_file = root / "kr04-start.flag"
    process = _spawn("kr04", root, marker, start_file=start_file)
    ready = _wait_marker(
        process,
        marker,
        "ready_before_commit",
        timeout=240,
    )
    start_file.write_text("start\n", encoding="utf-8")
    committing = _wait_committing(process, root / "evidence.db", timeout=60)
    killed = _kill(process)
    marker.unlink(missing_ok=True)
    verified = _run_verifier("verify-kr04", root, marker)
    return {
        "ready": ready,
        "committing": committing,
        "killed": killed,
        "verified": verified,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        choices=("kr02", "kr03", "kr04", "all"),
        default="all",
    )
    parser.add_argument("--root")
    args = parser.parse_args()
    root = (
        Path(args.root).expanduser().resolve()
        if args.root
        else ROOT.parent / f"openspace-b2-live-{uuid.uuid4().hex[:10]}"
    )
    root.mkdir(parents=True, exist_ok=True)
    cases = ("kr02", "kr03", "kr04") if args.case == "all" else (args.case,)
    results: dict[str, object] = {
        "root": str(root),
        "started_at": time.time(),
    }
    for case in cases:
        case_root = root / case
        case_root.mkdir(parents=True, exist_ok=True)
        if case == "kr02":
            results[case] = _run_kr02(case_root)
        elif case == "kr03":
            results[case] = _run_kr03(case_root)
        else:
            results[case] = _run_kr04(case_root)
    results["completed_at"] = time.time()
    output = root / "b2-live-results.json"
    output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"RESULT_PATH={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
