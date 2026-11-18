"""v18.5 Beta: Telegram-ID access control and local product illustrations."""
from pathlib import Path
from typing import Optional
import re
from fastapi import Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, StrictBool

BLOCKED = 'Доступ к приложению заблокирован владельцем.'


def deny_blocked(conn, uid, owner_id):
    if uid != owner_id and conn.execute('SELECT 1 FROM blocked_telegram WHERE tg_id=?', (uid,)).fetchone():
        raise HTTPException(403, BLOCKED)


class BlockRequest(BaseModel):
    blocked: StrictBool


def register_185(app, check_owner, session, transaction, audit, owner_id):
    directory = Path(__file__).resolve().parent
    assets = {'/release-v185.css': ('release_v185.css', 'text/css'),
              '/release-v185.js': ('release_v185.js', 'text/javascript'),
              '/catalog-v185.webp': ('catalog_v185.webp', 'image/webp'),
              '/catalog-dnp-v1851.webp': ('catalog_dnp_v1851.webp', 'image/webp'),
              '/catalog-dnp-black-v1852.webp': ('catalog_dnp_black_v1852.webp', 'image/webp')}
    for route, (filename, media) in assets.items():
        def endpoint(filename=filename, media=media):
            return FileResponse(directory / filename, media_type=media,
                                headers={'Cache-Control': 'public, max-age=86400' if media == 'image/webp' else 'no-cache'})
        app.add_api_route(route, endpoint, methods=['GET'], include_in_schema=False)

    @app.get('/api/v185/blocked')
    def list_blocked(x_init_data: Optional[str] = Header(None)):
        check_owner(x_init_data)
        with session() as conn:
            rows = conn.execute('SELECT b.tg_id,b.blocked_at,COALESCE(u.full_name,\'\') AS full_name,COALESCE(u.username,\'\') AS username FROM blocked_telegram b LEFT JOIN users u ON u.tg_id=b.tg_id ORDER BY b.blocked_at DESC,b.tg_id').fetchall()
            return [dict(row) for row in rows]

    @app.post('/api/v185/blocked/{tg_id}')
    def set_blocked(tg_id: str, req: BlockRequest, x_init_data: Optional[str] = Header(None)):
        actor = check_owner(x_init_data)
        if not re.fullmatch(r'[1-9][0-9]{0,15}', tg_id) or int(tg_id) >= 2**52:
            raise HTTPException(400, 'Укажите положительный числовой Telegram ID.')
        uid = int(tg_id)
        if uid == owner_id or uid == actor['tg_id']:
            raise HTTPException(403, 'Нельзя заблокировать владельца.')
        with transaction() as conn:
            if req.blocked:
                conn.execute('INSERT OR IGNORE INTO blocked_telegram(tg_id,blocked_by) VALUES(?,?)', (uid, actor['tg_id']))
                conn.execute('DELETE FROM web_sessions WHERE user_id=?', (uid,))
                conn.execute('DELETE FROM web_codes WHERE user_id=?', (uid,))
                conn.execute('DELETE FROM employee_preview WHERE user_id=?', (uid,))
            else:
                conn.execute('DELETE FROM blocked_telegram WHERE tg_id=?', (uid,))
            audit(conn, actor, 'Блокировка доступа' if req.blocked else 'Разблокировка доступа', uid)
        return {'tg_id': uid, 'blocked': req.blocked}
