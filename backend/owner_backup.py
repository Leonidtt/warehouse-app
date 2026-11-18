"""Owner-only SQLite backup delivery. No public download URL."""
import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl

import httpx
from fastapi import Header, HTTPException

MAX_BACKUP_BYTES = 49 * 1024 * 1024


def owner_id():
    try:
        value = int(os.environ.get('BETA_ADMIN_ID', '').strip())
        return value if value > 0 else None
    except ValueError:
        return None


def can_backup(user):
    return bool(owner_id() and user.get('tg_id') == owner_id()
                and user.get('role') == 'admin' and user.get('is_registered'))


def verify_owner(raw, token, path):
    try:
        if not raw or not token or not owner_id() or len(raw) > 16384:
            raise ValueError()
        entries = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
        pairs = dict(entries)
        if len(pairs) != len(entries):
            raise ValueError()
        given = pairs.pop('hash')
        data = '\n'.join(f'{k}={v}' for k, v in sorted(pairs.items()))
        secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(given, expected):
            raise ValueError()
        user = json.loads(pairs['user'])
        uid = user['id']
        age = time.time() - int(pairs['auth_date'])
        if type(uid) is not int or uid != owner_id():
            raise ValueError()
        if not -60 <= age <= 900:
            raise HTTPException(401, 'Закройте и заново откройте приложение.')
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(403, 'Резервная копия доступна только владельцу.') from None
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=5) as conn:
        row = conn.execute('SELECT role, is_registered FROM users WHERE tg_id=?', (uid,)).fetchone()
    conn.close()
    if not row or row[0] != 'admin' or not row[1]:
        raise HTTPException(403, 'Резервная копия доступна только владельцу.')
    return uid


def make_backup(path, target):
    source = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    dest = None
    try:
        if source.execute('PRAGMA page_count').fetchone()[0] * source.execute('PRAGMA page_size').fetchone()[0] > MAX_BACKUP_BYTES:
            raise HTTPException(413, 'База слишком большая для отправки ботом.')
        dest = sqlite3.connect(target)
        deadline = time.monotonic() + 40
        def progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise HTTPException(503, 'База занята. Повторите позже.')
        source.backup(dest, pages=128, progress=progress, sleep=0.1)
        for table in ('web_codes', 'web_sessions', 'employee_preview'):
            if dest.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                dest.execute('DELETE FROM '+table)
        dest.commit()
        dest.execute('VACUUM')
        if dest.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise HTTPException(500, 'Проверка копии не пройдена.')
    finally:
        if dest is not None:
            dest.close()
        source.close()
    if os.path.getsize(target) > MAX_BACKUP_BYTES:
        raise HTTPException(413, 'База слишком большая для отправки ботом.')


def register_owner_backup(app, path, token, get_user):
    lock = threading.Lock()
    last_attempt = float('-inf')

    @app.post('/api/owner/backup')
    def send_backup(x_init_data: str = Header(default='')):
        nonlocal last_attempt
        if not get_user(x_init_data).get("is_owner"):
            raise HTTPException(403,"Резервная копия доступна только владельцу")
        uid = verify_owner(x_init_data, token, path)
        if not lock.acquire(blocking=False):
            raise HTTPException(429, 'Копия уже создаётся.')
        try:
            now = time.monotonic()
            if now - last_attempt < 60:
                raise HTTPException(429, 'Повторите через минуту.')
            last_attempt = now
            filename = 'warehouse_backup_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '.db'
            with tempfile.TemporaryDirectory(prefix='warehouse_backup_') as directory:
                target = Path(directory) / filename
                make_backup(path, target)
                try:
                    with target.open('rb') as stream, httpx.Client(timeout=httpx.Timeout(60, connect=10)) as client:
                        response = client.post(
                            'https://api.telegram.org/bot' + token + '/sendDocument',
                            data={'chat_id': str(uid), 'caption': 'Резервная копия склада. Целостность SQLite проверена. Храните файл в безопасном месте.'},
                            files={'document': (filename, stream, 'application/octet-stream')},
                        )
                    if not response.is_success or response.json().get('ok') is not True:
                        raise HTTPException(502, 'Не удалось отправить файл. Откройте личный чат с ботом и нажмите /start.')
                except (httpx.HTTPError, ValueError, AttributeError):
                    raise HTTPException(502, 'Telegram не подтвердил отправку. Проверьте личный чат с ботом.') from None
            return {'status': 'ok', 'filename': filename}
        finally:
            lock.release()
