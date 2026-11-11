import sqlite3
import json
import hashlib
import hmac
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import qrcode
import io
import csv
import httpx
from PIL import Image, ImageDraw, ImageFont
import base64
from datetime import datetime
import os

BOT_TOKEN = "9136250747:AAHKFT5aMfLPuf64AX1ouyQRiq_aLEHywhI"
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB_PATH = "/data/warehouse.db"

def get_conn():
    if not os.path.exists("/data"):
        try: os.makedirs("/data")
        except: pass
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS locations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, type TEXT NOT NULL DEFAULT 'storage')""")
    c.execute("""CREATE TABLE IF NOT EXISTS users (tg_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, full_name TEXT DEFAULT '', role TEXT DEFAULT 'employee')""")
    try: c.execute("ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'employee'")
    except sqlite3.OperationalError: pass

    c.execute("""CREATE TABLE IF NOT EXISTS spots (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)""")
    
    # ТАБЛИЦА ITEMS С РАЗДЕЛЕНИЕМ КОМПЛЕКТАЦИИ
    c.execute("""CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        code TEXT UNIQUE NOT NULL, 
        name TEXT NOT NULL, 
        kind TEXT NOT NULL DEFAULT 'equipment', 
        min_stock INTEGER DEFAULT 0, 
        photo TEXT DEFAULT '', 
        needs_repair INTEGER DEFAULT 0,
        price REAL DEFAULT 0,
        kit_body TEXT DEFAULT '',
        kit_lens TEXT DEFAULT '',
        kit_flash TEXT DEFAULT '',
        kit_other TEXT DEFAULT ''
    )""")
    try: c.execute("ALTER TABLE items ADD COLUMN needs_repair INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE items ADD COLUMN price REAL DEFAULT 0")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE items ADD COLUMN kit_body TEXT DEFAULT ''")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE items ADD COLUMN kit_lens TEXT DEFAULT ''")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE items ADD COLUMN kit_flash TEXT DEFAULT ''")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE items ADD COLUMN kit_other TEXT DEFAULT ''")
    except sqlite3.OperationalError: pass

    c.execute("""CREATE TABLE IF NOT EXISTS bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT NOT NULL, user_id INTEGER NOT NULL, date_from TEXT NOT NULL, date_to TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT NOT NULL, user_id INTEGER NOT NULL, text TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS stock (item_code TEXT NOT NULL, location_id INTEGER NOT NULL, quantity INTEGER NOT NULL DEFAULT 0, spot TEXT DEFAULT '', PRIMARY KEY (item_code, location_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS checkouts (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT NOT NULL, user_id INTEGER NOT NULL, location_id INTEGER NOT NULL, taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, returned_at TIMESTAMP, returned_by INTEGER, taken_for TEXT DEFAULT '')""")
    try: c.execute("ALTER TABLE checkouts ADD COLUMN returned_by INTEGER")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE checkouts ADD COLUMN taken_for TEXT DEFAULT ''")
    except sqlite3.OperationalError: pass
    c.execute("""CREATE TABLE IF NOT EXISTS movements (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT NOT NULL, quantity INTEGER NOT NULL, from_location INTEGER, to_location INTEGER, to_spot TEXT DEFAULT '', user_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS writeoffs (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT NOT NULL, quantity INTEGER NOT NULL, location_id INTEGER, user_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS lost_items (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT NOT NULL, user_id INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    
    c.execute("SELECT COUNT(*) FROM locations")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO locations (name, type) VALUES ('Этаж2', 'workshop')")
        c.execute("INSERT INTO locations (name, type) VALUES ('Склад11', 'storage')")
        c.execute("INSERT INTO locations (name, type) VALUES ('Офис7', 'office')")
    conn.commit()
    conn.close()

init_db()

def verify_init_data(init_data: str) -> dict:
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        raise HTTPException(status_code=401, detail="Некорректный initData")
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
        conn.execute("INSERT INTO users (tg_id, first_name, username, full_name, role) VALUES (?, ?, ?, ?, 'employee')", 
                     (user["id"], user.get("first_name", ""), user.get("username", ""), full_name))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE tg_id = ?", (user["id"],)).fetchone()
    conn.close()
    return dict(row)

def check_admin(x_init_data: Optional[str]):
    user = get_user(x_init_data)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Доступ только для администратора")
    return user

async def send_notification(message: str):
    conn = get_conn()
    users = conn.execute("SELECT tg_id FROM users").fetchall()
    conn.close()
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        for u in users:
            try: await client.post(url, json={"chat_id": u["tg_id"], "text": message, "parse_mode": "HTML"})
            except: pass

class ItemCreate(BaseModel):
    code: str
    name: str
    kind: str = "equipment"
    location_id: int
    quantity: int = 0
    spot: str = ""
    min_stock: int = 0
    price: float = 0
    kit_body: str = ""
    kit_lens: str = ""
    kit_flash: str = ""
    kit_other: str = ""

class ItemUpdate(BaseModel):
    name: str
    kind: str
    location_id: int
    spot: str
    price: float
    kit_body: str
    kit_lens: str
    kit_flash: str
    kit_other: str

class MoveRequest(BaseModel):
    code: str
    from_location: int
    to_location: int
    quantity: int
    to_spot: str = ""

class WriteoffRequest(BaseModel):
    code: str
    location_id: int
    quantity: int

class SpotCreate(BaseModel):
    name: str

class SpotUpdate(BaseModel):
    old_name: str
    new_name: str

class BookingRequest(BaseModel):
    code: str
    date_from: str
    date_to: str

class CommentRequest(BaseModel):
    code: str
    text: str

class CheckoutRequest(BaseModel):
    code: str
    taken_for: str = ""

class RegisterRequest(BaseModel):
    full_name: str

class LocationCreate(BaseModel):
    name: str

@app.get("/api/me")
def get_me(x_init_data: Optional[str] = Header(None)):
    return get_user(x_init_data)

@app.post("/api/register")
def register(req: RegisterRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    conn = get_conn()
    conn.execute("UPDATE users SET full_name = ? WHERE tg_id = ?", (req.full_name.strip(), user["tg_id"]))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.get("/api/users")
def list_users(x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data)
    conn = get_conn()
    rows = conn.execute("SELECT tg_id, full_name, role FROM users ORDER BY role DESC, full_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/users/{tg_id}/role")
def set_role(tg_id: int, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data)
    conn = get_conn()
    current = conn.execute("SELECT role FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
    new_role = "employee" if current["role"] == "admin" else "admin"
    conn.execute("UPDATE users SET role = ? WHERE tg_id = ?", (new_role, tg_id))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.get("/api/locations")
def list_locations():
    conn = get_conn()
    rows = conn.execute("SELECT id, name, type FROM locations ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/locations")
def create_location(req: LocationCreate, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data)
    conn = get_conn()
    try:
        conn.execute("INSERT INTO locations (name) VALUES (?)", (req.name.strip(),))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close(); raise HTTPException(400, "Такая комната уже есть")
    conn.close()
    return {"status": "ok"}

@app.get("/api/spots")
def list_spots():
    conn = get_conn()
    rows = conn.execute("SELECT id, name FROM spots ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/spots")
def create_spot(spot: SpotCreate, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data)
    conn = get_conn()
    try:
        conn.execute("INSERT INTO spots (name) VALUES (?)", (spot.name.strip(),))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close(); raise HTTPException(status_code=400, detail="Такая полка уже есть")
    conn.close()
    return {"status": "ok"}

@app.put("/api/spots")
def update_spot(req: SpotUpdate, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data)
    conn = get_conn()
    # Обновляем полку в таблице spots
    conn.execute("UPDATE spots SET name = ? WHERE name = ?", (req.new_name.strip(), req.old_name))
    # Обновляем привязку в stock
    conn.execute("UPDATE stock SET spot = ? WHERE spot = ?", (req.new_name.strip(), req.old_name))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.get("/api/next_code")
def get_next_code(x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data)
    conn = get_conn()
    rows = conn.execute("SELECT code FROM items WHERE code LIKE 'ITEM-%'").fetchall()
    max_num = 0
    for r in rows:
        try:
            num = int(r["code"].split("-")[1])
            if num > max_num: max_num = num
        except: pass
    conn.close()
    return {"code": f"ITEM-{max_num + 1}"}

@app.get("/api/items")
def list_items(x_init_data: Optional[str] = Header(None)):
    is_admin = False
    try:
        user = get_user(x_init_data)
        is_admin = user["role"] == "admin"
    except: pass

    conn = get_conn()
    items = conn.execute("SELECT * FROM items ORDER BY name").fetchall()
    result = []
    for it in items:
        stocks = conn.execute("SELECT s.location_id, l.name AS location_name, s.quantity, s.spot FROM stock s JOIN locations l ON l.id = s.location_id WHERE s.item_code = ? AND s.quantity > 0", (it["code"],)).fetchall()
        holders = conn.execute("SELECT c.id, c.user_id, u.full_name, c.taken_at, c.taken_for FROM checkouts c LEFT JOIN users u ON u.tg_id = c.user_id WHERE c.item_code = ? AND c.returned_at IS NULL", (it["code"],)).fetchall()
        total = sum(s["quantity"] for s in stocks)
        
        item_data = {
            "code": it["code"], "name": it["name"], "kind": it["kind"], "min_stock": it["min_stock"], "photo": it["photo"], "needs_repair": it["needs_repair"],
            "kit_body": it["kit_body"], "kit_lens": it["kit_lens"], "kit_flash": it["kit_flash"], "kit_other": it["kit_other"],
            "total": total, "is_low": total <= it["min_stock"] and it["min_stock"] > 0 and it["kind"] == "consumable",
            "stocks": [dict(s) for s in stocks], "holders": [dict(h) for h in holders],
        }
        if is_admin:
            item_data["price"] = it["price"]
            
        result.append(item_data)
    conn.close()
    return result

@app.get("/api/items/{code}")
def get_item(code: str, x_init_data: Optional[str] = Header(None)):
    is_admin = False
    try:
        user = get_user(x_init_data)
        is_admin = user["role"] == "admin"
    except: pass

    conn = get_conn()
    item = conn.execute("SELECT * FROM items WHERE code = ?", (code,)).fetchone()
    if not item:
        conn.close(); raise HTTPException(status_code=404, detail="Товар не найден")
    stocks = conn.execute("SELECT s.location_id, l.name AS location_name, s.quantity, s.spot FROM stock s JOIN locations l ON l.id = s.location_id WHERE s.item_code = ? AND s.quantity > 0", (code,)).fetchall()
    holders = conn.execute("SELECT c.id, c.user_id, u.full_name, c.taken_at, c.taken_for FROM checkouts c LEFT JOIN users u ON u.tg_id = c.user_id WHERE c.item_code = ? AND c.returned_at IS NULL", (code,)).fetchall()
    conn.close()
    
    result = {
        "code": item["code"], "name": item["name"], "kind": item["kind"], "min_stock": item["min_stock"], "photo": item["photo"], "needs_repair": item["needs_repair"], 
        "kit_body": item["kit_body"], "kit_lens": item["kit_lens"], "kit_flash": item["kit_flash"], "kit_other": item["kit_other"],
        "stocks": [dict(s) for s in stocks], "holders": [dict(h) for h in holders]
    }
    if is_admin:
        result["price"] = item["price"]
        
    return result

@app.put("/api/items/{code}")
def update_item(code: str, req: ItemUpdate, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data)
    conn = get_conn()
    
    # Обновляем товар
    conn.execute("""UPDATE items SET name=?, kind=?, price=?, kit_body=?, kit_lens=?, kit_flash=?, kit_other=? WHERE code=?""",
                 (req.name, req.kind, req.price, req.kit_body, req.kit_lens, req.kit_flash, req.kit_other, code))
    
    # Обновляем локацию и полку в stock (только для первой записи, так как перемещение сложнее)
    # Для простоты обновляем только полку, если она есть
    if req.spot:
        conn.execute("UPDATE stock SET spot=? WHERE item_code=?", (req.spot, code))
    else:
        conn.execute("UPDATE stock SET spot='' WHERE item_code=?", (code,))
        
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.post("/api/items/{code}/repair")
def toggle_repair(code: str, x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data)
    conn = get_conn()
    item = conn.execute("SELECT needs_repair, name FROM items WHERE code = ?", (code,)).fetchone()
    if not item:
        conn.close(); raise HTTPException(404, "Товар не найден")
    new_status = 0 if item["needs_repair"] else 1
    conn.execute("UPDATE items SET needs_repair = ? WHERE code = ?", (new_status, code))
    conn.commit(); conn.close()
    status_text = "отправлен в ремонт" if new_status else "возвращен в строй"
    return {"status": "ok", "needs_repair": new_status, "message": f"Товар {item['name']} {status_text}"}

@app.post("/api/items/{code}/lost")
async def mark_lost(code: str, background_tasks: BackgroundTasks, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    conn = get_conn()
    item = conn.execute("SELECT name FROM items WHERE code = ?", (code,)).fetchone()
    if not item:
        conn.close(); raise HTTPException(404, "Товар не найден")
    conn.execute("INSERT INTO lost_items (item_code, user_id) VALUES (?, ?)", (code, user["tg_id"]))
    conn.commit(); conn.close()
    msg = f"🚨 <b>Тревога!</b>\nСотрудник {user['full_name']} не нашел на месте: <b>{item['name']}</b> ({code})."
    background_tasks.add_task(send_notification, msg)
    return {"status": "ok", "message": "Уведомление отправлено"}

@app.delete("/api/items/{code}")
def delete_item(code: str, x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data)
    conn = get_conn()
    conn.execute("DELETE FROM items WHERE code = ?", (code,))
    conn.execute("DELETE FROM stock WHERE item_code = ?", (code,))
    conn.execute("DELETE FROM bookings WHERE item_code = ?", (code,))
    conn.execute("DELETE FROM comments WHERE item_code = ?", (code,))
    conn.execute("DELETE FROM lost_items WHERE item_code = ?", (code,))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.get("/api/on_hand")
def on_hand():
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.item_code, i.name, u.full_name, c.taken_at, c.taken_for
        FROM checkouts c JOIN items i ON i.code = c.item_code LEFT JOIN users u ON u.tg_id = c.user_id
        WHERE c.returned_at IS NULL
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/bookings/{code}")
def get_bookings(code: str):
    conn = get_conn()
    rows = conn.execute("SELECT b.id, b.user_id, u.full_name, b.date_from, b.date_to FROM bookings b LEFT JOIN users u ON u.tg_id = b.user_id WHERE b.item_code = ? ORDER BY b.date_from", (code,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/bookings")
def create_booking(req: BookingRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    conn = get_conn()
    existing = conn.execute("SELECT id FROM bookings WHERE item_code = ? AND date_from <= ? AND date_to >= ?", (req.code, req.date_to, req.date_from)).fetchone()
    if existing:
        conn.close(); raise HTTPException(400, "На эти даты уже есть бронь")
    conn.execute("INSERT INTO bookings (item_code, user_id, date_from, date_to) VALUES (?, ?, ?, ?)", (req.code, user["tg_id"], req.date_from, req.date_to))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.get("/api/comments/{code}")
def get_comments(code: str):
    conn = get_conn()
    rows = conn.execute("SELECT c.id, c.text, c.created_at, u.full_name FROM comments c LEFT JOIN users u ON u.tg_id = c.user_id WHERE c.item_code = ? ORDER BY c.created_at DESC", (code,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/comments")
def create_comment(req: CommentRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    conn = get_conn()
    conn.execute("INSERT INTO comments (item_code, user_id, text) VALUES (?, ?, ?)", (req.code, user["tg_id"], req.text))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.post("/api/items")
async def create_item(
    code: str = Form(...), name: str = Form(...), kind: str = Form("equipment"), location_id: int = Form(...),
    quantity: int = Form(0), spot: str = Form(""), min_stock: int = Form(0), 
    price: float = Form(0), kit_body: str = Form(""), kit_lens: str = Form(""), kit_flash: str = Form(""), kit_other: str = Form(""),
    photo: Optional[UploadFile] = File(None),
    x_init_data: Optional[str] = Header(None)
):
    check_admin(x_init_data)
    conn = get_conn()
    photo_base64 = ""
    if photo:
        contents = await photo.read()
        photo_base64 = base64.b64encode(contents).decode("utf-8")
    try:
        conn.execute("INSERT INTO items (code, name, kind, min_stock, photo, price, kit_body, kit_lens, kit_flash, kit_other) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                     (code, name, kind, min_stock, photo_base64, price, kit_body, kit_lens, kit_flash, kit_other))
    except sqlite3.IntegrityError:
        conn.close(); raise HTTPException(status_code=400, detail="Код уже существует")
    if spot:
        try: conn.execute("INSERT OR IGNORE INTO spots (name) VALUES (?)", (spot,))
        except: pass
    conn.execute("INSERT INTO stock (item_code, location_id, quantity, spot) VALUES (?, ?, ?, ?)", (code, location_id, quantity, spot))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.post("/api/checkout")
async def checkout(req: CheckoutRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    conn = get_conn()
    item = conn.execute("SELECT kind, needs_repair FROM items WHERE code = ?", (req.code,)).fetchone()
    if not item: conn.close(); raise HTTPException(404, "Товар не найден")
    if item["needs_repair"]:
        conn.close(); raise HTTPException(400, "Товар в ремонте, выдача запрещена")
    if item["kind"] != "equipment":
        conn.close(); raise HTTPException(400, "Это расходник, используйте списание")
    
    existing = conn.execute("SELECT id FROM checkouts WHERE item_code = ? AND returned_at IS NULL", (req.code,)).fetchone()
    if existing:
        conn.close(); raise HTTPException(400, "Уже выдано")
    stock = conn.execute("SELECT location_id, quantity FROM stock WHERE item_code = ? AND quantity > 0 ORDER BY location_id LIMIT 1", (req.code,)).fetchone()
    if not stock:
        conn.close(); raise HTTPException(400, "Нет в наличии")
    
    conn.execute("INSERT INTO checkouts (item_code, user_id, location_id, taken_for) VALUES (?, ?, ?, ?)", (req.code, user["tg_id"], stock["location_id"], req.taken_for))
    conn.execute("UPDATE stock SET quantity = quantity - 1 WHERE item_code = ? AND location_id = ?", (req.code, stock["location_id"]))
    conn.execute("DELETE FROM stock WHERE item_code = ? AND quantity = 0", (req.code,))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.post("/api/return")
def return_item(code: str, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    conn = get_conn()
    co = conn.execute("SELECT id, user_id, location_id FROM checkouts WHERE item_code = ? AND returned_at IS NULL", (code,)).fetchone()
    if not co:
        conn.close(); raise HTTPException(400, "Не выдано")
    conn.execute("UPDATE checkouts SET returned_at = CURRENT_TIMESTAMP, returned_by = ? WHERE id = ?", (user["tg_id"], co["id"]))
    existing = conn.execute("SELECT quantity FROM stock WHERE item_code = ? AND location_id = ?", (code, co["location_id"])).fetchone()
    if existing:
        conn.execute("UPDATE stock SET quantity = quantity + 1 WHERE item_code = ? AND location_id = ?", (code, co["location_id"]))
    else:
        conn.execute("INSERT INTO stock (item_code, location_id, quantity) VALUES (?, ?, 1)", (code, co["location_id"]))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.post("/api/move")
def move_item(req: MoveRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    if req.from_location == req.to_location: raise HTTPException(400, "Локации должны отличаться")
    if req.quantity <= 0: raise HTTPException(400, "Количество должно быть > 0")
    conn = get_conn()
    row = conn.execute("SELECT quantity FROM stock WHERE item_code = ? AND location_id = ?", (req.code, req.from_location)).fetchone()
    if not row or row["quantity"] < req.quantity:
        conn.close(); raise HTTPException(400, f"Недостаточно товара.")
    
    conn.execute("UPDATE stock SET quantity = quantity - ? WHERE item_code = ? AND location_id = ?", (req.quantity, req.code, req.from_location))
    conn.execute("DELETE FROM stock WHERE item_code = ? AND location_id = ? AND quantity = 0", (req.code, req.from_location))

    if req.to_spot:
        try: conn.execute("INSERT OR IGNORE INTO spots (name) VALUES (?)", (req.to_spot,))
        except: pass
    existing = conn.execute("SELECT quantity FROM stock WHERE item_code = ? AND location_id = ?", (req.code, req.to_location)).fetchone()
    if existing:
        conn.execute("UPDATE stock SET quantity = quantity + ?, spot = COALESCE(NULLIF(?, ''), spot) WHERE item_code = ? AND location_id = ?", (req.quantity, req.to_spot, req.code, req.to_location))
    else:
        conn.execute("INSERT INTO stock (item_code, location_id, quantity, spot) VALUES (?, ?, ?, ?)", (req.code, req.to_location, req.quantity, req.to_spot))
    
    conn.execute("INSERT INTO movements (item_code, quantity, from_location, to_location, to_spot, user_id) VALUES (?, ?, ?, ?, ?, ?)", (req.code, req.quantity, req.from_location, req.to_location, req.to_spot, user["tg_id"]))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.post("/api/writeoff")
async def writeoff(req: WriteoffRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    conn = get_conn()
    row = conn.execute("SELECT quantity FROM stock WHERE item_code = ? AND location_id = ?", (req.code, req.location_id)).fetchone()
    if not row or row["quantity"] < req.quantity:
        conn.close(); raise HTTPException(400, "Недостаточно товара")
    conn.execute("UPDATE stock SET quantity = quantity - ? WHERE item_code = ? AND location_id = ?", (req.quantity, req.code, req.location_id))
    conn.execute("DELETE FROM stock WHERE item_code = ? AND location_id = ? AND quantity = 0", (req.code, req.location_id))
    conn.execute("INSERT INTO writeoffs (item_code, quantity, location_id, user_id) VALUES (?, ?, ?, ?)", (req.code, req.quantity, req.location_id, user["tg_id"]))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.get("/api/history")
def get_history(limit: int = 50):
    conn = get_conn()
    query = """
    SELECT 'checkout' as type, c.taken_at as date, c.item_code, i.name, u.full_name as user_name, 1 as quantity, NULL as from_loc, c.taken_for
    FROM checkouts c JOIN items i ON i.code = c.item_code LEFT JOIN users u ON u.tg_id = c.user_id
    UNION ALL
    SELECT 'return', c.returned_at, c.item_code, i.name, COALESCE(ru.full_name, 'Неизвестно') || ' (вернул за ' || COALESCE(u.full_name, 'Неизвестно') || ')', 1, NULL, NULL
    FROM checkouts c JOIN items i ON i.code = c.item_code LEFT JOIN users u ON u.tg_id = c.user_id LEFT JOIN users ru ON ru.tg_id = c.returned_by WHERE c.returned_at IS NOT NULL
    UNION ALL
    SELECT 'move', m.created_at, m.item_code, i.name, u.full_name, m.quantity, l1.name, NULL
    FROM movements m JOIN items i ON i.code = m.item_code LEFT JOIN users u ON u.tg_id = m.user_id LEFT JOIN locations l1 ON l1.id = m.from_location
    UNION ALL
    SELECT 'writeoff', w.created_at, w.item_code, i.name, u.full_name, w.quantity, l.name, NULL
    FROM writeoffs w JOIN items i ON i.code = w.item_code LEFT JOIN users u ON u.tg_id = w.user_id LEFT JOIN locations l ON l.id = w.location_id
    UNION ALL
    SELECT 'lost', l.created_at, l.item_code, i.name, u.full_name, 1, NULL, 'НЕ НАЙДЕН'
    FROM lost_items l JOIN items i ON i.code = l.item_code LEFT JOIN users u ON u.tg_id = l.user_id
    ORDER BY date DESC LIMIT ?
    """
    rows = conn.execute(query, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/export_history")
def export_history(x_init_data: Optional[str] = Header(None)):
    check_admin(x_init_data)
    conn = get_conn()
    query = """
    SELECT 'Выдача' as type, c.taken_at as date, c.item_code as code, i.name, u.full_name as user_name, 1 as quantity, '' as from_loc, c.taken_for as to_loc
    FROM checkouts c JOIN items i ON i.code = c.item_code LEFT JOIN users u ON u.tg_id = c.user_id
    UNION ALL
    SELECT 'Возврат', c.returned_at, c.item_code, i.name, COALESCE(ru.full_name, 'Неизвестно') || ' (вернул за ' || COALESCE(u.full_name, 'Неизвестно') || ')', 1, '', ''
    FROM checkouts c JOIN items i ON i.code = c.item_code LEFT JOIN users u ON u.tg_id = c.user_id LEFT JOIN users ru ON ru.tg_id = c.returned_by WHERE c.returned_at IS NOT NULL
    UNION ALL
    SELECT 'Перемещение', m.created_at, m.item_code, i.name, u.full_name, m.quantity, l1.name, l2.name
    FROM movements m JOIN items i ON i.code = m.item_code LEFT JOIN users u ON u.tg_id = m.user_id LEFT JOIN locations l1 ON l1.id = m.from_location LEFT JOIN locations l2 ON l2.id = m.to_location
    UNION ALL
    SELECT 'Списание', w.created_at, w.item_code, i.name, u.full_name, w.quantity, l.name, ''
    FROM writeoffs w JOIN items i ON i.code = w.item_code LEFT JOIN users u ON u.tg_id = w.user_id LEFT JOIN locations l ON l.id = w.location_id
    ORDER BY date DESC
    """
    rows = conn.execute(query).fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(["Действие", "Дата", "Код", "Название", "Сотрудник", "Кол-во", "Откуда", "Куда/Для кого"])
    for r in rows: writer.writerow([r["type"], r["date"], r["code"], r["name"], r["user_name"], r["quantity"], r["from_loc"], r["to_loc"]])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=warehouse_history.csv"})

@app.get("/api/qr/{code}")
def generate_qr(code: str):
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(code)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    width, height = qr_img.size
    new_height = height + 60
    result_img = Image.new("RGB", (width, new_height), "white")
    result_img.paste(qr_img, (0, 0))
    draw = ImageDraw.Draw(result_img)
    try: font = ImageFont.truetype("DejaVuSans.ttf", 36)
    except IOError: font = ImageFont.load_default()
    text_bbox = draw.textbbox((0, 0), code, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    draw.text(((width - text_width) / 2, height + 10), code, fill="black", font=font)
    buf = io.BytesIO()
    result_img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

app.mount("/", StaticFiles(directory=".", html=True), name="frontend")
