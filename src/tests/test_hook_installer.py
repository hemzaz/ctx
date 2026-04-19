"""
test_hook_installer.py -- Surgical settings.json mutation fixtures.

Covers plan.md §3.7 recipe:
  - install creates .pre-ctx.bak on first run, never overwrites
  - install is idempotent (no double-insert)
  - uninstall strips exactly what install added (all three markers)
  - invalid JSON is refused (backup not clobbered)
  - round-trip: install -> uninstall leaves settings semantically restored
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import hook_installer as hi  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def settings_path(tmp_path: Path) -> Path:
    return tmp_path / "settings.json"


@pytest.fixture()
def ctx_src(tmp_path: Path) -> Path:
    src = tmp_path / "ctx-src"
    src.mkdir()
    return src


@pytest.fixture()
def seeded_settings(settings_path: Path) -> Path:
    """Pre-existing settings with one unrelated hook entry."""
    settings_path.write_text(
        json.dumps({
            "theme": "dark",
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Read",
                        "hooks": [{"type": "command", "command": "echo user-hook"}],
                    }
                ]
            },
        }, indent=2),
        encoding="utf-8",
    )
    return settings_path


# ── install ──────────────────────────────────────────────────────────────────


def test_install_creates_backup_once(seeded_settings: Path, ctx_src: Path) -> None:
    hi.install(seeded_settings, ctx_src)
    backup = seeded_settings.with_suffix(seeded_settings.suffix + ".pre-ctx.bak")
    assert backup.exists(), "first install must create .pre-ctx.bak"
    first_backup_mtime = backup.stat().st_mtime
    first_backup_content = backup.read_text()

    # Tweak settings.json to ensure second install does NOT refresh backup.
    data = json.loads(seeded_settings.read_text())
    data["theme"] = "light"
    seeded_settings.write_text(json.dumps(data, indent=2))

    hi.install(seeded_settings, ctx_src)
    assert backup.stat().st_mtime == first_backup_mtime, (
        "backup must not be overwritten on subsequent installs"
    )
    assert backup.read_text() == first_backup_content


def test_install_inserts_tagged_entry(seeded_settings: Path, ctx_src: Path) -> None:
    hi.install(seeded_settings, ctx_src)
    data = json.loads(seeded_settings.read_text())
    entries = data["hooks"]["PostToolUse"]

    # User's original entry must survive.
    assert any(
        e.get("matcher") == "Read" and e.get(hi._MARKER_KEY) is not True
        for e in entries
    ), "unrelated user hook must be preserved"

    # Our entry must be tagged and present.
    ctx_entries = [e for e in entries if e.get(hi._MARKER_KEY) is True]
    assert len(ctx_entries) == 1
    commands = [h["command"] for h in ctx_entries[0]["hooks"]]
    assert any(hi._SHELL_MARKER in c for c in commands)
    assert any(str(ctx_src) in c for c in commands)


def test_install_idempotent(seeded_settings: Path, ctx_src: Path) -> None:
    hi.install(seeded_settings, ctx_src)
    hi.install(seeded_settings, ctx_src)
    hi.install(seeded_settings, ctx_src)
    data = json.loads(seeded_settings.read_text())
    ctx_count = sum(
        1 for e in data["hooks"]["PostToolUse"] if e.get(hi._MARKER_KEY) is True
    )
    assert ctx_count == 1, "triple install must not produce 3 tagged entries"


def test_install_into_empty_settings(settings_path: Path, ctx_src: Path) -> None:
    # File does not exist yet.
    assert not settings_path.exists()
    hi.install(settings_path, ctx_src)
    data = json.loads(settings_path.read_text())
    assert "hooks" in data
    assert any(
        e.get(hi._MARKER_KEY) is True for e in data["hooks"]["PostToolUse"]
    )


def test_install_refuses_invalid_json(settings_path: Path, ctx_src: Path) -> None:
    settings_path.write_text("{not valid json")
    with pytest.raises(SystemExit):
        hi.install(settings_path, ctx_src)


def test_install_refuses_non_object_settings(
    settings_path: Path, ctx_src: Path
) -> None:
    settings_path.write_text("[1,2,3]")
    with pytest.raises(SystemExit):
        hi.install(settings_path, ctx_src)


def test_install_refuses_non_dict_hooks(settings_path: Path, ctx_src: Path) -> None:
    settings_path.write_text(json.dumps({"hooks": "not a dict"}))
    with pytest.raises(SystemExit):
        hi.install(settings_path, ctx_src)


# ── uninstall ────────────────────────────────────────────────────────────────


def test_uninstall_strips_only_ctx_entries(
    seeded_settings: Path, ctx_src: Path
) -> None:
    hi.install(seeded_settings, ctx_src)
    result = hi.uninstall(seeded_settings, ctx_src)
    assert result["status"] == "ok"
    assert result["removed"] == 1

    data = json.loads(seeded_settings.read_text())
    entries = data["hooks"]["PostToolUse"]
    assert len(entries) == 1
    assert entries[0].get(hi._MARKER_KEY) is not True
    assert entries[0]["matcher"] == "Read"


def test_uninstall_removes_empty_hooks_dict(
    settings_path: Path, ctx_src: Path
) -> None:
    """If ctx was the only hook producer, the hooks dict should vanish."""
    settings_path.write_text(json.dumps({"theme": "dark"}))
    hi.install(settings_path, ctx_src)
    hi.uninstall(settings_path, ctx_src)
    data = json.loads(settings_path.read_text())
    assert "hooks" not in data
    assert data == {"theme": "dark"}


def test_uninstall_noop_when_no_file(tmp_path: Path, ctx_src: Path) -> None:
    result = hi.uninstall(tmp_path / "never-existed.json", ctx_src)
    assert result["status"] == "no-op"


def test_uninstall_matches_by_shell_marker_alone(
    seeded_settings: Path, ctx_src: Path
) -> None:
    """Even if the _ctx key is stripped, the shell-comment marker identifies us."""
    hi.install(seeded_settings, ctx_src)
    data = json.loads(seeded_settings.read_text())
    # Simulate a user manually removing the _ctx: true key
    for e in data["hooks"]["PostToolUse"]:
        e.pop(hi._MARKER_KEY, None)
    seeded_settings.write_text(json.dumps(data, indent=2))

    hi.uninstall(seeded_settings, ctx_src)
    data2 = json.loads(seeded_settings.read_text())
    remaining = data2["hooks"]["PostToolUse"]
    assert len(remaining) == 1 and remaining[0]["matcher"] == "Read"


# ── print_hook ───────────────────────────────────────────────────────────────


def test_print_hook_returns_json_does_not_touch_disk(
    settings_path: Path, ctx_src: Path
) -> None:
    assert not settings_path.exists()
    out = hi.print_hook(ctx_src)
    parsed = json.loads(out)
    assert "PostToolUse" in parsed
    assert parsed["PostToolUse"][0][hi._MARKER_KEY] is True
    assert not settings_path.exists(), "print_hook must not write anything"


# ── round trip ───────────────────────────────────────────────────────────────


def test_install_uninstall_roundtrip_preserves_user_data(
    seeded_settings: Path, ctx_src: Path
) -> None:
    original = json.loads(seeded_settings.read_text())
    hi.install(seeded_settings, ctx_src)
    hi.uninstall(seeded_settings, ctx_src)
    restored = json.loads(seeded_settings.read_text())
    assert restored == original, (
        "after install → uninstall, settings.json must equal the input"
    )
