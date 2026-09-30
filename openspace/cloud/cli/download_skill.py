#!/usr/bin/env python3
"""Acquire a Skill Candidate or package inspection artifacts from OpenSpace cloud.

Usage:
    openspace-download-skill --skill-id "<cloud_skill_uuid>" --output-dir ./skills/
    openspace-download-skill --package-id "<package_uuid>" --output-dir ./skills/
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import sys
from pathlib import Path

from openspace.cloud.client import OpenSpaceClient
from openspace.cloud.config import load_cloud_config, normalize_cloud_base_url


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="openspace-download-skill",
        description="Acquire a quarantined Skill Candidate from OpenSpace cloud",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--skill-id", help="Cloud skill ID. v2 UUIDs use /api/v2/skills/{id}/bundle.")
    target.add_argument("--package-id", help="v2 package UUID to download as a subtree bundle")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Intended formal placement root for a Skill Candidate",
    )
    parser.add_argument("--cloud-base-url", default=None, help="Override OpenSpace cloud service root URL")
    parser.add_argument("--audience", default="requester_visible", choices=["requester_visible", "public"])
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Allow refresh of an equal-id quarantined Candidate only; never "
            "overwrite a formally installed Skill"
        ),
    )

    args = parser.parse_args()

    output_base = Path(args.output_dir).resolve()

    if args.package_id:
        print(f"Fetching package: {args.package_id} ...", file=sys.stderr)
    else:
        print(f"Fetching skill: {args.skill_id} ...", file=sys.stderr)

    try:
        config = load_cloud_config()
        if args.cloud_base_url:
            config = replace(config, base_url=normalize_cloud_base_url(args.cloud_base_url))
        client = OpenSpaceClient(config)
        if args.package_id:
            result = client.import_package_bundle(args.package_id, output_base, audience=args.audience)
        else:
            result = client.import_skill(args.skill_id, output_base, audience=args.audience)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if result.get("status") == "already_exists":
        print(
            "ERROR: A formal Skill directory already exists and this command "
            "will not overwrite it.",
            file=sys.stderr,
        )
        sys.exit(1)

    files = result.get("files", [])
    output_path = result.get("candidate_path") or result.get("artifact_path") or ""
    print(f"  Extracted {len(files)} file(s) to {output_path}", file=sys.stderr)
    for f in files:
        print(f"    {f}", file=sys.stderr)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result.get("status") == "governance_required":
        print(
            f"\nCandidate quarantined at {output_path}; Governance required",
            file=sys.stderr,
        )
    elif result.get("inspection_only"):
        print(f"\nPackage inspection artifacts: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
