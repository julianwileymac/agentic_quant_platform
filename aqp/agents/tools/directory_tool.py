"""Directory-read tool — the file-system-side of data discovery."""
from __future__ import annotations

from pathlib import Path

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from aqp.config import settings


class DirectoryReadInput(BaseModel):
    path: str | None = Field(default=None, description="Directory to list (defaults to parquet dir).")
    glob: str = Field(default="*.parquet", description="Glob pattern to filter files.")
    depth: int = Field(default=2, description="Walk depth.")


class DirectoryReadTool(BaseTool):
    name: str = "directory_read"
    description: str = (
        "List files in the local data directory (default: Parquet lake). "
        "Returns paths, sizes, and last-modified timestamps."
    )
    args_schema: type[BaseModel] = DirectoryReadInput

    def _run(  # type: ignore[override]
        self,
        path: str | None = None,
        glob: str = "*.parquet",
        depth: int = 2,
    ) -> str:
        root = Path(path or (settings.parquet_dir / "bars"))
        if not root.exists():
            return f"No such directory: {root}"
        lines: list[str] = [f"Listing {root} (glob={glob}, depth={depth})"]
        for p in root.rglob(glob):
            try:
                rel = p.relative_to(root)
                if len(rel.parts) > depth:
                    continue
                size = p.stat().st_size
                lines.append(f"  {rel}  |  {size:,} bytes")
            except Exception:  # pragma: no cover
                continue
        if len(lines) == 1:
            lines.append("  (no matches)")
        return "\n".join(lines)
