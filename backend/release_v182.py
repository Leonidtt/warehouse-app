"""Production release guard, compact overview and print layout."""
import os
import sqlite3
import tempfile
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Optional
from contextlib import closing

import qrcode
from PIL import Image, ImageDraw
from fastapi import Header, HTTPException
from fastapi.responses import FileResponse
from warehouse_v18 import label_font, label_dimensions

MOSCOW = ZoneInfo("Europe/Moscow")


def prepare_migration(path, version="18.2"):
    db = Path(path).resolve()
    if not db.is_file() or not db.stat().st_size:
        raise RuntimeError('Рабочая база отсутствует: запуск отменён')
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=15)) as source:
        tables = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'items', 'users', 'locations', 'stock', 'checkouts', 'bookings'}.issubset(tables):
            raise RuntimeError('Рабочая база не соответствует ожидаемой схеме')
        if 'warehouse_release_meta' in tables and source.execute("SELECT 1 FROM warehouse_release_meta WHERE version=?", (version,)).fetchone():
            return
        fd, pending = tempfile.mkstemp(prefix='.warehouse_pre_v182_', suffix='.db', dir=db.parent)
        os.close(fd)
        try:
            with closing(sqlite3.connect(pending)) as dest:
                source.backup(dest)
                if dest.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise RuntimeError('Резервная копия не прошла проверку')
            with open(pending, 'rb') as stream:
                os.fsync(stream.fileno())
            target = db.parent / ('warehouse_pre_v' + version.replace('.','_') + '_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f') + '.db')
            os.replace(pending, target)
            print('Pre-release SQLite snapshot verified:', target.name, flush=True)
        finally:
            if os.path.exists(pending):
                os.unlink(pending)


def label_size(kind, width_mm=None, height_mm=None):
    default_width, default_height = (30, 50) if kind == 'equipment' else (50, 80)
    size = (default_width if width_mm is None else width_mm,
            default_height if height_mm is None else height_mm)
    label_dimensions(*size)
    return size


