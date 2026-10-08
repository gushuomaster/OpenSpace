"""Run the real bundled deliverable Provider for live kill/restart probes."""

from __future__ import annotations

import json
import os
from pathlib import Path


SKILL_ENGINEERING_ROOT = Path(os.environ["SKILL_ENGINEERING_REPO_ROOT"]).resolve()
TARGET = Path(os.environ["GOVERNANCE_TARGET_SKILL_PATH"]).resolve()


def main() -> int:
    from engine import GovernanceEngine
    from engine.host_adapters import build_default_provider_adapters
    from engine.providers import ProviderGateway

    marker = Path(os.environ["B2_MARKER"])
    marker.write_text(
        json.dumps({"parent_pid": os.getpid(), "phase": "starting"}),
        encoding="utf-8",
    )
    adapters = build_default_provider_adapters(
        SKILL_ENGINEERING_ROOT,
        timeout_seconds=300,
    )
    adapter = next(
        item
        for item in adapters
        if item.descriptor.capability == "DELIVERABLE_CONTRACT"
    )
    marker.write_text(
        json.dumps({"parent_pid": os.getpid(), "phase": "invoking"}),
        encoding="utf-8",
    )
    result = ProviderGateway([adapter]).invoke(
        "DELIVERABLE_CONTRACT",
        {
            "target_path": str(TARGET),
            "mode": "AUDIT",
            "inspection_id": "b2-kr01",
            "inspection_nonce": "b2-kr01-nonce",
            "target_digest": GovernanceEngine.artifact_digest(TARGET),
            "artifact_role": "BASELINE",
            "deliverable_contract_applicability": "REQUIRED",
        },
        formal_run=True,
    )
    marker.write_text(
        json.dumps(
            {
                "parent_pid": os.getpid(),
                "phase": "completed",
                "provider_status": result.provider_status.value,
            }
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
