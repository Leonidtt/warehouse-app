"""Exercise Main's HTTP routes using a disposable SQLite database."""

import ast
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from PIL import Image, ImageChops
import qrcode


BACKEND = Path(__file__).resolve().parents[1] / "backend"
CODE = "SMOKE-1"


def load_main(data_dir):
    # Preserve the production entry point and migration guard. Redirect /data in
    # this process and seed a fresh database before the guard takes its backup.
    source = BACKEND / "main.py"
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    database_paths = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value == "/data/warehouse.db":
                database_paths.append(node)
            if node.value == "/data" or node.value.startswith("/data/"):
                node.value = str(data_dir) + node.value.removeprefix("/data")
    if len(database_paths) != 1:
        raise RuntimeError("Review the smoke test: Main's database path changed.")

    for index, statement in enumerate(tree.body):
        if ast.unparse(statement) == "prepare_migration(DB_PATH, APP_VERSION)":
            tree.body.insert(index, ast.parse("init_db(DB_PATH)").body[0])
            break
    else:
        raise RuntimeError("Review the smoke test: Main's migration entry point changed.")

    namespace = {"__file__": str(source), "__name__": "warehouse_smoke"}
    configuration = {
        "BOT_TOKEN": "offline-smoke-test",
        "MAIN_ADMIN_ID": "1",
        "RAILWAY_SERVICE_ID": "",
        "RAILWAY_PUBLIC_DOMAIN": "",
    }
    with patch.object(sys, "path", [str(BACKEND), *sys.path]), patch.dict(os.environ, configuration):
        exec(compile(ast.fix_missing_locations(tree), str(source), "exec"), namespace)
    return namespace


