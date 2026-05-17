"""Local dbt project scaffolding and sandboxed file access."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aqp.config import settings

logger = logging.getLogger(__name__)

_EDITABLE_SUFFIXES = {".sql", ".yml", ".yaml", ".md", ".csv", ".json"}


@dataclass(frozen=True)
class DbtProjectStatus:
    """Serializable state for the local dbt project."""

    project_dir: Path
    profiles_dir: Path
    duckdb_path: Path
    export_dir: Path
    target: str
    exists: bool
    dbt_project_yml: bool
    profiles_yml: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_dir": str(self.project_dir),
            "profiles_dir": str(self.profiles_dir),
            "duckdb_path": str(self.duckdb_path),
            "export_dir": str(self.export_dir),
            "target": self.target,
            "exists": self.exists,
            "dbt_project_yml": self.dbt_project_yml,
            "profiles_yml": self.profiles_yml,
        }


class DbtProjectManager:
    """Owns the generated local dbt project rooted under ``settings`` paths."""

    def __init__(
        self,
        *,
        project_dir: Path | str | None = None,
        profiles_dir: Path | str | None = None,
        duckdb_path: Path | str | None = None,
        export_dir: Path | str | None = None,
        target: str | None = None,
        generated_schema: str | None = None,
        generated_tag: str | None = None,
    ) -> None:
        self.project_dir = Path(project_dir or settings.dbt_project_dir).expanduser().resolve()
        self.profiles_dir = Path(profiles_dir or settings.dbt_profiles_dir).expanduser().resolve()
        self.duckdb_path = Path(duckdb_path or settings.dbt_duckdb_path).expanduser().resolve()
        self.export_dir = Path(export_dir or settings.dbt_export_dir).expanduser().resolve()
        self.target = target or settings.dbt_target
        self.generated_schema = generated_schema or settings.dbt_generated_schema
        self.generated_tag = generated_tag or settings.dbt_generated_tag

    @classmethod
    def from_settings(cls) -> "DbtProjectManager":
        return cls()

    @property
    def target_dir(self) -> Path:
        return self.project_dir / "target"

    @property
    def generated_models_dir(self) -> Path:
        return self.project_dir / "models" / "aqp_generated"

    def status(self) -> DbtProjectStatus:
        return DbtProjectStatus(
            project_dir=self.project_dir,
            profiles_dir=self.profiles_dir,
            duckdb_path=self.duckdb_path,
            export_dir=self.export_dir,
            target=self.target,
            exists=self.project_dir.exists(),
            dbt_project_yml=(self.project_dir / "dbt_project.yml").exists(),
            profiles_yml=(self.profiles_dir / "profiles.yml").exists(),
        )

    def ensure_project(self, *, force: bool = False) -> dict[str, Any]:
        """Create the project skeleton and profile files if missing."""
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        for rel in (
            "models/aqp_generated/datasets",
            "models/aqp_generated/platform",
            "models/aqp_generated/entities",
            "macros",
            "seeds",
            "analyses",
            "snapshots",
            "tests",
        ):
            (self.project_dir / rel).mkdir(parents=True, exist_ok=True)

        written: list[str] = []
        project_yml = self.project_dir / "dbt_project.yml"
        if force or not project_yml.exists():
            project_yml.write_text(
                yaml.safe_dump(self._project_config(), sort_keys=False),
                encoding="utf-8",
            )
            written.append(str(project_yml))

        profiles_yml = self.profiles_dir / "profiles.yml"
        if force or not profiles_yml.exists():
            profiles_yml.write_text(
                yaml.safe_dump(self._profiles_config(), sort_keys=False),
                encoding="utf-8",
            )
            written.append(str(profiles_yml))

        gitkeep = self.generated_models_dir / ".gitkeep"
        if force or not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")
            written.append(str(gitkeep))

        return {"status": self.status().to_dict(), "written": written}

    def list_files(self) -> list[dict[str, Any]]:
        """Return editable files below the project directory."""
        if not self.project_dir.exists():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(self.project_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in _EDITABLE_SUFFIXES:
                continue
            rel = path.relative_to(self.project_dir).as_posix()
            rows.append(
                {
                    "path": rel,
                    "size": path.stat().st_size,
                    "modified_at": path.stat().st_mtime,
                    "generated": rel.startswith("models/aqp_generated/"),
                }
            )
        return rows

    def read_file(self, rel_path: str) -> dict[str, Any]:
        path = self.resolve_project_path(rel_path, for_write=False)
        return {
            "path": path.relative_to(self.project_dir).as_posix(),
            "content": path.read_text(encoding="utf-8"),
            "generated": path.relative_to(self.project_dir).as_posix().startswith(
                "models/aqp_generated/"
            ),
        }

    def write_file(self, rel_path: str, content: str) -> dict[str, Any]:
        path = self.resolve_project_path(rel_path, for_write=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {
            "path": path.relative_to(self.project_dir).as_posix(),
            "size": path.stat().st_size,
        }

    def resolve_project_path(self, rel_path: str, *, for_write: bool) -> Path:
        """Resolve a project-relative path without allowing traversal escapes."""
        raw = Path(rel_path)
        if raw.is_absolute():
            raise ValueError("dbt file paths must be relative to the project")
        path = (self.project_dir / raw).resolve()
        try:
            path.relative_to(self.project_dir)
        except ValueError as exc:
            raise ValueError("dbt file path escapes the configured project directory") from exc
        if path.suffix.lower() not in _EDITABLE_SUFFIXES:
            raise ValueError(f"unsupported dbt file suffix: {path.suffix or '<none>'}")
        if not for_write and not path.exists():
            raise FileNotFoundError(rel_path)
        return path

    def _project_config(self) -> dict[str, Any]:
        return {
            "name": "aqp_dbt",
            "version": "1.0.0",
            "config-version": 2,
            "profile": "aqp",
            "model-paths": ["models"],
            "analysis-paths": ["analyses"],
            "test-paths": ["tests"],
            "seed-paths": ["seeds"],
            "macro-paths": ["macros"],
            "snapshot-paths": ["snapshots"],
            "target-path": "target",
            "clean-targets": ["target", "dbt_packages"],
            "vars": {
                "aqp_export_dir": self.export_dir.as_posix(),
                "aqp_generated_tag": self.generated_tag,
            },
            "models": {
                "aqp_dbt": {
                    "+materialized": "view",
                    "aqp_generated": {
                        "+schema": self.generated_schema,
                        "+tags": [self.generated_tag],
                    },
                }
            },
        }

    def _profiles_config(self) -> dict[str, Any]:
        return {
            "aqp": {
                "target": self.target,
                "outputs": {
                    self.target: {
                        "type": "duckdb",
                        "path": self.duckdb_path.as_posix(),
                        "threads": 4,
                    }
                },
            }
        }
