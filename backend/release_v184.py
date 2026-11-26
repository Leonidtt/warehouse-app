"""Beta v18.4: read-only management view, scoped employee preview, thumbnails."""
import time
import re
from pathlib import Path
from typing import Optional
from fastapi import Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Literal
from collections import defaultdict


class PreviewRequest(BaseModel):
    role: Literal["admin", "boss", "employee"]


def effective_user(user, raw, digest, session):
    if user['role'] != 'admin' or not user.get('is_registered'):
        return user
    user = {**user, 'can_preview': True}
    with session() as conn:
        row = conn.execute('SELECT preview_role FROM employee_preview WHERE digest=? AND user_id=?', (digest(raw), user['tg_id'])).fetchone()
    if row and row[0] in ('employee', 'boss', 'simple'):
        preview_role = 'employee' if row[0] == 'simple' else row[0]
        return {**user, 'role': preview_role, 'is_owner': False, 'preview_role': preview_role}
    return user


def component_present(value):
    return str(value or '').strip().casefold() not in ('','-','—','нет','none','0','n/a','без','не указан')


def held_camera_count(row):
    category = str(row['category'] or '').strip().casefold()
    name = str(row['name'] or '').strip().casefold()
    return int(component_present(row['kit_body']) or category in ('фотоаппараты','фотокомплекты','камеры')
               or re.match(r'^(фотоаппарат|камера)(?:\s|$)',name) is not None)


def active_checkout_rows(conn):
    return conn.execute("""SELECT c.item_code,c.id,c.user_id,u.full_name,c.taken_at,c.taken_for,
        c.giver_id,g.full_name AS giver_name FROM checkouts c
        LEFT JOIN users u ON u.tg_id=c.user_id LEFT JOIN users g ON g.tg_id=c.giver_id
        WHERE c.returned_at IS NULL""")


def held_laptop_count(row):
    category = str(row['category'] or '').strip().casefold()
    name = str(row['name'] or '').strip().casefold()
    return int(bool(re.search(r'ноутбук|л[эе]птоп|макбук|macbook|laptop', category)
                    or re.match(r'^(ноутбук|л[эе]птоп|макбук|macbook|apple macbook|thinkpad|lenovo thinkpad|dell latitude)(?:\s|$)', name)))


def component_counts(row):
    body, flash = int(component_present(row['kit_body'])), int(component_present(row['kit_flash']))
    cat = str(row['category'] or '').strip().casefold()
    name = str(row['name'] or '').strip().casefold()
    if not body and (cat in ('фотоаппараты','фотокомплекты','камеры') or re.match(r'^(фотоаппарат|камера)\b',name)):
        body = 1
    if not flash and (cat in ('вспышки','фотовспышки') or re.match(r'^(вспышка|фотовспышка)\b',name)):
        flash = 1
    return body, flash


def buyout_name(value):
    return str(value or '').strip()


def boss_buyouts(rows):
    groups = {}
    for row in rows:
        if row['kind'] != 'equipment':
            continue
        name = buyout_name(row.get('buyout_status'))
        if not name:
            continue
        cam, flash = component_counts(row)
        group = groups.setdefault(name.casefold(), {'name': name, 'items': []})
        group['items'].append({'code': row['code'], 'name': row['name'],
            'camera': row['kit_body'], 'flash': row['kit_flash'], 'lens': row.get('kit_lens',''),
            'camera_count': cam, 'flash_count': flash,
            'holders': [h.get('taken_for') or h.get('full_name') or 'Не указан' for h in row['holders']]})
    return sorted(groups.values(), key=lambda g: g['name'].casefold())


def boss_rentals(conn):
    # SQLite checkout timestamps are UTC; business calendar is Moscow.
    rows = conn.execute("""
        SELECT c.id, c.item_code AS code, i.name, i.kind, i.category, i.kit_body,
               i.kit_flash, i.kit_lens, i.is_archived, c.taken_for,
               COALESCE(g.full_name, '') AS giver, c.taken_at, c.returned_at,
               date(c.taken_at, '+3 hours') AS day
        FROM checkouts c JOIN items i ON i.code=c.item_code
        LEFT JOIN users g ON g.tg_id=c.giver_id
        WHERE i.kind='equipment' AND trim(COALESCE(i.buyout_status,''))=''
          AND trim(COALESCE(c.taken_for,''))<>''
          AND date(c.taken_at, '+3 hours') >= date('now','+3 hours','-89 days')
        ORDER BY c.taken_at DESC, c.id DESC
    """).fetchall()
    groups = {}
    for raw in rows:
        row = dict(raw)
        cam, flash = component_counts(row)
        if not cam and not flash:
            continue
        name = row['taken_for'].strip()
        key = (row['day'], name.casefold())
        group = groups.setdefault(key, {'name':name, 'day':row['day'], 'items':[]})
        group['items'].append({'code':row['code'], 'name':row['name'], 'camera':row['kit_body'],
            'flash':row['kit_flash'], 'lens':row['kit_lens'], 'camera_count':cam, 'flash_count':flash,
            'giver':row['giver'], 'taken_at':row['taken_at'], 'returned_at':row['returned_at'],
            'archived':bool(row['is_archived'])})
    return {'today':conn.execute("SELECT date('now','+3 hours')").fetchone()[0],
            'groups':list(groups.values())}


