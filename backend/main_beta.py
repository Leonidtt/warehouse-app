# ==========================================
# БЛОК 1: ИМПОРТЫ И НАСТРОЙКИ
# ==========================================
import sqlite3
import json
import hashlib
import hmac
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List
import qrcode
import io
import csv
import httpx
from PIL import Image, ImageDraw, ImageFont
import base64
from datetime import datetime, timedelta
import os
import traceback
import pandas as pd
import asyncio
import gspread
from google.oauth2.service_account import Credentials
import urllib3
urllib3.disable_warnings()

BOT_TOKEN = "9259053694:AAFCDpRbUmoWQpNxbG7jz1-4CRBsMcEaFyg"
SPREADSHEET_ID = "1T8yAWtkmSo-qL9OciGsAVO3UpjqYNt9jjhirjkrqMr0"
DB_PATH = "/data/warehouse_beta.db"

app = FastAPI()

# ==========================================
# БЛОК 2: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И УВЕДОМЛЕНИЯ
# ==========================================
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

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def healthcheck(): return {"status": "ok"}

def get_conn():
    if not os.path.exists("/data"):
        try: os.makedirs("/data")
        except: pass
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

# ==========================================
# БЛОК 3: ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
# ==========================================
def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS locations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, type TEXT NOT NULL DEFAULT 'storage')""")
    c.execute("""CREATE TABLE IF NOT EXISTS users (tg_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, full_name TEXT DEFAULT '', role TEXT DEFAULT 'employee')""")
    c.execute("""CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'equipment', min_stock INTEGER DEFAULT 0, photo TEXT DEFAULT '', needs_repair INTEGER DEFAULT 0, price REAL DEFAULT 0, kit_body TEXT DEFAULT '', kit_lens TEXT DEFAULT '', kit_flash TEXT DEFAULT '', budget_tag TEXT DEFAULT '', serial_number TEXT DEFAULT '', buyout_status TEXT DEFAULT '', category TEXT DEFAULT '', is_archived INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT NOT NULL, user_id INTEGER NOT NULL, date_from TEXT NOT NULL, date_to TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT NOT NULL, user_id INTEGER NOT NULL, text TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS stock (item_code TEXT NOT NULL, location_id INTEGER NOT NULL, quantity INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (item_code, location_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS checkouts (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT NOT NULL, user_id INTEGER NOT NULL, location_id INTEGER NOT NULL, taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, returned_at TIMESTAMP, returned_by INTEGER, taken_for TEXT DEFAULT '')""")
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
        "ALTER TABLE items ADD COLUMN budget_tag TEXT DEFAULT ''",
        "ALTER TABLE items ADD COLUMN serial_number TEXT DEFAULT ''",
        "ALTER TABLE items ADD COLUMN buyout_status TEXT DEFAULT ''",
        "ALTER TABLE items ADD COLUMN category TEXT DEFAULT ''",
        "ALTER TABLE items ADD COLUMN is_archived INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'employee'",
        "ALTER TABLE users ADD COLUMN is_registered INTEGER DEFAULT 0",
        "ALTER TABLE checkouts ADD COLUMN returned_by INTEGER",
        "ALTER TABLE checkouts ADD COLUMN taken_for TEXT DEFAULT ''"
    ]
    for q in migrations:
        try: c.execute(q)
        except sqlite3.OperationalError: pass

    c.execute("SELECT COUNT(*) FROM locations")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO locations (name, type) VALUES ('Мастерская', 'workshop')")
        c.execute("INSERT INTO locations (name, type) VALUES ('Склад', 'storage')")
        c.execute("INSERT INTO locations (name, type) VALUES ('Офис', 'office')")

    c.execute("UPDATE users SET is_registered = 1 WHERE full_name != '' AND is_registered = 0")
    conn.commit(); conn.close()

init_db()

# ==========================================
# БЛОК 4: АВТОРИЗАЦИЯ И МОДЕЛИ ДАННЫХ
# ==========================================
def verify_init_data(init_data: str) -> dict:
    try: pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception: raise HTTPException(status_code=401, detail="Некорректный initData")
    received_hash = pairs.pop("hash", None)
    if not received_hash: raise HTTPException(status_code=401, detail="Нет подписи")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if calculated != received_hash: raise HTTPException(status_code=401, detail="Неверная подпись")
    user_json = pairs.get("user")
    if not user_json: raise HTTPException(status_code=401, detail="Нет пользователя")
    return json.loads(user_json)

def get_user(x_init_data: Optional[str]):
    if not x_init_data: raise HTTPException(status_code=401, detail="Нет авторизации")
    user = verify_init_data(x_init_data)
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE tg_id = ?", (user["id"],)).fetchone()
    if not row:
        full_name = f"{user.get('last_name', '')} {user.get('first_name', '')}".strip()
        conn.execute("INSERT INTO users (tg_id, first_name, username, full_name, role, is_registered) VALUES (?, ?, ?, ?, 'employee', 0)", (user["id"], user.get("first_name", ""), user.get("username", ""), full_name))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE tg_id = ?", (user["id"],)).fetchone()
    conn.close()
    user_dict = dict(row)
    user_dict["is_registered"] = row["is_registered"] if "is_registered" in row.keys() else 1
    return user_dict

def check_admin(x_init_data: Optional[str]):
    user = get_user(x_init_data)
    if user["role"] != "admin": raise HTTPException(status_code=403, detail="Доступ только для администратора")
    return user

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
    code: str; taken_for: str = ""
class RegisterRequest(BaseModel):
    full_name: str
class LocationCreate(BaseModel):
    name: str
class LocationUpdate(BaseModel):
    id: int; name: str
class ItemUpdate(BaseModel):
    name: str; kind: str; min_stock: int; price: float; kit_body: str; kit_lens: str; kit_flash: str; budget_tag: str; serial_number: str; buyout_status: str
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
class LogErrorRequest(BaseModel):
    error: str

# ==========================================
# БЛОК 5: ЭНДПОИНТЫ (API)
# ==========================================
@app.get("/api/me")
def get_me(x_init_data: Optional[str] = Header(None)): return get_user(x_init_data)

@app.post("/api/log_error")
async def log_error(req: LogErrorRequest, x_init_data: Optional[str] = Header(None)):
    try:
        user_name = "?"
        if x_init_data:
            try: user_name = get_user(x_init_data).get("full_name", "?")
            except: pass
        await notify_admin_about_error(req.error[:500], user_name)
    except: pass
    return {"status": "ok"}

@app.get("/api/sync_google")
def sync_google(sheet_name: str = "кц", x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data)
    creds_env = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not creds_env: return {"status": "error", "message": "Не настроены GOOGLE_CREDENTIALS_JSON на сервере."}
    try:
        decoded_bytes = base64.b64decode(creds_env)
        creds_json = decoded_bytes.decode('utf-8')
        creds_dict = json.loads(creds_json)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        
        sheets = spreadsheet.worksheets()
        target_sheet = None
        
        # 1. Ищем точное совпадение
        for s in sheets:
            if s.title.strip().lower() == sheet_name.strip().lower():
                target_sheet = s
                break
                
        # 2. Если точного нет, ищем по ключевому слову (тх или кц)
        if not target_sheet:
            keyword = "тх" if "тх" in sheet_name.lower() else "кц"
            for s in sheets:
                if keyword in s.title.strip().lower():
                    target_sheet = s
                    break
                    
        # 3. Если всё равно нет, и это теплоходы, берем 4-й лист (индекс 3)
        if not target_sheet and "тх" in sheet_name.lower() and len(sheets) >= 4:
            target_sheet = sheets[3]
            
        if not target_sheet:
            titles = [s.title for s in sheets]
            return {"status": "error", "message": f"Лист не найден. Доступные листы: {titles}"}
        
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
        return {"status": "error", "message": f"Ошибка на сервере при чтении таблицы: {str(e)}"}

@app.get("/api/my_bookings")
def my_bookings(x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data); conn = get_conn()
    rows = conn.execute("SELECT b.*, i.name FROM bookings b JOIN items i ON i.code = b.item_code WHERE b.user_id = ? AND b.date_to >= date('now') ORDER BY b.date_from", (user["tg_id"],)).fetchall()
    conn.close(); return [dict(r) for r in rows]

@app.get("/api/my_items")
def my_items(x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data); conn = get_conn()
    rows = conn.execute("SELECT c.item_code, i.name, c.taken_for FROM checkouts c JOIN items i ON i.code = c.item_code WHERE c.user_id = ? AND c.returned_at IS NULL ORDER BY c.taken_at DESC", (user["tg_id"],)).fetchall()
    conn.close(); return [dict(r) for r in rows]

@app.get("/api/daily_report")
def get_daily_report(x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data); conn = get_conn(); today = datetime.now().strftime("%Y-%m-%d")
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
    get_user(x_init_data); conn = get_conn(); rows = []
    co = conn.execute("SELECT c.id, c.item_code, i.name, c.user_id, u.full_name, c.taken_at AS date, c.returned_at, c.taken_for FROM checkouts c JOIN items i ON i.code = c.item_code LEFT JOIN users u ON u.tg_id = c.user_id ORDER BY c.taken_at DESC LIMIT 500").fetchall()
    for r in co:
        rows.append({"date": r["date"], "type": "checkout", "item_code": r["item_code"], "name": r["name"], "quantity": 1, "user_name": r["full_name"] or "—"})
        if r["returned_at"]: rows.append({"date": r["returned_at"], "type": "return", "item_code": r["item_code"], "name": r["name"], "quantity": 1, "user_name": r["full_name"] or "—"})
    mv = conn.execute("SELECT m.item_code, i.name, m.quantity, m.created_at AS date, u.full_name FROM movements m JOIN items i ON i.code = m.item_code LEFT JOIN users u ON u.tg_id = m.user_id ORDER BY m.created_at DESC LIMIT 500").fetchall()
    for r in mv: rows.append({"date": r["date"], "type": "move", "item_code": r["item_code"], "name": r["name"], "quantity": r["quantity"], "user_name": r["full_name"] or "—"})
    wo = conn.execute("SELECT w.item_code, i.name, w.quantity, w.created_at AS date, u.full_name FROM writeoffs w JOIN items i ON i.code = w.item_code LEFT JOIN users u ON u.tg_id = w.user_id ORDER BY w.created_at DESC LIMIT 500").fetchall()
    for r in wo: rows.append({"date": r["date"], "type": "writeoff", "item_code": r["item_code"], "name": r["name"], "quantity": r["quantity"], "user_name": r["full_name"] or "—"})
    conn.close(); rows.sort(key=lambda x: x["date"], reverse=True); return rows

@app.get("/api/export_history")
def export_history(x_init_data: Optional[str] = Header(None), init_data: Optional[str] = Query(None)):
    auth = x_init_data or init_data
    get_user(auth); rows = get_history(auth); buf = io.StringIO(); writer = csv.writer(buf)
    writer.writerow(["Дата", "Тип", "Код", "Название", "Кол-во", "Пользователь"])
    for r in rows: writer.writerow([r["date"], r["type"], r["item_code"], r["name"], r["quantity"], r["user_name"]])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=history.csv"})

@app.get("/api/export_stock")
def export_stock(x_init_data: Optional[str] = Header(None), init_data: Optional[str] = Query(None)):
    auth = x_init_data or init_data
    check_admin(auth); conn = get_conn()
    rows = conn.execute("SELECT i.code, i.name, l.name as location, s.quantity FROM stock s JOIN items i ON i.code = s.item_code JOIN locations l ON l.id = s.location_id WHERE s.quantity > 0 AND i.is_archived = 0 ORDER BY l.name, i.name").fetchall()
    conn.close(); buf = io.StringIO(); writer = csv.writer(buf, delimiter=';')
    writer.writerow(["Код", "Название", "Локация", "Количество"])
    for r in rows: writer.writerow([r["code"], r["name"], r["location"], r["quantity"]])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=stock.csv"})

@app.get("/api/export_qr_sheet")
def export_qr_sheet(x_init_data: Optional[str] = Header(None), init_data: Optional[str] = Query(None)):
    auth = x_init_data or init_data
    check_admin(auth); conn = get_conn()
    items = conn.execute("SELECT code, name FROM items WHERE is_archived = 0 ORDER BY name").fetchall()
    conn.close()
    cols = 4; rows_count = (len(items) + cols - 1) // cols
    qr_size = 180; padding = 20; text_height = 30
    cell_w = qr_size + padding * 2; cell_h = qr_size + text_height + padding * 2
    img_w = cols * cell_w; img_h = rows_count * cell_h
    if img_h == 0: img_h = 100
    img = Image.new("RGB", (img_w, img_h), "white"); draw = ImageDraw.Draw(img)
    try: font = ImageFont.truetype("DejaVuSans.ttf", 14)
    except IOError: font = ImageFont.load_default()
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

@app.post("/api/register")
def register(req: RegisterRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data); conn = get_conn(); conn.execute("UPDATE users SET full_name = ?, is_registered = 1 WHERE tg_id = ?", (req.full_name.strip(), user["tg_id"])); conn.commit(); conn.close(); return {"status": "ok"}

@app.get("/api/users")
def list_users(x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data); conn = get_conn()
    users = conn.execute("SELECT tg_id, full_name, role FROM users ORDER BY role DESC").fetchall()
    result = []
    for u in users:
        held = conn.execute("SELECT item_code FROM checkouts WHERE user_id = ? AND returned_at IS NULL", (u["tg_id"],)).fetchall()
        result.append({"tg_id": u["tg_id"], "full_name": u["full_name"], "role": u["role"], "held_items": [h["item_code"] for h in held]})
    conn.close(); return result

@app.post("/api/users/{tg_id}/update")
def update_user(tg_id: int, req: UserUpdate, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data); conn = get_conn(); conn.execute("UPDATE users SET full_name = ?, role = ? WHERE tg_id = ?", (req.full_name, req.role, tg_id)); conn.commit(); conn.close(); return {"status": "ok"}

@app.get("/api/locations")
def list_locations(x_init_data: Optional[str] = Header(None)):
    conn = get_conn(); rows = conn.execute("SELECT id, name, type FROM locations ORDER BY id").fetchall(); conn.close(); return [dict(r) for r in rows]

@app.get("/api/locations_view")
def locations_view(x_init_data: Optional[str] = Header(None)):
    conn = get_conn(); locations = conn.execute("SELECT id, name FROM locations ORDER BY id").fetchall(); result = []
    for loc in locations:
        count = conn.execute("SELECT COALESCE(SUM(s.quantity), 0) AS c FROM stock s JOIN items i ON i.code = s.item_code WHERE s.location_id = ? AND s.quantity > 0 AND i.is_archived = 0", (loc["id"],)).fetchone()["c"]
        result.append({"id": loc["id"], "name": loc["name"], "count": count})
    conn.close(); return result

@app.get("/api/room_detail/{location_id}")
def room_detail(location_id: int, x_init_data: Optional[str] = Header(None)):
    is_admin = False
    try: is_admin = get_user(x_init_data)["role"] == "admin"
    except: pass
    conn = get_conn(); location = conn.execute("SELECT name FROM locations WHERE id = ?", (location_id,)).fetchone()
    if not location: conn.close(); raise HTTPException(404, "Комната не найдена")
    
    items = conn.execute("SELECT s.item_code, s.quantity FROM stock s JOIN items i ON i.code = s.item_code WHERE s.location_id = ? AND s.quantity > 0 AND i.is_archived = 0", (location_id,)).fetchall()
    checkouts = conn.execute("SELECT c.item_code, u.full_name FROM checkouts c LEFT JOIN users u ON u.tg_id = c.user_id WHERE c.location_id = ? AND c.returned_at IS NULL", (location_id,)).fetchall()
    
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
        data = {"code": c["item_code"], "name": detail.get("name", "—"), "category": detail.get("category", ""), "quantity": 0, "serial_number": detail.get("serial_number", ""), "needs_repair": detail.get("needs_repair", 0), "budget_tag": detail.get("budget_tag", ""), "buyout_status": detail.get("buyout_status", ""), "is_on_hand": True, "holder": c["full_name"]}
        if is_admin: data["price"] = detail.get("price", 0)
        result_items.append(data)
        
    return {"location_name": location["name"], "items": result_items}

@app.post("/api/locations")
def create_location(req: LocationCreate, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data); conn = get_conn()
    try: conn.execute("INSERT INTO locations (name) VALUES (?)", (req.name.strip(),)); conn.commit()
    except sqlite3.IntegrityError: conn.close(); raise HTTPException(400, "Такая комната уже есть")
    conn.close(); return {"status": "ok"}

@app.post("/api/locations/update")
def update_location(req: LocationUpdate, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data); conn = get_conn()
    try: conn.execute("UPDATE locations SET name = ? WHERE id = ?", (req.name.strip(), req.id)); conn.commit()
    except Exception as e: conn.close(); raise HTTPException(400, str(e))
    conn.close(); return {"status": "ok"}

@app.get("/api/stats")
def get_stats(x_init_data: Optional[str] = Header(None)):
    conn = get_conn()
    default_cats = ["Фотокомплекты", "Вспышки", "Ноутбуки", "Принтеры"]
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

@app.get("/api/next_code")
def get_next_code(x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data); conn = get_conn(); rows = conn.execute("SELECT code FROM items WHERE code LIKE 'ITEM-%'").fetchall()
    max_num = max([int(r["code"].split("-")[1]) for r in rows if r["code"].split("-")[1].isdigit()] + [0])
    conn.close(); return {"code": f"ITEM-{max_num + 1}"}

@app.get("/api/items")
def list_items(x_init_data: Optional[str] = Header(None)):
    is_admin = False
    try: is_admin = get_user(x_init_data)["role"] == "admin"
    except: pass
    conn = get_conn(); items = conn.execute("SELECT * FROM items WHERE is_archived = 0 ORDER BY name").fetchall(); result = []
    for it in items:
        stocks = conn.execute("SELECT s.location_id, l.name AS location_name, s.quantity FROM stock s JOIN locations l ON l.id = s.location_id WHERE s.item_code = ? AND s.quantity > 0", (it["code"],)).fetchall()
        holders = conn.execute("SELECT c.id, c.user_id, u.full_name, c.taken_at, c.taken_for FROM checkouts c LEFT JOIN users u ON u.tg_id = c.user_id WHERE c.item_code = ? AND c.returned_at IS NULL", (it["code"],)).fetchall()
        total = sum(s["quantity"] for s in stocks)
        item_data = {"code": it["code"], "name": it["name"], "kind": it["kind"], "min_stock": it["min_stock"], "needs_repair": it["needs_repair"], "kit_body": it["kit_body"], "kit_lens": it["kit_lens"], "kit_flash": it["kit_flash"], "budget_tag": it["budget_tag"], "serial_number": it["serial_number"], "buyout_status": it["buyout_status"], "category": it["category"], "total": total, "is_low": total <= it["min_stock"] and it["min_stock"] > 0 and it["kind"] == "consumable", "stocks": [dict(s) for s in stocks], "holders": [dict(h) for h in holders]}
        if is_admin: item_data["price"] = it["price"]
        result.append(item_data)
    conn.close(); return result

@app.get("/api/items/{code}")
def get_item(code: str, x_init_data: Optional[str] = Header(None)):
    is_admin = False
    try: is_admin = get_user(x_init_data)["role"] == "admin"
    except: pass
    conn = get_conn(); item = conn.execute("SELECT * FROM items WHERE code = ?", (code,)).fetchone()
    if not item: conn.close(); raise HTTPException(404, "Товар не найден")
    stocks = conn.execute("SELECT s.location_id, l.name AS location_name, s.quantity FROM stock s JOIN locations l ON l.id = s.location_id WHERE s.item_code = ? AND s.quantity > 0", (code,)).fetchall()
    holders = conn.execute("SELECT c.id, c.user_id, u.full_name, c.taken_at, c.taken_for FROM checkouts c LEFT JOIN users u ON u.tg_id = c.user_id WHERE c.item_code = ? AND c.returned_at IS NULL", (code,)).fetchall()
    conn.close()
    result = {"code": item["code"], "name": item["name"], "kind": item["kind"], "min_stock": item["min_stock"], "needs_repair": item["needs_repair"], "kit_body": item["kit_body"], "kit_lens": item["kit_lens"], "kit_flash": item["kit_flash"], "budget_tag": item["budget_tag"], "serial_number": item["serial_number"], "buyout_status": item["buyout_status"], "category": item["category"], "stocks": [dict(s) for s in stocks], "holders": [dict(h) for h in holders]}
    if is_admin: result["price"] = item["price"]
    return result

@app.post("/api/items/{code}/update")
def update_item(code: str, req: ItemUpdate, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data); conn = get_conn()
    conn.execute("UPDATE items SET name=?, kind=?, min_stock=?, price=?, kit_body=?, kit_lens=?, kit_flash=?, budget_tag=?, serial_number=?, buyout_status=? WHERE code=?", (req.name, req.kind, req.min_stock, req.price, req.kit_body, req.kit_lens, req.kit_flash, req.budget_tag, req.serial_number, req.buyout_status, code))
    conn.commit(); conn.close(); return {"status": "ok"}

@app.post("/api/items/{code}/repair")
async def toggle_repair(code: str, x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data); conn = get_conn(); item = conn.execute("SELECT needs_repair, name FROM items WHERE code = ?", (code,)).fetchone()
    if not item: conn.close(); raise HTTPException(404, "Товар не найден")
    new_status = 0 if item["needs_repair"] else 1
    conn.execute("UPDATE items SET needs_repair = ? WHERE code = ?", (new_status, code)); conn.commit(); conn.close()
    if new_status == 1:
        asyncio.create_task(notify_admin_action(f"🔧 Товар {item['name']} ({code}) отправлен в ремонт."))
    return {"status": "ok", "message": f"Товар {item['name']} {'отправлен в ремонт' if new_status else 'возвращен в строй'}"}

@app.post("/api/items/{code}/lost")
def mark_lost(code: str, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data); conn = get_conn()
    item = conn.execute("SELECT name FROM items WHERE code = ?", (code,)).fetchone()
    if not item: conn.close(); raise HTTPException(404, "Товар не найден")
    conn.execute("INSERT INTO lost_items (item_code, user_id) VALUES (?, ?)", (code, user["tg_id"]))
    conn.commit(); conn.close(); return {"status": "ok", "message": f"Отмечено: {item['name']} не найден"}

@app.delete("/api/items/{code}")
def archive_item(code: str, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data); conn = get_conn()
    conn.execute("UPDATE items SET is_archived = 1 WHERE code = ?", (code,))
    conn.execute("DELETE FROM stock WHERE item_code = ?", (code,))
    conn.commit(); conn.close(); return {"status": "ok"}

@app.post("/api/items")
async def create_item(code: str = Form(...), name: str = Form(...), kind: str = Form("equipment"), location_id: int = Form(...), quantity: int = Form(0), min_stock: int = Form(0), price: float = Form(0), kit_body: str = Form(""), kit_lens: str = Form(""), kit_flash: str = Form(""), budget_tag: str = Form(""), serial_number: str = Form(""), buyout_status: str = Form(""), x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data); conn = get_conn()
    try: conn.execute("INSERT INTO items (code, name, kind, min_stock, price, kit_body, kit_lens, kit_flash, budget_tag, serial_number, buyout_status) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (code, name, kind, min_stock, price, kit_body, kit_lens, kit_flash, budget_tag, serial_number, buyout_status))
    except sqlite3.IntegrityError: conn.close(); raise HTTPException(400, "Код уже существует")
    conn.execute("INSERT INTO stock (item_code, location_id, quantity) VALUES (?,?,?)", (code, location_id, quantity))
    conn.commit(); conn.close(); return {"status": "ok"}

@app.post("/api/checkout_batch")
async def checkout_batch(req: BatchCheckoutRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data); conn = get_conn()
    success = []
    errors = []
    for code in req.codes:
        item = conn.execute("SELECT kind, needs_repair, name FROM items WHERE code = ?", (code,)).fetchone()
        if not item: errors.append(f"{code}: не найден"); continue
        if item["needs_repair"]: errors.append(f"{item['name']}: в ремонте"); continue
        if item["kind"] != "equipment": errors.append(f"{item['name']}: расходник"); continue
        if conn.execute("SELECT id FROM checkouts WHERE item_code = ? AND returned_at IS NULL", (code,)).fetchone(): errors.append(f"{item['name']}: уже выдан"); continue
        
        stock = conn.execute("SELECT location_id FROM stock WHERE item_code = ? AND quantity > 0 ORDER BY location_id LIMIT 1", (code,)).fetchone()
        if not stock: errors.append(f"{item['name']}: нет в наличии"); continue
        
        conn.execute("INSERT INTO checkouts (item_code, user_id, location_id, taken_for) VALUES (?,?,?,?)", (code, user["tg_id"], stock["location_id"], req.taken_for))
        conn.execute("UPDATE stock SET quantity = quantity - 1 WHERE item_code = ? AND location_id = ?", (code, stock["location_id"]))
        conn.execute("DELETE FROM stock WHERE item_code = ? AND quantity = 0", (code,))
        success.append(item["name"])
    
    conn.commit(); conn.close()
    if success:
        asyncio.create_task(notify_admin_action(f"📤 {user['full_name']} взял ({len(success)} шт): {', '.join(success)}."))
    return {"status": "ok", "success_count": len(success), "errors": errors}

@app.post("/api/checkout")
async def checkout(req: CheckoutRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data); conn = get_conn(); item = conn.execute("SELECT kind, needs_repair, name FROM items WHERE code = ?", (req.code,)).fetchone()
    if not item: conn.close(); raise HTTPException(404, "Товар не найден")
    if item["needs_repair"]: conn.close(); raise HTTPException(400, "Товар в ремонте")
    if item["kind"] != "equipment": conn.close(); raise HTTPException(400, "Это расходник")
    if conn.execute("SELECT id FROM checkouts WHERE item_code = ? AND returned_at IS NULL", (req.code,)).fetchone(): conn.close(); raise HTTPException(400, "Уже выдано")
    stock = conn.execute("SELECT location_id FROM stock WHERE item_code = ? AND quantity > 0 ORDER BY location_id LIMIT 1", (req.code,)).fetchone()
    if not stock: conn.close(); raise HTTPException(400, "Нет в наличии")
    conn.execute("INSERT INTO checkouts (item_code, user_id, location_id, taken_for) VALUES (?,?,?,?)", (req.code, user["tg_id"], stock["location_id"], req.taken_for))
    conn.execute("UPDATE stock SET quantity = quantity - 1 WHERE item_code = ? AND location_id = ?", (req.code, stock["location_id"]))
    conn.execute("DELETE FROM stock WHERE item_code = ? AND quantity = 0", (req.code,))
    conn.commit(); conn.close()
    asyncio.create_task(notify_admin_action(f"📤 {user['full_name']} взял {item['name']} ({req.code})."))
    return {"status": "ok"}

@app.post("/api/return")
async def return_item(code: str, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data); conn = get_conn()
    co = conn.execute("SELECT id, location_id FROM checkouts WHERE item_code = ? AND returned_at IS NULL", (code,)).fetchone()
    if not co: conn.close(); raise HTTPException(400, "Не выдано")
    
    conn.execute("UPDATE checkouts SET returned_at = CURRENT_TIMESTAMP, returned_by = ? WHERE id = ?", (user["tg_id"], co["id"]))
    if conn.execute("SELECT quantity FROM stock WHERE item_code = ? AND location_id = ?", (code, co["location_id"])).fetchone(): 
        conn.execute("UPDATE stock SET quantity = quantity + 1 WHERE item_code = ? AND location_id = ?", (code, co["location_id"]))
    else: 
        conn.execute("INSERT INTO stock (item_code, location_id, quantity) VALUES (?,?,1)", (code, co["location_id"]))
    conn.commit()
    item = conn.execute("SELECT name FROM items WHERE code = ?", (code,)).fetchone()
    conn.close()
    asyncio.create_task(notify_admin_action(f"📥 {user['full_name']} вернул {item['name']} ({code})."))
    return {"status": "ok"}

@app.post("/api/move")
def move_item(req: MoveRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    if req.quantity <= 0: raise HTTPException(400, "Количество должно быть больше 0")
    if req.from_location == req.to_location: raise HTTPException(400, "Выберите другую комнату")
    
    conn = get_conn(); row = conn.execute("SELECT quantity FROM stock WHERE item_code = ? AND location_id = ?", (req.code, req.from_location)).fetchone()
    if not row or row["quantity"] < req.quantity: conn.close(); raise HTTPException(400, "Недостаточно товара")
    
    conn.execute("UPDATE stock SET quantity = quantity - ? WHERE item_code = ? AND location_id = ?", (req.quantity, req.code, req.from_location))
    conn.execute("DELETE FROM stock WHERE item_code = ? AND location_id = ? AND quantity = 0", (req.code, req.from_location))
    if conn.execute("SELECT quantity FROM stock WHERE item_code = ? AND location_id = ?", (req.code, req.to_location)).fetchone(): 
        conn.execute("UPDATE stock SET quantity = quantity + ? WHERE item_code = ? AND location_id = ?", (req.quantity, req.code, req.to_location))
    else: 
        conn.execute("INSERT INTO stock (item_code, location_id, quantity) VALUES (?,?,?)", (req.code, req.to_location, req.quantity))
    conn.execute("INSERT INTO movements (item_code, quantity, from_location, to_location, user_id) VALUES (?,?,?,?,?)", (req.code, req.quantity, req.from_location, req.to_location, user["tg_id"]))
    conn.commit(); conn.close(); return {"status": "ok"}

@app.post("/api/move_batch")
def move_batch(req: BatchMoveRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    if req.from_location == req.to_location: raise HTTPException(400, "Локации должны отличаться")
    conn = get_conn()
    for code in req.codes:
        row = conn.execute("SELECT quantity FROM stock WHERE item_code = ? AND location_id = ?", (code, req.from_location)).fetchone()
        if row and row["quantity"] > 0:
            conn.execute("UPDATE stock SET quantity = quantity - 1 WHERE item_code = ? AND location_id = ?", (code, req.from_location))
            conn.execute("DELETE FROM stock WHERE item_code = ? AND location_id = ? AND quantity = 0", (code, req.from_location))
            if conn.execute("SELECT quantity FROM stock WHERE item_code = ? AND location_id = ?", (code, req.to_location)).fetchone(): 
                conn.execute("UPDATE stock SET quantity = quantity + 1 WHERE item_code = ? AND location_id = ?", (code, req.to_location))
            else: 
                conn.execute("INSERT INTO stock (item_code, location_id, quantity) VALUES (?,?,1)", (code, req.to_location))
            conn.execute("INSERT INTO movements (item_code, quantity, from_location, to_location, user_id) VALUES (?,1,?,?,?)", (code, req.from_location, req.to_location, user["tg_id"]))
    conn.commit(); conn.close(); return {"status": "ok"}

@app.post("/api/writeoff")
def writeoff(req: WriteoffRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data); conn = get_conn(); row = conn.execute("SELECT quantity FROM stock WHERE item_code = ? AND location_id = ?", (req.code, req.location_id)).fetchone()
    if not row or row["quantity"] < req.quantity: conn.close(); raise HTTPException(400, "Недостаточно товара")
    conn.execute("UPDATE stock SET quantity = quantity - ? WHERE item_code = ? AND location_id = ?", (req.quantity, req.code, req.location_id))
    conn.execute("DELETE FROM stock WHERE item_code = ? AND location_id = ? AND quantity = 0", (req.code, req.location_id))
    conn.execute("INSERT INTO writeoffs (item_code, quantity, location_id, user_id) VALUES (?,?,?,?)", (req.code, req.quantity, req.location_id, user["tg_id"]))
    conn.commit(); conn.close(); return {"status": "ok"}

@app.get("/api/bookings/{code}")
def get_bookings(code: str, x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data); conn = get_conn()
    rows = conn.execute("SELECT b.id, b.item_code, b.user_id, u.full_name, b.date_from, b.date_to FROM bookings b LEFT JOIN users u ON u.tg_id = b.user_id WHERE b.item_code = ? AND b.date_to >= date('now') ORDER BY b.date_from", (code,)).fetchall()
    conn.close(); return [dict(r) for r in rows]

@app.post("/api/bookings")
def create_booking(req: BookingRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data); conn = get_conn()
    conn.execute("INSERT INTO bookings (item_code, user_id, date_from, date_to) VALUES (?,?,?,?)", (req.code, user["tg_id"], req.date_from, req.date_to))
    conn.commit(); conn.close(); return {"status": "ok"}

@app.get("/api/comments/{code}")
def get_comments(code: str, x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data); conn = get_conn()
    rows = conn.execute("SELECT c.id, c.item_code, c.user_id, u.full_name, c.text, c.created_at FROM comments c LEFT JOIN users u ON u.tg_id = c.user_id WHERE c.item_code = ? ORDER BY c.created_at DESC", (code,)).fetchall()
    conn.close(); return [dict(r) for r in rows]

@app.post("/api/comments")
def create_comment(req: CommentRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data); conn = get_conn()
    conn.execute("INSERT INTO comments (item_code, user_id, text) VALUES (?,?,?)", (req.code, user["tg_id"], req.text))
    conn.commit(); conn.close(); return {"status": "ok"}

@app.post("/api/import_text")
def import_text(req: ImportTextRequest, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data); conn = get_conn(); added = 0; updated = 0
    try:
        lines = [line.strip() for line in req.text.strip().split('\n') if line.strip()]
        current_kit_code = None
        current_kit_data = {"name": "", "loc": "Офис7", "price": 0, "buyer": "", "body": "", "lens": "", "flash": ""}
        def save_kit(kit_code, kit_data):
            nonlocal added, updated
            if not kit_code: return
            loc = conn.execute("SELECT id FROM locations WHERE name = ?", (kit_data["loc"],)).fetchone()
            loc_id = loc["id"] if loc else 1
            existing = conn.execute("SELECT code FROM items WHERE code = ?", (kit_code,)).fetchone()
            if existing:
                conn.execute("UPDATE items SET name=?, price=?, kit_body=?, kit_lens=?, kit_flash=?, buyout_status=? WHERE code=?", (kit_data["name"], kit_data["price"], kit_data["body"], kit_data["lens"], kit_data["flash"], kit_data["buyer"], kit_code))
                stock_exists = conn.execute("SELECT quantity FROM stock WHERE item_code = ?", (kit_code,)).fetchone()
                if stock_exists: conn.execute("UPDATE stock SET location_id = ? WHERE item_code = ?", (loc_id, kit_code))
                else: conn.execute("INSERT INTO stock (item_code, location_id, quantity) VALUES (?,?,1)", (kit_code, loc_id))
                updated += 1
            else:
                try:
                    conn.execute("INSERT INTO items (code, name, kind, price, kit_body, kit_lens, kit_flash, buyout_status) VALUES (?,?,?,?,?,?,?,?)", (kit_code, kit_data["name"], "equipment", kit_data["price"], kit_data["body"], kit_data["lens"], kit_data["flash"], kit_data["buyer"]))
                    conn.execute("INSERT INTO stock (item_code, location_id, quantity) VALUES (?,?,1)", (kit_code, loc_id))
                    added += 1
                except sqlite3.IntegrityError: pass
        for line in lines:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 1: continue
            if parts[0].lower() == "допы": continue
            is_kit_header = False
            if parts[0] and not (len(parts) > 1 and parts[1]) and not (len(parts) > 2 and parts[2]): is_kit_header = True
            if parts[0].lower() not in ["камера", "объектив", "вспышка"] and parts[0]: is_kit_header = True
            if is_kit_header:
                if current_kit_code: save_kit(current_kit_code, current_kit_data)
                current_kit_code = parts[0].replace(" ", "")
                current_kit_data = {"name": f"Комплект {current_kit_code}", "loc": "Офис7", "price": 0, "buyer": "", "body": "", "lens": "", "flash": ""}
                continue
            if not current_kit_code: continue
            if parts[0].lower() == "камера": current_kit_data["body"] = parts[1] if len(parts) > 1 else ""
            elif parts[0].lower() == "объектив": current_kit_data["lens"] = parts[1] if len(parts) > 1 else ""
            elif parts[0].lower() == "вспышка": current_kit_data["flash"] = parts[1] if len(parts) > 1 else ""
            if len(parts) > 3 and parts[3]:
                val = parts[3]
                try: current_kit_data["price"] = float(val)
                except ValueError: current_kit_data["buyer"] = val
        if current_kit_code: save_kit(current_kit_code, current_kit_data)
        conn.commit()
    except Exception as e: conn.rollback(); conn.close(); raise HTTPException(status_code=400, detail=str(e))
    conn.close(); return {"status": "ok", "added": added, "updated": updated}

@app.post("/api/import_file")
async def import_file(file: UploadFile = File(...), x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data); contents = await file.read()
    try:
        if file.filename.endswith('.csv'): df = pd.read_csv(io.BytesIO(contents))
        else: df = pd.read_excel(io.BytesIO(contents))
        csv_buffer = io.StringIO(); df.to_csv(csv_buffer, index=False, header=False)
        req = ImportTextRequest(text=csv_buffer.getvalue())
        return import_text(req, x_init_data)
    except Exception as e: raise HTTPException(400, f"Ошибка чтения файла: {str(e)}")

@app.post("/api/clear_database")
def clear_database(x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data); conn = get_conn()
    try:
        for table in ["items", "stock", "checkouts", "movements", "writeoffs", "bookings", "comments", "lost_items", "daily_reports"]:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    except Exception as e: conn.rollback(); conn.close(); raise HTTPException(400, str(e))
    conn.close(); return {"status": "ok"}

@app.post("/api/inventory_finish")
def inventory_finish(req: InventoryResult, x_init_data: Optional[str] = Header(None)):
    user = check_admin(x_init_data); conn = get_conn(); missing_codes = []; extra_codes = []
    try:
        room_items = conn.execute("SELECT item_code FROM stock WHERE location_id = ? AND quantity > 0", (req.location_id,)).fetchall()
        room_codes = [r["item_code"] for r in room_items]
        missing_codes = [c for c in room_codes if c not in req.found]
        for code in missing_codes: conn.execute("INSERT INTO lost_items (item_code, user_id) VALUES (?, ?)", (code, user["tg_id"]))
        extra_codes = [c for c in req.found if c not in room_codes]
        conn.commit()
    except Exception as e: conn.rollback(); conn.close(); raise HTTPException(400, str(e))
    conn.close(); return {"status": "ok", "missing": missing_codes, "extra": extra_codes}

@app.post("/api/execute_sql")
def execute_sql(req: TerminalRequest, x_init_data: Optional[str] = Header(None)):
    user = check_admin(x_init_data); sql = req.sql.strip()
    if not sql: raise HTTPException(400, "Пустой запрос")
    sql_upper = sql.upper()
    if "DROP TABLE" in sql_upper or "DROP DATABASE" in sql_upper: raise HTTPException(400, "Нельзя удалять таблицы")
    conn = get_conn()
    try:
        cursor = conn.cursor(); cursor.execute(sql)
        conn.execute("INSERT INTO terminal_logs (user_id, sql_query) VALUES (?, ?)", (user["tg_id"], sql))
        if sql_upper.startswith("SELECT"):
            rows = cursor.fetchall(); result = [dict(r) for r in rows]
            conn.close(); return {"status": "ok", "type": "select", "data": result}
        else:
            conn.commit(); count = cursor.rowcount; conn.close()
            return {"status": "ok", "type": "update", "message": f"Выполнено успешно. Затронуто строк: {count}"}
    except Exception as e: conn.rollback(); conn.close(); raise HTTPException(400, detail=str(e))

@app.get("/api/qr/{code}")
def generate_qr(code: str):
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(code); qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    width, height = qr_img.size
    result_img = Image.new("RGB", (width, height + 60), "white"); result_img.paste(qr_img, (0, 0))
    draw = ImageDraw.Draw(result_img)
    try: font = ImageFont.truetype("DejaVuSans.ttf", 36)
    except IOError: font = ImageFont.load_default()
    try: text_w = draw.textlength(code, font=font)
    except AttributeError: text_w = draw.textsize(code, font=font)[0]
    draw.text(((width - text_w) / 2, height + 10), code, fill="black", font=font)
    buf = io.BytesIO(); result_img.save(buf, format="PNG"); buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

@app.get("/")
def serve_beta(): return FileResponse("beta.html")

app.mount("/", StaticFiles(directory=".", html=True), name="frontend")
