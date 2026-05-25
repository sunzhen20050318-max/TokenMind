"""Skills loader for agent capabilities."""

import glob
import importlib.util
import json
import os
import re
import shutil
import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=128)
def _has_python_package(name: str) -> bool:
    """Cached check: is ``name`` importable in the current interpreter?"""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


@lru_cache(maxsize=128)
def _has_bin(name: str) -> bool:
    """Check for a CLI binary, with platform-aware fallbacks for cases
    where the executable lives inside a GUI install whose author forgot
    to put it on PATH:

    * macOS — CLIs hidden inside ``/Applications/Foo.app/Contents/...``
      (LibreOffice's ``soffice`` is the canonical example).
    * Windows — installers that default to ``C:\\Program Files\\Foo\\``
      without offering "Add to PATH" (LibreOffice's ``soffice.exe``
      lives at ``C:\\Program Files\\LibreOffice\\program\\soffice.exe``).

    Cached because SkillsLoader can be re-instantiated several times per
    turn and we don't want to re-glob install roots each call.
    """
    if shutil.which(name):
        return True

    patterns: tuple[str, ...] = ()
    if sys.platform == "darwin":
        home_apps = str(Path.home() / "Applications")
        patterns = (
            f"/Applications/*/Contents/MacOS/{name}",
            f"/Applications/*/Contents/Resources/{name}",
            f"/Applications/*/Contents/Resources/bin/{name}",
            f"/Applications/*/Contents/Resources/app/bin/{name}",
            f"{home_apps}/*/Contents/MacOS/{name}",
        )
    elif sys.platform == "win32":
        exe = name if name.lower().endswith(".exe") else f"{name}.exe"
        roots: list[str] = []
        for env_key in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
            value = os.environ.get(env_key)
            if value:
                roots.append(value)
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            roots.append(os.path.join(local_appdata, "Programs"))
        # Skip duplicates that creep in when the 32-bit and 64-bit env
        # vars resolve to the same directory on a 32-bit-only host.
        seen: set[str] = set()
        ordered_roots: list[str] = []
        for r in roots:
            if r not in seen:
                seen.add(r)
                ordered_roots.append(r)
        subdirs = ("", "bin", "program")  # "program" = LibreOffice layout
        patterns = tuple(
            f"{root}/*/{sub + '/' if sub else ''}{exe}"
            for root in ordered_roots
            for sub in subdirs
        )

    for pattern in patterns:
        for match in glob.iglob(pattern):
            if os.access(match, os.X_OK):
                return True
    return False

# Default builtin skills directory (relative to this file)
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"


