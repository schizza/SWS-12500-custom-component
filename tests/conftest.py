"""Pytest configuration for tests under `dev/tests`.

Goals:
- Make `custom_components.*` importable.
- Keep this file lightweight and avoid global HA test-harness side effects.

Repository layout:
- Root custom components: `SWS-12500/custom_components/...` (symlinked to `dev/custom_components/...`)
- Integration sources: `SWS-12500/dev/custom_components/...`

Note:
Some tests use lightweight `hass` stubs (e.g. SimpleNamespace) that are not compatible with
Home Assistant's full test fixtures. Do NOT enable HA-only fixtures globally here.
Instead, request such fixtures (e.g. `enable_custom_integrations`) explicitly in the specific
tests that need HA's integration loader / flow managers.

"""

from __future__ import annotations

from pathlib import Path
import sys


def pytest_configure() -> None:
    """Adjust sys.path so imports and HA loader discovery work in tests."""
    repo_root = Path(__file__).resolve().parents[2]  # .../SWS-12500
    dev_root = repo_root / "dev"

    # Ensure the repo root is importable so HA can find `custom_components/<domain>/manifest.json`.
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

    # Also ensure `dev/` is importable for direct imports from dev tooling/tests.
    dev_root_str = str(dev_root)
    if dev_root_str not in sys.path:
        sys.path.insert(0, dev_root_str)
