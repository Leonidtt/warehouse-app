"""Serve a limited SQLite snapshot to the isolated Beta application."""
import hmac
import shutil
import sqlite3
import tempfile
import threading
from contextlib import closing
from pathlib import Path

from fastapi import Header, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from snapshot_format import (
    MAX_SNAPSHOT_BYTES,
    PROFILE_COLUMNS,
    SNAPSHOT_PATH,
    WAREHOUSE_TABLES,
    attach_warehouse,
    check_integrity,
    limit_sql_time,
    quote_identifier,
    snapshot_token,
)


def _create_snapshot(db_path, target):
    with closing(sqlite3.connect(target, timeout=5, uri=True)) as conn:
        limit_sql_time(conn)
        conn.execute("BEGIN")
        attach_warehouse(conn, db_path)
        profiles = ", ".join(f"src.{quote_identifier(column)}" for column in PROFILE_COLUMNS)
        conn.execute(f"CREATE TABLE users AS SELECT {profiles} FROM incoming.users AS src")
        tables = [(table, "*") for table in WAREHOUSE_TABLES]
        tables.append(("equipment_buyout_amounts", "item_code, total_cents, remaining_cents"))
        for table, columns in tables:
            name = quote_identifier(table)
            conn.execute(f"CREATE TABLE {name} AS SELECT {columns} FROM incoming.{name}")
            size = conn.execute("PRAGMA main.page_count").fetchone()[0]
            size *= conn.execute("PRAGMA main.page_size").fetchone()[0]
            if size > MAX_SNAPSHOT_BYTES:
                raise HTTPException(413, "Снимок склада слишком большой")
        check_integrity(conn)
        conn.commit()


def register_snapshot_export(app, db_path):
    lock = threading.Lock()

    @app.get(SNAPSHOT_PATH, include_in_schema=False)
    def export_snapshot(authorization: str = Header(default="")):
        token = snapshot_token()
        if not 32 <= len(token) <= 128:
            raise HTTPException(404, "Выдача снимка недоступна")
        if not hmac.compare_digest(authorization.encode(), f"Bearer {token}".encode()):
            raise HTTPException(403, "Доступ к снимку запрещён")
        if not lock.acquire(blocking=False):
            raise HTTPException(429, "Снимок уже создаётся")
        directory = None
        try:
            directory = Path(tempfile.mkdtemp(prefix="warehouse-snapshot-"))
            target = directory / "warehouse-snapshot.db"
            _create_snapshot(db_path, target)
            return FileResponse(
                target, media_type="application/octet-stream",
                headers={"Cache-Control": "no-store"},
                background=BackgroundTask(shutil.rmtree, directory, ignore_errors=True),
            )
        except (OSError, sqlite3.Error):
            if directory is not None:
                shutil.rmtree(directory, ignore_errors=True)
            raise HTTPException(503, "Не удалось подготовить снимок склада") from None
        except HTTPException:
            if directory is not None:
                shutil.rmtree(directory, ignore_errors=True)
            raise
        finally:
            lock.release()
