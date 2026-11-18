"""Production release guard, compact overview and print layout."""
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from contextlib import closing

import qrcode
from PIL import Image, ImageDraw
from fastapi import Header, HTTPException
from fastapi.responses import FileResponse
from warehouse_v18 import label_font, label_dimensions


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


def label_image(code, name, dpi=203, width_mm=50, height_mm=80):
    label_dimensions(width_mm, height_mm)
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
        get_user(x_init_data)
        with session() as conn:
            rows = conn.execute('''SELECT i.code,i.name,i.category,i.kind,i.needs_repair,i.min_stock,
                COALESCE(s.qty,0) AS stock,COALESCE(h.qty,0) AS held,COALESCE(m.unit,'шт.') AS unit,
                EXISTS(SELECT 1 FROM bookings b WHERE b.item_code=i.code AND date('now') BETWEEN b.date_from AND b.date_to) AS booked
                FROM items i LEFT JOIN (SELECT item_code,SUM(quantity) qty FROM stock GROUP BY item_code) s ON s.item_code=i.code
                LEFT JOIN (SELECT item_code,COUNT(*) qty FROM checkouts WHERE returned_at IS NULL GROUP BY item_code) h ON h.item_code=i.code
                LEFT JOIN item_metadata m ON m.code=i.code WHERE i.is_archived=0''').fetchall()
            yesterday = conn.execute("SELECT date('now','-1 day')").fetchone()[0]
            daily = dict(conn.execute('''SELECT (SELECT COUNT(*) FROM checkouts WHERE date(taken_at)=?) AS taken,
                ((SELECT COUNT(*) FROM checkouts WHERE date(returned_at)=?) + (SELECT COALESCE(SUM(quantity),0) FROM consumable_returns WHERE date(created_at)=?)) AS returned,
                (SELECT COALESCE(SUM(quantity),0) FROM writeoffs WHERE date(created_at)=?) AS written_off''', (yesterday,)*4).fetchone())
        counts = dict(stock=0, working=0, repair=0, total=0)
        cats, booked, low = {}, [], []
        for r in rows:
            stock, held = int(r['stock']), int(r['held'])
            if r['kind'] == 'consumable':
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
        return dict(counts=counts, categories=[dict(name=k, **v) for k,v in sorted(cats.items())], booked=booked, low=sorted(low,key=lambda r:r['name'].casefold()), daily=dict(date=yesterday, **daily))

    with session() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS warehouse_release_meta (version TEXT PRIMARY KEY)')
        conn.execute("INSERT OR IGNORE INTO warehouse_release_meta(version) VALUES ('18.2')")
        conn.commit()
