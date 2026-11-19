"""Additions for Warehouse v18 shared tools."""
import io
import json
import os
import re
import time
from pathlib import Path
from importlib.util import find_spec
from typing import Optional
from fastapi import Header, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from PIL import ImageFont
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


def label_font(size):
    candidates = [os.environ.get('LABEL_FONT_PATH'), 'DejaVuSans-Bold.ttf',
                  '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf']
    spec = find_spec('matplotlib')
    if spec and spec.origin:
        candidates.append(str(Path(spec.origin).parent / 'mpl-data' / 'fonts' / 'ttf' / 'DejaVuSans-Bold.ttf'))
    for path in filter(None, candidates):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    raise HTTPException(503, 'Шрифт этикеток не установлен. Проверьте сборку приложения.')


def label_dimensions(width_mm, height_mm):
    if not 30 <= width_mm <= 100 or not 40 <= height_mm <= 150:
        raise HTTPException(400, 'Ширина 30–100 мм, высота 40–150 мм')


class BulkEdit(BaseModel):
    codes: list[str] = Field(min_length=1, max_length=200)
    category: Optional[str] = None
    supplier: Optional[str] = None
    unit: Optional[str] = None


class KitCheckout(BaseModel):
    codes: list[str] = Field(min_length=1, max_length=50)


class Profile(BaseModel):
    favorites: list[str] = Field(default_factory=list, max_length=300)
    recent: list[str] = Field(default_factory=list, max_length=30)
    kits: dict[str, list[str]] = Field(default_factory=dict)
    templates: dict[str, dict[str, str]] = Field(default_factory=dict)


def spreadsheet(rows, headers, filename):
    wb = Workbook(); ws = wb.active; ws.title = 'Склад'
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF'); cell.fill = PatternFill('solid', fgColor='275D93')
    for row in rows:
        ws.append([v if not isinstance(v, str) or not v.lstrip().startswith(('=', '+', '-', '@')) else "'" + v for v in row])
    ws.freeze_panes = 'A2'; ws.auto_filter.ref = ws.dimensions
    for col in ws.columns:
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(60, max(12, max(len(str(c.value or '')) for c in col)+2))
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename={filename}', 'Cache-Control': 'no-store'})


