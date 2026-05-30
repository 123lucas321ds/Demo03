"""Load workspace or builtin skills by name."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SkillNotFound(FileNotFoundError):
    """Raised when a skill cannot be found in any configured root."""


@dataclass(frozen=True, slots=True)
class SkillLoader:
    """Resolve ``skills/{name}/SKILL.md`` from configured roots."""

    workspace: Path
    builtin_roots: tuple[Path, ...] = ()

    def load(self, name: str) -> dict[str, str]:
        safe_name = self._safe_name(name)
        for root in self._roots():
            path = root / safe_name / "SKILL.md"
            if path.exists():
                return {
                    "name": safe_name,
                    "path": str(path),
                    "content": path.read_text(encoding="utf-8"),
                }
        raise SkillNotFound(f"skill {safe_name!r} not found")

    def _roots(self) -> list[Path]:
        return [self.workspace / "skills", *self.builtin_roots]

    @staticmethod
    def _safe_name(name: str) -> str:
        value = name.strip()
        if not value or any(part in value for part in ("..", "/", "\\")):
            raise ValueError("skill name must be a simple directory name")
        return value

    @staticmethod
    def _parse_frontmatter(text: str) -> dict[str, Any] | None:
        """Parse YAML-like frontmatter from a SKILL.md string.
        Returns a dict with keys like name, description, always, or None on failure.
        No PyYAML dependency — simple line-by-line parsing.
        """
        if not text.startswith("---"):
            return None
        parts = text.split("---", 2)
        if len(parts) < 3:
            return None
        meta: dict[str, Any] = {}
        for line in parts[1].strip().splitlines():
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip()
            if v == "true":
                v = True
            elif v == "false":
                v = False
            meta[k] = v
        return meta if "name" in meta else None

    def scan_skills(self) -> list[dict[str, Any]]:
        """Scan all skill directories across all roots.
        Workspace skills take priority over builtin skills.
        Returns list of metadata dicts (name, description, always, path).
        """
        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for root in self._roots():
            if not root.exists():
                continue
            for entry in sorted(root.iterdir()):
                if not entry.is_dir():
                    continue
                name = entry.name
                if name in seen:
                    continue
                skill_md = entry / "SKILL.md"
                if not skill_md.exists():
                    continue
                text = skill_md.read_text(encoding="utf-8")
                meta = self._parse_frontmatter(text)
                if meta is None:
                    continue
                meta["path"] = str(skill_md)
                seen.add(name)
                results.append(meta)
        return results

    def get_always_skills(self) -> list[dict[str, str]]:
        """Return (name, content) for every always:true skill."""
        always: list[dict[str, str]] = []
        for meta in self.scan_skills():
            if meta.get("always") is True:
                loaded = self.load(meta["name"])
                always.append({
                    "name": meta["name"],
                    "content": loaded["content"],
                })
        return always
