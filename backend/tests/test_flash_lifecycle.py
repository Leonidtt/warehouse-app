"""Unit/integration regression checks for Main flash identities.

Run: python -m unittest discover -s backend/tests -p "test_flash_lifecycle.py" -v
No production DB, Railway secrets, or Telegram credentials are used.
"""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flash_lifecycle import (
    archive_flash_code, ensure_flash_tables, flash_budget, flash_number,
    migrate_flash_inventory, register_flash_lifecycle, rename_item_code,
    restore_flash, standalone_flash, update_flash_identity,
)


SCHEMA = """
CREATE TABLE items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'equipment',
  category TEXT NOT NULL DEFAULT '',
  kit_body TEXT DEFAULT '',
  kit_lens TEXT DEFAULT '',
  kit_flash TEXT DEFAULT '',
  budget_tag TEXT DEFAULT '',
  buyout_status TEXT DEFAULT '',
  needs_repair INTEGER DEFAULT 0,
  is_archived INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  photo TEXT DEFAULT ''
);
CREATE TABLE warehouse_release_meta(version TEXT PRIMARY KEY);
CREATE TABLE stock(item_code TEXT,location_id INTEGER,quantity INTEGER,
  PRIMARY KEY(item_code,location_id));
CREATE TABLE checkouts(id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_code TEXT,user_id INTEGER,returned_at TEXT,returned_by INTEGER);
CREATE TABLE bookings(item_code TEXT,date_to TEXT);
CREATE TABLE comments(item_code TEXT,text TEXT);
CREATE TABLE movements(item_code TEXT,quantity INTEGER);
CREATE TABLE writeoffs(item_code TEXT,quantity INTEGER);
CREATE TABLE lost_items(item_code TEXT);
CREATE TABLE receipts(item_code TEXT);
CREATE TABLE consumable_returns(item_code TEXT);
CREATE TABLE equipment_buyout_amounts(item_code TEXT PRIMARY KEY,
  total_cents INTEGER,remaining_cents INTEGER);
CREATE TABLE item_metadata(code TEXT PRIMARY KEY,notes TEXT);
CREATE TABLE repair_records(id INTEGER PRIMARY KEY,code TEXT,finished_at TEXT);
CREATE TABLE audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,
  action TEXT,subject TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE v18_profiles(user_id INTEGER PRIMARY KEY,data TEXT);
"""


def connect(database):
    db=sqlite3.connect(database)
    db.row_factory=sqlite3.Row
    return db


class FlashLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.path=os.path.join(self.dir.name,"warehouse_test.db")
        self.db=connect(self.path)
        self.db.executescript(SCHEMA)
        ensure_flash_tables(self.db)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.dir.cleanup()

    def item(self,code,name,category="Вспышки",budget="КЦ",archived=0,model="",photo=""):
        self.db.execute("""INSERT INTO items
            (code,name,category,budget_tag,is_archived,kit_flash,photo)
            VALUES(?,?,?,?,?,?,?)""",(code,name,category,budget,archived,model,photo))
        return self.db.execute("SELECT * FROM items WHERE code=?",(code,)).fetchone()

    def test_renumber_keeps_archived_history_and_all_relations(self):
        old=self.item("кц1","3","Вспышки","КЦ",1,model="Godox AD200")
        new=self.item("OLD-9","Вспышка Godox V1C","Вспышки","КЦ",0,photo="picture")
        other=self.item("FREE-8","Вспышка Sony","Вспышки","ТХ",0,model="Sony")
        self.item("тх1","Чужая техника","Аксессуары","КЦ")
        self.db.execute("INSERT INTO stock VALUES('кц1',11,1)")
        self.db.execute("INSERT INTO stock VALUES('OLD-9',12,1)")
        self.db.execute("INSERT INTO checkouts(item_code,user_id) VALUES('OLD-9',123)")
        self.db.execute("INSERT INTO item_metadata(code,notes) VALUES('OLD-9','no edits')")
        self.db.execute("INSERT INTO repair_records(code) VALUES('OLD-9')")
        self.db.execute("INSERT INTO equipment_buyout_amounts VALUES('OLD-9',5000,3000)")
        self.db.execute("INSERT INTO audit_log(user_id,action,subject) VALUES(1,'Создание','OLD-9')")
        self.db.execute("INSERT INTO v18_profiles VALUES(?,?)",(123,json.dumps({
            "favorites":["OLD-9"],"recent":["OLD-9"],"kits":{"Съёмка":["OLD-9"]}
        })))
        result=migrate_flash_inventory(self.db)
        self.db.commit()
        self.assertEqual(result["migrated"],2)
        self.assertEqual(result["skipped"],0)
        active=self.db.execute("SELECT * FROM items WHERE id=?",(new["id"],)).fetchone()
        archived=self.db.execute("SELECT * FROM items WHERE id=?",(old["id"],)).fetchone()
        self.assertEqual((active["code"],active["name"],active["budget_tag"],active["category"]),
                         ("кц1","1","КЦ","Вспышки"))
        self.assertEqual(active["kit_flash"],"Godox V1C")
        self.assertEqual(active["photo"],"picture")
        self.assertTrue(archived["code"].startswith("арх-"))
        self.assertEqual(self.db.execute("SELECT item_code FROM stock WHERE location_id=11").fetchone()[0],
                         archived["code"])
        for table,column in (("stock","item_code"),("checkouts","item_code"),
                             ("item_metadata","code"),("repair_records","code"),
                             ("equipment_buyout_amounts","item_code")):
            self.assertTrue(self.db.execute(
                f"SELECT 1 FROM {table} WHERE {column}='кц1'").fetchone(),table)
        profile=json.loads(self.db.execute("SELECT data FROM v18_profiles WHERE user_id=123").fetchone()[0])
        self.assertEqual(profile["favorites"],["кц1"])
        self.assertEqual(profile["kits"]["Съёмка"],["кц1"])
        tx=self.db.execute("SELECT * FROM items WHERE id=?",(other["id"],)).fetchone()
        self.assertEqual((tx["code"],tx["name"]),("тх2","2"))
        self.assertEqual(migrate_flash_inventory(self.db)["migrated"],0)

    def test_archiving_frees_number_without_repointing_old_history(self):
        item=self.item("кц1","1",model="Canon 600EX")
        self.db.execute("INSERT INTO checkouts(item_code,user_id,returned_at) VALUES('кц1',9,'2026-11-20')")
        self.db.execute("INSERT INTO stock VALUES('кц1',1,1)")
        code=archive_flash_code(self.db,item,"ordinary",actor={"tg_id":4})
        self.db.execute("UPDATE items SET is_archived=1 WHERE code=?",(code,))
        self.assertTrue(code.startswith("арх-"))
        self.assertEqual(flash_number(self.db,"КЦ"),(1,"кц1"))
        self.assertEqual(self.db.execute("SELECT item_code FROM checkouts").fetchone()[0],code)
        self.assertEqual(self.db.execute("SELECT item_code FROM stock").fetchone()[0],code)
        self.item("кц1","1",model="Godox V1")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM items").fetchone()[0],2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM checkouts WHERE item_code='кц1'").fetchone()[0],0)

    def test_budget_change_reassigns_code_without_losing_history(self):
        item=self.item("кц1","1")
        self.db.execute("INSERT INTO stock VALUES('кц1',1,1)")
        new_code,name=update_flash_identity(self.db,item,"ТХ")
        self.assertEqual((new_code,name),("тх1","1"))
        self.assertEqual(flash_number(self.db,"КЦ"),(1,"кц1"))
        self.assertEqual(self.db.execute("SELECT item_code FROM stock").fetchone()[0],"тх1")
        with self.assertRaises(HTTPException):
            flash_budget("")

    def test_untagged_legacy_flash_is_left_unmodified(self):
        item=self.item("X-999","Вспышка без бюджета",budget="")
        result=migrate_flash_inventory(self.db)
        self.assertEqual(result["skipped"],1)
        same=self.db.execute("SELECT code,name FROM items WHERE id=?",(item["id"],)).fetchone()
        self.assertEqual(tuple(same),("X-999","Вспышка без бюджета"))

    def client(self):
        @contextmanager
        def transaction():
            conn=connect(self.path)
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                conn.close()
        def auth(header):
            if header!="test-admin":
                raise HTTPException(403,"Не администратор")
            return {"tg_id":1}
        def active(conn,code):
            item=conn.execute("SELECT * FROM items WHERE code=? AND is_archived=0",(code,)).fetchone()
            if not item: raise HTTPException(404,"Товар не найден")
            return item
        def audit(conn,user,action,subject):
            conn.execute("INSERT INTO audit_log(user_id,action,subject) VALUES(?,?,?)",
                         (user["tg_id"],action,subject))
        app=FastAPI()
        register_flash_lifecycle(app,auth,transaction,active,audit)
        return TestClient(app)

    def test_buyout_archive_closes_checkout_as_sale_and_releases_slot(self):
        self.item("кц1","1",budget="КЦ",model="Godox V1")
        self.db.execute("INSERT INTO equipment_buyout_amounts VALUES('кц1',10000,0)")
        # Checked-out equipment has zero available units in the storeroom.
        self.db.execute("INSERT INTO stock VALUES('кц1',3,0)")
        self.db.execute("INSERT INTO checkouts(item_code,user_id) VALUES('кц1',9)")
        self.db.commit()
        client=self.client()
        res=client.post("/api/items/кц1/archive-buyout",
          headers={"X-Init-Data":"test-admin"},
          json={"buyer_name":"Иванов","confirmed":True})
        self.assertEqual(res.status_code,200,res.text)
        old_code=res.json()["archived_code"]
        self.assertEqual(res.json()["closed_checkouts"],1)
        self.assertTrue(old_code.startswith("арх-"))
        saved=connect(self.path)
        try:
            row=saved.execute("SELECT * FROM items WHERE code=?",(old_code,)).fetchone()
            self.assertEqual((row["is_archived"],row["buyout_status"]),(1,"Иванов"))
            self.assertEqual(saved.execute("SELECT quantity FROM stock").fetchone()[0],0)
            self.assertEqual(saved.execute("SELECT item_code FROM checkouts").fetchone()[0],old_code)
            self.assertIsNotNone(saved.execute("SELECT returned_at FROM checkouts").fetchone()[0])
            reason=saved.execute("SELECT reason,buyer_name FROM checkout_close_reasons").fetchone()
            self.assertEqual(tuple(reason),("buyout","Иванов"))
            d=saved.execute("SELECT buyer_name,reason FROM equipment_archive_details").fetchone()
            self.assertEqual(tuple(d),("Иванов","buyout"))
        finally:
            saved.close()
        self.assertEqual(client.get("/api/flash/next?budget=КЦ",
                           headers={"X-Init-Data":"test-admin"}).json()["code"],"кц1")

    def test_paid_archive_rejects_unpaid_or_unauthorized(self):
        self.item("кц1","1",budget="КЦ")
        self.db.execute("INSERT INTO equipment_buyout_amounts VALUES('кц1',10000,200)")
        self.db.commit()
        client=self.client()
        data={"buyer_name":"Петров","confirmed":True}
        self.assertEqual(client.post("/api/items/кц1/archive-buyout",json=data).status_code,403)
        res=client.post("/api/items/кц1/archive-buyout",
          headers={"X-Init-Data":"test-admin"},json=data)
        self.assertEqual(res.status_code,409,res.text)
        self.assertEqual(self.db.execute("SELECT is_archived FROM items WHERE code='кц1'").fetchone()[0],0)

    def test_model_suggestions_include_archived_and_new_values(self):
        self.item("A","3",model="Godox V1C",archived=1)
        self.item("B","4",model="Godox V1C",budget="ТХ")
        self.item("C","5",model="Profoto A10",budget="ТХ")
        self.db.commit()
        rows=self.client().get("/api/equipment/models",headers={"X-Init-Data":"test-admin"})
        self.assertEqual(rows.status_code,200,rows.text)
        self.assertEqual(rows.json()["kit_flash"],["Godox V1C","Profoto A10"])


if __name__=="__main__":
    unittest.main()