def equipment_label_image(code, name, dpi, width_mm, height_mm):
    width, height = (round(v / 25.4 * dpi) for v in (width_mm, height_mm))
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    inset = max(1, round(dpi * .2 / 25.4))
    stroke = max(1, round(dpi * .16 / 25.4))
    edge = inset + stroke + 1
    radius = max(4, round(dpi * 1.8 / 25.4))
    gap = max(2, round(dpi * .6 / 25.4))
    head_x = edge + gap
    head_y = edge + gap
    text_pad = max(3, gap)
    text_width = width - 2 * (head_x + text_pad)
    name = ' '.join(str(name).split())
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4, box_size=1)
    qr.add_data(str(code))
    qr.make(fit=True)
    modules = qr.modules_count + 8
    fonts = {}

    def text_layout(size, available_height):
        if size not in fonts:
            fonts[size] = label_font(size)
        font = fonts[size]
        # Keep a short inventory name/number on one line, as on the approved label.
        if len(name) <= 16 and draw.textlength(name, font=font) > text_width:
            return None
        lines, line = [], ''
        for word in name.split():
            joined = (line + ' ' + word).strip()
            if draw.textlength(joined, font=font) <= text_width:
                line = joined
                continue
            if line:
                lines.append(line)
                line = ''
            for char in word:
                if line and draw.textlength(line + char, font=font) > text_width:
                    lines.append(line)
                    line = ''
                line += char
        if line:
            lines.append(line)
        value = '\n'.join(lines)
        spacing = max(1, size // 12)
        bbox = draw.multiline_textbbox((0, 0), value, font=font, spacing=spacing, align='center')
        if bbox[2] - bbox[0] > text_width or bbox[3] - bbox[1] > available_height:
            return None
        return value, font, spacing, bbox

    # Whole-pixel modules and an untouched four-module quiet zone.
    # Maximize QR width first; shrink only if the full title cannot fit.
    min_font = max(11, round(dpi * .055))
    chosen = None
    for scale in range(min((width - 2 * edge) // modules, (height - 2 * edge) // modules), 2, -1):
        side = modules * scale
        qr_y = height - edge - side
        head_bottom = qr_y - gap
        available = head_bottom - head_y - 2 * text_pad
        if available < min_font or not text_layout(min_font, available):
            continue
        low, high = min_font, max(min_font, min(text_width * 2, available * 2))
        best = text_layout(low, available)
        while low <= high:
            mid = (low + high) // 2
            candidate = text_layout(mid, available)
            if candidate:
                best = candidate
                low = mid + 1
            else:
                high = mid - 1
        chosen = scale, qr_y, head_bottom, best
        break
    if not chosen:
        raise HTTPException(400, 'Увеличьте этикетку или сократите название')
    scale, qr_y, head_bottom, (value, font, spacing, bbox) = chosen
    draw.rounded_rectangle((inset, inset, width - inset - 1, height - inset - 1),
                           radius=radius, outline='black', width=stroke)
    draw.rounded_rectangle((head_x, head_y, width - head_x - 1, head_bottom - 1),
                           radius=max(3, radius - gap), fill='black')
    draw.multiline_text(((width - (bbox[2] - bbox[0])) / 2 - bbox[0],
                         head_y + (head_bottom - head_y - (bbox[3] - bbox[1])) / 2 - bbox[1]),
                        value, font=font, spacing=spacing, align='center', fill='white')
    qr.box_size = scale
    rendered = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    image.paste(rendered, ((width - rendered.width) // 2, qr_y))
    return image


def label_image(code, name, dpi=203, width_mm=None, height_mm=None, kind='consumable'):
    width_mm, height_mm = label_size(kind, width_mm, height_mm)
    if kind == 'equipment':
        return equipment_label_image(code, name, dpi, width_mm, height_mm)
    width, height = (round(v / 25.4 * dpi) for v in (width_mm, height_mm))
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    pad = max(2, round(dpi / 25.4))
    usable = width - 2 * pad
    code, name = str(code), ' '.join(str(name).split())
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4, box_size=1)
    qr.add_data(code)
    qr.make(fit=True)
    modules = qr.modules_count + 8
    font_cache = {}

    def measure(text, size, wrap=True, break_words=True):
        if size not in font_cache:
            font_cache[size] = label_font(size)
        font = font_cache[size]
        lines = []
        if draw.textlength(text, font=font) <= usable:
            lines = [text]
        elif not wrap:
            return None
        else:
            line = ''
            for word in text.split():
                joined = (line + ' ' + word).strip()
                if draw.textlength(joined, font=font) <= usable:
                    line = joined
                    continue
                if line:
                    lines.append(line)
                    line = ''
                if not break_words and draw.textlength(word, font=font) > usable:
                    return None
                for ch in word:
                    if line and draw.textlength(line + ch, font=font) > usable:
                        lines.append(line)
                        line = ''
                    line += ch
            if line:
                lines.append(line)
        value = '\n'.join(lines)
        spacing = max(2, size // 9)
        box = draw.multiline_textbbox((0, 0), value, font=font, spacing=spacing, align='center')
        if box[2] - box[0] > usable:
            return None
        return (value, font, spacing, box)

    def height_of(layout):
        return layout[3][3] - layout[3][1]

    def best(text, limit, min_size, wrap=True):
        # Prefer natural whole-word wrapping to a larger font with broken words.
        for break_words in ((False, True) if wrap else (False,)):
            for size in range(min(usable, max(12, limit * 2)), min_size - 1, -1):
                item = measure(text, size, wrap, break_words)
                if item and height_of(item) <= limit:
                    return item
        return None

    # Reserve real readable text first, then use the largest whole-pixel module size.
    min_name = max(11, round(dpi * .095))
    min_code = max(11, round(dpi * .11))
    min_top = measure(name, min_name)
    min_bottom = measure(code, min_code)
    if not min_top or not min_bottom:
        raise HTTPException(400, 'Текст не помещается на выбранной этикетке')
    chosen = None
    for scale in range(min(usable // modules, (height - 4 * pad) // modules), 1, -1):
        side = scale * modules
        remaining = height - side - 2 * pad
        if remaining < height_of(min_top) + height_of(min_bottom) + 2 * pad:
            continue
        # A long name may need several lines; prefer its intrinsic width when dividing the area.
        lo, hi = height_of(min_top) + pad, remaining - height_of(min_bottom) - pad
        top_area = max(lo, min(hi, round(remaining * .54)))
        top = best(name, top_area - pad, min_name)
        bottom = best(code, remaining - top_area - pad, min_code, wrap=False) or best(code, remaining - top_area - pad, min_code)
        if top and bottom:
            chosen = scale, top, bottom, top_area
            break
    if not chosen:
        raise HTTPException(400, 'Увеличьте этикетку или сократите название')
    scale, top, bottom, top_area = chosen
    qr.box_size = scale
    rendered = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    qr_y = pad + top_area
    image.paste(rendered, ((width - rendered.width) // 2, qr_y))

    def write(layout, y, area):
        value, font, spacing, bbox = layout
        draw.multiline_text(((width - (bbox[2] - bbox[0])) / 2 - bbox[0], y + (area - height_of(layout)) / 2 - bbox[1]), value, font=font, spacing=spacing, align='center', fill='black')

    write(top, pad, top_area)
    write(bottom, qr_y + rendered.height, height - pad - qr_y - rendered.height)
    return image


def register_release(app, get_user, session):
    directory = Path(__file__).resolve().parent

    @app.get('/release-v182.css', include_in_schema=False)
    def release_css():
        return FileResponse(directory / 'release_v182.css', media_type='text/css', headers={'Cache-Control': 'no-cache'})

    @app.get('/release-v182.js', include_in_schema=False)
    def release_js():
        return FileResponse(directory / 'release_v182.js', media_type='text/javascript', headers={'Cache-Control': 'no-cache'})

    @app.get('/api/v18/overview')
    def overview(x_init_data: Optional[str] = Header(None)):
        user=get_user(x_init_data)
        with session() as conn:
            rows = conn.execute('''SELECT i.code,i.name,i.category,i.kind,i.needs_repair,i.min_stock,
                COALESCE(s.qty,0) AS stock,COALESCE(h.qty,0) AS held,COALESCE(m.unit,'шт.') AS unit,
                EXISTS(SELECT 1 FROM bookings b WHERE b.item_code=i.code AND date('now') BETWEEN b.date_from AND b.date_to) AS booked
                FROM items i LEFT JOIN (SELECT item_code,SUM(quantity) qty FROM stock GROUP BY item_code) s ON s.item_code=i.code
                LEFT JOIN (SELECT item_code,COUNT(*) qty FROM checkouts WHERE returned_at IS NULL GROUP BY item_code) h ON h.item_code=i.code
                LEFT JOIN item_metadata m ON m.code=i.code WHERE i.is_archived=0''').fetchall()
            printer_locations = conn.execute("""
                SELECT l.id, l.name, l.type, COALESCE(SUM(CASE WHEN i.code IS NOT NULL
                    THEN s.quantity ELSE 0 END), 0) AS count
                FROM locations l
                LEFT JOIN stock s ON s.location_id=l.id AND s.quantity>0
                LEFT JOIN items i ON i.code=s.item_code AND i.is_archived=0
                    AND i.kind='equipment' AND i.category='Принтеры' AND i.needs_repair=0
                GROUP BY l.id, l.name, l.type
                ORDER BY l.id
            """).fetchall()
            today = datetime.now(MOSCOW).date()
            yesterday = today - timedelta(days=1)
            start, end = (
                datetime.combine(day, time.min, tzinfo=MOSCOW).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                for day in (yesterday, today)
            )
            daily = dict(conn.execute("""
                SELECT
                    (SELECT COUNT(*) FROM checkouts WHERE datetime(taken_at) >= :start AND datetime(taken_at) < :end) AS taken,
                    (SELECT COUNT(*) FROM checkouts WHERE datetime(returned_at) >= :start AND datetime(returned_at) < :end)
                        + (SELECT COALESCE(SUM(quantity), 0) FROM consumable_returns
                           WHERE datetime(created_at) >= :start AND datetime(created_at) < :end) AS returned,
                    (SELECT COALESCE(SUM(quantity), 0) FROM writeoffs
                     WHERE datetime(created_at) >= :start AND datetime(created_at) < :end) AS written_off
            """, {"start": start, "end": end}).fetchone())
        counts = dict(stock=0, working=0, repair=0, total=0)
        cats, booked, low = {}, [], []
        consumables = 0
        for r in rows:
            stock, held = int(r['stock']), int(r['held'])
            if r['kind'] == 'consumable':
                consumables += 1
                if r['min_stock'] > 0 and stock <= r['min_stock']:
                    low.append(dict(code=r['code'], name=r['name'], stock=stock, minimum=r['min_stock'], unit=r['unit']))
                continue
            if r['kind'] != 'equipment':
                continue
            if r['booked']:
                booked.append(r['code'])
            cat = cats.setdefault(r['category'] or 'Без категории', dict(stock=0, working=0, repair=0, total=0))
            for target in (counts, cat):
                target['total'] += stock + held
                if r['needs_repair']:
                    target['repair'] += stock + held
                else:
                    target['stock'] += stock
                    target['working'] += held
        return dict(
            counts=counts,
            categories=[dict(name=name, **values) for name, values in sorted(cats.items())],
            booked=booked,
            low=sorted(low, key=lambda row: row['name'].casefold()),
            daily=dict(date=yesterday.isoformat(), **daily) if user['role']=='admin' else None,
            printer_locations=[dict(row) for row in printer_locations],
            consumables=consumables,
        )

    with session() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS warehouse_release_meta (version TEXT PRIMARY KEY)')
        conn.execute("INSERT OR IGNORE INTO warehouse_release_meta(version) VALUES ('18.2')")
        conn.commit()
