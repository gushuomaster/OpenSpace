import importlib
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version


PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _project_mcp_requirement() -> Requirement:
    project = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    return next(
        Requirement(item)
        for item in project["dependencies"]
        if Requirement(item).name == "mcp"
    )


def _requirements_file_mcp_requirement() -> Requirement:
    requirement_lines = [
        line.split("#", 1)[0].strip()
        for line in (PROJECT_ROOT / "requirements.txt").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    return next(
        Requirement(line)
        for line in requirement_lines
        if line
        if Requirement(line).name == "mcp"
    )


def test_packaging_inputs_exclude_unsupported_mcp_v2() -> None:
    for requirement in (
        _project_mcp_requirement(),
        _requirements_file_mcp_requirement(),
    ):
        assert Version("1.30.0") in requirement.specifier
        assert Version("2.0.0") not in requirement.specifier


def test_connector_imports_with_supported_mcp_exception_api() -> None:
    connector_module = importlib.import_module(
        "openspace.grounding.backends.mcp.transport.connectors.base"
    )

    assert issubclass(connector_module.McpError, Exception)
