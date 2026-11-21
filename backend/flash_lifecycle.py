"""Flash numbering and purchased-equipment archive lifecycle.

Public flash codes are reusable slots (кц1, тх1, ...). Archived units receive
private tombstone codes so checkout/stock/repair history never refers to a new
unit with the same public slot. All changes use the caller's SQLite transaction.
"""
import json
import re
import sqlite3
import uuid

from fastapi import Header, HTTPException
from pydantic import BaseModel, Field


FLASH_CATEGORIES = {"вспышка", "вспышки", "фотовспышка", "фотовспышки"}
LINK_TABLES = {
    "stock": "item_code", "bookings": "item_code", "comments": "item_code",
    "checkouts": "item_code", "movements": "item_code", "writeoffs": "item_code",
    "lost_items": "item_code", "receipts": "item_code",
    "consumable_returns": "item_code", "equipment_buyout_amounts": "item_code",
    "item_metadata": "code", "repair_records": "code",
    "equipment_archive_details": "item_code",
}
FLASH_CODE_PATTERN = re.compile(r"^(кц|тх)([1-9][0-9]*)$", re.IGNORECASE)


def standalone_flash(category, name, kind="equipment"):
    return kind == "equipment" and (
        str(category or "").strip().casefold() in FLASH_CATEGORIES
        or bool(re.match(r"^(?:фото)?вспышка\b", str(name or "").strip(), re.I))
    )


def flash_budget(value):
    value = str(value or "").strip().upper()
    if value not in ("КЦ", "ТХ"):
        raise HTTPException(400, "Для вспышки обязательно выберите бюджет КЦ или ТХ")
    return value


def flash_number_code(budget, number):
    return ("кц" if budget == "КЦ" else "тх") + str(number)


def flash_number(conn, budget, ignore_item_id=None):
    budget = flash_budget(budget)
    occupied = set()
    for item in conn.execute("SELECT id, code FROM items"):
        if ignore_item_id is not None and item["id"] == ignore_item_id:
            continue
        occupied.add(item["code"].casefold())
    number = 1
    while flash_number_code(budget, number).casefold() in occupied:
        number += 1
    return number, flash_number_code(budget, number)


