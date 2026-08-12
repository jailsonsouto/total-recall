"""
tests/test_backup.py — Backup seguro e compactado dos bancos via SQLite Backup API

Cobre: resolução de pasta padrão (Desktop/macOS vs. pergunta), backup real
via Backup API (banco resultante íntegro e consultável), compactação em
.zip (sem deixar .db cru no destino), pular banco ausente sem erro, e
poda dos backups antigos por --keep.
"""

import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from total_recall.backup import (
    backup_all,
    backup_one,
    default_backup_root,
    prune_old_backups,
)
from total_recall.database import Database


def _make_db(path: Path) -> Path:
    """Banco real via Database() — schema completo, WAL ativo (como em produção)."""
    db = Database(db_path=path)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, project_path, file_path, file_hash) "
            "VALUES ('s1', '/tmp/proj', '/tmp/proj/s1.jsonl', 'hash1')"
        )
    return path


class TestDefaultBackupRoot:
    def test_macos_with_desktop_returns_desktop(self, tmp_path):
        home = tmp_path
        (home / "Desktop").mkdir()
        root = default_backup_root(home=home, is_macos=True)
        assert root == home / "Desktop"

    def test_macos_without_desktop_returns_none(self, tmp_path):
        root = default_backup_root(home=tmp_path, is_macos=True)
        assert root is None

    def test_non_macos_returns_none_even_with_desktop(self, tmp_path):
        (tmp_path / "Desktop").mkdir()
        root = default_backup_root(home=tmp_path, is_macos=False)
        assert root is None


class TestBackupOne:
    """backup_one() é a etapa intermediária (.db cru numa pasta temporária) —
    quem chama (backup_all) é responsável por compactar e descartar."""

    def test_produces_readable_standalone_db(self, tmp_path):
        src = _make_db(tmp_path / "src" / "total-recall.db")
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        dest_path = backup_one(src, dest_dir)

        assert dest_path == dest_dir / "total-recall.db"
        assert dest_path.exists()
        conn = sqlite3.connect(str(dest_path))
        row = conn.execute("SELECT session_id FROM sessions").fetchone()
        assert row[0] == "s1"
        conn.close()

    def test_missing_source_returns_none(self, tmp_path):
        result = backup_one(tmp_path / "nao-existe.db", tmp_path)
        assert result is None

    def test_reports_progress(self, tmp_path):
        src = _make_db(tmp_path / "src" / "total-recall.db")
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        calls = []
        backup_one(src, dest_dir, progress=lambda done, total: calls.append((done, total)))

        assert calls, "esperava ao menos uma chamada de progresso"
        last_done, last_total = calls[-1]
        assert last_done == last_total


class TestBackupAll:
    def test_produces_single_zip_with_both_databases(self, tmp_path):
        db_a = _make_db(tmp_path / "a.db")
        db_b = _make_db(tmp_path / "b.db")
        dest_root = tmp_path / "dest"

        run = backup_all(dest_root, databases=[("a", db_a), ("b", db_b)])

        assert run.zip_path is not None
        assert run.zip_path.suffix == ".zip"
        assert run.zip_path.exists()
        with zipfile.ZipFile(run.zip_path) as zf:
            assert set(zf.namelist()) == {"a.db", "b.db"}

    def test_no_raw_db_left_next_to_zip(self, tmp_path):
        existing = _make_db(tmp_path / "real.db")
        dest_root = tmp_path / "dest"

        run = backup_all(dest_root, databases=[("real", existing)])

        leftovers = list(run.zip_path.parent.glob("*.db"))
        assert leftovers == []

    def test_backs_up_only_existing_databases(self, tmp_path):
        existing = _make_db(tmp_path / "real.db")
        missing = tmp_path / "nao-existe.db"
        dest_root = tmp_path / "dest"

        run = backup_all(dest_root, databases=[("real", existing), ("fantasma", missing)])

        assert run.any_succeeded
        by_label = {r.label: r for r in run.results}
        assert by_label["real"].included
        assert not by_label["fantasma"].included
        with zipfile.ZipFile(run.zip_path) as zf:
            assert zf.namelist() == ["real.db"]

    def test_no_zip_created_when_everything_missing(self, tmp_path):
        dest_root = tmp_path / "dest"

        run = backup_all(dest_root, databases=[("fantasma", tmp_path / "nao-existe.db")])

        assert run.zip_path is None
        assert not run.any_succeeded

    def test_zip_lives_in_timestamped_backups_folder(self, tmp_path):
        existing = _make_db(tmp_path / "real.db")
        dest_root = tmp_path / "dest"

        run = backup_all(dest_root, databases=[("real", existing)])

        assert run.zip_path.parent == dest_root / "total-recall-backups"
        assert run.zip_path.name.startswith("total-recall-backup-")

    def test_zip_content_is_valid_readable_db(self, tmp_path):
        existing = _make_db(tmp_path / "real.db")
        dest_root = tmp_path / "dest"

        run = backup_all(dest_root, databases=[("real", existing)])

        extract_dir = tmp_path / "extracted"
        with zipfile.ZipFile(run.zip_path) as zf:
            zf.extractall(extract_dir)

        conn = sqlite3.connect(str(extract_dir / "real.db"))
        row = conn.execute("SELECT session_id FROM sessions").fetchone()
        assert row[0] == "s1"
        conn.close()


class TestPruneOldBackups:
    def test_keeps_only_n_most_recent(self, tmp_path):
        backups_dir = tmp_path / "total-recall-backups"
        backups_dir.mkdir(parents=True)
        names = [
            "total-recall-backup-2026-08-01_10-00-00.zip",
            "total-recall-backup-2026-08-05_10-00-00.zip",
            "total-recall-backup-2026-08-08_10-00-00.zip",
            "total-recall-backup-2026-08-10_10-00-00.zip",
        ]
        for name in names:
            (backups_dir / name).write_bytes(b"fake zip")

        removed = prune_old_backups(tmp_path, keep=2)

        assert {p.name for p in removed} == {
            "total-recall-backup-2026-08-01_10-00-00.zip",
            "total-recall-backup-2026-08-05_10-00-00.zip",
        }
        remaining = {p.name for p in backups_dir.iterdir()}
        assert remaining == {
            "total-recall-backup-2026-08-08_10-00-00.zip",
            "total-recall-backup-2026-08-10_10-00-00.zip",
        }

    def test_keep_greater_than_existing_removes_nothing(self, tmp_path):
        backups_dir = tmp_path / "total-recall-backups"
        backups_dir.mkdir(parents=True)
        (backups_dir / "total-recall-backup-2026-08-08_10-00-00.zip").write_bytes(b"fake")

        removed = prune_old_backups(tmp_path, keep=10)

        assert removed == []

    def test_no_backups_folder_is_a_noop(self, tmp_path):
        removed = prune_old_backups(tmp_path, keep=2)
        assert removed == []
