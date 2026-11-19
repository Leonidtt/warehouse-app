"""Beta-only linked physical kit components. All stock stays in existing tables."""
from pathlib import Path
from fastapi import Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Literal, Optional

PARTS = (('body', 'Фотоаппарат', 'Фотоаппараты', 'CAM'),
         ('lens', 'Объектив', 'Объективы', 'LENS'),
         ('flash', 'Вспышка', 'Вспышки', 'FLASH'))


def init_kits(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS physical_kit_parts (
        code TEXT PRIMARY KEY, kit_code TEXT NOT NULL, kit_name TEXT NOT NULL,
        part TEXT NOT NULL CHECK(part IN ('body','lens','flash')),
        UNIQUE(kit_code,part))''')


def present(value):
    return str(value or '').strip().casefold() not in ('','-','—','нет','none','0','n/a','без','не указан','не указана')


def split_reason(conn, item):
    code = item['code']
    if item['kind'] != 'equipment' or not present(item['kit_body']) or not any(present(item['kit_'+p]) for p in ('lens','flash')):
        return 'Нужен фотокомплект с камерой и объективом или вспышкой'
    if conn.execute('SELECT 1 FROM physical_kit_parts WHERE code=? OR kit_code=?',(code,code)).fetchone():
        return 'Комплект уже разделён'
    if item['needs_repair'] or conn.execute('SELECT 1 FROM repair_records WHERE code=? AND finished_at IS NULL',(code,)).fetchone():
        return 'Сначала завершите ремонт'
    if conn.execute('SELECT 1 FROM checkouts WHERE item_code=? AND returned_at IS NULL',(code,)).fetchone():
        return 'Сначала верните комплект'
    if conn.execute("SELECT 1 FROM bookings WHERE item_code=? AND date_to>=date('now')",(code,)).fetchone():
        return 'Сначала завершите или отмените действующие брони'
    stocks = conn.execute('SELECT location_id,quantity FROM stock WHERE item_code=? AND quantity>0',(code,)).fetchall()
    if len(stocks)!=1 or stocks[0]['quantity']!=1:
        return 'На складе должен быть ровно один комплект'
    return ''


def split_kit(conn, item):
    reason = split_reason(conn,item)
    if reason: raise HTTPException(409,reason)
    code, title = item['code'], item['name']
    location = conn.execute('SELECT location_id FROM stock WHERE item_code=? AND quantity>0',(code,)).fetchone()[0]
    values = {p:float(item['price_'+p] or 0) for p in ('body','lens','flash','acc','add')}
    parts_total = sum(values.values())
    total = parts_total if parts_total>0 else float(item['price'] or 0)
    child_prices = {p:values[p] for p in ('lens','flash') if present(item['kit_'+p])}
    camera_total = total-sum(child_prices.values())
    # The previous parent code and all its historical records remain on the camera.
    # Accessories, unallocated costs and original serial number stay with the camera.
    conn.execute('''UPDATE items SET name=?,category=?,kit_lens='',kit_flash='',
        price=?,price_body=?,price_lens=0,price_flash=0 WHERE code=?''',
        ((title+' · Фотоаппарат')[:250],'Фотоаппараты',camera_total,
         camera_total-values['acc']-values['add'],code))
    conn.execute('INSERT INTO physical_kit_parts VALUES(?,?,?,?)',(code,code,title,'body'))
    conn.execute('INSERT OR IGNORE INTO categories(name) VALUES(?)',('Фотоаппараты',))
    for part,label,category,suffix in PARTS[1:]:
        if not present(item['kit_'+part]): continue
        child = code+'-'+suffix; n=2
        while conn.execute('SELECT 1 FROM items WHERE code=?',(child,)).fetchone():
            child=code+'-'+suffix+'-'+str(n); n+=1
        model=str(item['kit_'+part]).strip()
        lens=model if part=='lens' else ''; flash=model if part=='flash' else ''
        price=child_prices[part]
        conn.execute('''INSERT INTO items(code,name,kind,category,price,kit_lens,kit_flash,
            price_lens,price_flash,budget_tag,buyout_status) VALUES(?,?,'equipment',?,?,?,?,?,?,?,?)''',
            (child,(title+' · '+label+' '+model)[:250],category,price,lens,flash,
             price if part=='lens' else 0,price if part=='flash' else 0,item['budget_tag'],item['buyout_status']))
        conn.execute('INSERT INTO stock(item_code,location_id,quantity) VALUES(?,?,1)',(child,location))
        conn.execute('INSERT INTO physical_kit_parts VALUES(?,?,?,?)',(child,code,title,part))
        conn.execute('INSERT OR IGNORE INTO categories(name) VALUES(?)',(category,))
    return code


def kit_info(conn, code):
    link=conn.execute('SELECT * FROM physical_kit_parts WHERE code=?',(code,)).fetchone()
    if not link: return None
    rows=conn.execute('''SELECT k.code,k.part,i.name,i.is_archived,i.needs_repair,
        i.kit_body,i.kit_lens,i.kit_flash FROM physical_kit_parts k
        LEFT JOIN items i ON i.code=k.code WHERE k.kit_code=?
        ORDER BY CASE k.part WHEN 'body' THEN 0 WHEN 'lens' THEN 1 ELSE 2 END''',(link['kit_code'],)).fetchall()
    parts=[]
    for r in rows:
        h=conn.execute('''SELECT c.id,c.user_id,c.taken_for,c.location_id,u.full_name
            FROM checkouts c LEFT JOIN users u ON u.tg_id=c.user_id
            WHERE c.item_code=? AND c.returned_at IS NULL''',(r['code'],)).fetchall()
        stock=conn.execute('''SELECT s.location_id,l.name,s.quantity FROM stock s JOIN locations l ON l.id=s.location_id
            WHERE s.item_code=? AND s.quantity>0''',(r['code'],)).fetchall()
        parts.append({'code':r['code'],'part':r['part'],'name':r['name'] or r['code'],
            'model':r['kit_'+r['part']] or '', 'archived':r['is_archived']!=0,
            'repair':bool(r['needs_repair']), 'holders':[dict(x) for x in h],
            'stocks':[dict(x) for x in stock]})
    complete=bool(parts) and all(not p['archived'] for p in parts)
    free=complete and all(not p['repair'] and not p['holders'] and sum(x['quantity'] for x in p['stocks'])==1 for p in parts)
    held=complete and all(len(p['holders'])==1 for p in parts)
    same=held and len({p['holders'][0]['user_id'] for p in parts})==1
    return {'kit_code':link['kit_code'],'kit_name':link['kit_name'],'parts':parts,
            'can_take':free,'can_return':same}


class KitAction(BaseModel):
    action: Literal['take','return']
    taken_for: str = ''


def apply_kit(conn, user, code, req, checkout_one):
    info=kit_info(conn,code)
    if not info: raise HTTPException(404,'Комплект не найден')
    if req.action=='take':
        if not info['can_take']: raise HTTPException(409,'Не все компоненты свободны')
        for p in info['parts']: checkout_one(conn,user,p['code'],req.taken_for)
    else:
        if not info['can_return']: raise HTTPException(409,'Компоненты выданы не одному получателю; верните отдельно')
        for p in info['parts']:
            h=p['holders'][0]
            conn.execute('UPDATE checkouts SET returned_at=CURRENT_TIMESTAMP,returned_by=? WHERE id=?',(user['tg_id'],h['id']))
            conn.execute('INSERT INTO stock(item_code,location_id,quantity) VALUES(?,?,1) ON CONFLICT(item_code,location_id) DO UPDATE SET quantity=quantity+1',(p['code'],h['location_id']))
    return len(info['parts'])


def register_186(app,get_user,check_admin,transaction,session,active_item,audit,checkout_one):
    @app.get('/release-v186.js',include_in_schema=False)
    def asset():
        return FileResponse(Path(__file__).resolve().parent/'release_v186.js',media_type='text/javascript',headers={'Cache-Control':'no-cache'})

    @app.get('/api/v186/kits/{code}')
    def details(code:str,x_init_data:Optional[str]=Header(None)):
        user=get_user(x_init_data)
        if not user['is_registered']: raise HTTPException(403,'Сначала зарегистрируйтесь')
        with session() as conn:
            item=active_item(conn,code)
            info=kit_info(conn,code)
            if info: return info
            candidate=item['kind']=='equipment' and present(item['kit_body']) and any(present(item['kit_'+p]) for p in ('lens','flash'))
            return {'candidate':candidate,'split_reason':split_reason(conn,item) if candidate and user['role']=='admin' else ''}

    @app.post('/api/v186/kits/{code}/split')
    def split(code:str,x_init_data:Optional[str]=Header(None)):
        user=check_admin(x_init_data)
        if not user['is_registered']: raise HTTPException(403,'Сначала зарегистрируйтесь')
        with transaction() as conn:
            split_kit(conn,active_item(conn,code)); audit(conn,user,'Разделение фотокомплекта',code)
            return kit_info(conn,code)

    @app.post('/api/v186/kits/{code}/action')
    def action(code:str,req:KitAction,x_init_data:Optional[str]=Header(None)):
        user=get_user(x_init_data)
        if not user['is_registered'] or user['role'] not in ('admin','employee'):
            raise HTTPException(403,'Доступ только сотрудникам и администраторам')
        with transaction() as conn:
            count=apply_kit(conn,user,code,req,checkout_one)
            audit(conn,user,'Выдача комплекта' if req.action=='take' else 'Возврат комплекта',code)
        return {'count':count}
