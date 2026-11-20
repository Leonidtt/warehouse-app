import sqlite3
import json
import hashlib
import hmac
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form, Request, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, RedirectResponse, Response, HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional, List
import qrcode
import io
import csv
import httpx
from PIL import Image, ImageDraw, ImageFont
import base64
from datetime import datetime, timedelta
from decimal import Decimal
import os
import traceback
import pandas as pd
import asyncio
import time
import math
import tempfile
import secrets
import re
from urllib.parse import urlsplit
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from warehouse_v18 import label_font, label_dimensions, register_v18
from release_v182 import label_image, prepare_migration, register_release
from release_v184 import effective_user, register_184
from release_v185 import register_185, deny_blocked
from release_v183 import register_183
from owner_backup import register_owner_backup
from snapshot_export import register_snapshot_export
from telegram_app_bot import register_telegram_app_bot
from return_reminders import PLANS, init_return_reminders, queue_return_reminder, register_return_reminders
from pwa_assets import render_icon_png

import urllib3
urllib3.disable_warnings()

# --- НАСТРОЙКИ RAILWAY (Основной сервис) ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("Не настроена переменная BOT_TOKEN для Основы")

try:
    MAIN_ADMIN_ID = int(os.environ.get("MAIN_ADMIN_ID", "").strip())
    if not 0 < MAIN_ADMIN_ID < 2**52:
        raise ValueError
except ValueError:
    raise RuntimeError("Укажите корректный MAIN_ADMIN_ID в Railway") from None

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "").strip()

APP_VERSION = "18.5.11"
app = FastAPI(title="Склад", version=APP_VERSION)

async def notify_admin_about_error(error_text: str, user_info: str = "Неизвестно"):
    try:
        conn = get_conn()
        admins = conn.execute("SELECT tg_id FROM users WHERE role = 'admin'").fetchall()
        conn.close()
        async with httpx.AsyncClient() as client:
            for admin in admins:
                await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": admin["tg_id"], "text": f"⚠️ ОШИБКА\n👤 {user_info}\n📝 {error_text}"})
    except: pass

async def notify_admin_action(action_text: str):
    try:
        conn = get_conn()
        admins = conn.execute("SELECT tg_id FROM users WHERE role = 'admin'").fetchall()
        conn.close()
        async with httpx.AsyncClient() as client:
            for admin in admins:
                await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": admin["tg_id"], "text": action_text})
    except: pass

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"ОШИБКА: {exc}\n{traceback.format_exc()}")
    return JSONResponse(status_code=500, content={"detail": "Внутренняя ошибка сервера."})

# Один домен для Mini App и сайта; междоменные запросы не открываем.

@app.get("/health")
def healthcheck(): return {"status": "ok"}

DB_PATH = "/data/warehouse.db"

# Основной сервис открывает только рабочую базу.
def get_conn(x_init_data: Optional[str] = None):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def recipient_name(value):
    return " ".join((value or "").split())

def recipient_key(value):
    return recipient_name(value).casefold().replace("ё", "е")

def resolve_recipient(conn, name, recipient_id):
    if recipient_id is not None:
        row = conn.execute("SELECT tg_id,full_name FROM users WHERE tg_id=?", (recipient_id,)).fetchone()
        if not row or not recipient_name(row["full_name"]):
            raise HTTPException(404, "Получатель не найден")
        deny_blocked(conn, row["tg_id"], MAIN_ADMIN_ID)
        return row["tg_id"], recipient_name(row["full_name"])

    key = recipient_key(name)
    rows = conn.execute("SELECT tg_id,full_name FROM users WHERE TRIM(COALESCE(full_name,''))<>''").fetchall()
    matches = [row for row in rows if recipient_key(row["full_name"]) == key]
    if not matches and " " not in key:
        matches = [row for row in rows if recipient_key(row["full_name"]).split(" ", 1)[0] == key]
    # A registered account takes precedence over a guest spelling of the same full name.
    if len({recipient_key(row["full_name"]) for row in matches}) == 1:
        accounts = [row for row in matches if row["tg_id"] > 0]
        if accounts:
            matches = accounts
    if len(matches) > 1:
        raise HTTPException(409, "Есть несколько получателей. Выберите нужного из списка")
    if matches:
        row = matches[0]
        deny_blocked(conn, row["tg_id"], MAIN_ADMIN_ID)
        return row["tg_id"], recipient_name(row["full_name"])

    guest_id = conn.execute("SELECT COALESCE(MIN(tg_id),0)-1 FROM users WHERE tg_id<0").fetchone()[0]
    conn.execute("INSERT INTO users(tg_id,full_name,role,is_registered) VALUES(?,?,'guest',1)", (guest_id, name))
    return guest_id, name


def backfill_legacy_guest_contacts(conn):
    # These historical checkouts have a confirmed person in the free-text recipient field.
    rows = conn.execute("""
        SELECT id, taken_for FROM checkouts
        WHERE id IN (32, 34, 35, 41) AND user_id=giver_id
          AND date(taken_at)='2026-11-15'
        ORDER BY id
    """).fetchall()
    created = transferred = 0
    for row in rows:
        name = recipient_name(row["taken_for"])
        if not name:
            continue
        before = conn.total_changes
        try:
            recipient_id, _ = resolve_recipient(conn, name, None)
        except HTTPException as error:
            if error.status_code not in (403, 409):
                raise
            continue
        created += conn.total_changes - before
        if recipient_id < 0:
            transferred += conn.execute(
                "UPDATE checkouts SET user_id=? WHERE id=? AND user_id=giver_id",
                (recipient_id, row["id"]),
            ).rowcount
    return created, transferred