def register_184(app, get_user, real_user, session, transaction, digest, list_items):
    directory = Path(__file__).resolve().parent
    for name, media in [('js','text/javascript'),('css','text/css')]:
        def asset(name=name, media=media):
            return FileResponse(directory / ('release_v184.'+name), media_type=media, headers={'Cache-Control':'no-cache'})
        app.add_api_route('/release-v184.'+name,asset,methods=['GET'],include_in_schema=False)

    def preview_admin(raw):
        user = real_user(raw)
        if user['role'] != 'admin' or not user.get('is_registered'):
            raise HTTPException(403, 'Доступ только администраторам')
        return user

    def change_preview(raw, role):
        user = preview_admin(raw)
        with transaction() as conn:
            # Recheck the actual database role in the write transaction.
            actual = conn.execute('SELECT role, is_registered FROM users WHERE tg_id=?', (user['tg_id'],)).fetchone()
            if not actual or actual[0] != 'admin' or not actual[1]:
                raise HTTPException(403, 'Доступ только администраторам')
            if role == 'admin':
                conn.execute('DELETE FROM employee_preview WHERE digest=? AND user_id=?', (digest(raw), user['tg_id']))
            else:
                # Existing authorization expiry still applies; no preview countdown.
                conn.execute('INSERT INTO employee_preview(digest,user_id,expires,preview_role) VALUES(?,?,0,?) ON CONFLICT(digest) DO UPDATE SET user_id=excluded.user_id,expires=0,preview_role=excluded.preview_role', (digest(raw),user['tg_id'],role))
        return {'role': role, 'preview_role': role if role != 'admin' else None}

    @app.post('/api/v184/preview/role')
    def set_preview(req: PreviewRequest, x_init_data: Optional[str]=Header(None)):
        return change_preview(x_init_data, req.role)

    @app.post('/api/v184/preview/start')
    def start(x_init_data: Optional[str]=Header(None)):
        return change_preview(x_init_data, 'employee')

    @app.post('/api/v184/preview/stop')
    def stop(x_init_data: Optional[str]=Header(None)):
        return change_preview(x_init_data, 'admin')

    @app.get('/api/v184/boss')
    def boss(x_init_data: Optional[str]=Header(None)):
        user=get_user(x_init_data)
        if user['role'] not in ('admin','boss') or not user['is_registered']:
            raise HTTPException(403,'Сводка доступна руководителю')
        # In office = all physical storage rooms; checkout quantities are separate.
        rows=list_items(x_init_data)
        office={'cameras':0,'flashes':0,'standalone_flashes':0}; held={'cameras':0,'flashes':0,'standalone_flashes':0,'laptops':0}; people={}; rooms={}
        for row in rows:
            if row['kind']!='equipment':continue
            cam,flash=component_counts(row)
            laptop=held_laptop_count(row)
            if laptop:cam,flash=0,0
            if not (cam or flash or laptop):continue
            for s in row['stocks'] if cam or flash else ():
                q=s['quantity']; office['cameras']+=cam*q;office['flashes']+=flash*q;office['standalone_flashes']+=(flash if not cam else 0)*q
                r=rooms.setdefault(s['location_id'],{'name':s['location_name'],'cameras':0,'flashes':0});r['cameras']+=cam*q;r['flashes']+=flash*q
            for h in row['holders']:
                held['laptops']+=laptop
                held['cameras']+=cam;held['flashes']+=flash;held['standalone_flashes']+=flash if not cam else 0
                name=h.get('taken_for') or h.get('full_name') or 'Не указан'
                key=(h['user_id'],name)
                p=people.setdefault(key,{'name':name,'cameras':0,'flashes':0,'items':[]})
                p['person_id']=h['user_id']; p['cameras']+=cam; p['flashes']+=flash
                p['items'].append({'code':row['code'],'name':row['name'],'camera':row['kit_body'],'flash':row['kit_flash'],'lens':row.get('kit_lens',''),'camera_count':cam,'flash_count':flash,'laptop_count':laptop,'buyout_status':row.get('buyout_status',''),'taken_at':h.get('taken_at','')})
        return {'office':office,'held':held,'people':sorted(people.values(),key=lambda p:p['name'].casefold()),'rooms':sorted(rooms.values(),key=lambda r:r['name'].casefold()),'buyouts':boss_buyouts(rows)}

    @app.get('/api/v1855/boss/rentals')
    def rentals(x_init_data: Optional[str]=Header(None)):
        user=get_user(x_init_data)
        if user['role'] not in ('admin','boss') or not user['is_registered']:
            raise HTTPException(403,'Сводка доступна руководителю')
        with session() as conn:
            return boss_rentals(conn)
