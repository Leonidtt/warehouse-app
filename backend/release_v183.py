"""v18.3: atomic batch actions; existing endpoints remain compatible."""
import io
import math
import re
from typing import Literal, Optional
from pathlib import Path
from fastapi import BackgroundTasks, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from warehouse_v18 import label_dimensions
from release_v182 import label_image
from flash_lifecycle import standalone_flash,flash_budget,flash_number,update_flash_identity,archive_flash_code


class BatchAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    codes: list[str] = Field(min_length=1, max_length=200)
    action: Literal['move','category','price','name','supplier','tag','repair','copy','stock','archive','delete','unit']
    value: str = Field(default='', max_length=3000)
    location: Optional[int] = None
    source: Optional[int] = None
    quantity: Optional[int] = Field(default=None, ge=0, le=1000000)
    confirmed: bool = False


class ConsumableReturn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    location_id: int
    quantity: int = Field(strict=True, gt=0, le=1000000)


class BatchLabels(BaseModel):
    model_config = ConfigDict(extra='forbid')
    codes: list[str] = Field(min_length=1, max_length=200)
    dpi: Literal[203,300] = 203
    width_mm: int = 50
    height_mm: int = 80


def register_183(app, get_user, check_admin, transaction, active_item, valid_location, move_one, audit, notify):
    folder = Path(__file__).resolve().parent

    @app.get('/release-v183.css', include_in_schema=False)
    def css183():
        return FileResponse(folder / 'release_v183.css', media_type='text/css', headers={'Cache-Control':'no-cache'})

    @app.get('/release-v183.js', include_in_schema=False)
    def js183():
        return FileResponse(folder / 'release_v183.js', media_type='text/javascript', headers={'Cache-Control':'no-cache'})

    @app.post('/api/items/{code}/return-consumable')
    def return_consumable(code: str, req: ConsumableReturn, x_init_data: Optional[str] = Header(None)):
        actor = get_user(x_init_data)
        if not actor.get('is_registered') or actor['role'] not in ('admin','employee','boss'):
            raise HTTPException(403,'Доступ только зарегистрированным сотрудникам')
        with transaction() as conn:
            item = active_item(conn,code)
            if item['kind'] != 'consumable':
                raise HTTPException(400,'Операция только для расходников')
            valid_location(conn,req.location_id)
            conn.execute('INSERT INTO stock(item_code,location_id,quantity) VALUES(?,?,?) ON CONFLICT(item_code,location_id) DO UPDATE SET quantity=quantity+excluded.quantity',(code,req.location_id,req.quantity))
            conn.execute('INSERT INTO consumable_returns(item_code,location_id,quantity,user_id) VALUES(?,?,?,?)',(code,req.location_id,req.quantity,actor['tg_id']))
            audit(conn,actor,f'Возврат расходника: +{req.quantity}; помещение {req.location_id}',code)
        return {'status':'ok'}

    @app.post('/api/v18/batch-action')
    def batch(req: BatchAction, background_tasks: BackgroundTasks, x_init_data: Optional[str] = Header(None)):
        actor = check_admin(x_init_data)
        if not actor.get('is_registered'): raise HTTPException(403,'Завершите регистрацию')
        if not req.confirmed:
            raise HTTPException(400,'Подтвердите операцию')
        if req.action == 'delete' and not actor.get('is_owner'):
            raise HTTPException(403,'Удаление доступно только владельцу')
        codes = list(dict.fromkeys(req.codes))
        action, value = req.action, req.value.strip()
        if action in ('name','unit','repair') and not value:
            raise HTTPException(400,'Заполните поле')
        if action in ('name','category','supplier','unit','tag') and len(value)>250:
            raise HTTPException(400,'Не более 250 символов')
        if action == 'tag' and value not in ('','КЦ','ТХ'):
            raise HTTPException(400,'Выберите метку')
        if action == 'price':
            try: price=float(value.replace(',','.'))
            except ValueError: raise HTTPException(400,'Некорректная цена') from None
            if not math.isfinite(price) or not 0 <= price <= 1e12:
                raise HTTPException(400,'Некорректная цена')
        changes, notices = [], []
        with transaction() as conn:
            items = [active_item(conn,code) for code in codes]
            if action in ('move','copy','stock'):
                if req.location is None: raise HTTPException(400,'Выберите помещение')
                valid_location(conn,req.location)
            if action == 'move':
                if req.source is None or req.source == req.location: raise HTTPException(400,'Выберите разные помещения')
                valid_location(conn,req.source)
            if action == 'stock' and req.quantity is None: raise HTTPException(400,'Укажите количество')
            if action == 'category' and value:
                conn.execute('INSERT OR IGNORE INTO categories(name) VALUES(?)',(value,))
            for item in items:
                code = item['code']; kind=item['kind']
                flash=standalone_flash(item['category'],item['name'],kind)
                if flash:
                    if action=='name':
                        raise HTTPException(409,f'{code}: название вспышки — её номер')
                    if action=='category' and value.strip().casefold()!='вспышки':
                        raise HTTPException(409,f'{code}: категорию вспышки менять нельзя')
                    if action=='tag' and value not in ('КЦ','ТХ'):
                        raise HTTPException(409,f'{code}: укажите бюджет КЦ или ТХ')
                held = conn.execute('SELECT 1 FROM checkouts WHERE item_code=? AND returned_at IS NULL',(code,)).fetchone()
                total = conn.execute('SELECT COALESCE(SUM(quantity),0) FROM stock WHERE item_code=?',(code,)).fetchone()[0]
                booked = conn.execute("SELECT 1 FROM bookings WHERE item_code=? AND date_to>=date('now')",(code,)).fetchone()
                repairing = conn.execute('SELECT 1 FROM repair_records WHERE code=? AND finished_at IS NULL',(code,)).fetchone()
                if action == 'move':
                    row=conn.execute('SELECT quantity FROM stock WHERE item_code=? AND location_id=?',(code,req.source)).fetchone()
                    if not row or row[0]<=0: raise HTTPException(409,f'{code}: нет остатка в исходном помещении')
                    move_one(conn,actor,code,req.source,req.location,row[0])
                elif action in ('name','category','tag'):
                    if action=='tag' and kind!='equipment': raise HTTPException(400,'Метки только для оборудования')
                    if action=='tag' and flash:
                        code,flash_name=update_flash_identity(conn,item,flash_budget(value),"bulk-budget-change")
                        conn.execute("UPDATE items SET budget_tag=?,name=? WHERE code=?",(value,flash_name,code))
                    else:
                        column={'name':'name','category':'category','tag':'budget_tag'}[action]
                        conn.execute(f'UPDATE items SET {column}=? WHERE code=?',(value,code))
                elif action == 'price':
                    # Preserve component prices; the bulk price is the existing standalone price.
                    if kind=='equipment' and any(item[k] for k in ('price_body','price_lens','price_flash','price_acc','price_add')):
                        raise HTTPException(409,f'{code}: стоимость комплекта определяется ценами деталей. Измените их в карточке.')
                    conn.execute('UPDATE items SET price=? WHERE code=?',(price,code))
                elif action in ('supplier','unit'):
                    if action=='unit' and kind!='consumable': raise HTTPException(400,'Единицы измерения только для расходников')
                    conn.execute('INSERT OR IGNORE INTO item_metadata(code) VALUES(?)',(code,))
                    conn.execute(f'UPDATE item_metadata SET {action}=? WHERE code=?',(value,code))
                elif action == 'repair':
                    if kind!='equipment' or repairing or item['needs_repair'] or held:
                        raise HTTPException(409,f'{code}: расходник, уже в ремонте или на руках')
                    conn.execute('INSERT INTO repair_records(code,description,cost,user_id) VALUES(?,?,0,?)',(code,value,actor['tg_id']))
                    conn.execute('UPDATE items SET needs_repair=1 WHERE code=?',(code,))
                    notices.append(f'🔧 В ремонт: {item["name"]} ({code})')
                elif action == 'copy':
                    # A copy has a new identity: no serial, allocations, bookings or repair history.
                    if flash:
                        n,new=flash_number(conn,flash_budget(item['budget_tag']))
                        columns=('kind','min_stock','photo','price','kit_body','kit_lens','kit_flash','kit_acc','kit_add','price_body','price_lens','price_flash','price_acc','price_add','budget_tag','category')
                        conn.execute(f'INSERT INTO items(code,name,{",".join(columns)}) SELECT ?,?,{",".join(columns)} FROM items WHERE code=?',
                                     (new,str(n),code))
                    else:
                        prefix=re.sub(r'[^\w.-]','',code.rsplit('-',1)[0])[:48] or 'ITEM'
                        n=1
                        while conn.execute('SELECT 1 FROM items WHERE code=?',(f'{prefix}-{n}',)).fetchone(): n+=1
                        new=f'{prefix}-{n}'
                        cols=('name','kind','min_stock','photo','price','kit_body','kit_lens','kit_flash','kit_acc','kit_add','price_body','price_lens','price_flash','price_acc','price_add','budget_tag','category')
                        conn.execute(f'INSERT INTO items(code,{",".join(cols)}) SELECT ?,{",".join(cols)} FROM items WHERE code=?',(new,code))
                    conn.execute('INSERT INTO item_metadata(code,unit,supplier,notes) SELECT ?,unit,supplier,notes FROM item_metadata WHERE code=?',(new,code))
                    conn.execute('INSERT INTO stock(item_code,location_id,quantity) VALUES(?,?,?)',(new,req.location,1 if kind=='equipment' else 0))
                    audit(conn,actor,'Массовое копирование: '+code,new)
                    changes.append(new); continue
                elif action == 'stock':
                    if kind!='consumable': raise HTTPException(400,'Остатки изменяются только у расходников')
                    old=conn.execute('SELECT quantity FROM stock WHERE item_code=? AND location_id=?',(code,req.location)).fetchone()
                    before=old[0] if old else 0
                    if req.quantity:
                        conn.execute('INSERT INTO stock(item_code,location_id,quantity) VALUES(?,?,?) ON CONFLICT(item_code,location_id) DO UPDATE SET quantity=excluded.quantity',(code,req.location,req.quantity))
                    else: conn.execute('DELETE FROM stock WHERE item_code=? AND location_id=?',(code,req.location))
                    audit(conn,actor,f'Корректировка остатка: помещение {req.location}; {before} → {req.quantity}',code)
                    newtotal=total-before+req.quantity
                    if item['min_stock']>0 and newtotal<=item['min_stock']<total:
                        notices.append(f'⚠️ Заканчивается: {item["name"]}. Осталось: {newtotal} шт.')
                    changes.append(code); continue
                elif action in ('archive','delete'):
                    if held or booked or repairing or item['needs_repair']:
                        raise HTTPException(409,f'{code}: сначала верните товар, завершите ремонт и отмените активную бронь')
                    if action=='delete' and total:
                        raise HTTPException(409,f'{code}: нельзя удалить товар с остатком; используйте архив')
                    paid=conn.execute("SELECT remaining_cents FROM equipment_buyout_amounts WHERE item_code=?",(code,)).fetchone()
                    if action=='archive' and paid and paid['remaining_cents']==0 and item['buyout_status']:
                        raise HTTPException(409,f'{code}: используйте архив «Выкуплено»')
                    if flash:
                        code=archive_flash_code(conn,item,'ordinary',actor=actor)
                    conn.execute('UPDATE items SET is_archived=? WHERE code=?',(2 if action=='delete' else 1,code))
                audit(conn,actor,'Массовое действие: '+action,code)
                changes.append(code)
        if notices:
            background_tasks.add_task(notify,'\n'.join(notices)[:3500])
        return {'updated':len(changes),'codes':changes}

    @app.post('/api/v18/batch-labels')
    def batch_labels(req: BatchLabels, x_init_data: Optional[str] = Header(None)):
        actor=check_admin(x_init_data)
        if not actor.get('is_registered'): raise HTTPException(403,'Завершите регистрацию')
        codes=list(dict.fromkeys(req.codes))
        label_dimensions(req.width_mm,req.height_mm)
        if len(codes)*round(req.width_mm/25.4*req.dpi)*round(req.height_mm/25.4*req.dpi)>100_000_000:
            raise HTTPException(400,'Выберите меньше товаров или меньший размер этикетки')
        with transaction() as conn:
            rows=[(code,active_item(conn,code)['name']) for code in codes]
        images=[label_image(code,name,req.dpi,req.width_mm,req.height_mm) for code,name in rows]
        try:
            buf=io.BytesIO(); images[0].save(buf,format='PDF',resolution=req.dpi,save_all=True,append_images=images[1:]); buf.seek(0)
        finally:
            for im in images: im.close()
        return StreamingResponse(buf,media_type='application/pdf',headers={'Cache-Control':'no-store','Content-Disposition':'attachment; filename=selected_labels.pdf'})
