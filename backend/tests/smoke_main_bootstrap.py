"""Cold-start smoke test of Main using a disposable local SQLite database.

Only for CI; never run with Railway credentials or production data.
"""
import ast
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys

SOURCE=Path(__file__).resolve().parents[1] / "main.py"
DB=Path("/data/warehouse.db")
if DB.exists():
    raise RuntimeError("Refusing to overwrite an existing DB in smoke test")
DB.parent.mkdir(parents=True,exist_ok=True)
tree=ast.parse(SOURCE.read_text(encoding="utf-8"))
init=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="init_db")
module=ast.fix_missing_locations(ast.Module(body=[init],type_ignores=[]))
sandbox={
    "sqlite3":sqlite3,
    "os":os,
    "init_telegram_onboarding":lambda conn: None,
    "init_return_reminders":lambda conn: None,
    "clean_camera_names":lambda conn: None,
}
exec(compile(module,str(SOURCE),"exec"),sandbox)
sandbox["init_db"](str(DB))
with closing(sqlite3.connect(DB)) as conn:
    conn.execute("CREATE TABLE IF NOT EXISTS warehouse_release_meta(version TEXT PRIMARY KEY)")
    conn.execute("""INSERT INTO items(code,name,kind,category,budget_tag,kit_flash,photo)
        VALUES('LEG-6','Вспышка Godox V1C','equipment','Вспышки','КЦ','Godox V1C','photo-preserved')""")
    conn.execute("INSERT INTO stock(item_code,location_id,quantity) VALUES('LEG-6',1,1)")
    conn.commit()
sys.path.insert(0,str(SOURCE.parent))
os.environ.setdefault("BOT_TOKEN","1234:TEST_TOKEN_DO_NOT_USE_FOR_NETWORK")
os.environ.setdefault("MAIN_ADMIN_ID","10001")
os.environ.pop("RAILWAY_SERVICE_ID",None)
import main
assert main.APP_VERSION=="18.5.15",main.APP_VERSION
with closing(sqlite3.connect(DB)) as conn:
    conn.row_factory=sqlite3.Row
    row=conn.execute("SELECT * FROM items WHERE kind='equipment' AND category='Вспышки'").fetchone()
    assert row["code"]=="кц1",(row["code"],row["name"])
    assert row["name"]=="1",row["name"]
    assert row["photo"]=="photo-preserved"
    assert conn.execute("SELECT item_code FROM stock LIMIT 1").fetchone()[0]=="кц1"
    assert conn.execute("SELECT COUNT(*) FROM flash_code_changes").fetchone()[0]>=2
    assert conn.execute("SELECT 1 FROM warehouse_release_meta WHERE version='flash-identity-20261121'").fetchone()
assert any(path.name.startswith("warehouse_pre_v18_5_15") for path in DB.parent.iterdir()),"Backup was not created"
routes={route.path for route in main.app.routes}
for expected in ("/health","/api/items","/api/items/{code}/archive-buyout",
                 "/api/flash/next","/api/equipment/models",
                 "/flash_lifecycle_ui.js","/flash_lifecycle_ui.css"):
    assert expected in routes,expected
print("Main cold-start smoke PASSED: historical flash migrated, photo and stock preserved, backup verified")
