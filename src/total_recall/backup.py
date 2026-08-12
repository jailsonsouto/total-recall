"""
backup.py — Backup seguro e compactado dos bancos SQLite
===========================================================

Produz um único .zip contendo snapshots consistentes de cada banco, via
SQLite Backup API — não uma cópia de arquivo ingênua. Ver
docs/BACKUP-E-RESTAURACAO.md (Método 1) para o raciocínio completo por
trás da escolha da Backup API em vez de `cp`.

O .db cru nunca fica no disco de destino: é gerado numa pasta temporária,
compactado para dentro do .zip e a pasta temporária é descartada — só o
.zip sobra.

Livre de dependência do `click` de propósito: quem fala com o terminal
(prompts, barra de progresso) é o cli.py — este módulo só sabe mexer
em bancos, zip e pastas, o que também deixa testável sem simular stdin/tty.
"""

import platform
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import sqlite_vec

from .config import DB_PATH, SIBLING_DB_PATH

# Todo banco que o backup cobre. Hoje só existem estes dois — se surgir um
# novo "irmão" (ver SIBLING_DB_PATH em config.py), adicionar aqui.
KNOWN_DATABASES: list[tuple[str, Path]] = [
    ("total-recall", DB_PATH),
    ("total-recall-codex", SIBLING_DB_PATH),
]

BACKUP_FOLDER_NAME = "total-recall-backups"


@dataclass
class BackupResult:
    label: str
    src_path: Path
    included: bool  # False = origem não existia nesta máquina, pulado
    size_bytes: int = 0  # tamanho do .db (não compactado) que entrou no zip


@dataclass
class BackupRun:
    zip_path: Optional[Path]  # None se nada foi copiado (nenhum .zip criado)
    results: list[BackupResult]

    @property
    def any_succeeded(self) -> bool:
        return any(r.included for r in self.results)

    @property
    def zip_size_bytes(self) -> int:
        return self.zip_path.stat().st_size if self.zip_path else 0


def default_backup_root(
    home: Optional[Path] = None, is_macos: Optional[bool] = None
) -> Optional[Path]:
    """Desktop do usuário que instalou, se existir e o SO for macOS.

    Retorna None quando isso não se aplica (SO diferente de macOS, ou a
    pasta Desktop não existe nesta conta) — o chamador deve então perguntar
    a pasta de destino ao usuário.
    """
    home = home or Path.home()
    if is_macos is None:
        is_macos = platform.system() == "Darwin"
    if not is_macos:
        return None
    desktop = home / "Desktop"
    return desktop if desktop.is_dir() else None


def estimate_pages(src_path: Path) -> int:
    """Número de páginas do banco (para dimensionar barra de progresso).
    0 se o arquivo não existir."""
    if not src_path.exists():
        return 0
    conn = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    try:
        return conn.execute("PRAGMA page_count").fetchone()[0]
    finally:
        conn.close()


def backup_one(
    src_path: Path,
    dest_dir: Path,
    progress: Optional[Callable[[int, int], None]] = None,
) -> Optional[Path]:
    """Backup online (SQLite Backup API) de um único banco para um arquivo
    .db cru em `dest_dir` (etapa intermediária — quem chama compacta e
    descarta esse arquivo depois, ver `backup_all`).

    Lê a origem read-only — nunca escreve nela — e produz um arquivo
    standalone (sem -wal/-shm associados), consistente mesmo que o banco
    esteja em uso no momento da cópia. Retorna None sem tocar em nada se
    `src_path` não existir (banco irmão não instalado nesta máquina, por
    exemplo — não é erro).
    """
    if not src_path.exists():
        return None

    dest_path = dest_dir / src_path.name

    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    src.enable_load_extension(True)
    sqlite_vec.load(src)
    src.enable_load_extension(False)

    dst = sqlite3.connect(str(dest_path))
    try:
        total_pages = src.execute("PRAGMA page_count").fetchone()[0] or 1

        def _on_progress(status, remaining, total):
            if progress:
                progress(total - remaining, total)

        # pages=2000 + sleep=0: backup local não precisa ceder tempo a
        # escritores concorrentes como um replicador de longa duração
        # cederia — só queremos callbacks de progresso periódicos.
        src.backup(dst, pages=2000, sleep=0, progress=_on_progress)
    finally:
        dst.close()
        src.close()

    return dest_path


def backup_all(
    dest_root: Path,
    databases: Optional[list[tuple[str, Path]]] = None,
    on_before_db: Optional[Callable[[str, Path], None]] = None,
    on_progress: Optional[Callable[[str, int, int], None]] = None,
    on_compress_start: Optional[Callable[[], None]] = None,
) -> BackupRun:
    """Faz backup de todos os bancos conhecidos e compacta num único .zip
    com timestamp em `dest_root/total-recall-backups/`. Bancos ausentes são
    pulados (não é erro) — útil quando o irmão total-recall-codex não está
    instalado nesta máquina.

    O .db cru só existe durante a execução, numa pasta temporária do SO —
    é descartado assim que entra no .zip.
    """
    databases = databases if databases is not None else KNOWN_DATABASES

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backups_dir = dest_root / BACKUP_FOLDER_NAME
    backups_dir.mkdir(parents=True, exist_ok=True)
    zip_path = backups_dir / f"total-recall-backup-{stamp}.zip"

    results = []
    with tempfile.TemporaryDirectory(prefix="total-recall-backup-") as tmp:
        tmp_dir = Path(tmp)

        for label, src_path in databases:
            if on_before_db:
                on_before_db(label, src_path)

            def _progress(done, total, _label=label):
                if on_progress:
                    on_progress(_label, done, total)

            snapshot_path = backup_one(src_path, tmp_dir, progress=_progress)
            size = snapshot_path.stat().st_size if snapshot_path else 0
            results.append(
                BackupResult(label=label, src_path=src_path, included=snapshot_path is not None, size_bytes=size)
            )

        included = [r for r in results if r.included]
        if not included:
            return BackupRun(zip_path=None, results=results)

        if on_compress_start:
            on_compress_start()

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for r in included:
                zf.write(tmp_dir / r.src_path.name, arcname=r.src_path.name)

    return BackupRun(zip_path=zip_path, results=results)


def prune_old_backups(dest_root: Path, keep: int) -> list[Path]:
    """Remove backups (.zip) mais antigos que os `keep` mais recentes em
    `dest_root/total-recall-backups/`. Retorna os arquivos removidos.

    Nomes de arquivo trazem timestamp `YYYY-MM-DD_HH-MM-SS` — ordenação
    lexicográfica já é ordenação cronológica.
    """
    backups_dir = dest_root / BACKUP_FOLDER_NAME
    if keep < 0 or not backups_dir.is_dir():
        return []

    files = sorted(
        (p for p in backups_dir.iterdir() if p.is_file() and p.suffix == ".zip"),
        key=lambda p: p.name,
        reverse=True,
    )
    removed = []
    for f in files[keep:]:
        f.unlink()
        removed.append(f)
    return removed
