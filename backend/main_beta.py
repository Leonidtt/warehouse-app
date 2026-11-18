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

# --- НАСТРОЙКИ RAILWAY (только Бета) ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("Не настроена переменная BOT_TOKEN для Беты")

try:
    BETA_ADMIN_ID = int(os.environ.get("BETA_ADMIN_ID", "").strip())
    if not 0 < BETA_ADMIN_ID < 2**52:
        raise ValueError
except ValueError:
    raise RuntimeError("Укажите корректный BETA_ADMIN_ID в Railway") from None

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "").strip()

app = FastAPI()

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

DB_PATH_BETA = "/data/warehouse_beta.db"

# Бета не открывает базу Основы ни при каких данных авторизации.
def get_conn(x_init_data: Optional[str] = None):
    os.makedirs(os.path.dirname(DB_PATH_BETA), exist_ok=True)
    conn = sqlite3.connect(DB_PATH_BETA)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def find_or_create_guest(full_name, conn):
    name = full_name.strip()
    if not name: return None
    row = conn.execute("SELECT tg_id FROM users WHERE full_name = ?", (name,)).fetchone()
    if row: return row["tg_id"]
    
    min_id_row = conn.execute("SELECT MIN(tg_id) FROM users WHERE tg_id < 0").fetchone()
    min_id = min_id_row[0] if min_id_row and min_id_row[0] is not None else 0
    new_id = min_id - 1
    
    conn.execute("INSERT INTO users (tg_id, full_name, role, is_registered) VALUES (?, ?, 'guest', 1)", (new_id, name))
    conn.commit()
