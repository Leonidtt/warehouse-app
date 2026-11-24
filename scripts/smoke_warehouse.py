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
from PIL import Image


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

    def test_only_admin_can_edit_consumable_location_photo(self):
        def headers(session):
            return {"Cookie": f"{self.main['WEB_COOKIE']}={session}", "Origin": "http://testserver"}

        with closing(sqlite3.connect(self.database)) as conn, conn:
            conn.executemany("INSERT OR REPLACE INTO users(tg_id, full_name, role, is_registered) VALUES (?, ?, ?, 1)",
                             [(1, "Admin", "admin"), (2, "Employee", "employee")])
            conn.executemany("INSERT INTO web_sessions VALUES (?, ?, ?)", [
                (self.main["web_digest"](session), user_id, int(time.time()) + 300)
                for user_id, session in [(1, "photo-admin"), (2, "photo-employee")]
            ])
            conn.execute("INSERT INTO items(code, name, kind, photo) VALUES ('C-1', 'Tape', 'consumable', 'original-photo')")
            conn.execute("INSERT INTO items(code, name) VALUES ('E-1', 'Camera')")

        item_path = "/api/items/C-1"
        photo_path = item_path + "/location-photo"
        employee = headers("photo-employee")
        admin = headers("photo-admin")
        with BytesIO() as picture:
            Image.new("RGB", (80, 60), "red").save(picture, "PNG")
            files = {"photo": ("shelf.png", picture.getvalue(), "image/png")}
        self.assertEqual(self.client.get(photo_path, headers=employee).status_code, 404)
        self.assertFalse(self.client.get(item_path, headers=employee).json()["has_location_photo"])
        self.assertEqual(self.client.put(photo_path, headers=employee, files=files).status_code, 403)
        self.assertEqual(self.client.put("/api/items/E-1/location-photo", headers=admin, files=files).status_code, 400)
        self.assertEqual(self.client.put(photo_path, headers=admin, files=files).status_code, 200)
        self.assertEqual(self.client.get(photo_path).status_code, 401)
        self.assertTrue(self.client.get(item_path, headers=employee).json()["has_location_photo"])
        result = self.client.get(photo_path, headers=employee)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers["content-type"], "image/jpeg")
        with Image.open(BytesIO(result.content)) as saved:
            self.assertEqual(saved.size, (80, 60))
        with closing(sqlite3.connect(self.database)) as conn, conn:
            self.assertEqual(conn.execute("SELECT photo FROM items WHERE code='C-1'").fetchone()[0], "original-photo")
            conn.execute("UPDATE items SET is_archived=1 WHERE code='C-1'")
        self.assertEqual(self.client.get(photo_path, headers=employee).status_code, 404)

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