def register_v18(app, get_user, check_admin, transaction, active_item, audit, web_digest, web_cookie, checkout_one, get_history):
    with transaction() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS v18_profiles (user_id INTEGER PRIMARY KEY, data TEXT NOT NULL)')
    directory = Path(__file__).resolve().parent

    @app.get('/warehouse-v18.css', include_in_schema=False)
    def v18_css():
        return FileResponse(directory / 'warehouse_v18.css', media_type='text/css', headers={'Cache-Control':'no-cache'})

    @app.get('/warehouse-v18.js', include_in_schema=False)
    def v18_js():
        return FileResponse(directory / 'warehouse_v18.js', media_type='text/javascript', headers={'Cache-Control':'no-cache'})

    @app.get('/api/v18/profile')
    def profile_get(x_init_data: Optional[str] = Header(None)):
        user = get_user(x_init_data)
        with transaction() as conn:
            row = conn.execute('SELECT data FROM v18_profiles WHERE user_id=?', (user['tg_id'],)).fetchone()
        profile = json.loads(row[0]) if row else Profile().model_dump()
        if user['role'] != 'admin':
            profile['templates'] = {}
        return profile

    @app.put('/api/v18/profile')
    def profile_save(req: Profile, x_init_data: Optional[str] = Header(None)):
        user = get_user(x_init_data)
        if len(req.kits)>40 or len(req.templates)>40 or any(len(k)>100 or len(v)>50 for k,v in req.kits.items()) or any(len(k)>100 or len(v)>40 for k,v in req.templates.items()):
            raise HTTPException(400,'Слишком много шаблонов или комплектов')
        with transaction() as conn:
            if user['role'] != 'admin':
                existing = conn.execute('SELECT data FROM v18_profiles WHERE user_id=?', (user['tg_id'],)).fetchone()
                req.templates = json.loads(existing[0]).get('templates', {}) if existing else {}
            data = req.model_dump_json()
            if len(data)>120000: raise HTTPException(400,'Слишком большой профиль')
            conn.execute('INSERT INTO v18_profiles VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data', (user['tg_id'],data))
        return {'status':'ok'}

    @app.post('/api/v18/bulk-edit')
    def bulk_edit(req: BulkEdit, x_init_data: Optional[str] = Header(None)):
        actor = check_admin(x_init_data)
        fields = {k:v.strip() for k,v in {'category':req.category,'supplier':req.supplier,'unit':req.unit}.items() if v is not None}
        if not fields or any(len(v)>250 for v in fields.values()) or ('unit' in fields and not fields['unit']):
            raise HTTPException(400,'Проверьте поля')
        codes=list(dict.fromkeys(req.codes))
        with transaction() as conn:
            for code in codes: active_item(conn,code)
            if fields.get('category'): conn.execute('INSERT OR IGNORE INTO categories(name) VALUES(?)',(fields['category'],))
            for code in codes:
                if 'category' in fields: conn.execute('UPDATE items SET category=? WHERE code=?',(fields['category'],code))
                for key in ('supplier','unit'):
                    if key in fields:
                        conn.execute('INSERT OR IGNORE INTO item_metadata(code) VALUES(?)',(code,))
                        conn.execute(f'UPDATE item_metadata SET {key}=? WHERE code=?',(fields[key],code))
            audit(conn,actor,'Массовое редактирование',', '.join(codes))
        return {'updated':len(codes)}

    @app.post('/api/v18/checkout-kit')
    def checkout_kit(req: KitCheckout, x_init_data: Optional[str] = Header(None)):
        user=get_user(x_init_data); codes=list(dict.fromkeys(req.codes))
        with transaction() as conn:
            for code in codes: checkout_one(conn,user,code,'')
            audit(conn,user,'Выдача комплекта',', '.join(codes))
        return {'success_count':len(codes)}

    @app.get('/api/v18/usage')
    def usage(x_init_data: Optional[str] = Header(None)):
        check_admin(x_init_data)
        with transaction() as conn:
            rows=conn.execute('''SELECT i.code,i.name,COUNT(c.id) AS checkouts,MAX(c.taken_at) AS last_checkout
                FROM items i LEFT JOIN checkouts c ON c.item_code=i.code
                WHERE i.is_archived=0 AND i.kind='equipment' GROUP BY i.code,i.name ORDER BY checkouts DESC,i.name''').fetchall()
            return [dict(r) for r in rows]

    @app.get('/api/v18/sessions')
    def sessions(request: Request, x_init_data: Optional[str] = Header(None)):
        user=get_user(x_init_data); current=web_digest(request.cookies.get(web_cookie)) if request.cookies.get(web_cookie) else ''
        with transaction() as conn:
            rows=conn.execute('SELECT digest,expires FROM web_sessions WHERE user_id=? AND expires>? ORDER BY expires DESC',(user['tg_id'],int(time.time()))).fetchall()
        return [{'id':r['digest'][:24],'expires':r['expires'],'current':r['digest']==current} for r in rows]

    @app.delete('/api/v18/sessions/{session_id}')
    def revoke_session(session_id:str,x_init_data: Optional[str] = Header(None)):
        user=get_user(x_init_data)
        if not re.fullmatch(r'[0-9a-f]{24}',session_id): raise HTTPException(400,'Неверный сеанс')
        with transaction() as conn:
            conn.execute('DELETE FROM web_sessions WHERE user_id=? AND substr(digest,1,24)=?',(user['tg_id'],session_id))
        return {'status':'ok'}

    @app.get('/api/v18/stock.xlsx')
    def stock_xlsx(x_init_data: Optional[str] = Header(None)):
        check_admin(x_init_data)
        with transaction() as conn:
            rows=conn.execute('''SELECT i.code,i.name,i.kind,i.category,l.name,s.quantity,i.price FROM stock s
                JOIN items i ON i.code=s.item_code JOIN locations l ON l.id=s.location_id
                WHERE s.quantity>0 AND i.is_archived=0 ORDER BY l.name,i.name''').fetchall()
        return spreadsheet(rows,['Код','Название','Тип','Категория','Помещение','Количество','Цена за единицу'],'stock.xlsx')

    @app.get('/api/v18/history.xlsx')
    def history_xlsx(x_init_data: Optional[str] = Header(None)):
        check_admin(x_init_data)
        rows=get_history(x_init_data)
        return spreadsheet(([r[k] for k in ('date','type','item_code','name','quantity','user_name','taken_for')] for r in rows),['Дата','Действие','Код','Название','Количество','Сотрудник','Кому'],'history.xlsx')