def ensure_flash_tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS equipment_archive_details (
        item_code TEXT PRIMARY KEY,
        old_code TEXT NOT NULL,
        old_name TEXT NOT NULL,
        reason TEXT NOT NULL CHECK(reason IN ('buyout','ordinary')),
        buyer_name TEXT NOT NULL DEFAULT '',
        archived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        archived_by INTEGER,
        original_stock TEXT NOT NULL DEFAULT '[]'
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS checkout_close_reasons (
        checkout_id INTEGER PRIMARY KEY,
        reason TEXT NOT NULL CHECK(reason='buyout'),
        buyer_name TEXT NOT NULL,
        closed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS flash_code_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        old_code TEXT NOT NULL,
        new_code TEXT NOT NULL,
        reason TEXT NOT NULL,
        changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flash_code_changes_item ON flash_code_changes(item_id)")


def _table_exists(conn, table):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _record_code_change(conn, item_id, old_code, new_code, reason):
    conn.execute("""INSERT INTO flash_code_changes(item_id,old_code,new_code,reason)
                 VALUES(?,?,?,?)""", (item_id, old_code, new_code, reason))


def rename_item_code(conn, old_code, new_code, reason):
    """Keep every relational reference tied to the same piece of equipment."""
    if old_code == new_code:
        return
    if conn.execute("SELECT 1 FROM items WHERE code=? COLLATE NOCASE", (new_code,)).fetchone():
        raise HTTPException(409, "Код уже используется: " + new_code)
    item = conn.execute("SELECT id FROM items WHERE code=?", (old_code,)).fetchone()
    if not item:
        raise HTTPException(404, "Оборудование не найдено")
    conn.execute("UPDATE items SET code=? WHERE id=?", (new_code, item["id"]))
    for table, column in LINK_TABLES.items():
        if _table_exists(conn, table):
            conn.execute(f"UPDATE {table} SET {column}=? WHERE {column}=?", (new_code, old_code))
    if _table_exists(conn, "audit_log"):
        conn.execute("UPDATE audit_log SET subject=? WHERE subject=?", (new_code, old_code))
    if _table_exists(conn, "v18_profiles"):
        for row in conn.execute("SELECT user_id,data FROM v18_profiles"):
            try:
                data=json.loads(row["data"])
            except (ValueError, TypeError):
                raise RuntimeError("Некорректный пользовательский профиль — смена кода отменена")
            modified=False
            for field in ("favorites", "recent"):
                if isinstance(data.get(field), list) and old_code in data[field]:
                    data[field] = list(dict.fromkeys(new_code if v == old_code else v for v in data[field]))
                    modified=True
            if isinstance(data.get("kits"), dict):
                for key, values in data["kits"].items():
                    if isinstance(values, list) and old_code in values:
                        data["kits"][key] = list(dict.fromkeys(new_code if v == old_code else v for v in values))
                        modified=True
            if modified:
                conn.execute("UPDATE v18_profiles SET data=? WHERE user_id=?",
                             (json.dumps(data,ensure_ascii=False), row["user_id"]))
    _record_code_change(conn, item["id"], old_code, new_code, reason)


def _archive_code(conn, item):
    candidate = "арх-" + str(item["id"]) + "-" + uuid.uuid4().hex[:8]
    while conn.execute("SELECT 1 FROM items WHERE code=? COLLATE NOCASE", (candidate,)).fetchone():
        candidate = "арх-" + str(item["id"]) + "-" + uuid.uuid4().hex[:8]
    return candidate


def archive_flash_code(conn, item, reason, buyer="", actor=None, stock_json="[]"):
    """Archive a flash identity and release its public number immediately."""
    old_code = item["code"]
    archived_code = _archive_code(conn, item)
    rename_item_code(conn, old_code, archived_code, "archive-" + reason)
    conn.execute("""INSERT INTO equipment_archive_details
        (item_code,old_code,old_name,reason,buyer_name,archived_by,original_stock)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(item_code) DO UPDATE SET
          old_code=excluded.old_code,old_name=excluded.old_name,
          reason=excluded.reason,buyer_name=excluded.buyer_name,
          archived_at=CURRENT_TIMESTAMP,archived_by=excluded.archived_by,
          original_stock=excluded.original_stock""",
        (archived_code,old_code,item["name"],reason,buyer,
         actor["tg_id"] if actor else None,stock_json))
    return archived_code


def update_flash_identity(conn, item, budget, reason="update"):
    """Assign a slot to one flash atomically; archived rows are not candidates."""
    budget = flash_budget(budget)
    if item["is_archived"]:
        raise HTTPException(409,"Нельзя перенумеровать архивную вспышку")
    old_code = item["code"]
    match = FLASH_CODE_PATTERN.fullmatch(old_code)
    if match and ("КЦ" if match[1].casefold()=="кц" else "ТХ")==budget:
        return old_code, str(int(match[2]))
    number, new_code = flash_number(conn, budget, ignore_item_id=item["id"])
    rename_item_code(conn, old_code, new_code, reason)
    return new_code, str(number)


def _take_model_from_legacy_name(conn, item):
    if str(item["kit_flash"] or "").strip():
        return
    raw = str(item["name"] or "").strip()
    raw = re.sub(r"^(?:фото)?вспышка\s*[№#.:—-]*\s*", "", raw, flags=re.I)
    if raw and not re.fullmatch(r"[№#\s\d.-]+", raw) and re.search(r"[A-Za-zА-Яа-я]", raw):
        conn.execute("UPDATE items SET kit_flash=? WHERE id=?", (raw[:250], item["id"]))


def migrate_flash_inventory(conn):
    """One-time migration. Ambiguous missing budgets are reported, never guessed."""
    ensure_flash_tables(conn)
    if conn.execute("SELECT 1 FROM warehouse_release_meta WHERE version='flash-identity-20261121'").fetchone():
        return {"migrated":0,"skipped":0}
    archived=conn.execute("SELECT * FROM items WHERE is_archived<>0 ORDER BY id").fetchall()
    recycled=0
    for item in archived:
        if standalone_flash(item["category"], item["name"], item["kind"]) and FLASH_CODE_PATTERN.fullmatch(item["code"]):
            archive_flash_code(conn,item,"ordinary")
            recycled+=1
    originals=conn.execute("SELECT * FROM items WHERE is_archived=0 ORDER BY created_at,id").fetchall()
    candidates=[]
    skipped=[]
    for item in originals:
        if not standalone_flash(item["category"],item["name"],item["kind"]):
            continue
        budget=str(item["budget_tag"] or "").strip().upper()
        if budget not in ("КЦ","ТХ"):
            inferred=FLASH_CODE_PATTERN.fullmatch(item["code"])
            if inferred:
                budget="КЦ" if inferred[1].casefold()=="кц" else "ТХ"
            else:
                skipped.append((item["code"],item["name"]))
                continue
        _take_model_from_legacy_name(conn,item)
        candidates.append((item,budget))
    # Move every candidate away from its old public key before assigning any
    # sequential keys; this also handles permutations and existing collisions.
    for item,budget in candidates:
        rename_item_code(conn,item["code"],"врем-"+str(item["id"])+"-"+uuid.uuid4().hex[:8],"migrate-staging")
    moved=[]
    for item,budget in candidates:
        pending=conn.execute("SELECT * FROM items WHERE id=?", (item["id"],)).fetchone()
        number,new_code=flash_number(conn,budget)
        rename_item_code(conn,pending["code"],new_code,"migrate-final")
        conn.execute("UPDATE items SET name=?,budget_tag=?,category='Вспышки' WHERE id=?",
                     (str(number),budget,item["id"]))
        moved.append((item["code"],new_code,str(number)))
    conn.execute("INSERT INTO warehouse_release_meta(version) VALUES('flash-identity-20261121')")
    return {"migrated":len(moved),"archived_codes_freed":recycled,
            "skipped":len(skipped),"pending_budgets":skipped[:40]}


def restore_flash(conn, item):
    if not standalone_flash(item["category"],item["name"],item["kind"]):
        return item["code"]
    budget=flash_budget(item["budget_tag"])
    number,new_code=flash_number(conn,budget,ignore_item_id=item["id"])
    rename_item_code(conn,item["code"],new_code,"restore")
    conn.execute("UPDATE items SET name=?,is_archived=0 WHERE id=?",(str(number),item["id"]))
    return new_code


class BuyoutArchiveRequest(BaseModel):
    buyer_name: str = Field(min_length=1,max_length=150)
    confirmed: bool = False


def register_flash_lifecycle(app, check_admin, transaction, active_item, audit):
    @app.get("/api/flash/next")
    def next_flash(budget: str, x_init_data: str = Header(default="")):
        check_admin(x_init_data)
        with transaction() as conn:
            number,code=flash_number(conn,budget)
            return {"code":code,"name":str(number)}

    @app.get("/api/equipment/models")
    def equipment_models(x_init_data: str = Header(default="")):
        check_admin(x_init_data)
        with transaction() as conn:
            results={}
            for field in ("kit_body","kit_lens","kit_flash"):
                values={}
                for row in conn.execute(f"SELECT {field} FROM items WHERE kind='equipment' AND TRIM({field})<>''"):
                    value=" ".join(str(row[0]).split())
                    if value and value.casefold() not in values:
                        values[value.casefold()]=value
                results[field]=sorted(values.values(),key=str.casefold)[:300]
            return results

    @app.post("/api/items/{code}/archive-buyout")
    def archive_buyout(code: str, req: BuyoutArchiveRequest,
                       x_init_data: str = Header(default="")):
        actor=check_admin(x_init_data)
        buyer=" ".join(req.buyer_name.split())
        if not req.confirmed:
            raise HTTPException(400,"Подтвердите завершённый выкуп")
        if not buyer or len(buyer)>150:
            raise HTTPException(400,"Укажите фамилию покупателя")
        with transaction() as conn:
            ensure_flash_tables(conn)
            item=active_item(conn,code)
            if item["kind"]!="equipment":
                raise HTTPException(400,"Выкуп применим только к оборудованию")
            expected=" ".join(str(item["buyout_status"] or "").split())
            if expected and expected.casefold().replace("ё","е") != buyer.casefold().replace("ё","е"):
                raise HTTPException(409,"Фамилия не совпадает с получателем выкупа в карточке")
            amounts=conn.execute("""SELECT total_cents,remaining_cents FROM equipment_buyout_amounts
                WHERE item_code=?""",(code,)).fetchone()
            if not amounts or amounts["total_cents"]<=0 or amounts["remaining_cents"]!=0:
                raise HTTPException(409,"Сначала укажите сумму выкупа и нулевой остаток оплаты")
            if item["needs_repair"] or conn.execute("SELECT 1 FROM repair_records WHERE code=? AND finished_at IS NULL",(code,)).fetchone():
                raise HTTPException(409,"Сначала завершите ремонт")
            if conn.execute("SELECT 1 FROM bookings WHERE item_code=? AND date_to>=date('now')",(code,)).fetchone():
                raise HTTPException(409,"Сначала отмените будущие брони")
            stocks=[dict(row) for row in conn.execute(
                "SELECT location_id,quantity FROM stock WHERE item_code=? AND quantity<>0",(code,))]
            held=[row["id"] for row in conn.execute(
                "SELECT id FROM checkouts WHERE item_code=? AND returned_at IS NULL",(code,))]
            if len(held)>1 or sum(row["quantity"] for row in stocks)>1 or (held and any(row["quantity"]>0 for row in stocks)):
                raise HTTPException(409,"Обнаружены противоречивые остатки или выдачи — сначала проверьте учёт")
            for checkout_id in held:
                conn.execute("UPDATE checkouts SET returned_at=CURRENT_TIMESTAMP,returned_by=? WHERE id=?",
                             (actor["tg_id"],checkout_id))
                conn.execute("""INSERT INTO checkout_close_reasons(checkout_id,reason,buyer_name)
                    VALUES(?,'buyout',?)""",(checkout_id,buyer))
            conn.execute("UPDATE stock SET quantity=0 WHERE item_code=?",(code,))
            conn.execute("UPDATE items SET is_archived=1,buyout_status=? WHERE code=?",(buyer,code))
            stored_code=code
            if standalone_flash(item["category"],item["name"],item["kind"]):
                stored_code=archive_flash_code(conn,item,"buyout",buyer,actor,
                                               json.dumps(stocks,ensure_ascii=False))
            else:
                conn.execute("""INSERT INTO equipment_archive_details
                    (item_code,old_code,old_name,reason,buyer_name,archived_by,original_stock)
                    VALUES(?,?,?,'buyout',?,?,?)""",
                    (code,code,item["name"],buyer,actor["tg_id"],json.dumps(stocks)))
            audit(conn,actor,"Выкуплено и архивировано",
                  f"{item['name']} ({code}) → {stored_code}; покупатель: {buyer}; выплачено: {amounts['total_cents']/100:.2f}")
            return {"status":"ok","archived_code":stored_code,"buyer_name":buyer,
                    "closed_checkouts":len(held)}