class WarehouseSmokeTest(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Smoke test must be offline")))
        self.main = load_main(directory)
        self.database = directory / "warehouse.db"
        # TestClient without a lifespan skips the Telegram background workers.
        self.client = TestClient(self.main["app"])
        self.addCleanup(self.client.close)

    def test_main_and_pwa(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        version = self.client.get("/app/version").json()["version"]
        self.assertRegex(version, r"^[0-9a-f]{20}$")
        marker = f'<meta name="warehouse-app-version" content="{version}">'
        for path in ("/", "/pwa/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(marker, response.text)
        self.assertIn("/pwa/manifest.webmanifest", response.text)
        assets = ("/pwa/manifest.webmanifest", "/pwa/sw.js", "/warehouse-v18.js", "/warehouse-v18.css")
        for path in assets:
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_niimbot_labels(self):
        session = "label-export-session"
        items = [("KOR-1", "Коробочка для рамок", "consumable"),
                 ("KAM-12", "КЦ-12", "equipment"),
                 ("0007", "7", "equipment"), ("=1+1", "Код как текст", "equipment"),
                 ("тх8", "8", "equipment")]
        with closing(sqlite3.connect(self.database)) as conn, conn:
            conn.execute("INSERT OR REPLACE INTO users(tg_id, full_name, role, is_registered) VALUES (1, 'Admin', 'admin', 1)")
            conn.execute("INSERT INTO web_sessions VALUES (?, ?, ?)",
                         (self.main["web_digest"](session), 1, int(time.time()) + 300))
            conn.executemany("INSERT INTO items(code,name,kind) VALUES (?,?,?)", items)
        headers = {"Cookie": f"{self.main['WEB_COOKIE']}={session}", "Origin": "http://testserver"}
        self.assertEqual(self.client.post("/api/export_labels?format=xlsx",
                         json={"codes":["KAM-12"]}).status_code, 401)
        response = self.client.post("/api/export_labels?format=xlsx",
                                    json={"codes":[code for code, _, _ in items],"copies":2},headers=headers)
        self.assertEqual(response.status_code, 200, response.text if not response.is_success else "")
        with closing(load_workbook(BytesIO(response.content))) as workbook:
            sheet = workbook.active
            self.assertEqual(list(sheet.values), [("Код","Название","QR")] +
                             [(code,name,code) for code,name,_ in items for _ in range(2)])
            self.assertTrue(all(c.data_type == "s" and c.number_format == "@" for row in sheet.iter_rows(min_row=2) for c in row))
            self.assertEqual(len(sheet._images), 0)

        for dpi in (203,300):
            for code, name, kind in (items[0],items[1],items[4]):
                response = self.client.get("/api/label/"+code,params={"dpi":dpi},headers=headers)
                self.assertEqual(response.status_code,200)
                with Image.open(BytesIO(response.content)) as image:
                    w,h=(30,50) if kind=="equipment" else (50,80)
                    self.assertEqual(image.size,(round(w/25.4*dpi),round(h/25.4*dpi)))
                    if kind=="equipment":
                        qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,border=4,box_size=1)
                        qr.add_data(code);qr.make(fit=True)
                        edge=max(1,round(dpi*.2/25.4))+max(1,round(dpi*.16/25.4))+1
                        qr.box_size=(image.width-2*edge)//(qr.modules_count+8)
                        expected=qr.make_image(fill_color='black',back_color='white').convert('RGB')
                        x=(image.width-expected.width)//2
                        y=image.height-edge-expected.height
                        self.assertIsNone(ImageChops.difference(image.convert('RGB').crop((x,y,x+expected.width,y+expected.height)),expected).getbbox())
                        head_y=edge+max(2,round(dpi*.6/25.4))
                        self.assertEqual(image.convert('RGB').getpixel((image.width//2,head_y)),(0,0,0))
        custom=self.client.get("/api/label/KAM-12",params={"width_mm":40,"height_mm":60},headers=headers)
        self.assertEqual(custom.status_code,200)
        with Image.open(BytesIO(custom.content)) as image:
            self.assertEqual(image.size,(round(40/25.4*203),round(60/25.4*203)))
        provisional=self.client.get("/api/label/PREVIEW",params={"name":"КЦ-99","kind":"equipment"},headers=headers)
        self.assertEqual(provisional.status_code,200)
        with Image.open(BytesIO(provisional.content)) as image:
            self.assertEqual(image.size,(round(30/25.4*203),round(50/25.4*203)))
        pdf=self.client.post("/api/export_labels",json={"codes":["KAM-12","KOR-1"],"copies":2},headers=headers)
        self.assertEqual(pdf.status_code,200)
        self.assertTrue(pdf.content.startswith(b"%PDF-"))
        self.assertEqual(pdf.headers["content-type"],"application/pdf")

    def test_concurrent_checkout_and_retry_of_return(self):
        session = "smoke-session"
        with closing(sqlite3.connect(self.database)) as conn, conn:
            conn.executemany("INSERT INTO users(tg_id, full_name, is_registered) VALUES (?, ?, 1)",
                             [(2, "Smoke employee"), (3, "Smoke recipient")])
            conn.execute("INSERT INTO web_sessions VALUES (?, ?, ?)",
                         (self.main["web_digest"](session), 2, int(time.time()) + 300))
            conn.execute("INSERT INTO items(code, name) VALUES (?, ?)", (CODE, "Smoke equipment"))
            location = conn.execute("SELECT id FROM locations WHERE type='storage' LIMIT 1").fetchone()[0]
            conn.execute("INSERT INTO stock VALUES (?, ?, 1)", (CODE, location))

        payload = {"code": CODE, "recipient_id": 3}
        self.assertEqual(self.client.post("/api/checkout", json=payload).status_code, 401)
        headers = {"Cookie": f"{self.main['WEB_COOKIE']}={session}", "Origin": "http://testserver"}

        def checkout():
            with closing(TestClient(self.main["app"])) as client:
                return client.post("/api/checkout", json=payload, headers=headers).status_code

        with ThreadPoolExecutor(max_workers=2) as workers:
            attempts = [workers.submit(checkout) for _ in range(2)]
            self.assertEqual(sorted(attempt.result() for attempt in attempts), [200, 409])

        def stock_and_checkouts():
            with closing(sqlite3.connect(self.database)) as conn:
                stock = conn.execute("SELECT location_id, quantity FROM stock WHERE item_code=?", (CODE,)).fetchall()
                rows = conn.execute("SELECT user_id, giver_id, returned_at IS NOT NULL FROM checkouts WHERE item_code=?",
                                    (CODE,)).fetchall()
                return stock, rows

        self.assertEqual(stock_and_checkouts(), ([], [(3, 2, 0)]))
        self.assertEqual(self.client.post("/api/return", params={"code": CODE}, headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/api/return", params={"code": CODE}, headers=headers).status_code, 400)
        self.assertEqual(stock_and_checkouts(), ([(location, 1)], [(3, 2, 1)]))


if __name__ == "__main__":
    unittest.main()
