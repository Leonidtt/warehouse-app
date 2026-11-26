from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional
from fastapi import Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, conint, constr

GROUPS = ('Зимние', 'Москва', 'Кино', 'Любовь')
ORIENTATIONS = ('Горизонтальные', 'Вертикальные')
Count = conint(strict=True, ge=0, le=1000000)

class Change(BaseModel):
    position: conint(strict=True, ge=1, le=8)
    kind: Literal['inventory', 'receipt', 'issue', 'transfer', 'minimum', 'unpack']
    boxes: Count = 0
    packs: Count = 0
    loose: Count = 0
    minimum: Optional[Count] = None
    revision: Count
    comment: constr(max_length=500) = ''
    destination: constr(max_length=200) = ''


def total(boxes, packs, loose):
    return boxes * 500 + packs * 50 + loose


def init_frames(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS frame_stock (
        id INTEGER PRIMARY KEY, boxes INTEGER NOT NULL DEFAULT 0 CHECK(boxes>=0),
        packs INTEGER NOT NULL DEFAULT 0 CHECK(packs>=0), loose INTEGER NOT NULL DEFAULT 0 CHECK(loose>=0),
        minimum INTEGER, revision INTEGER NOT NULL DEFAULT 0, counted_at TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS frame_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, position INTEGER NOT NULL, kind TEXT NOT NULL,
        boxes INTEGER NOT NULL, packs INTEGER NOT NULL, loose INTEGER NOT NULL,
        before_total INTEGER, after_total INTEGER NOT NULL, delta INTEGER,
        actor_id INTEGER NOT NULL, actor TEXT NOT NULL, comment TEXT NOT NULL, created_at TEXT NOT NULL, destination TEXT NOT NULL DEFAULT '')''')
    if 'destination' not in {r[1] for r in conn.execute('PRAGMA table_info(frame_events)')}:
        conn.execute("ALTER TABLE frame_events ADD COLUMN destination TEXT NOT NULL DEFAULT ''")
    conn.executemany('INSERT OR IGNORE INTO frame_stock(id) VALUES(?)', [(i,) for i in range(1,9)])


def apply_change(conn, req, actor):
    row = conn.execute('SELECT * FROM frame_stock WHERE id=?', (req.position,)).fetchone()
    if row['revision'] != req.revision:
        raise HTTPException(409, 'Остаток изменился. Обновите данные и повторите.')
    destination = ' '.join(req.destination.split())
    if req.kind == 'transfer' and not destination:
        raise HTTPException(400, 'Укажите площадку.')
    if req.kind != 'transfer':
        destination = ''
    old = tuple(row[k] for k in ('boxes','packs','loose'))
    given = (req.boxes, req.packs, req.loose)
    known = row['counted_at'] is not None
    before = total(*old) if known else None
    stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
    counted_at, minimum = row['counted_at'], row['minimum']
    if req.kind == 'minimum':
        minimum = req.minimum
        new = old
    elif req.kind == 'inventory':
        new = given
        counted_at = stamp
    else:
        if not known:
            raise HTTPException(409, 'Сначала проведите инвентаризацию этой позиции.')
        if not total(*given):
            raise HTTPException(400, 'Укажите количество.')
        if req.kind == 'unpack':
            if req.loose or req.boxes > old[0] or req.packs > old[1] + req.boxes * 10:
                raise HTTPException(400, 'Недостаточно закрытых коробок или упаковок.')
            new = (old[0]-req.boxes, old[1]+req.boxes*10-req.packs, old[2]+req.packs*50)
        else:
            sign = 1 if req.kind == 'receipt' else -1
            new = tuple(a+sign*b for a,b in zip(old,given))
            if min(new)<0:
                raise HTTPException(400, 'Недостаточно рамок в этой фасовке. При необходимости распакуйте коробку или упаковку.')
    if max(new)>1000000:
        raise HTTPException(400, 'Превышен допустимый остаток.')
    after = total(*new)
    conn.execute('UPDATE frame_stock SET boxes=?,packs=?,loose=?,minimum=?,counted_at=?,revision=revision+1 WHERE id=?', (*new,minimum,counted_at,req.position))
    if req.kind != 'minimum':
        conn.execute('INSERT INTO frame_events(position,kind,boxes,packs,loose,before_total,after_total,delta,actor_id,actor,comment,created_at,destination) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (req.position,req.kind,*given,before,after,None if before is None else after-before,actor['tg_id'],actor.get('full_name') or actor.get('first_name') or str(actor['tg_id']),req.comment.strip(),stamp,destination))
    return {'before':before,'after':after,'difference':None if before is None else after-before}


def read_frames(conn):
    now = datetime.now(timezone(timedelta(hours=3)))
    day = now.replace(hour=0,minute=0,second=0,microsecond=0)
    bounds = [day, day-timedelta(days=day.weekday()), day.replace(day=1)]
    bounds = [d.astimezone(timezone.utc).isoformat(timespec='seconds') for d in bounds]
    rows=[]
    for raw in conn.execute('SELECT * FROM frame_stock ORDER BY id'):
        r=dict(raw); i=r['id']-1
        r.update(group=GROUPS[i//2],orientation=ORIENTATIONS[i%2])
        r['total']=total(r['boxes'],r['packs'],r['loose']) if r['counted_at'] else None
        r['low']=r['total'] is not None and r['minimum'] is not None and r['total']<r['minimum']
        r['usage']=[conn.execute("SELECT COALESCE(SUM(-delta),0) FROM frame_events WHERE position=? AND kind IN ('issue','transfer') AND created_at>=?",(r['id'],d)).fetchone()[0] for d in bounds]
        rows.append(r)
    shipments=[dict(r) for r in conn.execute("SELECT destination, SUM(-delta) AS quantity FROM frame_events WHERE kind='transfer' AND created_at>=? GROUP BY destination ORDER BY quantity DESC,destination",(bounds[2],))]
    return {'rows':rows,'shipments':shipments,'events':[dict(r) for r in conn.execute('SELECT * FROM frame_events ORDER BY id DESC LIMIT 100')]}


def register_frames(app, check_admin, transaction, audit):
    with transaction() as conn:
        init_frames(conn)

    @app.get('/frame-stock.js', include_in_schema=False)
    def frame_script():
        return FileResponse(Path(__file__).with_name('frame_stock.js'),media_type='text/javascript',headers={'Cache-Control':'no-cache','X-Content-Type-Options':'nosniff'})

    def admin(raw):
        actor=check_admin(raw)
        if not actor.get('is_registered'):
            raise HTTPException(403,'Завершите регистрацию')
        return actor

    @app.get('/api/frames')
    def frames_get(x_init_data: Optional[str]=Header(None)):
        admin(x_init_data)
        with transaction() as conn:
            return read_frames(conn)

    @app.post('/api/frames')
    def frames_change(req: Change,x_init_data: Optional[str]=Header(None)):
        actor=admin(x_init_data)
        with transaction() as conn:
            result=apply_change(conn,req,actor)
            audit(conn,actor,'frames_'+req.kind,str(req.position))
            return result


class MaterialChange(BaseModel):
    position: Literal['vinyl','paper46','paper68']
    kind: Literal['inventory','receipt','transfer','issue','unpack','cut','minimum']
    boxes: Count = 0
    loose: Count = 0
    minimum: Optional[Count] = None
    revision: Count
    destination: constr(max_length=200) = ''
    comment: constr(max_length=500) = ''

def register_materials(app, check_admin, transaction, audit):
    with transaction() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS material_stock (
            position TEXT PRIMARY KEY, boxes INTEGER NOT NULL DEFAULT 0 CHECK(boxes>=0),
            loose INTEGER NOT NULL DEFAULT 0 CHECK(loose>=0), minimum INTEGER,
            revision INTEGER NOT NULL DEFAULT 0, counted_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS material_events (
            id INTEGER PRIMARY KEY, position TEXT NOT NULL, kind TEXT NOT NULL,
            boxes INTEGER NOT NULL, loose INTEGER NOT NULL, before_boxes INTEGER NOT NULL,
            before_loose INTEGER NOT NULL, after_boxes INTEGER NOT NULL, after_loose INTEGER NOT NULL,
            actor_id INTEGER NOT NULL, destination TEXT NOT NULL, comment TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        conn.executemany("INSERT OR IGNORE INTO material_stock(position) VALUES(?)", [(x,) for x in ('vinyl','paper46','paper68')])

    @app.get('/api/materials')
    def materials_get(x_init_data: Optional[str]=Header(None)):
        check_admin(x_init_data)
        with transaction() as conn:
            return {'rows':[dict(r) for r in conn.execute('SELECT * FROM material_stock ORDER BY position')],
                    'events':[dict(r) for r in conn.execute('SELECT * FROM material_events ORDER BY id DESC LIMIT 500')]}

    @app.post('/api/materials')
    def materials_change(req: MaterialChange, x_init_data: Optional[str]=Header(None)):
        actor=check_admin(x_init_data)
        with transaction() as conn:
            row=conn.execute('SELECT * FROM material_stock WHERE position=?',(req.position,)).fetchone()
            if row['revision']!=req.revision:
                raise HTTPException(409,'Остаток изменился. Обновите данные.')
            a,b=row['boxes'],row['loose']
            x,y=req.boxes,req.loose
            stamp=datetime.now(timezone.utc).isoformat(timespec='seconds')
            counted,minimum=row['counted_at'],row['minimum']
            vinyl=req.position=='vinyl'
            destination=req.destination.strip() if req.kind=='transfer' else ''
            if req.kind=='transfer' and not destination:
                raise HTTPException(400,'Укажите площадку')
            if req.kind=='minimum':
                minimum=req.minimum
            elif req.kind=='inventory':
                a,b=x,y
                counted=stamp
            else:
                if not counted:
                    raise HTTPException(409,'Сначала проведите инвентаризацию')
                if not x and not y:
                    raise HTTPException(400,'Укажите количество')
                if req.kind=='cut':
                    if not vinyl or not x or not y:
                        raise HTTPException(400,'Укажите количество цельных и нарезанных коробок')
                    a,b=a-x,b+y
                elif req.kind=='unpack':
                    if vinyl or not x or y:
                        raise HTTPException(400,'Укажите количество коробок бумаги')
                    a,b=a-x,b+2*x
                elif req.kind=='receipt':
                    a,b=a+x,b+y
                else:
                    a,b=a-x,b-y
            if min(a,b)<0 or max(a,b)>1000000:
                raise HTTPException(400,'Недостаточно остатка или превышен лимит')
            conn.execute('UPDATE material_stock SET boxes=?,loose=?,minimum=?,counted_at=?,revision=revision+1 WHERE position=?',(a,b,minimum,counted,req.position))
            conn.execute('INSERT INTO material_events(position,kind,boxes,loose,before_boxes,before_loose,after_boxes,after_loose,actor_id,destination,comment,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(req.position,req.kind,x,y,row['boxes'],row['loose'],a,b,actor['tg_id'],destination,req.comment.strip(),stamp))
            audit(conn,actor,'materials_'+req.kind,req.position)
            return {'status':'ok'}
