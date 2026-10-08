"""Read-only visibility admission for managed Skill artifacts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from engine.inventory import digest_tree

from openspace.cloud.candidate_lifecycle import (
    CandidateManifest,
    CandidateRepository,
    CandidateStatus,
    candidate_identity,
    formal_candidate_path,
)


@dataclass(frozen=True, slots=True)
class CandidateVisibilityDecision:
    allowed: bool
    code: str
    candidate_id: str | None = None


@dataclass(frozen=True, slots=True)
class _CandidateMatch:
    candidate_id: str
    manifest: CandidateManifest | None
    invalid: bool


class CandidateVisibilityPolicy:
    """Admit ordinary Skills and only fully installed managed Candidates."""

    def __init__(self, repository: CandidateRepository) -> None:
        self.repository = repository

    def inspect(self, skill_dir: str | Path) -> CandidateVisibilityDecision:
        lexical = Path(os.path.abspath(Path(skill_dir).expanduser()))
        try:
            resolved = lexical.resolve(strict=False)
        except OSError:
            return CandidateVisibilityDecision(False, "SKILL_PATH_INVALID")

        marker_decision = self._inspect_package_markers(lexical, resolved)
        if marker_decision is not None:
            return marker_decision

        quarantine = self.repository.quarantine_root.resolve(strict=False)
        if resolved == quarantine or resolved.is_relative_to(quarantine):
            return self._quarantine_decision(resolved, quarantine)

        matches = self._formal_matches(resolved)
        if len(matches) > 1:
            return CandidateVisibilityDecision(
                False, "CANDIDATE_OWNERSHIP_AMBIGUOUS"
            )
        if not matches:
            return CandidateVisibilityDecision(True, "ORDINARY_LOCAL_SKILL")

        match = matches[0]
        if match.invalid or match.manifest is None:
            return CandidateVisibilityDecision(
                False, "CANDIDATE_RECORD_INVALID", match.candidate_id
            )
        return self._installed_decision(match.manifest, resolved)

    def _inspect_package_markers(
        self,
        lexical: Path,
        resolved: Path,
    ) -> CandidateVisibilityDecision | None:
        visited: set[Path] = set()
        for start in (lexical, resolved):
            for directory in (start, *start.parents):
                normalized = Path(os.path.normcase(str(directory)))
                if normalized in visited:
                    continue
                visited.add(normalized)
                marker = directory / ".cloud_package.json"
                if not marker.is_file():
                    continue
                try:
                    payload = json.loads(marker.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    return CandidateVisibilityDecision(
                        False, "INVALID_INSPECTION_MARKER"
                    )
                if not isinstance(payload, dict) or not isinstance(
                    payload.get("inspection_only"), bool
                ):
                    return CandidateVisibilityDecision(
                        False, "INVALID_INSPECTION_MARKER"
                    )
                if payload["inspection_only"]:
                    return CandidateVisibilityDecision(
                        False, "INSPECTION_ONLY_PACKAGE"
                    )
        return None

    def _quarantine_decision(
        self,
        resolved: Path,
        quarantine: Path,
    ) -> CandidateVisibilityDecision:
        relative = resolved.relative_to(quarantine)
        candidate_id = relative.parts[0] if relative.parts else None
        if candidate_id not in self.repository.candidate_ids():
            return CandidateVisibilityDecision(
                False, "CANDIDATE_QUARANTINED", candidate_id
            )
        try:
            manifest = self.repository.load_manifest(candidate_id)
            state = self.repository.load_state(candidate_id)
            if manifest.candidate_id != candidate_id or state.schema_version != "1.0":
                raise ValueError("Candidate record identity mismatch")
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return CandidateVisibilityDecision(
                False, "CANDIDATE_RECORD_INVALID", candidate_id
            )
        return CandidateVisibilityDecision(
            False, "CANDIDATE_QUARANTINED", candidate_id
        )

    def _formal_matches(self, resolved: Path) -> list[_CandidateMatch]:
        matches: list[_CandidateMatch] = []
        for candidate_id in self.repository.candidate_ids():
            try:
                manifest = self.repository.load_manifest(candidate_id)
                target = formal_candidate_path(manifest)
            except (OSError, UnicodeError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                target = self._best_effort_formal_path(candidate_id)
                if target == resolved:
                    matches.append(_CandidateMatch(candidate_id, None, True))
                continue
            if target != resolved:
                continue
            try:
                state = self.repository.load_state(candidate_id)
                invalid = (
                    manifest.schema_version != "1.0"
                    or state.schema_version != "1.0"
                    or manifest.candidate_id != candidate_id
                    or candidate_identity(
                        cloud_skill_id=manifest.cloud_skill_id,
                        source_bundle_sha256=manifest.source_bundle_sha256,
                        source_manifest_hash=manifest.source_manifest_hash,
                        source_integrity_status=manifest.source_integrity_status,
                        candidate_digest=manifest.candidate_digest,
                        final_skill_id=manifest.final_skill_id,
                        final_directory_name=manifest.final_directory_name,
                        intended_install_parent=manifest.intended_install_parent,
                        local_category_path=manifest.local_category_path,
                    )
                    != candidate_id
                )
            except (OSError, UnicodeError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                invalid = True
            matches.append(_CandidateMatch(candidate_id, manifest, invalid))
        return matches

    def _best_effort_formal_path(self, candidate_id: str) -> Path | None:
        try:
            payload: Any = json.loads(
                self.repository.manifest_path(candidate_id).read_text(encoding="utf-8")
            )
            if not isinstance(payload, dict):
                return None
            parent = Path(str(payload["intended_install_parent"])).expanduser().resolve()
            category = PurePosixPath(
                str(payload["local_category_path"]).replace("\\", "/")
            )
            name = str(payload["final_directory_name"])
            if (
                not name
                or "/" in name
                or "\\" in name
                or category.is_absolute()
                or any(part in {"", ".", ".."} for part in category.parts)
            ):
                return None
            target = parent.joinpath(*category.parts, name).resolve()
            return target if target.is_relative_to(parent) else None
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def _installed_decision(
        self,
        manifest: CandidateManifest,
        resolved: Path,
    ) -> CandidateVisibilityDecision:
        candidate_id = manifest.candidate_id
        try:
            state = self.repository.load_state(candidate_id)
            if state.status is not CandidateStatus.INSTALLED:
                return CandidateVisibilityDecision(
                    False, "CANDIDATE_NOT_INSTALLED", candidate_id
                )
            binding = self.repository.load_governance_binding(candidate_id)
            payload = self.repository.payload_path(manifest).resolve(strict=True)
            installed = Path(str(state.installed_path)).expanduser().resolve(strict=True)
            receipt_digest = str(state.receipt_digest or "")
            if (
                installed != resolved
                or state.installed_digest != manifest.candidate_digest
                or not receipt_digest
                or binding.schema_version != "1.0"
                or binding.candidate_id != candidate_id
                or binding.candidate_manifest_digest
                != self.repository.manifest_digest(candidate_id)
                or Path(binding.canonical_payload_path).expanduser().resolve(strict=True)
                != payload
                or binding.candidate_digest != manifest.candidate_digest
                or binding.managed_completion_receipt_digest != receipt_digest
                or digest_tree(installed) != manifest.candidate_digest
            ):
                raise ValueError("installed Candidate binding mismatch")
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return CandidateVisibilityDecision(
                False, "CANDIDATE_RECORD_INVALID", candidate_id
            )
        return CandidateVisibilityDecision(
            True, "INSTALLED_CANDIDATE", candidate_id
        )


__all__ = ["CandidateVisibilityDecision", "CandidateVisibilityPolicy"]
