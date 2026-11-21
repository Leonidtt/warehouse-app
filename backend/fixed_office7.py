"""Beta only: equipment storage is fixed to Office 7."""
import re
import uuid
from fastapi import HTTPException

def normalize_office(value):
    return re.sub(r'[^\w]+', '', str(value or '').casefold().replace('ё', 'е'))

def office7_location_id(conn, create=False):
    matches=[row['id'] for row in conn.execute("SELECT id,name FROM locations")
             if normalize_office(row['name'])=='офис7']
    if len(matches)>1:
        raise HTTPException(409,'Найдено несколько помещений «Офис 7». Уточните названия.')
    if matches:
        return matches[0]
    if not create:
        raise HTTPException(409,'Помещение «Офис 7» не найдено.')
    result=conn.execute("INSERT INTO locations(name,type) VALUES('Офис 7','office')")
    return result.lastrowid

def consolidate_office7_stock(conn):
    """Archive original locations before relocating available equipment.

    Caller controls transaction; checkout, movement and booking history stays intact.
    """
    office=office7_location_id(conn,create=True)
    bad=conn.execute("""SELECT COUNT(*) FROM stock s
        JOIN items i ON i.code=s.item_code
        WHERE i.kind='equipment' AND s.quantity<0""").fetchone()[0]
    if bad:
        raise RuntimeError('Отрицательные остатки оборудования — перенос отменён')
    total_before=conn.execute("""SELECT COALESCE(SUM(s.quantity),0) FROM stock s
        JOIN items i ON i.code=s.item_code WHERE i.kind='equipment'""").fetchone()[0]
    conn.execute("""CREATE TABLE IF NOT EXISTS beta_office7_stock_rollback(
        batch_id TEXT NOT NULL, item_code TEXT NOT NULL,
        original_location_id INTEGER NOT NULL, quantity INTEGER NOT NULL,
        moved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(batch_id,item_code,original_location_id))""")
    rows=conn.execute("""SELECT s.item_code,s.location_id,s.quantity FROM stock s
        JOIN items i ON i.code=s.item_code
        WHERE i.kind='equipment' AND s.quantity>0 AND s.location_id<>?
        ORDER BY s.item_code,s.location_id""",(office,)).fetchall()
    batch=uuid.uuid4().hex
    for row in rows:
        code,location,amount=row['item_code'],row['location_id'],row['quantity']
        conn.execute("""INSERT INTO beta_office7_stock_rollback
            (batch_id,item_code,original_location_id,quantity) VALUES(?,?,?,?)""",
            (batch,code,location,amount))
        conn.execute("""INSERT INTO stock(item_code,location_id,quantity) VALUES(?,?,?)
            ON CONFLICT(item_code,location_id) DO UPDATE SET quantity=quantity+excluded.quantity""",
            (code,office,amount))
        conn.execute("DELETE FROM stock WHERE item_code=? AND location_id=?",(code,location))
    total_after=conn.execute("""SELECT COALESCE(SUM(s.quantity),0) FROM stock s
        JOIN items i ON i.code=s.item_code WHERE i.kind='equipment'""").fetchone()[0]
    if total_after!=total_before:
        raise RuntimeError('Общий остаток изменился — перенос отменён')
    return len(rows)
