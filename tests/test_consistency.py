"""Consistency checks between the files of the integration."""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

import custom_components.eprowallbox as integration
from custom_components.eprowallbox.const import FRONTEND_VERSION

COMPONENT = Path(integration.__file__).parent


def _keys(data: dict, prefix: str = "") -> set[str]:
    """Flatten the key paths of a nested dict."""
    paths: set[str] = set()
    for key, value in data.items():
        path = f"{prefix}.{key}"
        paths.add(path)
        if isinstance(value, dict):
            paths |= _keys(value, path)
    return paths


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest() -> None:
    """pymodbus is a requirement (not an integration dependency)."""
    manifest = _json(COMPONENT / "manifest.json")
    assert "pymodbus" not in manifest["dependencies"]
    assert any(req.startswith("pymodbus") for req in manifest["requirements"])
    assert {"frontend", "http"} <= set(manifest["dependencies"])
    assert manifest["config_flow"] is True


def test_every_platform_has_its_own_module() -> None:
    """Each platform module sets up the platform it is named after."""
    for platform in integration.PLATFORMS:
        source = (COMPONENT / f"{platform.value}.py").read_text(encoding="utf-8")
        first_line = source.splitlines()[0].lower()
        expected = platform.value.replace("_", " ")
        assert first_line.startswith(f'"""{expected} platform'), (
            f"{platform.value}.py does not look like the {expected} platform"
        )


def test_no_unused_service_declared() -> None:
    """A registered service needs a services.yaml (and vice versa)."""
    sources = "\n".join(path.read_text(encoding="utf-8") for path in COMPONENT.glob("*.py"))
    registers_service = "services.async_register" in sources
    assert registers_service == (COMPONENT / "services.yaml").exists()


def test_no_import_of_missing_modules() -> None:
    """Relative imports point to modules that exist."""
    for path in COMPONENT.glob("*.py"):
        for module in re.findall(r"^from \.(\w+) import", path.read_text(encoding="utf-8"), re.M):
            assert (COMPONENT / f"{module}.py").exists(), f"{path.name} imports .{module}"


def test_strings_match_english_translation() -> None:
    """strings.json is the source of translations/en.json."""
    assert _json(COMPONENT / "strings.json") == _json(COMPONENT / "translations" / "en.json")


@pytest.mark.parametrize("lang", ["de", "es", "fr"])
def test_translations_have_the_same_keys(lang: str) -> None:
    """Every translation defines the same keys as strings.json."""
    reference = _keys(_json(COMPONENT / "strings.json"))
    assert _keys(_json(COMPONENT / "translations" / f"{lang}.json")) == reference


def test_card_version_matches_constant() -> None:
    """FRONTEND_VERSION (cache busting) follows the version of the card."""
    card = (COMPONENT / "frontend" / "eprowallbox-card.js").read_text(encoding="utf-8")
    match = re.search(r'const CARD_VERSION = "([^"]+)"', card)
    assert match
    assert match.group(1) == FRONTEND_VERSION
