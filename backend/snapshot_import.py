"""Receive and atomically import a warehouse snapshot into Beta."""
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from snapshot_format import (
    MAX_SNAPSHOT_BYTES,
    PROFILE_COLUMNS,
    SNAPSHOT_PATH,
    WAREHOUSE_TABLES,
    attach_warehouse,
    check_integrity,
    limit_sql_time,
    quote_identifier,
    readonly_uri,
    snapshot_token,
)


def save_snapshot(path, chunks):
    size = 0
    with Path(path).open("wb") as output:
        for chunk in chunks:
            size += len(chunk)
            if size > MAX_SNAPSHOT_BYTES:
                raise HTTPException(413, "Файл снимка слишком большой")
            output.write(chunk)
    if not size:
        raise HTTPException(400, "Файл снимка пуст")


def fetch_snapshot(path):
    url = os.environ.get("WAREHOUSE_SNAPSHOT_URL", "").strip()
    token = snapshot_token()
    try:
        endpoint = urlsplit(url)
        acceptable = (
            endpoint.scheme == "https" and endpoint.hostname and not endpoint.username
            and not endpoint.password and not endpoint.query and not endpoint.fragment
            and endpoint.path == SNAPSHOT_PATH
        )
    except ValueError:
        acceptable = False
    if not acceptable or not token:
        raise HTTPException(503, "Автокопирование ещё не настроено. Можно загрузить резервную копию.")
    deadline = time.monotonic() + 90
    try:
        with httpx.Client(timeout=httpx.Timeout(60, connect=5), follow_redirects=False) as client:
            with client.stream("GET", url, headers={"Authorization": f"Bearer {token}"}) as response:
                response.raise_for_status()

                def chunks():
                    for chunk in response.iter_bytes(1024 * 1024):
                        if time.monotonic() >= deadline:
                            raise HTTPException(503, "Превышено время загрузки снимка")
                        yield chunk

                save_snapshot(path, chunks())
    except (OSError, httpx.HTTPError):
        raise HTTPException(503, "Основа не выдала снимок. Проверьте настройки подключения.") from None


def _backup_beta(path):
    path = Path(path)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix="beta-before-import-", delete=False) as stream:
        pending = Path(stream.name)
    deadline = time.monotonic() + 45

    def check_progress(status, remaining, total):
        if time.monotonic() >= deadline:
            raise sqlite3.DatabaseError("Beta backup deadline exceeded")

    try:
        with closing(sqlite3.connect(readonly_uri(path), timeout=5, uri=True)) as source:
            with closing(sqlite3.connect(pending)) as backup:
                source.backup(backup, pages=128, progress=check_progress, sleep=0.1)
                backup.execute("PRAGMA journal_mode=DELETE").fetchone()
                check_integrity(backup)
        pending.replace(path.with_name("warehouse_beta_before_import.db"))
    finally:
        pending.unlink(missing_ok=True)


def import_snapshot(conn, source, beta_path):
    try:
        attach_warehouse(conn, source)
        limit_sql_time(conn)
        check_integrity(conn, "incoming")
        columns_by_table = {}
        for table in WAREHOUSE_TABLES:
            name = quote_identifier(table)
            current = [row[1] for row in conn.execute(f"PRAGMA main.table_info({name})")]
            incoming = {row[1] for row in conn.execute(f"PRAGMA incoming.table_info({name})")}
            if not current or not set(current).issubset(incoming):
                raise sqlite3.DatabaseError("Incompatible warehouse schema")
            columns_by_table[table] = [quote_identifier(column) for column in current]

        profile_columns = {
            row[1] for row in conn.execute("PRAGMA incoming.table_info(users)")
        }
        if not set(PROFILE_COLUMNS).issubset(profile_columns):
            raise sqlite3.DatabaseError("Incompatible user profile schema")
        _backup_beta(beta_path)
        limit_sql_time(conn)
        conn.execute("""
            INSERT INTO users (tg_id, first_name, username, full_name, role, is_registered)
            SELECT tg_id, first_name, username, full_name,
                   CASE WHEN tg_id < 0 THEN 'guest' ELSE 'employee' END,
                   CASE WHEN tg_id < 0 THEN 1 ELSE 0 END
            FROM incoming.users WHERE 1
            ON CONFLICT(tg_id) DO UPDATE SET
                first_name=excluded.first_name, username=excluded.username,
                full_name=excluded.full_name
        """)
        for table, columns in columns_by_table.items():
            name = quote_identifier(table)
            fields = ", ".join(columns)
            source_fields = ", ".join(f"src.{column}" for column in columns)
            conn.execute(f"DELETE FROM main.{name}")
            conn.execute(
                f"INSERT INTO main.{name} ({fields}) SELECT {source_fields} FROM incoming.{name} AS src"
            )
        if conn.execute("PRAGMA main.foreign_key_check").fetchone():
            raise sqlite3.DatabaseError("Inconsistent warehouse references")
    except (OSError, sqlite3.Error):
        raise HTTPException(400, "Не удалось импортировать снимок. Проверьте версию и целостность базы.") from None
    finally:
        conn.set_progress_handler(None, 0)
    return len(WAREHOUSE_TABLES) + 1