class SkillsLoader:
    """
    Loader for agent skills.

    Skills are markdown files (SKILL.md) that teach the agent how to use
    specific tools or perform certain tasks.
    """

    def __init__(
        self,
        workspace: Path,
        builtin_skills_dir: Path | None = None,
        disabled_skills: list[str] | None = None,
    ):
        self.workspace = workspace
        self.workspace_skills = workspace / "skills"
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR
        self._disabled_skills = set(disabled_skills or [])

    def _discover_skills(self) -> list[dict[str, str]]:
        """Scan workspace + built-in directories for every available skill, without filtering."""
        skills: list[dict[str, str]] = []
        if self.workspace_skills.exists():
            for skill_dir in self.workspace_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        skills.append(
                            {"name": skill_dir.name, "path": str(skill_file), "source": "workspace"}
                        )

        if self.builtin_skills and self.builtin_skills.exists():
            for skill_dir in self.builtin_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists() and not any(
                        s["name"] == skill_dir.name for s in skills
                    ):
                        skills.append(
                            {"name": skill_dir.name, "path": str(skill_file), "source": "builtin"}
                        )
        return skills

    def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
        """
        List skills that should be exposed to the agent.

        Disabled skills (via config) are always excluded. When ``filter_unavailable``
        is true, skills with unmet requirements are also dropped.
        """
        skills = [
            skill for skill in self._discover_skills() if skill["name"] not in self._disabled_skills
        ]
        if filter_unavailable:
            return [s for s in skills if self._check_requirements(self._get_skill_meta(s["name"]))]
        return skills

    def list_all_skills(self) -> list[dict[str, str]]:
        """Return every installed skill, ignoring disabled / unavailable filters.

        This is the view the Settings UI uses to render toggles.
        """
        return self._discover_skills()

    def load_skill(self, name: str) -> str | None:
        """
        Load a skill by name.

        Args:
            name: Skill name (directory name).

        Returns:
            Skill content or None if not found.
        """
        # Check workspace first
        workspace_skill = self.workspace_skills / name / "SKILL.md"
        if workspace_skill.exists():
            return workspace_skill.read_text(encoding="utf-8")

        # Check built-in
        if self.builtin_skills:
            builtin_skill = self.builtin_skills / name / "SKILL.md"
            if builtin_skill.exists():
                return builtin_skill.read_text(encoding="utf-8")

        return None

    def load_skills_for_context(self, skill_names: list[str]) -> str:
        """
        Load specific skills for inclusion in agent context.

        Args:
            skill_names: List of skill names to load.

        Returns:
            Formatted skills content.
        """
        parts = []
        for name in skill_names:
            content = self.load_skill(name)
            if content:
                content = self._strip_frontmatter(content)
                parts.append(f"### Skill: {name}\n\n{content}")

        return "\n\n---\n\n".join(parts) if parts else ""

    def build_skills_summary(self) -> str:
        """
        Build a summary of all skills (name, description, path, availability).

        This is used for progressive loading - the agent can read the full
        skill content using read_file when needed.

        Returns:
            XML-formatted skills summary.
        """
        # Respect the user's disabled list so the agent only sees skills it may use.
        all_skills = self.list_skills(filter_unavailable=False)
        if not all_skills:
            return ""

        def escape_xml(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        lines = ["<skills>"]
        for s in all_skills:
            name = escape_xml(s["name"])
            path = s["path"]
            desc = escape_xml(self._get_skill_description(s["name"]))
            skill_meta = self._get_skill_meta(s["name"])
            available = self._check_requirements(skill_meta)

            lines.append(f"  <skill available=\"{str(available).lower()}\">")
            lines.append(f"    <name>{name}</name>")
            lines.append(f"    <description>{desc}</description>")
            lines.append(f"    <location>{path}</location>")

            # Show missing requirements for unavailable skills
            if not available:
                missing = self._get_missing_requirements(skill_meta)
                if missing:
                    lines.append(f"    <requires>{escape_xml(missing)}</requires>")

            lines.append("  </skill>")
        lines.append("</skills>")

        return "\n".join(lines)

    def build_skill_route_index(self, max_hints: int = 10) -> str:
        """Build a compact one-line-per-skill index for create/update routing."""

        skills = self.list_skills(filter_unavailable=False)
        if not skills:
            return ""

        lines: list[str] = []
        for skill in skills:
            name = skill["name"]
            desc = self._get_skill_description(name)
            meta = self._get_skill_meta(name)
            hints = self._skill_hints(name, desc, meta, max_hints=max_hints)
            hint_text = ", ".join(hints) if hints else "none"
            source = skill.get("source") or "unknown"
            path = skill.get("path") or ""
            lines.append(f"- {name}: {desc} | hints: {hint_text} | source: {source} | path: {path}")
        return "\n".join(lines)

    def _get_missing_requirements(self, skill_meta: dict) -> str:
        """Get a description of missing requirements."""
        missing = []
        requires = skill_meta.get("requires", {})
        for b in requires.get("bins", []):
            if not _has_bin(b):
                missing.append(f"CLI: {b}")
        for env in requires.get("env", []):
            if not os.environ.get(env):
                missing.append(f"ENV: {env}")
        for pkg in requires.get("python", []):
            if not _has_python_package(pkg):
                missing.append(f"pip: {pkg}")
        return ", ".join(missing)

    def _get_skill_description(self, name: str) -> str:
        """Get the description of a skill from its frontmatter."""
        meta = self.get_skill_metadata(name)
        if meta and meta.get("description"):
            return meta["description"]
        return name  # Fallback to skill name

    @classmethod
    def _skill_hints(
        cls,
        name: str,
        description: str,
        skill_meta: dict,
        max_hints: int,
    ) -> list[str]:
        raw_items: list[str] = [name, description]
        for key in ("triggers", "hints", "capabilities"):
            value = skill_meta.get(key)
            if isinstance(value, list):
                raw_items.extend(str(item) for item in value)
            elif isinstance(value, str):
                raw_items.append(value)
        scope = skill_meta.get("scope")
        if isinstance(scope, str):
            raw_items.append(scope)

        seen: set[str] = set()
        hints: list[str] = []
        for item in raw_items:
            for token in cls._hint_tokens(item):
                lowered = token.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                hints.append(token)
                if len(hints) >= max_hints:
                    return hints
        return hints

    @staticmethod
    def _hint_tokens(text: str) -> list[str]:
        tokens = re.findall(r"[A-Za-z0-9_.:/+-]{3,}|[\u4e00-\u9fff]{2,}", text or "")
        return [token.strip("-_.,:;/ ") for token in tokens if token.strip("-_.,:;/ ")]

    def _strip_frontmatter(self, content: str) -> str:
        """Remove YAML frontmatter from markdown content."""
        if content.startswith("---"):
            match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
            if match:
                return content[match.end():].strip()
        return content

    def _parse_tokenmind_metadata(self, raw: str) -> dict:
        """Parse skill metadata JSON from frontmatter (supports tokenmind and openclaw keys)."""
        try:
            data = json.loads(raw)
            return data.get("tokenmind", data.get("openclaw", {})) if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _check_requirements(self, skill_meta: dict) -> bool:
        """Check if skill requirements are met (bins, env vars, python packages).

        ``requires.python`` lets a skill declare importable module names. We
        check via ``importlib.util.find_spec`` (cached) so failed imports
        from missing optional deps show up the same way missing CLIs do —
        as a ``<requires>pip: X</requires>`` annotation in the skill list.
        """
        requires = skill_meta.get("requires", {})
        for b in requires.get("bins", []):
            if not _has_bin(b):
                return False
        for env in requires.get("env", []):
            if not os.environ.get(env):
                return False
        for pkg in requires.get("python", []):
            if not _has_python_package(pkg):
                return False
        return True

    def _get_skill_meta(self, name: str) -> dict:
        """Get tokenmind metadata for a skill (cached in frontmatter)."""
        meta = self.get_skill_metadata(name) or {}
        return self._parse_tokenmind_metadata(meta.get("metadata", ""))

    def get_always_skills(self) -> list[str]:
        """Get skills marked as always=true that meet requirements."""
        result = []
        for s in self.list_skills(filter_unavailable=True):
            meta = self.get_skill_metadata(s["name"]) or {}
            skill_meta = self._parse_tokenmind_metadata(meta.get("metadata", ""))
            if skill_meta.get("always") or meta.get("always"):
                result.append(s["name"])
        return result

    def get_skill_metadata(self, name: str) -> dict | None:
        """
        Get metadata from a skill's frontmatter.

        Args:
            name: Skill name.

        Returns:
            Metadata dict or None.
        """
        content = self.load_skill(name)
        if not content:
            return None

        if content.startswith("---"):
            match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                # Simple YAML parsing
                metadata = {}
                for line in match.group(1).split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        metadata[key.strip()] = value.strip().strip('"\'')
                return metadata

        return None
