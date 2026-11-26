"""Read-only copy of the Google Sheets worksheet linked in Beta."""
import asyncio
import base64
import json
import logging
import os
from contextlib import suppress
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

from fastapi import Header, HTTPException, Response


def read_buyout_sheet(spreadsheet_id):
    import gspread
    from google.oauth2.service_account import Credentials

    encoded = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
    credentials = Credentials.from_service_account_info(
        json.loads(base64.b64decode(encoded)),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    client = gspread.authorize(credentials)
    client.set_timeout(15)
    try:
        worksheet = client.open_by_key(spreadsheet_id).get_worksheet_by_id(0)
        return {"title": worksheet.title, "rows": worksheet.get_all_values(pad_values=False)}
    except (PermissionError, gspread.exceptions.SpreadsheetNotFound) as error:
        raise HTTPException(
            503, "Google не открыл таблицу. Проверьте доступ на чтение для аккаунта бота."
        ) from error
    except gspread.exceptions.WorksheetNotFound as error:
        raise HTTPException(503, "Лист по ссылке не найден в таблице") from error


def register_buyout_sheet(app, transaction, session, check_admin, spreadsheet_id):
    logger = logging.getLogger("uvicorn.error")
    lock = Lock()
    with transaction() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS beta_buyout_sheet (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                spreadsheet_id TEXT NOT NULL,
                snapshot_json TEXT NOT NULL
            )
        """)

    def import_copy():
        if not spreadsheet_id:
            raise HTTPException(503, "Источник таблицы выкупа не настроен")
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "Копия уже обновляется")
        try:
            try:
                snapshot = read_buyout_sheet(spreadsheet_id)
            except HTTPException:
                raise
            except Exception as error:
                logger.warning("Beta buyout sheet: Google read failed (%s)", type(error).__name__)
                raise HTTPException(503, "Не удалось прочитать таблицу Google") from error
            snapshot["synced_at"] = datetime.now(timezone.utc).isoformat()
            with transaction() as conn:
                conn.execute("""
                    INSERT INTO beta_buyout_sheet VALUES (1, ?, ?)
                    ON CONFLICT(singleton) DO UPDATE SET
                        spreadsheet_id=excluded.spreadsheet_id, snapshot_json=excluded.snapshot_json
                """, (spreadsheet_id, json.dumps(snapshot, ensure_ascii=False)))
            logger.info("Beta buyout sheet: copied %s rows", len(snapshot["rows"]))
            return snapshot
        finally:
            lock.release()

    @app.get("/api/beta/buyout-sheet")
    def get_buyout_sheet(response: Response, x_init_data: Optional[str] = Header(None)):
        check_admin(x_init_data)
        response.headers["Cache-Control"] = "no-store"
        with session() as conn:
            row = conn.execute(
                "SELECT snapshot_json FROM beta_buyout_sheet WHERE spreadsheet_id=?",
                (spreadsheet_id,),
            ).fetchone()
        return {"snapshot": json.loads(row[0]) if row else None}

    @app.post("/api/beta/buyout-sheet/refresh")
    def refresh_buyout_sheet(response: Response, x_init_data: Optional[str] = Header(None)):
        check_admin(x_init_data)
        response.headers["Cache-Control"] = "no-store"
        return {"snapshot": import_copy()}

    async def initialize_copy():
        try:
            await asyncio.to_thread(import_copy)
        except HTTPException as error:
            logger.warning("Beta buyout sheet: startup copy unavailable (%s)", error.detail)
        except Exception as error:
            logger.warning("Beta buyout sheet: startup copy failed (%s)", type(error).__name__)

    task = None

    @app.on_event("startup")
    async def start_buyout_sheet():
        nonlocal task
        if spreadsheet_id:
            task = asyncio.create_task(initialize_copy())

    @app.on_event("shutdown")
    async def stop_buyout_sheet():
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
