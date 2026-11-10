import sqlite3
import json
import hashlib
import hmac
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import qrcode
import io

# ВСТАВЬТЕ СЮДА ВАШ ТОКЕН ИЗ BOTFATHER (вместо 123456789:AAH...)
BOT_TOKEN = "9136250747:AAHKFT5aMfLPuf64AX1ouyQRiq_aLEHywhI"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

DB_PATH = "warehouse.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        type TEXT NOT NULL DEFAULT 'storage'
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        tg_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'equipment'
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS stock (
        item_code TEXT NOT NULL,
        location_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 0,
        spot TEXT DEFAULT '',
        PRIMARY KEY (item_code, location_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS checkouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_code TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        location_id INTEGER NOT NULL,
        taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        returned_at TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_code TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        from_location INTEGER,
        to_location INTEGER,
        to_spot TEXT DEFAULT '',
        user_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS writeoffs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_code TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        location_id INTEGER,
        user_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("SELECT COUNT(*) FROM locations")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO locations (name, type) VALUES ('Мастерская', 'workshop')")
        c.execute("INSERT INTO locations (name, type) VALUES ('Склад', 'storage')")
        c.execute("INSERT INTO locations (name, type) VALUES ('Офис', 'office')")
    conn.commit()
    conn.close()

init_db()

def verify_init_data(init_data: str) -> dict:
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        raise HTTPException(status_code=401, detail="Некорректный initData")
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Нет подписи")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if calculated != received_hash:
        raise HTTPException(status_code=401, detail="Неверная подпись")
    user_json = pairs.get("user")
    if not user_json:
        raise HTTPException(status_code=401, detail="Нет пользователя")
    return json.loads(user_json)

def get_user(x_init_data: Optional[str]):
    if not x_init_data:
        raise HTTPException(status_code=401, detail="Нет авторизации")
    user = verify_init_data(x_init_data)
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO users (tg_id, first_name, username) VALUES (?, ?, ?)",
        (user["id"], user.get("first_name", ""), user.get("username", "")),
    )
    conn.commit()
    conn.close()
    return user

class ItemCreate(BaseModel):
    code: str
    name: str
    kind: str = "equipment"
    location_id: int
    quantity: int = 0
    spot: str = ""

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

@app.get("/api/locations")
def list_locations():
    conn = get_conn()
    rows = conn.execute("SELECT id, name, type FROM locations ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/items")
def list_items():
    conn = get_conn()
    items = conn.execute("SELECT code, name, kind FROM items ORDER BY name").fetchall()
    result = []
    for it in items:
        stocks = conn.execute(
            """SELECT s.location_id, l.name AS location_name, s.quantity, s.spot
               FROM stock s JOIN locations l ON l.id = s.location_id
               WHERE s.item_code = ?""", (it["code"],)
        ).fetchall()
        holders = conn.execute(
            """SELECT c.id AS checkout_id, c.user_id, u.first_name, u.username, c.taken_at
               FROM checkouts c LEFT JOIN users u ON u.tg_id = c.user_id
               WHERE c.item_code = ? AND c.returned_at IS NULL""", (it["code"],)
        ).fetchall()
        result.append({
            "code": it["code"], "name": it["name"], "kind": it["kind"],
            "total": sum(s["quantity"] for s in stocks),
            "stocks": [dict(s) for s in stocks],
            "holders": [dict(h) for h in holders],
        })
    conn.close()
    return result

@app.get("/api/items/{code}")
def get_item(code: str):
    conn = get_conn()
    item = conn.execute("SELECT code, name, kind FROM items WHERE code = ?", (code,)).fetchone()
    if not item:
        conn.close(); raise HTTPException(status_code=404, detail="Товар не найден")
    stocks = conn.execute(
        """SELECT s.location_id, l.name AS location_name, s.quantity, s.spot
           FROM stock s JOIN locations l ON l.id = s.location_id
           WHERE s.item_code = ?""", (code,)
    ).fetchall()
    holders = conn.execute(
        """SELECT c.id AS checkout_id, c.user_id, u.first_name, u.username, c.taken_at
           FROM checkouts c LEFT JOIN users u ON u.tg_id = c.user_id
           WHERE c.item_code = ? AND c.returned_at IS NULL""", (code,)
    ).fetchall()
    conn.close()
    return {
        "code": item["code"], "name": item["name"], "kind": item["kind"],
        "stocks": [dict(s) for s in stocks],
        "holders": [dict(h) for h in holders],
    }

@app.post("/api/items")
def create_item(item: ItemCreate, x_init_data: Optional[str] = Header(None)):
    get_user(x_init_data)
    conn = get_conn()
    try:
        conn.execute("INSERT INTO items (code, name, kind) VALUES (?, ?, ?)",
                     (item.code, item.name, item.kind))
    except sqlite3.IntegrityError:
        conn.close(); raise HTTPException(status_code=400, detail="Код уже существует")
    conn.execute("INSERT INTO stock (item_code, location_id, quantity, spot) VALUES (?, ?, ?, ?)",
                 (item.code, item.location_id, item.quantity, item.spot))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.post("/api/checkout")
def checkout(code: str, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    conn = get_conn()
    item = conn.execute("SELECT kind FROM items WHERE code = ?", (code,)).fetchone()
    if not item: conn.close(); raise HTTPException(404, "Товар не найден")
    if item["kind"] != "equipment":
        conn.close(); raise HTTPException(400, "Это расходник, используйте списание")
    existing = conn.execute(
        "SELECT id FROM checkouts WHERE item_code = ? AND returned_at IS NULL", (code,)
    ).fetchone()
    if existing:
        conn.close(); raise HTTPException(400, "Уже выдано")
    stock = conn.execute(
        "SELECT location_id, quantity FROM stock WHERE item_code = ? AND quantity > 0 ORDER BY location_id LIMIT 1",
        (code,)
    ).fetchone()
    if not stock:
        conn.close(); raise HTTPException(400, "Нет в наличии")
    conn.execute(
        "INSERT INTO checkouts (item_code, user_id, location_id) VALUES (?, ?, ?)",
        (code, user["id"], stock["location_id"]),
    )
    conn.execute(
        "UPDATE stock SET quantity = quantity - 1 WHERE item_code = ? AND location_id = ?",
        (code, stock["location_id"]),
    )
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.post("/api/return")
def return_item(code: str, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    conn = get_conn()
    co = conn.execute(
        "SELECT id, user_id, location_id FROM checkouts WHERE item_code = ? AND returned_at IS NULL",
        (code,)
    ).fetchone()
    if not co:
        conn.close(); raise HTTPException(400, "Не выдано")
    if co["user_id"] != user["id"]:
        conn.close(); raise HTTPException(403, "Эту вещь держит другой сотрудник")
    conn.execute("UPDATE checkouts SET returned_at = CURRENT_TIMESTAMP WHERE id = ?", (co["id"],))
    existing = conn.execute(
        "SELECT quantity FROM stock WHERE item_code = ? AND location_id = ?",
        (code, co["location_id"])
    ).fetchone()
    if existing:
        conn.execute("UPDATE stock SET quantity = quantity + 1 WHERE item_code = ? AND location_id = ?",
                     (code, co["location_id"]))
    else:
        conn.execute("INSERT INTO stock (item_code, location_id, quantity) VALUES (?, ?, 1)",
                     (code, co["location_id"]))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.post("/api/move")
def move_item(req: MoveRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    if req.from_location == req.to_location:
        raise HTTPException(400, "Локации должны отличаться")
    if req.quantity <= 0:
        raise HTTPException(400, "Количество должно быть > 0")
    conn = get_conn()
    row = conn.execute(
        "SELECT quantity FROM stock WHERE item_code = ? AND location_id = ?",
        (req.code, req.from_location)
    ).fetchone()
    if not row or row["quantity"] < req.quantity:
        conn.close(); raise HTTPException(400, "Недостаточно товара в источнике")
    conn.execute("UPDATE stock SET quantity = quantity - ? WHERE item_code = ? AND location_id = ?",
                 (req.quantity, req.code, req.from_location))
    existing = conn.execute(
        "SELECT quantity FROM stock WHERE item_code = ? AND location_id = ?",
        (req.code, req.to_location)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE stock SET quantity = quantity + ?, spot = COALESCE(NULLIF(?, ''), spot) WHERE item_code = ? AND location_id = ?",
            (req.quantity, req.to_spot, req.code, req.to_location))
    else:
        conn.execute("INSERT INTO stock (item_code, location_id, quantity, spot) VALUES (?, ?, ?, ?)",
                     (req.code, req.to_location, req.quantity, req.to_spot))
    conn.execute(
        "INSERT INTO movements (item_code, quantity, from_location, to_location, to_spot, user_id) VALUES (?, ?, ?, ?, ?, ?)",
        (req.code, req.quantity, req.from_location, req.to_location, req.to_spot, user["id"]))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.post("/api/writeoff")
def writeoff(req: WriteoffRequest, x_init_data: Optional[str] = Header(None)):
    user = get_user(x_init_data)
    conn = get_conn()
    row = conn.execute(
        "SELECT quantity FROM stock WHERE item_code = ? AND location_id = ?",
        (req.code, req.location_id)
    ).fetchone()
    if not row or row["quantity"] < req.quantity:
        conn.close(); raise HTTPException(400, "Недостаточно товара")
    conn.execute("UPDATE stock SET quantity = quantity - ? WHERE item_code = ? AND location_id = ?",
                 (req.quantity, req.code, req.location_id))
    conn.execute("INSERT INTO writeoffs (item_code, quantity, location_id, user_id) VALUES (?, ?, ?, ?)",
                 (req.code, req.quantity, req.location_id, user["id"]))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.get("/api/qr/{code}")
def generate_qr(code: str):
    img = qrcode.make(code)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

app.mount("/", StaticFiles(directory=".", html=True), name="frontend")