def init_db(db_path):
    # Создаем директорию для файла базы данных, если ее нет
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("BEGIN IMMEDIATE")
    c.execute("""CREATE TABLE IF NOT EXISTS locations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, type TEXT NOT NULL DEFAULT 'storage')""")
    c.execute("""CREATE TABLE IF NOT EXISTS users (tg_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, full_name TEXT DEFAULT '', role TEXT DEFAULT 'employee')""")
    c.execute("""CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'equipment', min_stock INTEGER DEFAULT 0, photo TEXT DEFAULT '', needs_repair INTEGER DEFAULT 0, price REAL DEFAULT 0, kit_body TEXT DEFAULT '', kit_lens TEXT DEFAULT '', kit_flash TEXT DEFAULT '', kit_acc TEXT DEFAULT '', kit_add TEXT DEFAULT '', budget_tag TEXT DEFAULT '', serial_number TEXT DEFAULT '', buyout_status TEXT DEFAULT '', category TEXT DEFAULT '', is_archived INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, price_body REAL DEFAULT 0, price_lens REAL DEFAULT 0, price_flash REAL DEFAULT 0, price_acc REAL DEFAULT 0, price_add REAL DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT NOT NULL, user_id INTEGER NOT NULL, date_from TEXT NOT NULL, date_to TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT NOT NULL, user_id INTEGER NOT NULL, text TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS stock (item_code TEXT NOT NULL, location_id INTEGER NOT NULL, quantity INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (item_code, location_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS checkouts (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT NOT NULL, user_id INTEGER NOT NULL, giver_id INTEGER, location_id INTEGER NOT NULL, taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, returned_at TIMESTAMP, returned_by INTEGER, taken_for TEXT DEFAULT '')""")
    c.execute("""CREATE TABLE IF NOT EXISTS movements (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT NOT NULL, quantity INTEGER NOT NULL, from_location INTEGER, to_location INTEGER, user_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS writeoffs (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT NOT NULL, quantity INTEGER NOT NULL, location_id INTEGER, user_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS lost_items (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT NOT NULL, user_id INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS daily_reports (date TEXT PRIMARY KEY, report_text TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS terminal_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, sql_query TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

    migrations = [
        "ALTER TABLE items ADD COLUMN needs_repair INTEGER DEFAULT 0",
        "ALTER TABLE items ADD COLUMN price REAL DEFAULT 0",
        "ALTER TABLE items ADD COLUMN kit_body TEXT DEFAULT ''",
        "ALTER TABLE items ADD COLUMN kit_lens TEXT DEFAULT ''",
        "ALTER TABLE items ADD COLUMN kit_flash TEXT DEFAULT ''",
        "ALTER TABLE items ADD COLUMN kit_acc TEXT DEFAULT ''",
        "ALTER TABLE items ADD COLUMN kit_add TEXT DEFAULT ''",
        "ALTER TABLE items ADD COLUMN budget_tag TEXT DEFAULT ''",
        "ALTER TABLE items ADD COLUMN serial_number TEXT DEFAULT ''",
        "ALTER TABLE items ADD COLUMN buyout_status TEXT DEFAULT ''",
        "ALTER TABLE items ADD COLUMN category TEXT DEFAULT ''",
        "ALTER TABLE items ADD COLUMN is_archived INTEGER DEFAULT 0",
        "ALTER TABLE items ADD COLUMN created_at TIMESTAMP",
        "ALTER TABLE items ADD COLUMN price_body REAL DEFAULT 0",
        "ALTER TABLE items ADD COLUMN price_lens REAL DEFAULT 0",
        "ALTER TABLE items ADD COLUMN price_flash REAL DEFAULT 0",
        "ALTER TABLE items ADD COLUMN price_acc REAL DEFAULT 0",
        "ALTER TABLE items ADD COLUMN price_add REAL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'employee'",
        "ALTER TABLE users ADD COLUMN is_registered INTEGER DEFAULT 0",
        "ALTER TABLE checkouts ADD COLUMN returned_by INTEGER",
        "ALTER TABLE checkouts ADD COLUMN taken_for TEXT DEFAULT ''",
        "ALTER TABLE checkouts ADD COLUMN giver_id INTEGER"
    ]
    for q in migrations:
        try: c.execute(q)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                conn.rollback(); conn.close(); raise

    c.execute("UPDATE checkouts SET giver_id = user_id WHERE giver_id IS NULL")
    c.execute("SELECT COUNT(*) FROM locations")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO locations (name, type) VALUES ('Мастерская', 'workshop')")
        c.execute("INSERT INTO locations (name, type) VALUES ('Склад', 'storage')")
        c.execute("INSERT INTO locations (name, type) VALUES ('Офис', 'office')")

    first_categories = not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='categories'").fetchone()
    c.execute("CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY COLLATE NOCASE)")
    for name in ["Фотокомплекты","Объективы","Вспышки","Ноутбуки","Принтеры","Освещение","Аксессуары","Расходники","Прочее"] if first_categories else []:
        c.execute("INSERT OR IGNORE INTO categories(name) VALUES (?)",(name,))
    c.execute("INSERT OR IGNORE INTO categories(name) SELECT DISTINCT category FROM items WHERE TRIM(COALESCE(category,'')) != ''")
    c.execute("CREATE TABLE IF NOT EXISTS item_metadata (code TEXT PRIMARY KEY, unit TEXT DEFAULT 'шт.', supplier TEXT DEFAULT '', site TEXT DEFAULT '', vessel TEXT DEFAULT '', notes TEXT DEFAULT '')")
    c.execute("CREATE TABLE IF NOT EXISTS repair_records (id INTEGER PRIMARY KEY, code TEXT NOT NULL, description TEXT NOT NULL, cost REAL DEFAULT 0, user_id INTEGER NOT NULL, started_at TEXT DEFAULT CURRENT_TIMESTAMP, finished_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, action TEXT NOT NULL, subject TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("""CREATE TABLE IF NOT EXISTS checkout_handoffs (
        checkout_id INTEGER PRIMARY KEY,
        handed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS equipment_buyout_amounts (
        item_code TEXT PRIMARY KEY,
        total_cents INTEGER NOT NULL CHECK(total_cents>=0),
        remaining_cents INTEGER NOT NULL CHECK(remaining_cents BETWEEN 0 AND total_cents)
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_checkouts_code_return ON checkouts(item_code,returned_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_bookings_dates ON bookings(item_code,date_from,date_to)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_stock_location ON stock(location_id)")
    c.execute("CREATE TABLE IF NOT EXISTS consumable_returns (id INTEGER PRIMARY KEY, item_code TEXT NOT NULL, location_id INTEGER NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0), user_id INTEGER NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS receipts (id INTEGER PRIMARY KEY, item_code TEXT NOT NULL, location_id INTEGER NOT NULL, quantity INTEGER NOT NULL, unit_price REAL NOT NULL, user_id INTEGER NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS repair_photos (repair_id INTEGER PRIMARY KEY, photo TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS inventory_runs (id INTEGER PRIMARY KEY, location_id INTEGER NOT NULL, user_id INTEGER NOT NULL, report TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS web_codes (digest TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires INTEGER NOT NULL)")
    c.execute("""CREATE TABLE IF NOT EXISTS telegram_bot_updates (
        update_id INTEGER PRIMARY KEY,
        received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("CREATE TABLE IF NOT EXISTS web_sessions (digest TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires INTEGER NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS employee_preview (digest TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires INTEGER NOT NULL)")
    if "preview_role" not in {row[1] for row in c.execute("PRAGMA table_info(employee_preview)")}:
        c.execute("ALTER TABLE employee_preview ADD COLUMN preview_role TEXT NOT NULL DEFAULT 'employee'")
        c.execute("DELETE FROM employee_preview")
    c.execute("CREATE TABLE IF NOT EXISTS blocked_telegram (tg_id INTEGER PRIMARY KEY CHECK(tg_id>0), blocked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, blocked_by INTEGER NOT NULL)")
    init_return_reminders(conn)
    conn.commit(); conn.close()

# Создаем папку /data перед инициализацией баз
if not os.path.exists("/data"):
    try: os.makedirs("/data")
    except: pass

prepare_migration(DB_PATH, APP_VERSION)
init_db(DB_PATH)

def verify_init_data(init_data: str, token: str) -> dict:
    try:
        if len(init_data)>24000: raise ValueError()
        raw = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        pairs = dict(raw)
        if len(raw)!=len(pairs): raise ValueError()
    except Exception: raise HTTPException(status_code=401, detail="Некорректный initData")
    received_hash = pairs.pop("hash", None)
    if not received_hash: raise HTTPException(status_code=401, detail="Нет подписи")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash): raise HTTPException(status_code=401, detail="Неверная подпись")
    try:
        age = time.time() - int(pairs["auth_date"])
        if not -60 <= age <= 43200: raise ValueError()
    except (KeyError, ValueError):
        raise HTTPException(401, "Срок авторизации истёк. Откройте приложение заново.")
    user_json = pairs.get("user")
    if not user_json: raise HTTPException(status_code=401, detail="Нет пользователя")
    return json.loads(user_json)

def real_user(x_init_data: Optional[str]):
    if not x_init_data:
        raise HTTPException(status_code=401, detail="Нет авторизации")
    # ID берется только из данных, подписанных токеном Основы.
    try:
        if x_init_data.startswith("web:"):
            with contextmanager_session() as session_conn:
                session = session_conn.execute("SELECT u.* FROM web_sessions s JOIN users u ON u.tg_id=s.user_id WHERE s.digest=? AND s.expires>?", (web_digest(x_init_data[4:]), int(time.time()))).fetchone()
                if session: deny_blocked(session_conn, session["tg_id"], MAIN_ADMIN_ID)
            if not session: raise HTTPException(401,"Войдите на сайт заново")
            user=dict(session); user["is_owner"]=user["tg_id"]==MAIN_ADMIN_ID
            if user["is_owner"]: user["role"]="admin"
            return user
        user = verify_init_data(x_init_data, BOT_TOKEN)
        tg_id = user["id"]
        if type(tg_id) is not int or not 0 < tg_id < 2**52:
            raise ValueError
    except HTTPException:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise HTTPException(status_code=401, detail="Некорректные данные пользователя")

    is_owner = tg_id == MAIN_ADMIN_ID
    conn = get_conn(x_init_data)
    try:
        deny_blocked(conn, tg_id, MAIN_ADMIN_ID)
        row = conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
        if not row:
            full_name = f"{user.get('last_name', '')} {user.get('first_name', '')}".strip()
            conn.execute("INSERT OR IGNORE INTO users (tg_id, first_name, username, full_name, role, is_registered) VALUES (?, ?, ?, ?, ?, 0)", (tg_id, user.get("first_name", ""), user.get("username", ""), full_name, "admin" if is_owner else "employee"))
        username = user.get("username", "")
        if not isinstance(username, str): username = ""
        conn.execute("UPDATE users SET username=? WHERE tg_id=? AND COALESCE(username,'')<>?", (username, tg_id, username))
        if is_owner:
            conn.execute("UPDATE users SET role = 'admin' WHERE tg_id = ? AND role IS NOT 'admin'", (tg_id,))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
        user_dict = dict(row)
        user_dict["is_registered"] = row["is_registered"] if "is_registered" in row.keys() else 1
        user_dict["is_owner"] = is_owner
        return user_dict
    finally:
        conn.close()

def get_user(x_init_data: Optional[str]):
    return effective_user(real_user(x_init_data), x_init_data, web_digest, contextmanager_session)

def check_admin(x_init_data: Optional[str]):
    user = get_user(x_init_data)
    if user["role"] != "admin": raise HTTPException(status_code=403, detail="Доступ только для администратора")
    return user

def check_owner(x_init_data: Optional[str]):
    user = get_user(x_init_data)
    if not user["is_owner"]:
        raise HTTPException(status_code=403, detail="Доступ только для главного администратора")
    return user

@contextmanager
def transaction():
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def audit(conn, actor, action, subject):
    conn.execute("INSERT INTO audit_log(user_id,action,subject) VALUES (?,?,?)", (actor["tg_id"],action,str(subject)[:500]))


def budget_for_equipment_name(name: str) -> str:
    # "Комплект Т10" belongs to ТХ; other equipment belongs to КЦ.
    actual = re.sub(r"^(?:\s*комплект\b[\s№#.:–—-]*)+", "", str(name or ""), flags=re.IGNORECASE).lstrip()
    return "ТХ" if actual.casefold().startswith(("т", "t")) else "КЦ"


def active_item(conn, code):
    row=conn.execute("SELECT * FROM items WHERE code=? AND is_archived=0",(code,)).fetchone()
    if not row: raise HTTPException(404,"Товар не найден")
    return row


def valid_location(conn, loc):
    if not conn.execute("SELECT 1 FROM locations WHERE id=?",(loc,)).fetchone(): raise HTTPException(404,"Помещение не найдено")


def validate_item_fields(name,kind,min_stock,prices):
    if not name.strip() or len(name)>250: raise HTTPException(400,"Укажите название до 250 символов")
    if kind not in ("equipment","consumable"): raise HTTPException(400,"Неизвестный тип товара")
    if min_stock<0 or any(not math.isfinite(p) or p<0 for p in prices): raise HTTPException(400,"Цена и минимальный остаток не могут быть отрицательными")


class ReplenishRequest(BaseModel):
    location_id: int
    quantity: int = 1
    unit_price: Optional[float] = None

class MoveRequest(BaseModel):
    code: str; from_location: int; to_location: int; quantity: int
class BatchMoveRequest(BaseModel):
    codes: List[str]; from_location: int; to_location: int
class BatchCheckoutRequest(BaseModel):
    codes: List[str]; taken_for: str = ""
class WriteoffRequest(BaseModel):
    code: str; location_id: int; quantity: int
class BookingRequest(BaseModel):
    code: str; date_from: str; date_to: str
class CommentRequest(BaseModel):
    code: str; text: str
class CheckoutRequest(BaseModel):
    code: str
    taken_for: str = ""
    recipient_id: Optional[int] = None
class RegisterRequest(BaseModel):
    full_name: str
class LocationCreate(BaseModel):
    name: str
class LocationUpdate(BaseModel):
    id: int; name: str
class BuyoutAmounts(BaseModel):
    total: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    remaining: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class ItemUpdate(BaseModel):
    name: str; kind: str; min_stock: int; price: float; kit_body: str; kit_lens: str; kit_flash: str; kit_acc: str; kit_add: str; budget_tag: str; serial_number: str; buyout_status: str; category: str = ""; price_body: float = 0; price_lens: float = 0; price_flash: float = 0; price_acc: float = 0; price_add: float = 0
    buyout: Optional[BuyoutAmounts] = None
class ImportTextRequest(BaseModel):
    text: str
class UserUpdate(BaseModel):
    full_name: str
    role: str
class TerminalRequest(BaseModel):
    sql: str
class InventoryResult(BaseModel):
    location_id: int
    found: List[str]
    counts: Optional[dict[str,int]] = None
class LogErrorRequest(BaseModel):
    error: str

@app.get("/api/me")
def get_me(x_init_data: Optional[str] = Header(None)): return get_user(x_init_data)

@app.post("/api/log_error")
async def log_error(req: LogErrorRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    try:
        user_name = user.get("full_name", "?")
        await notify_admin_about_error(req.error[:500], user_name)
    except: pass
    return {"status": "ok"}

@app.get("/api/sync_google")
def sync_google(sheet_name: Optional[str] = None, x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data)
    sheet_name = sheet_name or os.environ.get("SHEET_NAME", "").strip() or "кц"
    if sheet_name not in ("кц","тх мск"): raise HTTPException(403,"Лист недоступен")
    if not SPREADSHEET_ID:
        return {"status": "error", "message": "Не настроена переменная SPREADSHEET_ID на сервере."}
    creds_env = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not creds_env: return {"status": "error", "message": "Не настроены GOOGLE_CREDENTIALS_JSON на сервере."}
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        decoded_bytes = base64.b64decode(creds_env)
        creds_json = decoded_bytes.decode('utf-8')
        creds_dict = json.loads(creds_json)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        
        try:
            target_sheet = spreadsheet.worksheet(sheet_name)
        except Exception:
            titles = [s.title for s in spreadsheet.worksheets()]
            return {"status": "error", "message": f"Лист '{sheet_name}' не найден. Доступные листы: {titles}. Проверьте регистр и пробелы!"}
        
        all_values = target_sheet.get_all_values()
        if not all_values: return {"status": "ok", "sheet_title": target_sheet.title, "data": []}
        
        headers = all_values[0]
        data_rows = all_values[1:]
        records = []
        is_th_sheet = "тх" in sheet_name.lower()
        
        for row in data_rows:
            if not row or len(row) == 0: continue
            first_cell = row[0].strip() if row[0] else ""
            if not first_cell: continue
            if len(row) > 1 and row[1] is not None and "1899" in str(row[1]): continue
            
            record = {}
            if is_th_sheet or not headers[0].strip():
                record["Название"] = first_cell
                start_idx = 1
            else:
                start_idx = 0
                
            for i in range(start_idx, len(headers)):
                h = headers[i].strip() if i < len(headers) else ""
                if h and i < len(row):
                    record[h] = row[i].strip() if row[i] else ""
            records.append(record)
            
        return {"status": "ok", "sheet_title": target_sheet.title, "data": records}
    except Exception as e:
        return {"status": "error", "message": "Не удалось прочитать таблицу Google Sheets. Проверьте настройки."}

@app.get("/api/my_bookings")
def my_bookings(x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data); conn = get_conn(x_init_data)
    rows = conn.execute("SELECT b.*, i.name FROM bookings b JOIN items i ON i.code = b.item_code WHERE b.user_id = ? AND b.date_to >= date('now') ORDER BY b.date_from", (user["tg_id"],)).fetchall()
    conn.close(); return [dict(r) for r in rows]

@app.get("/api/my_items")
def my_items(x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data); conn = get_conn(x_init_data)
    rows = conn.execute("""
        SELECT c.item_code, i.name, i.kind, i.category, i.kit_body, i.kit_lens, i.kit_flash, CASE WHEN LENGTH(COALESCE(i.photo,''))>0 THEN 1 ELSE 0 END AS has_photo, c.taken_for, c.user_id, c.giver_id, u.full_name as target_name,
               c.id AS checkout_id, h.handed_at,
               (c.giver_id=? AND c.user_id!=c.giver_id AND TRIM(COALESCE(c.taken_for,''))<>'' AND h.checkout_id IS NULL) AS can_handoff
        FROM checkouts c
        JOIN items i ON i.code = c.item_code
        LEFT JOIN users u ON u.tg_id = c.user_id
        LEFT JOIN checkout_handoffs h ON h.checkout_id = c.id
        WHERE (c.user_id = ? OR (c.giver_id = ? AND h.checkout_id IS NULL)) AND c.returned_at IS NULL
        ORDER BY c.taken_at DESC
    """, (user["tg_id"], user["tg_id"], user["tg_id"])).fetchall()
    conn.close(); return [dict(r) for r in rows]

@app.get("/api/daily_report")
def get_daily_report(x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data); conn = get_conn(x_init_data); today = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute("SELECT report_text FROM daily_reports WHERE date = ?", (today,)).fetchone()
    if not row:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        stats = conn.execute("SELECT (SELECT COUNT(*) FROM checkouts WHERE date(taken_at) = ?) as taken, (SELECT COUNT(*) FROM checkouts WHERE date(returned_at) = ?) as returned, (SELECT COUNT(*) FROM writeoffs WHERE date(created_at) = ?) as written_off", (yesterday, yesterday, yesterday)).fetchone()
        low_stock = conn.execute("SELECT name FROM items WHERE kind='consumable' AND min_stock > 0 AND (SELECT SUM(quantity) FROM stock WHERE item_code = items.code) <= min_stock").fetchall()
        low_list = ", ".join([i["name"] for i in low_stock]) if low_stock else "Нет"
        report = f"📊 Сводка за {yesterday}:\n\n📤 Выдано: {stats['taken']} шт.\n📥 Возвращено: {stats['returned']} шт.\n📉 Списано: {stats['written_off']} шт.\n\n⚠️ Заканчивается: {low_list}"
        conn.execute("INSERT INTO daily_reports (date, report_text) VALUES (?, ?)", (today, report)); conn.commit()
    else: report = row["report_text"]
    conn.close(); return {"report": report}

@app.get("/api/history")
def get_history(x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data); conn = get_conn(x_init_data); rows = []
    co = conn.execute("""
        SELECT c.id, c.item_code, i.name, c.user_id, u.full_name, c.taken_at AS date, c.returned_at, c.taken_for, c.giver_id, g.full_name as giver_name, ret.full_name AS returner_name
        FROM checkouts c 
        JOIN items i ON i.code = c.item_code 
        LEFT JOIN users u ON u.tg_id = c.user_id 
        LEFT JOIN users g ON g.tg_id = c.giver_id
        LEFT JOIN users ret ON ret.tg_id=c.returned_by
        ORDER BY c.taken_at DESC LIMIT 500
    """).fetchall()
    for r in co:
        user_display = r["giver_name"] if r["taken_for"] else r["full_name"]
        rows.append({"date": r["date"], "type": "checkout", "item_code": r["item_code"], "name": r["name"], "quantity": 1, "user_name": user_display or "—", "taken_for": r["taken_for"]})
        if r["returned_at"]: rows.append({"date": r["returned_at"], "type": "return", "item_code": r["item_code"], "name": r["name"], "quantity": 1, "user_name": r["returner_name"] or r["full_name"] or "—", "taken_for": ""})
    mv = conn.execute("SELECT m.item_code, i.name, m.quantity, m.created_at AS date, u.full_name FROM movements m JOIN items i ON i.code = m.item_code LEFT JOIN users u ON u.tg_id = m.user_id ORDER BY m.created_at DESC LIMIT 500").fetchall()
    for r in mv: rows.append({"date": r["date"], "type": "move", "item_code": r["item_code"], "name": r["name"], "quantity": r["quantity"], "user_name": r["full_name"] or "—", "taken_for": ""})
    wo = conn.execute("SELECT w.item_code, i.name, w.quantity, w.created_at AS date, u.full_name FROM writeoffs w JOIN items i ON i.code = w.item_code LEFT JOIN users u ON u.tg_id = w.user_id ORDER BY w.created_at DESC LIMIT 500").fetchall()
    for r in wo: rows.append({"date": r["date"], "type": "writeoff", "item_code": r["item_code"], "name": r["name"], "quantity": r["quantity"], "user_name": r["full_name"] or "—", "taken_for": ""})
    for r in conn.execute("SELECT r.item_code, i.name, r.quantity, r.created_at AS date, u.full_name FROM consumable_returns r JOIN items i ON i.code=r.item_code LEFT JOIN users u ON u.tg_id=r.user_id ORDER BY r.created_at DESC LIMIT 500"):
        rows.append({"date":r["date"],"type":"return","item_code":r["item_code"],"name":r["name"],"quantity":r["quantity"],"user_name":r["full_name"] or "—","taken_for":""})
    conn.close(); rows.sort(key=lambda x: x["date"], reverse=True); return rows

def csv_safe(v):
    if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@','\t','\r')): return "'"+v
    return v

@app.get("/api/export_history")
def export_history(x_init_data: Optional[str] = Header(None)):
    auth = x_init_data
    get_user(auth); rows = get_history(auth); buf = io.StringIO(); writer = csv.writer(buf)
    writer.writerow(["Дата", "Тип", "Код", "Название", "Кол-во", "Пользователь"])
    for r in rows: writer.writerow([csv_safe(v) for v in [r["date"], r["type"], r["item_code"], r["name"], r["quantity"], r["user_name"]]])
    buf.seek(0)
    return StreamingResponse(iter(["\ufeff"+buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=history.csv"})

@app.get("/api/export_stock")
def export_stock(x_init_data: Optional[str] = Header(None)):
    auth = x_init_data
    check_admin(auth); conn = get_conn(auth)
    rows = conn.execute("SELECT i.code, i.name, l.name as location, s.quantity FROM stock s JOIN items i ON i.code = s.item_code JOIN locations l ON l.id = s.location_id WHERE s.quantity > 0 AND i.is_archived = 0 ORDER BY l.name, i.name").fetchall()
    conn.close(); buf = io.StringIO(); writer = csv.writer(buf, delimiter=';')
    writer.writerow(["Код", "Название", "Локация", "Количество"])
    for r in rows: writer.writerow([csv_safe(v) for v in [r["code"], r["name"], r["location"], r["quantity"]]])
    buf.seek(0)
    return StreamingResponse(iter(["\ufeff"+buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=stock.csv"})

@app.get("/api/export_qr_sheet")
def export_qr_sheet(x_init_data: Optional[str] = Header(None)):
    auth = x_init_data
    check_admin(auth); conn = get_conn(auth)
    items = conn.execute("SELECT code, name FROM items WHERE is_archived = 0 ORDER BY name").fetchall()
    conn.close()
    cols = 4; rows_count = (len(items) + cols - 1) // cols
    qr_size = 180; padding = 20; text_height = 30
    cell_w = qr_size + padding * 2; cell_h = qr_size + text_height + padding * 2
    img_w = cols * cell_w; img_h = rows_count * cell_h
    if img_h == 0: img_h = 100
    img = Image.new("RGB", (img_w, img_h), "white"); draw = ImageDraw.Draw(img)
    font = label_font(14)
    for idx, item in enumerate(items):
        row = idx // cols; col = idx % cols
        x = col * cell_w + padding; y = row * cell_h + padding
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=1)
        qr.add_data(item["code"]); qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((qr_size, qr_size))
        img.paste(qr_img, (x, y))
        draw.text((x, y + qr_size + 5), f"{item['code']} - {item['name'][:15]}", fill="black", font=font)
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    return StreamingResponse(buf, media_type="image/png", headers={"Content-Disposition": "attachment; filename=qrs.png"})

@app.post("/api/items/{code}/replenish")
def replenish_item(code: str, req: ReplenishRequest, x_init_data: Optional[str] = Header(None)):
    actor=check_admin(x_init_data)
    if req.quantity<=0: raise HTTPException(400,"Количество должно быть больше нуля")
    if req.unit_price is not None and (req.unit_price<0 or not math.isfinite(req.unit_price)): raise HTTPException(400,"Некорректная цена")
    with transaction() as conn:
        item=active_item(conn,code); valid_location(conn,req.location_id)
        if item["kind"]=="equipment" and (req.quantity!=1 or conn.execute("SELECT 1 FROM stock WHERE item_code=? AND quantity>0",(code,)).fetchone() or conn.execute("SELECT 1 FROM checkouts WHERE item_code=? AND returned_at IS NULL",(code,)).fetchone()): raise HTTPException(409,"Каждая единица оборудования должна иметь собственный QR-код")
        conn.execute("INSERT INTO stock(item_code,location_id,quantity) VALUES(?,?,?) ON CONFLICT(item_code,location_id) DO UPDATE SET quantity=quantity+excluded.quantity", (code,req.location_id,req.quantity))
        if req.unit_price is not None: conn.execute("INSERT INTO receipts(item_code,location_id,quantity,unit_price,user_id) VALUES(?,?,?,?,?)",(code,req.location_id,req.quantity,req.unit_price,actor["tg_id"]))
        audit(conn,actor,"Пополнение",code)
    return {"status":"ok"}

@app.post("/api/register")
def register(req: RegisterRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    if not 3<=len(req.full_name.strip())<=150: raise HTTPException(400,"Укажите имя от 3 до 150 символов")
    conn = get_conn(x_init_data); conn.execute("UPDATE users SET full_name = ?, is_registered = 1 WHERE tg_id = ?", (req.full_name.strip(), user["tg_id"])); conn.commit(); conn.close(); return {"status": "ok"}

@app.get("/api/users")
def list_users(x_init_data: Optional[str] = Header(None)):
    actor = check_admin(x_init_data); conn = get_conn(x_init_data)
    users = conn.execute("SELECT u.tg_id,u.full_name,u.role,u.username,EXISTS(SELECT 1 FROM blocked_telegram b WHERE b.tg_id=u.tg_id) AS blocked FROM users u ORDER BY u.role DESC,u.full_name COLLATE NOCASE").fetchall()
    result = []
    for u in users:
        held = conn.execute("SELECT item_code FROM checkouts WHERE user_id = ? AND returned_at IS NULL", (u["tg_id"],)).fetchall()
        result.append({"tg_id": u["tg_id"], "full_name": u["full_name"], "role": ("" if u["tg_id"] == MAIN_ADMIN_ID and not actor["is_owner"] else u["role"]), "is_owner": actor["is_owner"] and u["tg_id"] == MAIN_ADMIN_ID, "held_items": [h["item_code"] for h in held], "username": (u["username"] or "") if u["tg_id"] != MAIN_ADMIN_ID or actor["is_owner"] else "", "blocked": bool(u["blocked"])})
    conn.close(); return result

@app.post("/api/users/{tg_id}/update")
def update_user(tg_id: int, req: UserUpdate, x_init_data: Optional[str] = Header(None)):
    actor=check_admin(x_init_data)
    if req.role not in ("admin","employee","guest","boss") or not req.full_name.strip(): raise HTTPException(400,"Некорректные данные пользователя")
    with transaction() as conn:
        target=conn.execute("SELECT role FROM users WHERE tg_id=?",(tg_id,)).fetchone()
        if not target: raise HTTPException(404,"Пользователь не найден")
        if tg_id==MAIN_ADMIN_ID and (not actor["is_owner"] or req.role!="admin"): raise HTTPException(403,"Главный администратор защищён")
        if not actor["is_owner"] and (target["role"] in ("admin","boss") or req.role in ("admin","boss")): raise HTTPException(403,"Только главный администратор управляет администраторами")
        if (tg_id<0)!=(req.role=="guest"): raise HTTPException(400,"Нельзя изменить тип аккаунта")
        conn.execute("UPDATE users SET full_name=?,role=? WHERE tg_id=?",(req.full_name.strip(),req.role,tg_id))
        audit(conn,actor,"Изменение пользователя",tg_id)
    return {"status":"ok"}

@app.delete("/api/users/{tg_id}")
def delete_user(tg_id: int, x_init_data: Optional[str] = Header(None)):
    actor=check_admin(x_init_data)
    with transaction() as conn:
        target=conn.execute("SELECT role FROM users WHERE tg_id=?",(tg_id,)).fetchone()
        if not target: raise HTTPException(404,"Пользователь не найден")
        if tg_id==MAIN_ADMIN_ID or (target["role"] in ("admin","boss") and not actor["is_owner"]): raise HTTPException(403,"Нельзя удалить этого администратора")
        if conn.execute("SELECT 1 FROM checkouts WHERE (user_id=? OR giver_id=?) AND returned_at IS NULL",(tg_id,tg_id)).fetchone(): raise HTTPException(409,"Сначала верните оборудование")
        conn.execute("DELETE FROM web_sessions WHERE user_id=?",(tg_id,))
        conn.execute("DELETE FROM web_codes WHERE user_id=?",(tg_id,))
        conn.execute("DELETE FROM users WHERE tg_id=?",(tg_id,))
        audit(conn,actor,"Удаление пользователя",tg_id)
    return {"status":"ok"}

@app.get("/api/locations")
def list_locations(x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data)
    conn = get_conn(x_init_data); rows = conn.execute("SELECT id, name, type FROM locations ORDER BY id").fetchall(); conn.close(); return [dict(r) for r in rows]

@app.get("/api/locations_view")
def locations_view(x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data)
    with contextmanager_session() as conn:
        rows = conn.execute("""SELECT l.id, l.name, l.type,
            COALESCE(SUM(CASE WHEN i.code IS NOT NULL THEN s.quantity ELSE 0 END),0) AS count,
            COALESCE(SUM(CASE WHEN i.kind='equipment' THEN s.quantity ELSE 0 END),0) AS equipment_count,
            COALESCE(SUM(CASE WHEN i.kind='consumable' THEN s.quantity ELSE 0 END),0) AS consumable_count
            FROM locations l LEFT JOIN stock s ON s.location_id=l.id AND s.quantity>0
            LEFT JOIN items i ON i.code=s.item_code AND i.is_archived=0
            GROUP BY l.id,l.name,l.type ORDER BY l.id""").fetchall()
        return [dict(row) for row in rows]

@app.get("/api/room_detail/{location_id}")
def room_detail(location_id: int, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data); is_admin = True
    conn = get_conn(x_init_data); location = conn.execute("SELECT name FROM locations WHERE id = ?", (location_id,)).fetchone()
    if not location: conn.close(); raise HTTPException(404, "Комната не найдена")
    items = conn.execute("SELECT s.item_code, s.quantity FROM stock s JOIN items i ON i.code = s.item_code WHERE s.location_id = ? AND s.quantity > 0 AND i.is_archived = 0", (location_id,)).fetchall()
    checkouts = conn.execute("SELECT c.item_code, u.full_name, c.taken_for FROM checkouts c LEFT JOIN users u ON u.tg_id = c.user_id WHERE c.location_id = ? AND c.returned_at IS NULL", (location_id,)).fetchall()
    item_details = {i["code"]: dict(i) for i in conn.execute("SELECT code, name, category, serial_number, needs_repair, price, budget_tag, buyout_status FROM items").fetchall()}
    conn.close()
    
    result_items = []
    for item in items:
        detail = item_details.get(item["item_code"], {})
        data = {"code": item["item_code"], "name": detail.get("name", "—"), "category": detail.get("category", ""), "quantity": item["quantity"], "serial_number": detail.get("serial_number", ""), "needs_repair": detail.get("needs_repair", 0), "budget_tag": detail.get("budget_tag", ""), "buyout_status": detail.get("buyout_status", ""), "is_on_hand": False}
        if is_admin: data["price"] = detail.get("price", 0)
        result_items.append(data)
        
    for c in checkouts:
        detail = item_details.get(c["item_code"], {})
        holder_name = c["full_name"] or c["taken_for"] or "—"
        data = {"code": c["item_code"], "name": detail.get("name", "—"), "category": detail.get("category", ""), "quantity": 0, "serial_number": detail.get("serial_number", ""), "needs_repair": detail.get("needs_repair", 0), "budget_tag": detail.get("budget_tag", ""), "buyout_status": detail.get("buyout_status", ""), "is_on_hand": True, "holder": holder_name}
        if is_admin: data["price"] = detail.get("price", 0)
        result_items.append(data)
        
    return {"location_name": location["name"], "items": result_items}

@app.post("/api/locations")
def create_location(req: LocationCreate, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data); conn = get_conn(x_init_data)
    try: conn.execute("INSERT INTO locations (name) VALUES (?)", (req.name.strip(),)); conn.commit()
    except sqlite3.IntegrityError: conn.close(); raise HTTPException(400, "Такая комната уже есть")
    conn.close(); return {"status": "ok"}

@app.post("/api/locations/update")
def update_location(req: LocationUpdate, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data); conn = get_conn(x_init_data)
    try: conn.execute("UPDATE locations SET name = ? WHERE id = ?", (req.name.strip(), req.id)); conn.commit()
    except Exception as e: conn.close(); raise HTTPException(400, str(e))
    conn.close(); return {"status": "ok"}

@app.get("/api/stats")
def get_stats(x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data)
    conn = get_conn(x_init_data)
    default_cats = [r[0] for r in conn.execute("SELECT name FROM categories ORDER BY name")]
    db_cats = [r["category"] for r in conn.execute("SELECT DISTINCT category FROM items WHERE category != '' AND is_archived = 0").fetchall()]
    all_cats = list(dict.fromkeys(default_cats + db_cats))
    
    result = []
    for name in all_cats:
        total_qty = conn.execute("SELECT COALESCE(SUM(s.quantity), 0) AS q FROM stock s JOIN items i ON i.code = s.item_code WHERE i.category = ? AND i.is_archived = 0", (name,)).fetchone()["q"]
        in_work = conn.execute("SELECT COUNT(*) AS q FROM checkouts c JOIN items i ON i.code = c.item_code WHERE i.category = ? AND c.returned_at IS NULL AND i.is_archived = 0", (name,)).fetchone()["q"]
        result.append({"name": name, "total": total_qty + in_work, "on_stock": total_qty, "in_work": in_work})
        
    no_cat_total = conn.execute("SELECT COALESCE(SUM(s.quantity), 0) AS q FROM stock s JOIN items i ON i.code = s.item_code WHERE (i.category = '' OR i.category IS NULL) AND i.is_archived = 0").fetchone()["q"]
    no_cat_work = conn.execute("SELECT COUNT(*) AS q FROM checkouts c JOIN items i ON i.code = c.item_code WHERE (i.category = '' OR i.category IS NULL) AND c.returned_at IS NULL AND i.is_archived = 0").fetchone()["q"]
    
    if no_cat_total + no_cat_work > 0:
        result.append({"name": "Без категории", "total": no_cat_total + no_cat_work, "on_stock": no_cat_total, "in_work": no_cat_work})
        
    conn.close()
    return result

@app.get("/api/low_stock")
def get_low_stock(x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data)
    conn = get_conn(x_init_data)
    rows = conn.execute("""
        SELECT i.code, i.name, i.min_stock, COALESCE(SUM(s.quantity), 0) as total_qty
        FROM items i
        LEFT JOIN stock s ON i.code = s.item_code
        WHERE i.kind = 'consumable' AND i.min_stock > 0 AND i.is_archived = 0
        GROUP BY i.code
        HAVING total_qty <= i.min_stock
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def next_item_code(conn, prefix):
    prefix = (prefix or "").upper()
    if not re.fullmatch(r"[A-Z]{2,12}", prefix):
        prefix = "ITEM"
    rows = conn.execute("SELECT code FROM items WHERE code LIKE ?", (f"{prefix}-%",))
    suffixes = (row["code"].rsplit("-", 1)[-1] for row in rows)
    serial = max((int(val) for val in suffixes if val.isascii() and val.isdigit()), default=0)
    return f"{prefix}-{serial + 1}"


@app.get("/api/next_code")
def get_next_code(prefix: Optional[str] = None, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data)
    with contextmanager_session() as conn:
        return {"code": next_item_code(conn, prefix)}

@app.get("/api/items")
def list_items(x_init_data: Optional[str] = Header(None)):
    is_admin = get_user(x_init_data)["role"] == "admin"
    conn = get_conn(x_init_data); items = conn.execute("SELECT i.code,i.name,i.kind,i.min_stock,i.needs_repair,i.kit_body,i.kit_lens,i.kit_flash,i.kit_acc,i.kit_add,i.budget_tag,i.serial_number,i.buyout_status,i.category,i.created_at,i.price,i.price_body,i.price_lens,i.price_flash,i.price_acc,i.price_add,CASE WHEN LENGTH(COALESCE(i.photo,''))>0 THEN 1 ELSE 0 END AS has_photo,COALESCE(m.site,'') AS site,COALESCE(m.vessel,'') AS vessel,COALESCE(m.unit,'шт.') AS unit FROM items i LEFT JOIN item_metadata m ON m.code=i.code WHERE i.is_archived=0 ORDER BY i.name").fetchall(); result = []
    stock_map={}; holder_map={}
    for row in conn.execute("SELECT s.item_code,s.location_id,l.name AS location_name,s.quantity FROM stock s JOIN locations l ON l.id=s.location_id WHERE s.quantity>0"):
        v=dict(row); key=v.pop("item_code"); stock_map.setdefault(key,[]).append(v)
    for row in conn.execute("SELECT c.item_code,c.id,c.user_id,u.full_name,c.taken_at,c.taken_for,c.giver_id,g.full_name AS giver_name FROM checkouts c LEFT JOIN users u ON u.tg_id=c.user_id LEFT JOIN users g ON g.tg_id=c.giver_id WHERE c.returned_at IS NULL"):
        v=dict(row); key=v.pop("item_code"); holder_map.setdefault(key,[]).append(v)
    for it in items:
        stocks=stock_map.get(it['code'],[]); holders=holder_map.get(it['code'],[])
        total = sum(s["quantity"] for s in stocks)
        
        c_at = it["created_at"] if "created_at" in it.keys() else ""
        
        item_data = {"code": it["code"], "name": it["name"], "kind": it["kind"], "min_stock": it["min_stock"], "needs_repair": it["needs_repair"], "kit_body": it["kit_body"], "kit_lens": it["kit_lens"], "kit_flash": it["kit_flash"], "kit_acc": it["kit_acc"], "kit_add": it["kit_add"], "budget_tag": it["budget_tag"], "serial_number": it["serial_number"], "buyout_status": it["buyout_status"], "category": it["category"], "total": total, "created_at": c_at, "is_low": total <= it["min_stock"] and it["min_stock"] > 0 and it["kind"] == "consumable", "stocks": [dict(s) for s in stocks], "holders": [dict(h) for h in holders]}
        
        item_data.update({"has_photo":bool(it["has_photo"]),"site":it["site"],"vessel":it["vessel"],"unit":it["unit"]})
        if is_admin: 
            item_data["price"] = it["price"]
            item_data["price_body"] = it["price_body"]
            item_data["price_lens"] = it["price_lens"]
            item_data["price_flash"] = it["price_flash"]
            item_data["price_acc"] = it["price_acc"]
            item_data["price_add"] = it["price_add"]
            
        result.append(item_data)
    conn.close(); return result

@app.get("/api/items/{code}")
def get_item(code: str, x_init_data: Optional[str] = Header(None)):
    is_admin = get_user(x_init_data)["role"] == "admin"
    conn = get_conn(x_init_data)
    item = conn.execute("""
        SELECT i.*, COALESCE(NULLIF(m.unit,''),'шт.') AS unit
        FROM items i LEFT JOIN item_metadata m ON m.code=i.code
        WHERE i.code=? AND i.is_archived=0
    """, (code,)).fetchone()
    if not item: conn.close(); raise HTTPException(404, "Товар не найден")
    stocks = conn.execute("SELECT s.location_id, l.name AS location_name, s.quantity FROM stock s JOIN locations l ON l.id = s.location_id WHERE s.item_code = ? AND s.quantity > 0", (code,)).fetchall()
    holders = conn.execute("""
        SELECT c.id, c.user_id, u.full_name, c.taken_at, c.taken_for, c.giver_id, g.full_name as giver_name, reminder.plan AS return_plan, handoff.handed_at
        FROM checkouts c 
        LEFT JOIN users u ON u.tg_id = c.user_id
        LEFT JOIN users g ON g.tg_id = c.giver_id
        LEFT JOIN checkout_return_reminders reminder ON reminder.checkout_id = c.id
        LEFT JOIN checkout_handoffs handoff ON handoff.checkout_id = c.id
        WHERE c.item_code = ? AND c.returned_at IS NULL
    """, (code,)).fetchall()
    buyout = None
    if is_admin and str(item["buyout_status"] or "").strip():
        buyout = conn.execute(
            "SELECT total_cents,remaining_cents FROM equipment_buyout_amounts WHERE item_code=?", (code,)
        ).fetchone()
    conn.close()
    
    c_at = item["created_at"] if "created_at" in item.keys() else ""
    
    result = {"code": item["code"], "name": item["name"], "kind": item["kind"], "min_stock": item["min_stock"], "needs_repair": item["needs_repair"], "kit_body": item["kit_body"], "kit_lens": item["kit_lens"], "kit_flash": item["kit_flash"], "kit_acc": item["kit_acc"], "kit_add": item["kit_add"], "budget_tag": item["budget_tag"], "serial_number": item["serial_number"], "buyout_status": item["buyout_status"], "category": item["category"], "created_at": c_at, "unit": item["unit"], "stocks": [dict(s) for s in stocks], "holders": [dict(h, return_plan=PLANS.get(h["return_plan"])) for h in holders]}
    
    if is_admin: 
        result["price"] = item["price"]
        result["price_body"] = item["price_body"]
        result["price_lens"] = item["price_lens"]
        result["price_flash"] = item["price_flash"]
        result["price_acc"] = item["price_acc"]
        result["price_add"] = item["price_add"]
        
        if buyout:
            result["buyout"] = {
                "total": buyout["total_cents"] / 100,
                "remaining": buyout["remaining_cents"] / 100,
                "paid": (buyout["total_cents"] - buyout["remaining_cents"]) / 100,
            }
    return result

@app.post("/api/items/{code}/update")
def update_item(code: str, req: ItemUpdate, x_init_data: Optional[str] = Header(None)):
    actor=check_admin(x_init_data)
    validate_item_fields(req.name,req.kind,req.min_stock,[req.price,req.price_body,req.price_lens,req.price_flash,req.price_acc,req.price_add])
    req.name=req.name.strip(); req.category=req.category.strip()
    if req.kind=="equipment" and not req.budget_tag.strip(): req.budget_tag=budget_for_equipment_name(req.name)
    buyout_total = buyout_remaining = None
    if req.buyout is not None and (req.buyout.total is not None or req.buyout.remaining is not None):
        if req.kind != "equipment" or not req.buyout_status.strip():
            raise HTTPException(400, "Укажите, у кого техника на выкупе")
        if req.buyout.total is None:
            raise HTTPException(400, "Укажите полную сумму выкупа")
        buyout_total = req.buyout.total
        buyout_remaining = req.buyout.remaining if req.buyout.remaining is not None else buyout_total
        if buyout_remaining > buyout_total:
            raise HTTPException(400, "Остаток не может быть больше суммы выкупа")

    with transaction() as conn:
        existing = active_item(conn, code)
        if existing["kind"] != req.kind:
            raise HTTPException(409, "Тип существующего товара менять нельзя")
        if req.kind == "consumable":
            req.kit_body=req.kit_lens=req.kit_flash=req.kit_acc=req.kit_add=req.serial_number=req.buyout_status=""
            req.price_body=req.price_lens=req.price_flash=req.price_acc=req.price_add=0
        conn.execute("""UPDATE items SET
            name=?, kind=?, min_stock=?, price=?,
            kit_body=?, kit_lens=?, kit_flash=?, kit_acc=?, kit_add=?,
            price_body=?, price_lens=?, price_flash=?, price_acc=?, price_add=?,
            budget_tag=?, serial_number=?, buyout_status=?, category=?
            WHERE code=?""", (
                req.name, req.kind, req.min_stock, req.price,
                req.kit_body, req.kit_lens, req.kit_flash, req.kit_acc, req.kit_add,
                req.price_body, req.price_lens, req.price_flash, req.price_acc, req.price_add,
                req.budget_tag, req.serial_number, req.buyout_status, req.category, code
            ))
        if buyout_total is not None:
            conn.execute("""INSERT INTO equipment_buyout_amounts(item_code,total_cents,remaining_cents)
                VALUES(?,?,?) ON CONFLICT(item_code) DO UPDATE SET
                total_cents=excluded.total_cents, remaining_cents=excluded.remaining_cents""",
                (code, int(buyout_total * 100), int(buyout_remaining * 100)))
        elif req.buyout is not None or not req.buyout_status.strip():
            conn.execute("DELETE FROM equipment_buyout_amounts WHERE item_code=?", (code,))
        if req.category:
            conn.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (req.category,))
        audit(conn, actor, "Изменение товара", code)
    return {"status": "ok"}

@app.post("/api/items/{code}/repair")
async def toggle_repair(code: str, x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data); conn = get_conn(x_init_data); item = conn.execute("SELECT needs_repair, name FROM items WHERE code = ?", (code,)).fetchone()
    if not item: conn.close(); raise HTTPException(404, "Товар не найден")
    new_status = 0 if item["needs_repair"] else 1
    if not new_status and conn.execute("SELECT 1 FROM repair_records WHERE code=? AND finished_at IS NULL",(code,)).fetchone(): conn.close(); raise HTTPException(409,"Завершите ремонт в карточке")
    conn.execute("UPDATE items SET needs_repair = ? WHERE code = ?", (new_status, code)); conn.commit(); conn.close()
    if new_status == 1:
        asyncio.create_task(notify_admin_action(f"🔧 Внимание! Товар {item['name']} ({code}) отправлен в ремонт."))
    return {"status": "ok", "message": f"Товар {item['name']} {'отправлен в ремонт' if new_status else 'возвращен в строй'}"}

@app.post("/api/items/{code}/lost")
def mark_lost(code: str, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data); conn = get_conn(x_init_data)
    item = conn.execute("SELECT name FROM items WHERE code = ?", (code,)).fetchone()
    if not item: conn.close(); raise HTTPException(404, "Товар не найден")
    conn.execute("INSERT INTO lost_items (item_code, user_id) VALUES (?, ?)", (code, user["tg_id"]))
    conn.commit(); conn.close(); return {"status": "ok", "message": f"Отмечено: {item['name']} не найден"}

@app.delete("/api/items/{code}")
def archive_item(code: str, x_init_data: Optional[str] = Header(None)):
    actor=check_admin(x_init_data)
    with transaction() as conn:
        active_item(conn,code)
        if conn.execute("SELECT 1 FROM checkouts WHERE item_code=? AND returned_at IS NULL",(code,)).fetchone(): raise HTTPException(409,"Сначала верните оборудование")
        conn.execute("UPDATE items SET is_archived=1 WHERE code=?",(code,))
        audit(conn,actor,"Архивирование",code)
    return {"status":"ok"}

@app.post("/api/items")
async def create_item(code: str = Form(""), name: str = Form(...), kind: str = Form("equipment"), location_id: int = Form(0), quantity: int = Form(0), min_stock: int = Form(0), price: float = Form(0), kit_body: str = Form(""), kit_lens: str = Form(""), kit_flash: str = Form(""), kit_acc: str = Form(""), kit_add: str = Form(""), price_body: float = Form(0), price_lens: float = Form(0), price_flash: float = Form(0), price_acc: float = Form(0), price_add: float = Form(0), budget_tag: str = Form(""), serial_number: str = Form(""), buyout_status: str = Form(""), category: str = Form(""), photo: Optional[UploadFile] = File(None), code_prefix: str = Form(""), unit: str = Form("шт."), supplier: str = Form(""), notes: str = Form(""), x_init_data: Optional[str] = Header(None)):
    actor=check_admin(x_init_data)
    validate_item_fields(name,kind,min_stock,[price,price_body,price_lens,price_flash,price_acc,price_add])
    code=code.strip(); name=name.strip(); category=category.strip()
    if kind=="equipment" and not budget_tag.strip(): budget_tag=budget_for_equipment_name(name)
    if code and not re.fullmatch(r"[\w.-]{1,64}",code): raise HTTPException(400,"Недопустимый код")
    if quantity<0: raise HTTPException(400,"Количество не может быть отрицательным")
    if kind=="consumable":
        metadata = passport_values(ItemMetadata(unit=unit, supplier=supplier, notes=notes))
        kit_body=kit_lens=kit_flash=kit_acc=kit_add=serial_number=buyout_status=""
        price_body=price_lens=price_flash=price_acc=price_add=0
    photo_base64=""
    if photo:
        raw=await photo.read(5*1024*1024+1)
        if len(raw)>5*1024*1024: raise HTTPException(413,"Фото больше 5 МБ")
        try:
            with Image.open(io.BytesIO(raw)) as im:
                if im.width*im.height>24_000_000: raise ValueError()
                im.thumbnail((1600,1600)); output=io.BytesIO(); im.convert("RGB").save(output,format="JPEG",quality=85)
                photo_base64=base64.b64encode(output.getvalue()).decode("ascii")
        except Exception: raise HTTPException(400,"Некорректное изображение")
    if kind == "equipment":
        quantity = quantity or 1
        if quantity != 1:
            raise HTTPException(400, "У оборудования должен быть уникальный код на каждую единицу")

    with transaction() as conn:
        if location_id == 0:
            location = conn.execute("SELECT id FROM locations ORDER BY id LIMIT 1").fetchone()
            location_id = location["id"] if location else 1
        valid_location(conn, location_id)
        code = code or next_item_code(conn, code_prefix)
        if conn.execute("SELECT 1 FROM items WHERE code=?", (code,)).fetchone():
            raise HTTPException(400, "Код уже существует")
        conn.execute("""INSERT INTO items (
            code, name, kind, min_stock, photo, price,
            kit_body, kit_lens, kit_flash, kit_acc, kit_add,
            price_body, price_lens, price_flash, price_acc, price_add,
            budget_tag, serial_number, buyout_status, category
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (code, name, kind, min_stock, photo_base64, price,
         kit_body, kit_lens, kit_flash, kit_acc, kit_add,
         price_body, price_lens, price_flash, price_acc, price_add,
         budget_tag, serial_number, buyout_status, category))
        conn.execute("INSERT INTO stock (item_code, location_id, quantity) VALUES (?,?,?)", (code, location_id, quantity))
        if kind == "consumable":
            conn.execute("INSERT INTO item_metadata(code,unit,supplier,site,vessel,notes) VALUES(?,?,?,?,?,?)", (code, *metadata))
        if category:
            conn.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (category,))
        audit(conn, actor, "Создание товара", code)
    return {"status": "ok", "code": code}

@app.get("/api/checkout/recipients")
def checkout_recipients(x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    if not user["is_registered"]:
        raise HTTPException(403, "Сначала завершите регистрацию")
    with contextmanager_session() as conn:
        current = conn.execute("""
            SELECT u.tg_id, u.full_name
            FROM users u
            LEFT JOIN blocked_telegram b ON b.tg_id=u.tg_id
            WHERE u.tg_id!=? AND b.tg_id IS NULL AND TRIM(COALESCE(u.full_name,''))<>''
              AND (u.is_registered=1 OR EXISTS (
                  SELECT 1 FROM checkouts c WHERE c.user_id=u.tg_id
                    AND TRIM(COALESCE(c.taken_for,''))<>''
              ))
        """, (user["tg_id"],)).fetchall()
        history = conn.execute("""
            SELECT DISTINCT c.taken_for
            FROM checkouts c
            LEFT JOIN users u ON u.tg_id=c.user_id
            LEFT JOIN blocked_telegram b ON b.tg_id=c.user_id
            WHERE c.user_id!=? AND b.tg_id IS NULL
              AND (u.tg_id IS NULL OR TRIM(COALESCE(u.full_name,''))='')
              AND TRIM(COALESCE(c.taken_for,''))<>''
        """, (user["tg_id"],)).fetchall()

    results = [{"id": row["tg_id"], "name": recipient_name(row["full_name"])} for row in current]
    known = {recipient_key(row["name"]) for row in results}
    for row in history:
        name = recipient_name(row["taken_for"])
        key = recipient_key(name)
        if key not in known:
            known.add(key)
            results.append({"id": None, "name": name})
    return sorted(results, key=lambda row: recipient_key(row["name"]))


@app.post("/api/checkout_batch")
async def checkout_batch(req: BatchCheckoutRequest, x_init_data: Optional[str] = Header(None)):
    user=get_user(x_init_data); success=[]; errors=[]
    with transaction() as conn:
        for code in dict.fromkeys(req.codes):
            conn.execute("SAVEPOINT batch_checkout")
            try:
                _checkout_one(conn,user,code,req.taken_for)
                success.append(code)
            except HTTPException as exc:
                conn.execute("ROLLBACK TO batch_checkout")
                errors.append(f"{code}: {exc.detail}")
            finally:
                conn.execute("RELEASE batch_checkout")
    return {"status":"ok","success_count":len(success),"errors":errors}

@app.post("/api/checkout")
async def checkout(req: CheckoutRequest, x_init_data: Optional[str] = Header(None)):
    user=get_user(x_init_data)
    with transaction() as conn: _checkout_one(conn,user,req.code,req.taken_for,req.recipient_id)
    return {"status":"ok"}


def _checkout_one(conn,user,code,taken_for,recipient_id=None):
    item=active_item(conn,code)
    if item["kind"]!="equipment": raise HTTPException(400,"Это расходник")
    if item["needs_repair"]: raise HTTPException(400,"Товар в ремонте")
    if conn.execute("SELECT 1 FROM checkouts WHERE item_code=? AND returned_at IS NULL",(code,)).fetchone(): raise HTTPException(409,"Уже выдано")
    stock=conn.execute("SELECT location_id FROM stock WHERE item_code=? AND quantity>0 ORDER BY location_id LIMIT 1",(code,)).fetchone()
    if not stock: raise HTTPException(409,"Нет в наличии")
    taken_for = recipient_name(taken_for)
    if len(taken_for) > 150:
        raise HTTPException(400, "Укажите имя получателя до 150 символов")
    target = user["tg_id"]
    if taken_for or recipient_id is not None:
        target, taken_for = resolve_recipient(conn, taken_for, recipient_id)
        if target == user["tg_id"]:
            taken_for = ""
    booking=conn.execute("SELECT user_id FROM bookings WHERE item_code=? AND date('now') BETWEEN date_from AND date_to",(code,)).fetchall()
    if booking and not all(b['user_id']==target for b in booking): raise HTTPException(409,"Сегодня оборудование забронировано другим сотрудником")
    record = conn.execute("""
        INSERT INTO checkouts(item_code,user_id,giver_id,location_id,taken_for)
        VALUES(?,?,?,?,?) RETURNING id,taken_at
    """, (code,target,user["tg_id"],stock["location_id"],taken_for)).fetchone()
    if target > 0:
        queue_return_reminder(conn,record["id"],record["taken_at"])
    conn.execute("UPDATE stock SET quantity=quantity-1 WHERE item_code=? AND location_id=?",(code,stock["location_id"]))
    conn.execute("DELETE FROM stock WHERE item_code=? AND quantity=0",(code,))


@app.post("/api/checkout/{checkout_id}/handoff")
def handoff_checkout(checkout_id: int, x_init_data: Optional[str] = Header(None)):
    actor = get_user(x_init_data)
    with transaction() as conn:
        checkout = conn.execute("""
            SELECT item_code, taken_for
            FROM checkouts
            WHERE id=? AND giver_id=? AND user_id!=giver_id AND returned_at IS NULL
              AND TRIM(COALESCE(taken_for,''))<>''
        """, (checkout_id, actor["tg_id"])).fetchone()
        if not checkout:
            raise HTTPException(404, "Выдача для передачи недоступна")
        created = conn.execute("INSERT OR IGNORE INTO checkout_handoffs(checkout_id) VALUES(?)", (checkout_id,))
        if created.rowcount:
            audit(conn, actor, "Передача техники", f'{checkout["item_code"]} · {checkout["taken_for"]}')
    return {"status": "ok", "recipient": checkout["taken_for"], "code": checkout["item_code"]}

@app.post("/api/return")
async def return_item(code: str, x_init_data: Optional[str] = Header(None)):
    user=get_user(x_init_data)
    with transaction() as conn:
        co=conn.execute("SELECT id,location_id FROM checkouts WHERE item_code=? AND returned_at IS NULL",(code,)).fetchone()
        if not co: raise HTTPException(400,"Не выдано")
        conn.execute("UPDATE checkouts SET returned_at=CURRENT_TIMESTAMP,returned_by=? WHERE id=?",(user["tg_id"],co["id"]))
        conn.execute("INSERT INTO stock(item_code,location_id,quantity) VALUES(?,?,1) ON CONFLICT(item_code,location_id) DO UPDATE SET quantity=quantity+1",(code,co["location_id"]))
    return {"status":"ok"}

@app.post("/api/move")
def move_item(req: MoveRequest, x_init_data: Optional[str] = Header(None)):
    user=get_user(x_init_data)
    with transaction() as conn: _move_one(conn,user,req.code,req.from_location,req.to_location,req.quantity)
    return {"status":"ok"}


def _move_one(conn,user,code,source,dest,quantity):
    if quantity<=0 or source==dest: raise HTTPException(400,"Проверьте количество и помещения")
    active_item(conn,code); valid_location(conn,source); valid_location(conn,dest)
    row=conn.execute("SELECT quantity FROM stock WHERE item_code=? AND location_id=?",(code,source)).fetchone()
    if not row or row[0]<quantity: raise HTTPException(400,"Недостаточно товара")
    conn.execute("UPDATE stock SET quantity=quantity-? WHERE item_code=? AND location_id=?",(quantity,code,source))
    conn.execute("DELETE FROM stock WHERE item_code=? AND location_id=? AND quantity=0",(code,source))
    conn.execute("INSERT INTO stock(item_code,location_id,quantity) VALUES(?,?,?) ON CONFLICT(item_code,location_id) DO UPDATE SET quantity=quantity+excluded.quantity",(code,dest,quantity))
    conn.execute("INSERT INTO movements(item_code,quantity,from_location,to_location,user_id) VALUES(?,?,?,?,?)",(code,quantity,source,dest,user["tg_id"]))

@app.post("/api/move_batch")
def move_batch(req: BatchMoveRequest, x_init_data: Optional[str] = Header(None)):
    user=get_user(x_init_data); errors=[]; count=0
    with transaction() as conn:
        for code in dict.fromkeys(req.codes):
            try: _move_one(conn,user,code,req.from_location,req.to_location,1); count+=1
            except HTTPException as exc: errors.append(f"{code}: {exc.detail}")
    return {"status":"ok","success_count":count,"errors":errors}

@app.post("/api/writeoff")
async def writeoff(req: WriteoffRequest, background_tasks: BackgroundTasks, x_init_data: Optional[str] = Header(None)):
    user=get_user(x_init_data); notice=None
    if req.quantity<=0: raise HTTPException(400,"Количество должно быть больше нуля")
    with transaction() as conn:
        item=active_item(conn,req.code); valid_location(conn,req.location_id)
        row=conn.execute("SELECT quantity FROM stock WHERE item_code=? AND location_id=?",(req.code,req.location_id)).fetchone()
        if not row or row[0]<req.quantity: raise HTTPException(400,"Недостаточно товара")
        total=conn.execute("SELECT COALESCE(SUM(quantity),0) FROM stock WHERE item_code=?",(req.code,)).fetchone()[0]
        conn.execute("UPDATE stock SET quantity=quantity-? WHERE item_code=? AND location_id=?",(req.quantity,req.code,req.location_id))
        conn.execute("DELETE FROM stock WHERE item_code=? AND location_id=? AND quantity=0",(req.code,req.location_id))
        conn.execute("INSERT INTO writeoffs(item_code,quantity,location_id,user_id) VALUES(?,?,?,?)",(req.code,req.quantity,req.location_id,user["tg_id"]))
        new=total-req.quantity
        if item["kind"]=="consumable" and item["min_stock"]>0 and new<=item["min_stock"]<total:
            notice=f"⚠️ Заканчивается: {item['name']}. Осталось: {new} шт."
    if notice: background_tasks.add_task(notify_admin_action,notice)
    return {"status":"ok"}

@app.get("/api/bookings/{code}")
def get_bookings(code: str, x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data); conn = get_conn(x_init_data)
    rows = conn.execute("SELECT b.id, b.item_code, b.user_id, u.full_name, b.date_from, b.date_to FROM bookings b LEFT JOIN users u ON u.tg_id = b.user_id WHERE b.item_code = ? AND b.date_to >= date('now') ORDER BY b.date_from", (code,)).fetchall()
    conn.close(); return [dict(r) for r in rows]

@app.post("/api/bookings")
def create_booking(req: BookingRequest, x_init_data: Optional[str] = Header(None)):
    user=get_user(x_init_data)
    try: start=date.fromisoformat(req.date_from); end=date.fromisoformat(req.date_to)
    except ValueError: raise HTTPException(400,"Укажите даты в формате ГГГГ-ММ-ДД")
    if start>end or start<date.today(): raise HTTPException(400,"Проверьте даты бронирования")
    with transaction() as conn:
        item=active_item(conn,req.code)
        if item["kind"]!="equipment" or item["needs_repair"]: raise HTTPException(409,"Бронирование недоступно")
        if conn.execute("SELECT 1 FROM bookings WHERE item_code=? AND date_from<=? AND date_to>=?",(req.code,end.isoformat(),start.isoformat())).fetchone(): raise HTTPException(409,"Оборудование уже забронировано на эти даты")
        conn.execute("INSERT INTO bookings(item_code,user_id,date_from,date_to) VALUES(?,?,?,?)",(req.code,user["tg_id"],start.isoformat(),end.isoformat()))
    return {"status":"ok"}

@app.get("/api/comments/{code}")
def get_comments(code: str, x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data); conn = get_conn(x_init_data)
    rows = conn.execute("SELECT c.id, c.item_code, c.user_id, u.full_name, c.text, c.created_at FROM comments c LEFT JOIN users u ON u.tg_id = c.user_id WHERE c.item_code = ? ORDER BY c.created_at DESC", (code,)).fetchall()
    conn.close(); return [dict(r) for r in rows]

@app.post("/api/comments")
def create_comment(req: CommentRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    if not 1<=len(req.text.strip())<=3000: raise HTTPException(400,"Введите комментарий до 3000 символов")
    conn = get_conn(x_init_data)
    active_item(conn,req.code)
    conn.execute("INSERT INTO comments (item_code, user_id, text) VALUES (?,?,?)", (req.code, user["tg_id"], req.text))
    conn.commit(); conn.close(); return {"status": "ok"}

@app.post("/api/clear_database")
def clear_database(x_init_data: Optional[str] = Header(None)):
    check_owner(x_init_data)
    raise HTTPException(403,"Массовое удаление рабочей базы отключено")

@app.post("/api/inventory_finish")
def inventory_finish(req: InventoryResult, x_init_data: Optional[str] = Header(None)):
    user=check_admin(x_init_data)
    with transaction() as conn:
        valid_location(conn,req.location_id)
        rows=conn.execute("SELECT s.item_code,s.quantity,i.kind,i.name FROM stock s JOIN items i ON i.code=s.item_code WHERE s.location_id=? AND s.quantity>0 AND i.is_archived=0",(req.location_id,)).fetchall()
        expected={r["item_code"]:r for r in rows}
        actual=req.counts if req.counts is not None else {c:expected[c]["quantity"] if c in expected else 1 for c in req.found}
        if any(q<0 or q>1000000 for q in actual.values()): raise HTTPException(400,"Некорректное количество")
        missing=[c for c,r in expected.items() if actual.get(c,0)<r["quantity"]]
        extra=[c for c,q in actual.items() if q>(expected[c]["quantity"] if c in expected else 0)]
        differences=[{"code":c,"expected":expected[c]["quantity"] if c in expected else 0,"actual":actual.get(c,0)} for c in dict.fromkeys(missing+extra)]
        for c in missing:
            if expected[c]["kind"]=="equipment" and actual.get(c,0)==0: conn.execute("INSERT INTO lost_items(item_code,user_id) VALUES(?,?)",(c,user["tg_id"]))
        report={"status":"ok","missing":missing,"extra":extra,"differences":differences}
        conn.execute("INSERT INTO inventory_runs(location_id,user_id,report) VALUES(?,?,?)",(req.location_id,user["tg_id"],json.dumps(report,ensure_ascii=False)))
        audit(conn,user,"Инвентаризация",req.location_id)
    return report

@app.get('/api/inventory_runs')
def inventory_runs(x_init_data:Optional[str]=Header(None)):
    check_admin(x_init_data)
    with contextmanager_session() as conn:
        return [{**dict(r),"report":json.loads(r["report"])} for r in conn.execute("SELECT r.*,l.name,u.full_name FROM inventory_runs r LEFT JOIN locations l ON l.id=r.location_id LEFT JOIN users u ON u.tg_id=r.user_id ORDER BY r.id DESC LIMIT 100")]

@app.post("/api/execute_sql")
def execute_sql(req: TerminalRequest, x_init_data: Optional[str] = Header(None)):
    user = check_owner(x_init_data); sql = req.sql.strip()
    if not sql: raise HTTPException(400, "Пустой запрос")
    sql_upper = sql.upper()
    if "DROP TABLE" in sql_upper or "DROP DATABASE" in sql_upper: raise HTTPException(400, "Нельзя удалять таблицы")
    conn = get_conn(x_init_data)
    try:
        blocked={sqlite3.SQLITE_ATTACH,sqlite3.SQLITE_DETACH,sqlite3.SQLITE_PRAGMA,sqlite3.SQLITE_DROP_TABLE,sqlite3.SQLITE_DROP_TEMP_TABLE,sqlite3.SQLITE_ALTER_TABLE,sqlite3.SQLITE_TRANSACTION,sqlite3.SQLITE_SAVEPOINT}
        def authorize(action,arg1,arg2,db,trigger):
            if str(arg1).lower() in ("web_codes","web_sessions") or action in blocked or (action==sqlite3.SQLITE_FUNCTION and str(arg2).lower() in ('load_extension','readfile','writefile')):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        conn.execute("BEGIN IMMEDIATE")
        conn.set_authorizer(authorize)
        cursor=conn.cursor(); cursor.execute(sql)
        rows=[dict(r) for r in cursor.fetchall()] if cursor.description else None
        conn.set_authorizer(None)
        conn.execute("INSERT INTO terminal_logs (user_id, sql_query) VALUES (?, ?)", (user["tg_id"], sql))
        if rows is not None:
            conn.commit(); conn.close(); return {"status": "ok", "type": "select", "data": rows}
        else:
            conn.commit(); count = cursor.rowcount; conn.close()
            return {"status": "ok", "type": "update", "message": f"Выполнено успешно. Затронуто строк: {count}"}
    except Exception as e: conn.set_authorizer(None); conn.rollback(); conn.close(); raise HTTPException(400, detail=str(e))

@app.get("/api/qr/{code}")
def generate_qr(code: str):
    if not 1 <= len(code) <= 64: raise HTTPException(400,"Недопустимый код")
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(code); qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    width, height = qr_img.size
    result_img = Image.new("RGB", (width, height + 60), "white"); result_img.paste(qr_img, (0, 0))
    draw = ImageDraw.Draw(result_img)
    font = label_font(36)
    try: text_w = draw.textlength(code, font=font)
    except AttributeError: text_w = draw.textsize(code, font=font)[0]
    draw.text(((width - text_w) / 2, height + 10), code, fill="black", font=font)
    buf = io.BytesIO(); result_img.save(buf, format="PNG"); buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

# --- Дополнительные API v17: интерфейс подключается отдельно ---
class CategoryChange(BaseModel):
    name: str

@app.get('/api/categories')
def categories(x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data)
    with transaction() as conn:
        return [r[0] for r in conn.execute('SELECT name FROM categories ORDER BY name')]

@app.post('/api/categories')
def add_category(req: CategoryChange, x_init_data: Optional[str] = Header(None)):
    actor=check_admin(x_init_data); name=req.name.strip()
    if not name or len(name)>80: raise HTTPException(400,'Название до 80 символов')
    with transaction() as conn:
        if any(r[0].casefold()==name.casefold() for r in conn.execute('SELECT name FROM categories')): raise HTTPException(409,'Такая категория уже существует')
        conn.execute('INSERT INTO categories(name) VALUES(?)',(name,)); audit(conn,actor,'Создание категории',name)
    return {'status':'ok'}

@app.put('/api/categories/{old}')
def rename_category(old: str, req: CategoryChange, x_init_data: Optional[str] = Header(None)):
    actor=check_admin(x_init_data); name=req.name.strip()
    if not name or len(name)>80: raise HTTPException(400,'Название до 80 символов')
    with transaction() as conn:
        if not conn.execute('SELECT 1 FROM categories WHERE name=?',(old,)).fetchone(): raise HTTPException(404,'Категория не найдена')
        if any(r[0].casefold()==name.casefold() and r[0]!=old for r in conn.execute('SELECT name FROM categories')): raise HTTPException(409,'Такая категория уже существует')
        conn.execute('UPDATE categories SET name=? WHERE name=?',(name,old)); conn.execute('UPDATE items SET category=? WHERE category=?',(name,old)); audit(conn,actor,'Переименование категории',old+' → '+name)
    return {'status':'ok'}

@app.delete('/api/categories/{name}')
def remove_category(name: str, x_init_data: Optional[str] = Header(None)):
    actor=check_admin(x_init_data)
    with transaction() as conn:
        if conn.execute('SELECT 1 FROM items WHERE category=?',(name,)).fetchone(): raise HTTPException(409,'Сначала перенесите товары в другую категорию')
        if not conn.execute('DELETE FROM categories WHERE name=?',(name,)).rowcount: raise HTTPException(404,'Категория не найдена')
        audit(conn,actor,'Удаление категории',name)
    return {'status':'ok'}

@app.get('/api/dashboard')
def dashboard(x_init_data: Optional[str] = Header(None)):
    user=get_user(x_init_data)
    with contextmanager_session() as conn:
        rows=conn.execute('''SELECT i.code,i.kind,i.needs_repair,i.min_stock,i.category,i.price,i.price_body,i.price_lens,i.price_flash,i.price_acc,i.price_add, COALESCE(s.qty,0) AS qty, COALESCE(h.qty,0) AS held,
          EXISTS(SELECT 1 FROM bookings b WHERE b.item_code=i.code AND date('now') BETWEEN b.date_from AND b.date_to) AS booked
          FROM items i LEFT JOIN (SELECT item_code,SUM(quantity) qty FROM stock GROUP BY item_code) s ON s.item_code=i.code
          LEFT JOIN (SELECT item_code,COUNT(*) qty FROM checkouts WHERE returned_at IS NULL GROUP BY item_code) h ON h.item_code=i.code WHERE i.is_archived=0''').fetchall()
    counts={'free':0,'on_hand':0,'repair':0,'booked_today':0,'low_stock':0}
    money={'total':0,'on_hand':0,'repair':0,'consumables':0}; by_cat={}
    for r in rows:
        qty=r['qty']; held=r['held']; price=r['price'] or 0
        if r['kind']=='equipment':
            # Repair and booking indicators can overlap with on-hand status.
            counts['free']+=qty if not r['needs_repair'] and not r['booked'] else 0
            counts['on_hand']+=held
            counts['repair']+=qty+held if r['needs_repair'] else 0
            counts['booked_today']+=int(bool(r['booked']))
            parts=sum(r[k] or 0 for k in ('price_body','price_lens','price_flash','price_acc','price_add'))
            if parts>0: price=parts
            money['on_hand']+=price*held
            if r['needs_repair']: money['repair']+=price*(qty+held)
        else:
            counts['low_stock']+=int(r['min_stock']>0 and qty<=r['min_stock'])
            money['consumables']+=price*qty
        value=price*(qty+held); money['total']+=value
        cat=r['category'] or 'Без категории'; by_cat[cat]=by_cat.get(cat,0)+value
    result={'counts':counts}
    if user['role'] == 'admin':
        with contextmanager_session() as conn:
            money['repair_cost_30_days']=conn.execute("SELECT COALESCE(SUM(cost),0) FROM repair_records WHERE finished_at>=datetime('now','-30 days')").fetchone()[0]
            money['receipt_cost_30_days']=conn.execute("SELECT COALESCE(SUM(quantity*unit_price),0) FROM receipts WHERE created_at>=datetime('now','-30 days')").fetchone()[0]
        result['finance']={**{k:round(v,2) for k,v in money.items()},'by_category':{k:round(v,2) for k,v in by_cat.items()}}
    return result

@app.get('/api/archive')
def archived_items(x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data)
    with transaction() as conn:
        return [dict(r) for r in conn.execute('SELECT code,name,kind,category FROM items WHERE is_archived=1 ORDER BY name')]

@app.post('/api/archive/{code}/restore')
def restore_item(code: str,x_init_data: Optional[str] = Header(None)):
    actor=check_admin(x_init_data)
    with transaction() as conn:
        if not conn.execute('UPDATE items SET is_archived=0 WHERE code=? AND is_archived=1',(code,)).rowcount: raise HTTPException(404,'Товар не найден в архиве')
        audit(conn,actor,'Восстановление товара',code)
    return {'status':'ok'}

@app.get('/api/audit')
def administrative_audit(x_init_data: Optional[str] = Header(None)):
    check_owner(x_init_data)
    with transaction() as conn:
        return [dict(r) for r in conn.execute('SELECT a.*,u.full_name FROM audit_log a LEFT JOIN users u ON a.user_id=u.tg_id ORDER BY a.id DESC LIMIT 500')]

@app.get('/api/backup')
def download_backup(x_init_data: Optional[str] = Header(None)):
    check_owner(x_init_data)
    with tempfile.TemporaryDirectory() as directory:
        path=os.path.join(directory,'snapshot.db'); source=get_conn(); target=sqlite3.connect(path)
        try: source.backup(target)
        finally: target.close(); source.close()
        clean=sqlite3.connect(path)
        try:
            clean.execute('DELETE FROM web_codes');clean.execute('DELETE FROM web_sessions');clean.commit();clean.execute('VACUUM')
        finally: clean.close()
        with open(path,'rb') as f: content=f.read()
    return StreamingResponse(io.BytesIO(content),media_type='application/octet-stream',headers={'Content-Disposition':'attachment; filename=warehouse_backup.db','Cache-Control':'no-store'})

@app.get('/api/label/{code}')
def print_label(code: str,name: Optional[str]=None,dpi: int=203,format: str='png',width_mm: int=50,height_mm: int=80,x_init_data: Optional[str]=Header(None)):
    if name is None: get_user(x_init_data)
    else: check_admin(x_init_data)
    if dpi not in (203,300) or format not in ('png','pdf') or not 1<=len(code)<=64: raise HTTPException(400,'Некорректные параметры этикетки')
    if name is None:
        with transaction() as conn: name=active_item(conn,code)['name']
    if not name.strip() or len(name)>250: raise HTTPException(400,'Укажите название')
    im=label_image(code,name,dpi,width_mm,height_mm); buf=io.BytesIO()
    if format=='pdf': im.save(buf,format='PDF',resolution=dpi)
    else: im.save(buf,format='PNG',dpi=(dpi,dpi))
    buf.seek(0)
    return StreamingResponse(buf,media_type='application/pdf' if format=='pdf' else 'image/png',headers={'Cache-Control':'no-store'})



class ItemMetadata(BaseModel):
    unit: str = "шт."
    supplier: str = ""
    site: str = ""
    vessel: str = ""
    notes: str = ""

@app.get('/api/items/{code}/passport')
def item_passport(code: str,x_init_data: Optional[str]=Header(None)):
    user=get_user(x_init_data)
    with transaction() as conn:
        item=active_item(conn,code)
        meta=conn.execute('SELECT unit,supplier,site,vessel,notes FROM item_metadata WHERE code=?',(code,)).fetchone()
        result=dict(meta) if meta else dict(ItemMetadata())
        if user['role'] not in ('admin','boss'): result.pop('supplier',None)
        result['has_photo']=bool(item['photo'])
    return result

def passport_values(metadata):
    values = [metadata.unit.strip(), metadata.supplier.strip(), metadata.site.strip(), metadata.vessel.strip(), metadata.notes.strip()]
    if not values[0] or any(len(value) > 250 for value in values[:4]) or len(values[4]) > 3000:
        raise HTTPException(400, "Проверьте поля паспорта")
    return values


@app.put('/api/items/{code}/passport')
def save_passport(code: str,req: ItemMetadata,x_init_data: Optional[str]=Header(None)):
    actor=check_admin(x_init_data)
    values=passport_values(req)
    with transaction() as conn:
        active_item(conn,code)
        conn.execute('INSERT INTO item_metadata(code,unit,supplier,site,vessel,notes) VALUES(?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET unit=excluded.unit,supplier=excluded.supplier,site=excluded.site,vessel=excluded.vessel,notes=excluded.notes',(code,*values))
        audit(conn,actor,'Обновление паспорта',code)
    return {'status':'ok'}

@app.get('/api/items/{code}/photo')
def item_photo(code: str,x_init_data: Optional[str]=Header(None)):
    get_user(x_init_data)
    with transaction() as conn: photo=active_item(conn,code)['photo']
    if not photo: raise HTTPException(404,'Фото отсутствует')
    try:
        with Image.open(io.BytesIO(base64.b64decode(photo))) as im:
            if im.width*im.height>24_000_000: raise ValueError()
            im.thumbnail((1600,1600)); buf=io.BytesIO(); im.convert('RGB').save(buf,format='JPEG',quality=85)
    except Exception: raise HTTPException(404,'Фото недоступно')
    buf.seek(0); return StreamingResponse(buf,media_type='image/jpeg',headers={'Cache-Control':'no-store'})

class RepairDetails(BaseModel):
    description: str
    cost: float=0

@app.get('/api/items/{code}/repairs')
def repair_history(code: str,x_init_data: Optional[str]=Header(None)):
    user=get_user(x_init_data)
    with transaction() as conn:
        active_item(conn,code)
        rows=[dict(r) for r in conn.execute('SELECT r.*,EXISTS(SELECT 1 FROM repair_photos p WHERE p.repair_id=r.id) AS has_photo FROM repair_records r WHERE code=? ORDER BY r.id DESC',(code,))]
    if user['role'] != 'admin':
        for r in rows: r.pop('cost',None)
    return rows

@app.post('/api/items/{code}/repairs')
def start_repair(code: str,req: RepairDetails,background_tasks: BackgroundTasks,x_init_data: Optional[str]=Header(None)):
    actor=get_user(x_init_data)
    if not req.description.strip() or len(req.description)>3000 or req.cost<0 or not math.isfinite(req.cost): raise HTTPException(400,'Проверьте описание и стоимость')
    if actor['role']!='admin' and req.cost: raise HTTPException(403,'Стоимость может задать только администратор')
    with transaction() as conn:
        item=active_item(conn,code)
        if item['kind']!='equipment': raise HTTPException(400,'Это расходник')
        if conn.execute('SELECT 1 FROM repair_records WHERE code=? AND finished_at IS NULL',(code,)).fetchone(): raise HTTPException(409,'Ремонт уже открыт')
        conn.execute('INSERT INTO repair_records(code,description,cost,user_id) VALUES(?,?,?,?)',(code,req.description.strip(),req.cost,actor['tg_id']))
        conn.execute('UPDATE items SET needs_repair=1 WHERE code=?',(code,)); audit(conn,actor,'Начало ремонта',code)
    background_tasks.add_task(notify_admin_action,f"🔧 В ремонт: {item['name']} ({code})")
    return {'status':'ok'}

@app.post('/api/items/{code}/repairs/finish')
def finish_repair(code: str,req: RepairDetails,x_init_data: Optional[str]=Header(None)):
    actor=check_admin(x_init_data)
    if req.cost<0 or not math.isfinite(req.cost): raise HTTPException(400,'Некорректная стоимость')
    with transaction() as conn:
        active_item(conn,code)
        if not conn.execute('UPDATE repair_records SET cost=?,finished_at=CURRENT_TIMESTAMP WHERE code=? AND finished_at IS NULL',(req.cost,code)).rowcount: raise HTTPException(409,'Нет открытого ремонта')
        conn.execute('UPDATE items SET needs_repair=0 WHERE code=?',(code,)); audit(conn,actor,'Завершение ремонта',code)
    return {'status':'ok'}

@app.get("/api/boss/equipment-costs")
def boss_equipment_costs(x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    if not user.get("is_registered") or user["role"] != "admin":
        raise HTTPException(403, "Нет доступа")
    with contextmanager_session() as conn:
        rows = conn.execute("""SELECT code,name,budget_tag,kit_body,kit_lens,kit_flash,
            price,price_body,price_lens,price_flash,price_acc,price_add
            FROM items WHERE kind='equipment' AND is_archived=0 ORDER BY name COLLATE NOCASE""").fetchall()
        result = []
        for item in rows:
            components = sum(float(item[key] or 0) for key in
                ("price_body","price_lens","price_flash","price_acc","price_add"))
            amount = components if components > 0 else float(item["price"] or 0)
            result.append({
                "code": item["code"], "name": item["name"],
                "model": (item["kit_body"] or item["kit_lens"] or item["kit_flash"] or "").strip(),
                "budget_tag": item["budget_tag"] or budget_for_equipment_name(item["name"]),
                "price": round(amount, 2),
            })
        return result


@app.get('/api/purchases')
def purchase_suggestions(x_init_data: Optional[str]=Header(None)):
    actor = get_user(x_init_data)
    if actor['role'] not in ('admin','boss'): raise HTTPException(403,'Нет доступа')
    with transaction() as conn:
        rows = [dict(r) for r in conn.execute("""SELECT i.code,i.name,i.min_stock,i.price,COALESCE(s.qty,0) AS remaining,COALESCE(w.qty,0) AS used_30_days,COALESCE(m.unit,'шт.') AS unit,COALESCE(m.supplier,'') AS supplier, MAX(0,i.min_stock+1-COALESCE(s.qty,0)) AS suggested_quantity FROM items i LEFT JOIN (SELECT item_code,SUM(quantity) qty FROM stock GROUP BY item_code) s ON s.item_code=i.code LEFT JOIN (SELECT item_code,SUM(quantity) qty FROM writeoffs WHERE created_at>=datetime('now','-30 days') GROUP BY item_code) w ON w.item_code=i.code LEFT JOIN item_metadata m ON m.code=i.code WHERE i.is_archived=0 AND i.kind='consumable' AND i.min_stock>0 AND COALESCE(s.qty,0)<=i.min_stock ORDER BY i.name""")]
    if actor['role'] != 'admin':
        for row in rows:
            row.pop('price')
    return rows


WEB_COOKIE = "warehouse_main_session"

def web_digest(value):
    return hmac.new(BOT_TOKEN.encode(), ("warehouse-main-web:" + value).encode(), hashlib.sha256).hexdigest()

@contextmanager
def contextmanager_session():
    conn=get_conn()
    try: yield conn
    finally: conn.close()

@app.middleware("http")
async def web_session_middleware(request: Request, call_next):
    path=request.url.path
    if path.startswith("/api/"):
        raw=request.headers.get("x-init-data", "")
        if raw.startswith("web:"):
            return JSONResponse(status_code=401,content={"detail":"Недопустимая авторизация"})
        cookie=request.cookies.get(WEB_COOKIE)
        if cookie and not raw:
            if request.method not in ("GET","HEAD","OPTIONS"):
                origin=request.headers.get("origin", "")
                # Railway terminates TLS at its proxy; require the actual public host.
                if not origin or urlsplit(origin).netloc.lower()!=request.headers.get("host", "").lower() or urlsplit(origin).scheme not in ("http","https"):
                    return JSONResponse(status_code=403,content={"detail":"Запрос с другого сайта запрещён"})
            request.scope["headers"]=[(k,v) for k,v in request.scope["headers"] if k.lower()!=b"x-init-data"]+[(b"x-init-data",("web:"+cookie).encode("ascii",errors="ignore"))]
        if path=="/api/web/login" and request.method=="POST":
            origin=request.headers.get("origin", "")
            if not origin or urlsplit(origin).netloc.lower()!=request.headers.get("host", "").lower():
                return JSONResponse(status_code=403,content={"detail":"Запрос с другого сайта запрещён"})
    response=await call_next(request)
    if path=="/api/me" and request.method=="GET" and request.cookies.get(WEB_COOKIE) and not request.headers.get("x-init-data") and request.headers.get("x-warehouse-pwa")=="1" and response.status_code==200:
        # On successful PWA re-entry, renew the browser cookie and preserve session until revoked.
        token=request.cookies.get(WEB_COOKIE)
        with transaction() as conn:
            entry=conn.execute("SELECT expires FROM web_sessions WHERE digest=? AND expires>?",(web_digest(token),int(time.time()))).fetchone()
            if entry:
                if entry["expires"]<4102444800:
                    conn.execute("UPDATE web_sessions SET expires=4102444800 WHERE digest=?",(web_digest(token),))
                response.set_cookie(WEB_COOKIE,token,max_age=34560000,httponly=True,secure=True,samesite="strict",path="/")
    if path.startswith("/api/"): response.headers["Cache-Control"]="no-store"
    return response

def authorize_telegram_app_user(conn, user_id):
    deny_blocked(conn, user_id, MAIN_ADMIN_ID)
    user = conn.execute("SELECT is_registered FROM users WHERE tg_id=?", (user_id,)).fetchone()
    if not user or not user["is_registered"]:
        raise HTTPException(403, "Сначала откройте Склад в Telegram и завершите регистрацию.")


class WebLogin(BaseModel):
    code: str
    pwa: bool = False

def issue_web_login_code(conn, user_id, rate_limit=False):
    code = secrets.token_hex(6).upper()
    now = int(time.time())
    if rate_limit and conn.execute("SELECT 1 FROM web_codes WHERE user_id=? AND expires>?", (user_id, now + 290)).fetchone():
        raise HTTPException(429, "Новый код можно запросить через несколько секунд")
    conn.execute("DELETE FROM web_codes WHERE expires<=? OR user_id=?", (now, user_id))
    conn.execute("INSERT INTO web_codes VALUES(?,?,?)", (web_digest(code), user_id, now + 300))
    return code


@app.post("/api/web/code")
def web_code(x_init_data: Optional[str] = Header(None)):
    if not x_init_data or x_init_data.startswith("web:"):
        raise HTTPException(403, "Код можно получить только внутри Telegram")
    user = get_user(x_init_data)
    if not user["is_registered"]:
        raise HTTPException(403, "Сначала завершите регистрацию")
    with transaction() as conn:
        code = issue_web_login_code(conn, user["tg_id"])
    return {"code": code, "expires_in": 300}

@app.post("/api/web/login")
def web_login(req: WebLogin):
    code=re.sub(r"[ -]","",req.code).upper()
    if not re.fullmatch(r"[A-F0-9]{12}",code): raise HTTPException(400,"Введите код из Telegram")
    token=secrets.token_urlsafe(32)
    session_ttl=34560000 if req.pwa else 43200
    session_expires=4102444800 if req.pwa else int(time.time())+session_ttl
    with transaction() as conn:
        row=conn.execute("SELECT c.user_id FROM web_codes c JOIN users u ON u.tg_id=c.user_id WHERE digest=? AND expires>?",(web_digest(code),int(time.time()))).fetchone()
        if not row: raise HTTPException(401,"Код неверный или истёк")
        deny_blocked(conn, row[0], MAIN_ADMIN_ID)
        conn.execute("DELETE FROM web_codes WHERE digest=?",(web_digest(code),))
        conn.execute("DELETE FROM web_sessions WHERE expires<=?",(int(time.time()),))
        conn.execute("INSERT INTO web_sessions VALUES(?,?,?)",(web_digest(token),row[0],session_expires))
    response=JSONResponse({"status":"ok"})
    response.set_cookie(WEB_COOKIE,token,max_age=session_ttl,httponly=True,secure=True,samesite="strict",path="/")
    return response

@app.post("/api/web/logout")
def web_logout(request: Request):
    token=request.cookies.get(WEB_COOKIE)
    if token:
        with transaction() as conn: conn.execute("DELETE FROM web_sessions WHERE digest=?",(web_digest(token),))
    response=JSONResponse({"status":"ok"})
    response.delete_cookie(WEB_COOKIE,path="/",secure=True,httponly=True,samesite="strict")
    return response

class BookingCancel(BaseModel):
    pass

@app.delete('/api/bookings/id/{booking_id}')
def cancel_booking(booking_id:int,x_init_data:Optional[str]=Header(None)):
    user=get_user(x_init_data)
    with transaction() as conn:
        row=conn.execute('SELECT * FROM bookings WHERE id=?',(booking_id,)).fetchone()
        if not row: raise HTTPException(404,'Бронь не найдена')
        if row['user_id']!=user['tg_id'] and user['role']!='admin': raise HTTPException(403,'Нет доступа')
        conn.execute('DELETE FROM bookings WHERE id=?',(booking_id,))
    return {'status':'ok'}

@app.get('/api/booking_calendar')
def booking_calendar(x_init_data:Optional[str]=Header(None)):
    get_user(x_init_data)
    with transaction() as conn:
        return [dict(r) for r in conn.execute("SELECT b.*,i.name,u.full_name FROM bookings b JOIN items i ON i.code=b.item_code LEFT JOIN users u ON u.tg_id=b.user_id WHERE i.is_archived=0 AND date_to>=date('now') ORDER BY date_from,name")]

def labels_pdf(rows, dpi, width_mm, height_mm, copies=1):
    if dpi not in (203, 300):
        raise HTTPException(400, "Выберите 203 или 300 dpi")
    label_dimensions(width_mm, height_mm)
    pages = len(rows) * copies
    if pages > 500:
        raise HTTPException(400, "Выберите до 500 этикеток с учётом копий")
    pixels = round(width_mm / 25.4 * dpi) * round(height_mm / 25.4 * dpi)
    if pages * pixels > 100_000_000:
        raise HTTPException(400, "Слишком большой PDF, уменьшите число этикеток, размер или dpi")
    images = [label_image(row["code"], row["name"], dpi, width_mm, height_mm) for row in rows]
    ordered = [image for image in images for _ in range(copies)]
    buf = io.BytesIO()
    ordered[0].save(buf, format="PDF", resolution=dpi, save_all=True, append_images=ordered[1:])
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Cache-Control": "no-store"})


@app.get('/api/export_labels')
def export_labels(dpi: int = 203, width_mm: int = 50, height_mm: int = 80, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data)
    with contextmanager_session() as conn:
        rows = conn.execute("SELECT code,name FROM items WHERE is_archived=0 ORDER BY name LIMIT 501").fetchall()
    if not rows:
        raise HTTPException(400, "Склад пуст")
    return labels_pdf(rows, dpi, width_mm, height_mm)


class LabelSelection(BaseModel):
    codes: List[str] = Field(min_length=1, max_length=500)
    copies: int = Field(default=1, ge=1, le=20)
    dpi: int = 203
    width_mm: int = 50
    height_mm: int = 80

@app.post('/api/export_labels')
def export_selected_labels(req: LabelSelection, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data)
    codes = list(dict.fromkeys(req.codes))
    if any(not 1 <= len(code) <= 64 for code in codes):
        raise HTTPException(400, "Проверьте коды товаров")
    placeholders = ",".join("?" for _ in codes)
    with contextmanager_session() as conn:
        rows = {
            row["code"]: row for row in conn.execute(
                f"SELECT code,name FROM items WHERE is_archived=0 AND code IN ({placeholders})", codes
            )
        }
    if len(rows) != len(codes):
        raise HTTPException(404, "Один из выбранных товаров недоступен")
    return labels_pdf([rows[code] for code in codes], req.dpi, req.width_mm, req.height_mm, req.copies)

@app.put('/api/items/{code}/photo')
async def update_photo(code:str,photo:UploadFile=File(...),x_init_data:Optional[str]=Header(None)):
    actor=check_admin(x_init_data)
    raw=await photo.read(5*1024*1024+1)
    if len(raw)>5*1024*1024: raise HTTPException(413,'Фото больше 5 МБ')
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.width*im.height>24000000: raise ValueError()
            im.thumbnail((1600,1600)); buf=io.BytesIO(); im.convert('RGB').save(buf,format='JPEG',quality=85)
    except Exception: raise HTTPException(400,'Некорректное изображение')
    with transaction() as conn:
        active_item(conn,code); conn.execute('UPDATE items SET photo=? WHERE code=?',(base64.b64encode(buf.getvalue()).decode(),code)); audit(conn,actor,'Фото товара',code)
    return {'status':'ok'}


@app.put('/api/repairs/{repair_id}/photo')
async def repair_photo_upload(repair_id:int,photo:UploadFile=File(...),x_init_data:Optional[str]=Header(None)):
    actor=get_user(x_init_data); raw=await photo.read(5*1024*1024+1)
    if len(raw)>5*1024*1024: raise HTTPException(413,'Фото больше 5 МБ')
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.width*im.height>24000000: raise ValueError()
            im.thumbnail((1600,1600)); buf=io.BytesIO(); im.convert('RGB').save(buf,format='JPEG',quality=85)
    except Exception: raise HTTPException(400,'Некорректное изображение')
    with transaction() as conn:
        row=conn.execute('SELECT * FROM repair_records WHERE id=?',(repair_id,)).fetchone()
        if not row: raise HTTPException(404,'Ремонт не найден')
        if actor['role']!='admin' and row['user_id']!=actor['tg_id']: raise HTTPException(403,'Нет доступа')
        conn.execute('INSERT INTO repair_photos(repair_id,photo) VALUES(?,?) ON CONFLICT(repair_id) DO UPDATE SET photo=excluded.photo',(repair_id,base64.b64encode(buf.getvalue()).decode()))
    return {'status':'ok'}

@app.get('/api/repairs/{repair_id}/photo')
def repair_photo_download(repair_id:int,x_init_data:Optional[str]=Header(None)):
    get_user(x_init_data)
    with contextmanager_session() as conn: row=conn.execute('SELECT photo FROM repair_photos WHERE repair_id=?',(repair_id,)).fetchone()
    if not row: raise HTTPException(404,'Фото отсутствует')
    return StreamingResponse(io.BytesIO(base64.b64decode(row[0])),media_type='image/jpeg')

register_v18(app, get_user, check_admin, transaction, active_item, audit, web_digest, WEB_COOKIE, _checkout_one, get_history)
register_owner_backup(app, DB_PATH, BOT_TOKEN, get_user)
register_snapshot_export(app, DB_PATH)
register_telegram_app_bot(
    app, BOT_TOKEN, "https://warehouse-app-production-3e9d62c2.up.railway.app", transaction,
    authorize_telegram_app_user, issue_web_login_code,
    owner_chat_id=MAIN_ADMIN_ID,
    auto_configure=os.environ.get("RAILWAY_SERVICE_ID") == "07cb1e8f-fbf7-4ecf-955b-243625619fad",
)
register_return_reminders(
    app, get_user, transaction, lambda _conn: None, BOT_TOKEN,
    os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip(),
)
register_release(app, get_user, contextmanager_session)
register_183(app, get_user, check_admin, transaction, active_item, valid_location, _move_one, audit, notify_admin_action)
register_184(app, get_user, real_user, contextmanager_session, transaction, web_digest, list_items)
register_185(app, check_owner, contextmanager_session, transaction, audit, MAIN_ADMIN_ID)
with transaction() as conn:
    migration = 'legacy-guest-contacts-2026-11-20'
    if not conn.execute("SELECT 1 FROM warehouse_release_meta WHERE version=?", (migration,)).fetchone():
        created_guests, transferred = backfill_legacy_guest_contacts(conn)
        conn.execute("INSERT INTO warehouse_release_meta(version) VALUES (?)", (migration,))
        print("Legacy guest contacts created:", created_guests, "checkouts reassigned:", transferred, flush=True)
    conn.execute("INSERT OR IGNORE INTO warehouse_release_meta(version) VALUES ('18.5.4'), (?)", (APP_VERSION,))



# PWA is a separate entrance to the SAME Main inventory and user accounts.
# Render an opt-in HTML variant: leave the regular Telegram index.html untouched.
_MAIN_PWA_DIR = Path(__file__).resolve().parent

@app.get("/pwa", include_in_schema=False)
def main_pwa_redirect():
    return RedirectResponse("/pwa/", status_code=307)

_WAREHOUSE_VERSION_FILES=tuple(sorted(p for p in _MAIN_PWA_DIR.iterdir() if p.suffix in (".py",".html",".css",".js")))
_WAREHOUSE_VERSION=hashlib.sha256(b"".join(p.name.encode("utf-8")+b"\\0"+hashlib.sha256(p.read_bytes()).digest() for p in _WAREHOUSE_VERSION_FILES)).hexdigest()[:20]

@app.get("/app/version", include_in_schema=False)
def warehouse_version():
    return JSONResponse({"version":_WAREHOUSE_VERSION},headers={"Cache-Control":"no-store"})

@app.get("/pull-refresh.js", include_in_schema=False)
def pull_refresh_script():
    return FileResponse(_MAIN_PWA_DIR / "pull_refresh.js",media_type="text/javascript",headers={"Cache-Control":"no-cache,no-store,must-revalidate"})

@app.get("/pwa/", include_in_schema=False)
def main_pwa_home():
    html=(_MAIN_PWA_DIR / "index.html").read_text(encoding="utf-8")
    title_marker='<title>Склад</title>'
    login_marker="JSON.stringify({code:$('web-code').value})"
    if html.count(title_marker)!=1 or html.count(login_marker)!=1 or html.count('</head>')!=1 or html.count('</body>')!=1:
        raise HTTPException(500,"Не удалось подготовить PWA")
    meta='''<link rel="manifest" href="/pwa/manifest.webmanifest">
    <link rel="apple-touch-icon" sizes="180x180" href="/pwa/icon-180.png">
    <link rel="icon" type="image/png" sizes="192x192" href="/pwa/icon-192.png">
    <meta name="theme-color" content="#0e1534">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="Склад">'''
    styles='''<style>
    @media(display-mode:standalone){body.pwa-mode{padding-top:env(safe-area-inset-top)}}
    body.pwa-mode .sticky-header{top:env(safe-area-inset-top)}
    .pwa-install-info{margin:16px 0 6px;padding:14px;border-radius:15px;background:var(--skeleton-bg);font-size:13px;line-height:1.55;text-align:left}
    .pwa-install-info p{margin:5px 0}
    .pwa-install-info button{margin:10px 0 0;min-height:40px}
    </style>'''
    html=html.replace(title_marker,title_marker+'\n    '+meta,1)
    html=html.replace(login_marker,"JSON.stringify({code:$('web-code').value,pwa:true})",1)
    html=html.replace('</head>',styles+'<meta name="warehouse-app-version" content="'+_WAREHOUSE_VERSION+'"></head>',1)
    html=html.replace('</body>','<script src="/pwa/client.js?v=2"></script>\n</body>',1)
    return HTMLResponse(html,headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})

@app.get("/pwa/manifest.webmanifest", include_in_schema=False)
def main_pwa_manifest():
    return FileResponse(_MAIN_PWA_DIR / "pwa_manifest.webmanifest",media_type="application/manifest+json",headers={"Cache-Control":"public,max-age=3600","X-Content-Type-Options":"nosniff"})

@app.get("/pwa/sw.js", include_in_schema=False)
def main_pwa_sw():
    return FileResponse(_MAIN_PWA_DIR / "pwa_sw.js",media_type="text/javascript",headers={"Cache-Control":"no-cache,no-store,must-revalidate","Service-Worker-Allowed":"/pwa/","X-Content-Type-Options":"nosniff"})

@app.get("/pwa/client.js", include_in_schema=False)
def main_pwa_client():
    return FileResponse(_MAIN_PWA_DIR / "pwa_client.js",media_type="text/javascript",headers={"Cache-Control":"no-cache","X-Content-Type-Options":"nosniff"})

@app.get("/pwa/jsqr.js", include_in_schema=False)
def main_pwa_jsqr():
    return FileResponse(_MAIN_PWA_DIR / "pwa_jsqr.js",media_type="text/javascript",headers={"Cache-Control":"public,max-age=86400","X-Content-Type-Options":"nosniff"})

@app.get("/pwa/offline.html", include_in_schema=False)
def main_pwa_offline():
    return FileResponse(_MAIN_PWA_DIR / "pwa_offline.html",media_type="text/html",headers={"Cache-Control":"public,max-age=3600","X-Content-Type-Options":"nosniff"})

@app.get("/pwa/icon-{size}.png", include_in_schema=False)
def main_pwa_icon(size:int):
    if size not in (180,192,512): raise HTTPException(404,"Иконка не найдена")
    return Response(content=render_icon_png(size),media_type="image/png",headers={"Cache-Control":"public,max-age=86400","X-Content-Type-Options":"nosniff"})

@app.get("/")
@app.get("/index.html")
def serve_main():
    html=(_MAIN_PWA_DIR / "index.html").read_text(encoding="utf-8")
    html=html.replace("</head>",'<meta name="warehouse-app-version" content="'+_WAREHOUSE_VERSION+'"></head>',1)
    return HTMLResponse(html,headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})
