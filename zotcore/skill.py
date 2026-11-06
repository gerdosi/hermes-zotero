"""The skill bundled with the plugin (registered through Hermes' ctx.register_skill)."""
from __future__ import annotations

from pathlib import Path

SKILL_NAME = "zotero-library"
SKILL_DESCRIPTION = "Research questions: check the user's Zotero library first"


def skill_path(plugin_root) -> Path:
    """SKILL.md of the bundled skill under the plugin's root folder."""
    return Path(plugin_root) / "skills" / SKILL_NAME / "SKILL.md"
