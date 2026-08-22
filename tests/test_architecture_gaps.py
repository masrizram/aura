"""Regression tests for gaps discovered in the blind documentation rebuild (RULE 10)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from aura import cli as cli_mod
from aura.config import DatabaseConfig
from aura.db import Database
from aura.engine import Engine


class TestGAPDBPathResolution01:
    """DB path MUST resolve against repo_root, not process CWD."""

    def test_relative_db_path_anchored_to_repo_root(self) -> None:
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            ra, rb = Path(a), Path(b)
            (ra / "src").mkdir()
            (ra / "src" / "a.py").write_text("print('A')\n")
            (rb / "src").mkdir()
            (rb / "src" / "b.py").write_text("print('B')\n")
            ea = Engine(ra)
            out_a = ea.run_audit()
            eb = Engine(rb)
            out_b = eb.run_audit()
            ea.db.close()
            eb.db.close()
            assert (ra / ".aura" / "state" / "aura.db").exists()
            assert (rb / ".aura" / "state" / "aura.db").exists()
            assert out_a["cycle_number"] == out_b["cycle_number"]

    def test_absolute_db_path_unchanged(self, tmp_path: Path) -> None:
        abs_db = tmp_path / "custom.db"
        db = Database(DatabaseConfig(path=str(abs_db)), repo_root=tmp_path)
        db.initialize()
        assert db._path == abs_db
        db.close()

    def test_relative_db_path_without_repo_root_falls_back_to_cwd(self) -> None:
        db = Database(DatabaseConfig(path=".aura/state/x.db"))
        assert db._path == Path(".aura/state/x.db")


class TestGAPCLIVersionBanner02:
    """CLI banner docstring must reflect the package version (no stale literal)."""

    def test_banner_uses_version_constant(self) -> None:
        candidates = [
            getattr(cli_mod.cli, "help", None),
            getattr(cli_mod.cli, "short_help", None),
            getattr(cli_mod.cli.callback, "__doc__", None)
            if hasattr(cli_mod.cli, "callback")
            else None,
        ]
        doc = next((d for d in candidates if d), "")
        assert f"v{cli_mod.VERSION}" in doc, f"banner missing current version: {doc!r}"
        assert "v3.5.0" not in doc, f"stale v3.5.0 literal present: {doc!r}"
