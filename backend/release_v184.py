"""Beta v18.4: read-only management view, scoped employee preview, thumbnails."""
import time
import re
from pathlib import Path
from typing import Optional
from fastapi import Header, HTTPException
from fastapi.responses import FileResponse
from collections import defaultdict


def effective_user(user, raw, digest, session):
    if user['role'] != 'admin':
        return user
    with session() as conn:
        row = conn.execute('SELECT expires FROM employee_preview WHERE digest=? AND user_id=?', (digest(raw), user['tg_id'])).fetchone()
    now = int(time.time())
    if row and row[0] > now:
        return {**user, 'role':'employee', 'is_owner':False, 'preview_until':row[0]}
    return user


def component_counts(row):
    def present(v):
        return str(v or '').strip().casefold() not in ('','-','—','нет','none','0','n/a','без','не указан')
    body, flash = int(present(row['kit_body'])), int(present(row['kit_flash']))
    cat = str(row['category'] or '').strip().casefold()
    name = str(row['name'] or '').strip().casefold()
    if not body and (cat in ('фотоаппараты','камеры') or re.match(r'^(фотоаппарат|камера)\b',name)):
        body = 1
    if not flash and (cat in ('вспышки','фотовспышки') or re.match(r'^(вспышка|фотовспышка)\b',name)):
        flash = 1
    return body, flash


def register_184(app, get_user, real_user, session, transaction, digest, list_items):
    directory = Path(__file__).resolve().parent
    for name, media in [('js','text/javascript'),('css','text/css')]:
        def asset(name=name, media=media):
            return FileResponse(directory / ('release_v184.'+name), media_type=media, headers={'Cache-Control':'no-cache'})
        app.add_api_route('/release-v184.'+name,asset,methods=['GET'],include_in_schema=False)

    @app.post('/api/v184/preview/start')
    def start(x_init_data: Optional[str]=Header(None)):
        user=real_user(x_init_data)
        if user['role']!='admin' or not user['is_registered']:
            raise HTTPException(403,'Доступ только администраторам')
        now=int(time.time())
        with transaction() as conn:
            conn.execute('DELETE FROM employee_preview WHERE expires<=?',(now,))
            conn.execute('INSERT INTO employee_preview(digest,user_id,expires) VALUES(?,?,?) ON CONFLICT(digest) DO UPDATE SET user_id=excluded.user_id,expires=excluded.expires',(digest(x_init_data),user['tg_id'],now+180))
        return {'preview_until':now+180}

    @app.post('/api/v184/preview/stop')
    def stop(x_init_data: Optional[str]=Header(None)):
        user=real_user(x_init_data)
        with transaction() as conn:
            conn.execute('DELETE FROM employee_preview WHERE digest=? AND user_id=?',(digest(x_init_data),user['tg_id']))
        return {'status':'ok'}

    @app.get('/api/v184/boss')
    def boss(x_init_data: Optional[str]=Header(None)):
        user=get_user(x_init_data)
        if user['role'] not in ('admin','boss') or not user['is_registered']:
            raise HTTPException(403,'Сводка доступна руководителю')
        # In office = all physical storage rooms; checkout quantities are separate.
        rows=list_items(x_init_data)
        office={'cameras':0,'flashes':0}; held={'cameras':0,'flashes':0}; people={}; rooms={}
        for row in rows:
            if row['kind']!='equipment':continue
            cam,flash=component_counts(row)
            if not cam and not flash:continue
            for s in row['stocks']:
                q=s['quantity']; office['cameras']+=cam*q;office['flashes']+=flash*q
                r=rooms.setdefault(s['location_id'],{'name':s['location_name'],'cameras':0,'flashes':0});r['cameras']+=cam*q;r['flashes']+=flash*q
            for h in row['holders']:
                held['cameras']+=cam;held['flashes']+=flash
                name=h.get('taken_for') or h.get('full_name') or 'Не указан'
                key=(h['user_id'],name)
                p=people.setdefault(key,{'name':name,'cameras':0,'flashes':0,'items':[]})
                p['cameras']+=cam;p['flashes']+=flash;p['items'].append({'code':row['code'],'name':row['name'],'camera':row['kit_body'],'flash':row['kit_flash']})
        return {'office':office,'held':held,'people':sorted(people.values(),key=lambda p:p['name'].casefold()),'rooms':sorted(rooms.values(),key=lambda r:r['name'].casefold())}
