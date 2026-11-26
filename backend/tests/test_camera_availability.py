"""Check the camera report's treatment of open checkouts."""

from contextlib import closing
import sqlite3
import unittest

from delivery_schedule import camera_availability


class CameraAvailabilityTest(unittest.TestCase):
    def test_preview_matches_open_checkouts_and_the_displayed_recipient(self):
        with closing(sqlite3.connect(":memory:")) as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript("""
                CREATE TABLE users(tg_id INTEGER, full_name TEXT);
                CREATE TABLE items(code TEXT, kit_body TEXT, category TEXT, name TEXT,
                                   kind TEXT, is_archived INTEGER);
                CREATE TABLE checkouts(id INTEGER, item_code TEXT, user_id INTEGER,
                    giver_id INTEGER, taken_at TEXT, taken_for TEXT, returned_at TEXT);
                CREATE TABLE checkout_handoffs(checkout_id INTEGER);
                INSERT INTO users VALUES (1,'Семенов Петр'),(2,'Сидорова Анна'),
                    (3,'Котова Мария'),(4,'Зайцева Лидия'),(5,'Тихонова Вера'),
                    (6,'Зайцева Мария');
                INSERT INTO items VALUES
                    ('C1','Canon','Фотоаппараты','Камера','equipment',0),
                    ('C2','Sony','Фотоаппараты','Камера','equipment',0),
                    ('C3','Canon','Фотоаппараты','Камера','equipment',0),
                    ('F1','','Вспышки','Вспышка','equipment',0);
                INSERT INTO checkouts VALUES
                    (1,'C1',2,1,'2026-11-26','Сидорова Анна',NULL),
                    (2,'C2',1,1,'2026-11-26','Котовой',NULL),
                    (3,'C3',5,5,'2026-11-26','','2026-11-27'),
                    (4,'F1',5,5,'2026-11-26','',NULL);
            """)
            people = ["Сидорова", "Котова", "Семенов", "Тихонова", "Зайцева"]
            actual = camera_availability(conn, people, preview=True)
            self.assertEqual(actual, {
                "Сидорова": 1, "Котова": 1, "Семенов": 0, "Тихонова": 0, "Зайцева": None,
            })
            self.assertEqual(camera_availability(conn, ["Сидорова"]), {"Сидорова": 0})
