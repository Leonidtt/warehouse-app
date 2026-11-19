"""SQLite snapshot format and limits shared by the warehouse services."""
import os
import sqlite3
import time
from pathlib import Path

SNAPSHOT_PATH = "/api/internal/warehouse-snapshot"
MAX_SNAPSHOT_BYTES = 256 * 1024 * 1024
WAREHOUSE_TABLES = (
    "locations", "categories", "items", "item_metadata", "stock", "bookings",
    "comments", "checkouts", "movements", "writeoffs", "lost_items",
    "daily_reports", "repair_records", "receipts", "repair_photos",
    "inventory_runs", "consumable_returns",
)
PROFILE_COLUMNS = ("tg_id", "first_name", "username", "full_name")


def quote_identifier(name):
    return '"' + name.replace('"', '""') + '"'


def readonly_uri(path):
    return Path(path).resolve().as_uri() + "?mode=ro"


def attach_warehouse(conn, path):
    conn.execute("PRAGMA trusted_schema=OFF")
    conn.execute("ATTACH DATABASE ? AS incoming", (readonly_uri(path),))
    tables = {row[1] for row in conn.execute("PRAGMA incoming.table_list") if row[2] == "table"}
    if not set(("users", *WAREHOUSE_TABLES)).issubset(tables):
        raise sqlite3.DatabaseError("Missing warehouse tables")


def check_integrity(conn, schema="main"):
    if tuple(conn.execute(f"PRAGMA {schema}.quick_check").fetchone() or ()) != ("ok",):
        raise sqlite3.DatabaseError("SQLite integrity check failed")


def limit_sql_time(conn, seconds=45):
    deadline = time.monotonic() + seconds
    conn.set_progress_handler(lambda: int(time.monotonic() >= deadline), 10000)


def snapshot_token():
    token = os.environ.get("WAREHOUSE_SNAPSHOT_TOKEN", "").strip()
    if token.isascii() and token.isprintable() and " " not in token:
        return token
    return ""
