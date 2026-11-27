"""Import weekly Moscow rota and group camera deliveries by venue. Beta only."""
import base64
import bz2
import hashlib
from collections import defaultdict
from colorsys import hls_to_rgb, rgb_to_hls
import io
import json
import os
import posixpath
import re
import zipfile
import zlib
from datetime import date, datetime, timedelta
from xml.etree import ElementTree as ET
from fastapi import File, Form, Header, HTTPException, Query, UploadFile
from openpyxl.styles.colors import COLOR_INDEX
from pydantic import BaseModel, Field
from release_v184 import active_checkout_rows, held_camera_count
from camera_overrides import person_key, init_camera_overrides, save_camera_override, apply_camera_overrides

N='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RN='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
PN='{http://schemas.openxmlformats.org/package/2006/relationships}'
A='{http://schemas.openxmlformats.org/drawingml/2006/main}'
THEME_COLORS=('lt1','dk1','lt2','dk2','accent1','accent2','accent3','accent4','accent5','accent6','hlink','folHlink')
FROZEN_REVIEW_DATE = date(2026, 11, 21)
DEPARTMENTS={'АДМИН КЦ','АДМИН ТХ','ПЕЧАТНИК КЦ','ТХ','КЦ','РЕЗЕРВ','СТАЖЕРЫ','СТАЖЁРЫ','СТАЖЕРЫ П','СТАЖЁРЫ П'}
PHOTO=re.compile(r'(?<![А-ЯЁ])Ф(?![А-ЯЁ])',re.I)
ABSENCE=re.compile(r'\b(?:БОЛЕЕТ|БОЛЬНИЧ\w*|ОТПУСК\w*|ВЫХ|ВЫХОДН\w*|ОТГУЛ\w*)\b',re.I)
VENUE_ROSTER_VERSION=5


class VenueDeliveryNotes(BaseModel):
    venue: str = Field(min_length=1, max_length=160)
    equipment: str = Field(default='', max_length=3000)
    supplies: str = Field(default='', max_length=3000)

def plain(value):
    return ' '.join(str(value or '').split()).strip()

def fill_color(color,theme,palette):
    if color is None:
        return ''
    rgb=color.get('rgb','')
    if color.get('theme') is not None:
        index=int(color.get('theme'))
        rgb=theme.get(THEME_COLORS[index],'') if 0<=index<len(THEME_COLORS) else ''
    elif color.get('indexed') is not None:
        index=int(color.get('indexed'))
        rgb=palette[index] if 0<=index<len(palette) else ''
    if not re.fullmatch(r'(?:[0-9a-fA-F]{2})?[0-9a-fA-F]{6}',rgb):
        return ''
    rgb=rgb[-6:].upper()
    tint=float(color.get('tint','0'))
    if -1<=tint<=1 and tint:
        h,l,s=rgb_to_hls(*(int(rgb[i:i+2],16)/255 for i in (0,2,4)))
        l=l*(1+tint) if tint<0 else l+(1-l)*tint
        rgb=''.join(f'{round(value*255):02X}' for value in hls_to_rgb(h,l,s))
    return '#'+rgb

def cell_fill_colors(archive,names):
    if 'xl/styles.xml' not in names:
        return []
    theme={}
    if 'xl/theme/theme1.xml' in names:
        root=ET.fromstring(archive.read('xl/theme/theme1.xml'))
        scheme=root.find('.//'+A+'clrScheme')
        if scheme is not None:
            for entry in scheme:
                if len(entry):
                    theme[entry.tag.removeprefix(A)]=entry[0].get('lastClr') or entry[0].get('val','')
    styles=ET.fromstring(archive.read('xl/styles.xml'))
    indexed=styles.findall(N+'colors/'+N+'indexedColors/'+N+'rgbColor')
    palette=[color.get('rgb','') for color in indexed] if indexed else COLOR_INDEX
    fills=[]
    for fill in styles.findall(N+'fills/'+N+'fill'):
        pattern=fill.find(N+'patternFill')
        color=pattern.find(N+'fgColor') if pattern is not None and pattern.get('patternType')=='solid' else None
        fills.append(fill_color(color,theme,palette))
    result=[]
    for style in styles.findall(N+'cellXfs/'+N+'xf'):
        index=int(style.get('fillId','0'))
        result.append(fills[index] if 0<=index<len(fills) else '')
    return result

def sheets_from_xlsx(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        info=z.infolist()
        if len(info)>1500 or sum(x.file_size for x in info)>50_000_000:
            raise ValueError('Таблица слишком большая')
        names=set(z.namelist())
        if 'xl/workbook.xml' not in names or 'xl/_rels/workbook.xml.rels' not in names:
            raise ValueError('Файл не является таблицей Excel')
        style_colors=cell_fill_colors(z,names)
        strings=[]
        if 'xl/sharedStrings.xml' in names:
            root=ET.fromstring(z.read('xl/sharedStrings.xml'))
            strings=[''.join(t.text or '' for t in entry.iter(N+'t')) for entry in root.findall(N+'si')]
        targets={}
        for rel in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')).findall(PN+'Relationship'):
            if '/worksheet' not in rel.get('Type','') or rel.get('TargetMode')=='External':
                continue
            target=rel.get('Target','').lstrip('/')
            if not target.startswith('xl/'):
                target=posixpath.normpath('xl/'+target)
            if target.startswith('xl/worksheets/') and target in names:
                targets[rel.get('Id')]=target
        book=ET.fromstring(z.read('xl/workbook.xml'))
        settings=book.find(N+'workbookPr')
        uses_1904=settings is not None and settings.get('date1904') in ('1','true')
        epoch=datetime(1904,1,1) if uses_1904 else datetime(1899,12,30)
        for sheet in book.findall('.//'+N+'sheet'):
            rid=sheet.get(RN+'id')
            if rid not in targets:
                continue
            root=ET.fromstring(z.read(targets[rid]))
            cells,fills={},{}
            for c in root.iter(N+'c'):
                address=c.get('r')
                if address and style_colors:
                    style=int(c.get('s','0'))
                    if 0<=style<len(style_colors) and style_colors[style]:
                        fills[address]=style_colors[style]
                value=c.find(N+'v')
                inline=c.find(N+'is')
                text=(value.text or '') if value is not None else ''
                if c.get('t')=='s' and text:
                    idx=int(text)
                    if idx>=len(strings) or idx<0:
                        continue
                    text=strings[idx]
                elif inline is not None:
                    text=''.join(t.text or '' for t in inline.iter(N+'t'))
                if address and text:
                    cells[address]=plain(text)
            yield sheet.get('name',''),cells,fills,epoch

def excel_date(value,epoch):
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        pass
    for pattern in ('%d.%m.%Y','%d.%m.%y'):
        try:
            return datetime.strptime(value,pattern).date()
        except ValueError:
            continue
    return (epoch+timedelta(days=float(value))).date()

def guess_venue(assignment,names):
    note=plain(assignment).casefold().replace('ё','е')
    for name in sorted(names,key=len,reverse=True):
        label=name.casefold().replace('ё','е')
        if note==label or (len(label)>=4 and re.search(r'(?<!\w)'+re.escape(label)+r'(?!\w)',note)):
            return name
    return ''

def venues_by_color(venues,fills,columns,name_col='A',*,preview=False):
    result={}
    for column in columns:
        choices=defaultdict(set)
        for row,name in venues.items():
            for legend in ((name_col,) if preview else (name_col,column)):
                color=fills.get(legend+str(row))
                if color:
                    choices[color].add(name)
        result[column]={color:next(iter(names)) for color,names in choices.items() if len(names)==1}
    return result

def classify(text,needs_camera,venue):
    if ABSENCE.search(text):
        return 'excluded'
    if not venue and text in ('!','?','-','—'):
        return 'review'
    return 'delivery' if needs_camera else 'no_camera'

def parse_xlsx_schedule(raw, *, preview=False, camera_day=None):
    if len(raw)>8_000_000 or not raw.startswith(b'PK'):
        raise ValueError('Нужен файл Excel .xlsx не больше 8 МБ')
    rows,coverage=[],set()
    weeks={}
    count=0
    for sheet,cells,fills,epoch in sheets_from_xlsx(raw):
        count+=1
        # Find all seven week dates from the header. Three oldest tabs are shifted
        # (F:L or E:K), while newer tabs use D:J.
        days={}
        for col in 'DEFGHIJKLM':
            try:
                date_obj=excel_date(cells.get(col+'2',''),epoch)
                if date(2020,1,1)<=date_obj<=date(2040,12,31):
                    days[col]=date_obj.isoformat()
            except (OverflowError,ValueError,TypeError):
                continue
        if len(days)!=7:
            continue
        dates=[date.fromisoformat(days[col]) for col in sorted(days)]
        if any(dates[i]-dates[i-1]!=timedelta(days=1) for i in range(1,7)):
            continue
        if camera_day and camera_day not in days.values():
            continue
        # The first two tabs have surnames and venue names in B, later tabs in A.
        name_col='B' if plain(cells.get('B4','')).upper()=='МОСКВА' else 'A'
        first_department=next((row for row in range(30,85)
            if plain(cells.get(name_col+str(row),'')).upper() in DEPARTMENTS),None)
        if first_department is None:
            continue
        if preview and any(day in coverage for day in days.values()):
            raise ValueError('Одна дата указана на нескольких листах. Оставьте один лист на неделю.')
        coverage.update(days.values())
        weeks[min(days.values())]=max(days.values())
        venues={row:cells.get(name_col+str(row),'') for row in range(4,first_department)}
        venues={row:name for row,name in venues.items() if name and name.upper() not in ('МОСКВА','ПИТЕР','НИЖНИЙ НОВГОРОД','ТЕСТ')}
        if preview:
            if plain(cells.get(name_col+'4')).upper()!='МОСКВА':
                raise ValueError('В графике отсутствует раздел «Москва»')
            other_city=next((row for row in range(5,first_department)
                if plain(cells.get(name_col+str(row))).upper() in
                ('ПИТЕР','САНКТ-ПЕТЕРБУРГ','СПБ','НИЖНИЙ НОВГОРОД')),first_department)
            venues={row:name for row,name in venues.items() if row<other_city}
            colors={col:venues_by_color(
                {row:name for row,name in venues.items() if cells.get(col+str(row))},
                fills,[col],name_col,preview=True)[col] for col in days}
        else:
            colors=venues_by_color(venues,fills,days,name_col)
        # The current workbook's camera marker is immediately before Monday.
        # Preserve the original import rules for saved schedules.
        camera_col=chr(ord(min(days))-1) if preview else chr(ord(max(days))+1)
        department=''
        for row in range(first_department,350):
            person=cells.get(name_col+str(row),'')
            if person.upper() in DEPARTMENTS:
                department=person.upper()
                continue
            if department not in DEPARTMENTS or not person:
                continue
            roster_photo=PHOTO.search(cells.get(camera_col+str(row),'')) is not None
            for col,day in days.items():
                if camera_day and day!=camera_day:
                    continue
                address=col+str(row)
                assignment=cells.get(address,'')
                fill=fills.get(address,'')
                colored_venue=colors[col].get(fill,'')
                needs_camera=roster_photo or (preview and PHOTO.fullmatch(assignment) is not None)
                if camera_day and not needs_camera:
                    continue
                if assignment or colored_venue or camera_day:
                    venue=colored_venue if preview else colored_venue or guess_venue(assignment,venues.values())
                    rows.append({
                        'work_date':day,'person':person,'department':department,
                        'assignment':assignment,'venue':venue,
                        'venue_color':fill if colored_venue else '',
                        'status':classify(assignment,needs_camera,venue),'sheet':sheet
                    })
    if camera_day and camera_day not in coverage:
        raise ValueError('Дата не найдена в графике. Проверьте файл и выбранную дату.')
    if count<1 or len(coverage)<7 or len(rows)>12000:
        raise ValueError('Не удалось прочитать недельный график')
    if not rows and not camera_day:
        raise ValueError('В файле нет назначений сотрудников')
    return {'rows':rows,'first_date':min(coverage),'last_date':max(coverage),
            'format_version':VENUE_ROSTER_VERSION,'weeks':weeks}

def save_schedule(conn,data,source):
    rows=data['rows']
    if not isinstance(rows,list) or not 0<len(rows)<=12000:
        raise ValueError('В файле нет назначений сотрудников')
    entries=[(r['work_date'],r['person'],r['department'],r['assignment'],
              r.get('venue',''),r.get('venue_color',''),r['status'],r.get('sheet','')) for r in rows]
    first_date,last_date=data['first_date'],data['last_date']
    conn.execute('DELETE FROM delivery_schedule')
    conn.executemany("""INSERT INTO delivery_schedule
        (work_date,person,department,assignment,venue,venue_color,status,sheet) VALUES (?,?,?,?,?,?,?,?)""",
        entries)
    conn.execute("""INSERT INTO delivery_schedule_meta(id,source,updated_at,first_date,last_date,format_version)
        VALUES(1,?,datetime('now'),?,?,?) ON CONFLICT(id) DO UPDATE SET
        source=excluded.source,updated_at=excluded.updated_at,
        first_date=excluded.first_date,last_date=excluded.last_date,
        format_version=excluded.format_version""",
        (source,first_date,last_date,data.get('format_version',1)))

def init_delivery_schedule(conn):
    init_camera_overrides(conn)
    conn.execute("""CREATE TABLE IF NOT EXISTS delivery_schedule(
        id INTEGER PRIMARY KEY AUTOINCREMENT,work_date TEXT NOT NULL,
        person TEXT NOT NULL,department TEXT NOT NULL,assignment TEXT NOT NULL,
        venue TEXT NOT NULL DEFAULT '',venue_color TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL,sheet TEXT NOT NULL DEFAULT '')""")
    if 'venue_color' not in {column[1] for column in conn.execute('PRAGMA table_info(delivery_schedule)')}:
        conn.execute("ALTER TABLE delivery_schedule ADD COLUMN venue_color TEXT NOT NULL DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_delivery_schedule_date ON delivery_schedule(work_date,status)")
    conn.execute("""CREATE TABLE IF NOT EXISTS delivery_schedule_meta(
        id INTEGER PRIMARY KEY CHECK(id=1),source TEXT NOT NULL,
        updated_at TEXT NOT NULL,first_date TEXT NOT NULL,last_date TEXT NOT NULL,
        format_version INTEGER NOT NULL DEFAULT 1)""")
    if 'format_version' not in {column[1] for column in conn.execute('PRAGMA table_info(delivery_schedule_meta)')}:
        conn.execute('ALTER TABLE delivery_schedule_meta ADD COLUMN format_version INTEGER NOT NULL DEFAULT 1')
    conn.execute("""CREATE TABLE IF NOT EXISTS delivery_schedule_notes(
        work_date TEXT NOT NULL,venue TEXT NOT NULL,
        equipment TEXT NOT NULL,supplies TEXT NOT NULL,
        PRIMARY KEY(work_date,venue))""")
    if FROZEN_REVIEW_DATE:
        conn.execute("""CREATE TABLE IF NOT EXISTS delivery_review_snapshot(
            work_date TEXT PRIMARY KEY,
            delivery_json TEXT NOT NULL,
            staff_json TEXT NOT NULL)""")
        if conn.execute('SELECT 1 FROM delivery_review_snapshot WHERE work_date=?',
                        (FROZEN_REVIEW_DATE.isoformat(),)).fetchone():
            return
    seed=os.environ.get('DELIVERY_SCHEDULE_BOOTSTRAP_Z64','').strip()
    if seed and not conn.execute('SELECT 1 FROM delivery_schedule_meta WHERE id=1').fetchone():
        conn.execute('SAVEPOINT delivery_schedule_seed')
        try:
            if len(seed)>128000:
                raise ValueError('Seed too large')
            unpacked=zlib.decompress(base64.b64decode(seed))
            if len(unpacked)>1000000:
                raise ValueError('Unpacked seed too large')
            dataset=json.loads(unpacked)
            save_schedule(conn,dataset,'График МСК · исходная копия')
            print('Beta delivery schedule seeded:',len(dataset['rows']),flush=True)
        except Exception as exc:
            conn.execute('ROLLBACK TO delivery_schedule_seed')
            print('Beta delivery schedule seed error:',type(exc).__name__,str(exc)[:130],flush=True)
        finally:
            conn.execute('RELEASE delivery_schedule_seed')

    # Column B means "Фойе" (foyer), never a camera.
    # Reverse only rows inserted by the previous faulty Beta supplement,
    # keeping the original rows, uploaded schedules and venue notes intact.
    revert_tag='beta-foyer-b-supplement-reverted-2026-11-21'
    source_row=conn.execute("SELECT source FROM delivery_schedule_meta WHERE id=1").fetchone()
    if (source_row and source_row['source']=='График МСК · исходная копия'
            and not conn.execute("SELECT 1 FROM warehouse_release_meta WHERE version=?",(revert_tag,)).fetchone()):
        conn.execute("""CREATE TABLE IF NOT EXISTS delivery_foyer_reverted_rows(
            original_id INTEGER PRIMARY KEY,work_date TEXT NOT NULL,
            person TEXT NOT NULL,department TEXT NOT NULL,assignment TEXT NOT NULL,
            venue TEXT NOT NULL,venue_color TEXT NOT NULL,status TEXT NOT NULL,
            sheet TEXT NOT NULL,reverted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        # Archive exact rows before removing them; IDs in this ledger came from
        # the supplementary import, not from the original Excel roster.
        conn.execute("""INSERT OR IGNORE INTO delivery_foyer_reverted_rows(
            original_id,work_date,person,department,assignment,venue,venue_color,status,sheet)
            SELECT s.id,s.work_date,s.person,s.department,s.assignment,
                s.venue,s.venue_color,s.status,s.sheet
            FROM delivery_schedule s JOIN delivery_roster_supplement_rollback b
              ON b.schedule_id=s.id AND b.work_date=s.work_date
              AND b.person=s.person AND b.sheet=s.sheet
            WHERE s.status='delivery'""") if conn.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
                       AND name='delivery_roster_supplement_rollback'""").fetchone() else None
        removed=conn.execute("""DELETE FROM delivery_schedule WHERE id IN
            (SELECT original_id FROM delivery_foyer_reverted_rows)""").rowcount
        # No manual user edits are touched: uploaded schedules have their own source.
        conn.execute("INSERT INTO warehouse_release_meta(version) VALUES(?)",(revert_tag,))
        print('Beta erroneous foyer-as-camera rows reverted:',removed,flush=True)



    # Private full-roster recovery, derived from the owner's exact Excel copy,
    # delivered via Railway Variables only. Never commit names/roster to Git.
    source_row=conn.execute("SELECT source FROM delivery_schedule_meta WHERE id=1").fetchone()
    verified_blob=os.environ.get('DELIVERY_VERIFIED_ROSTER_BZ64','').strip()
    if not verified_blob:
        verified_blob=''.join(os.environ.get('DELIVERY_VERIFIED_ROSTER_BZ64_'+str(i),'').strip() for i in range(1,4))
    marker='beta-verified-full-weekly-roster-2026-11-21'
    if (verified_blob and source_row and source_row['source']=='График МСК · исходная копия'
            and not conn.execute("SELECT 1 FROM warehouse_release_meta WHERE version=?",(marker,)).fetchone()):
        conn.execute('SAVEPOINT verified_roster')
        try:
            if len(verified_blob)>20000:
                raise ValueError('Verified roster payload too large')
            compressed=base64.b64decode(verified_blob,validate=True)
            decompressor=bz2.BZ2Decompressor()
            decoded=decompressor.decompress(compressed,max_length=650000)
            if not decompressor.eof or len(decoded)>650000:
                raise ValueError('Verified roster expanded too large')
            if hashlib.sha256(decoded).hexdigest()!='d2b60df9a5dfbfd51ad580d77bed9f859c46b6ba08b27745864a5f8431b46402':
                raise ValueError('Verified roster checksum mismatch')
            payload=json.loads(decoded)
            if (not isinstance(payload,dict) or payload.get('v')!=5
                    or payload.get('first_date')!='2026-09-28'
                    or payload.get('last_date')!='2027-02-28'
                    or not isinstance(payload.get('rows'),list) or len(payload['rows'])!=3011):
                raise ValueError('Verified roster metadata mismatch')
            fields=('work_date','person','department','assignment','venue','venue_color','status','sheet')
            rows=[]
            for entry in payload['rows']:
                if (not isinstance(entry,list) or len(entry)!=8
                        or not all(isinstance(x,str) and len(x)<500 for x in entry)
                        or entry[6] not in ('delivery','review','excluded','no_camera')
                        or entry[2] not in DEPARTMENTS):
                    raise ValueError('Invalid verified roster entry')
                day=date.fromisoformat(entry[0]).isoformat()
                if not payload['first_date']<=day<=payload['last_date']:
                    raise ValueError('Verified roster out-of-range date')
                rows.append(dict(zip(fields,entry)))
            conn.execute("""CREATE TABLE IF NOT EXISTS delivery_schedule_pre_verified_20261121
                AS SELECT * FROM delivery_schedule""")
            conn.execute("""CREATE TABLE IF NOT EXISTS delivery_schedule_meta_pre_verified_20261121
                AS SELECT * FROM delivery_schedule_meta""")
            save_schedule(conn,{'rows':rows,'first_date':payload['first_date'],
                'last_date':payload['last_date'],'format_version':VENUE_ROSTER_VERSION},
                'График МСК · проверенный Excel')
            conn.execute("INSERT INTO warehouse_release_meta(version) VALUES(?)",(marker,))
            print('Beta complete verified Excel roster imported:',len(rows),flush=True)
        except (ValueError,TypeError,KeyError,IndexError,EOFError,OSError) as exc:
            conn.execute('ROLLBACK TO verified_roster')
            print('Beta verified roster import error:',type(exc).__name__,str(exc)[:110],flush=True)
        finally:
            conn.execute('RELEASE verified_roster')

    if FROZEN_REVIEW_DATE:
        freeze_review_snapshot(conn)


def camera_name_key(value):
    surname,separator,rest=plain(value).casefold().replace('ё','е').partition(' ')
    surname=re.sub(r'(ов|ев|ин)ой$',r'\1а',surname)
    surname=re.sub(r'(ск|цк)ой$',r'\1ая',surname)
    return surname+separator+rest


def camera_availability(conn,people,*,preview=False):
    if not people:
        return {}
    by_name,by_surname=defaultdict(set),defaultdict(set)
    def index_name(user_id,name):
        key=camera_name_key(name)
        if key:
            by_name[key].add(user_id)
            by_surname[key.split(' ',1)[0]].add(user_id)

    for row in conn.execute("SELECT tg_id,full_name FROM users"):
        index_name(row['tg_id'],row['full_name'])
    cameras={
        row['code'] for row in conn.execute("""SELECT code,kit_body,category,name FROM items
            WHERE kind='equipment' AND is_archived=0""")
        if held_camera_count(row)
    }
    held=defaultdict(int)
    handed=set() if preview else {r['checkout_id'] for r in conn.execute('SELECT checkout_id FROM checkout_handoffs')}
    for row in active_checkout_rows(conn):
        if row['item_code'] not in cameras:
            continue
        user_id=row['user_id']
        recipient=plain(row['taken_for'])
        if not preview and user_id!=row['giver_id'] and recipient and row['id'] not in handed:
            continue
        if preview and recipient and camera_name_key(recipient)!=camera_name_key(row['full_name']):
            # Count the displayed recipient of a legacy checkout, even if its user ID belongs to the giver.
            key=camera_name_key(recipient)
            matches=by_name[key] if ' ' in key else by_surname[key]
            user_id=next(iter(matches)) if len(matches)==1 else ('recipient',key)
        index_name(user_id,recipient or row['full_name'])
        held[user_id]+=1

    result={}
    for person in people:
        key=camera_name_key(person)
        matches=by_name[key] if ' ' in key else by_surname[key]
        parts=key.split()
        if not matches and len(parts)==2:
            matches=by_name[camera_name_key(' '.join(reversed(parts)))]
            initial=parts[1].rstrip('.')
            if preview and len(initial)==1 and not matches:
                prefix=parts[0]+' '+initial
                matches={user_id for full,ids in by_name.items() if full.startswith(prefix) for user_id in ids}
        if preview and not matches:
            result[person]=0
        else:
            result[person]=held[next(iter(matches))] if len(matches)==1 else None
    return result


def camera_preview_data(conn, day, rows):
    by_person=defaultdict(list)
    for row in rows:
        by_person[camera_name_key(row['person'])].append(row)
    assignments=[]
    unmatched=[]
    for matches in by_person.values():
        active={row['venue']:row['person'] for row in matches if row['venue'] and row['status']!='excluded'}
        if len(active)==1:
            assignments.append(next(iter(active.items())))
            continue
        row=matches[0]
        if active:
            reason='В графике несколько площадок'
        elif row['status']=='excluded':
            reason=row['assignment']
        else:
            reason='Московская площадка не указана'
            if row['assignment']:
                reason+=' ('+row['assignment']+')'
        unmatched.append({'name':row['person'],'reason':reason})

    availability=camera_availability(conn,{name for _,name in assignments},preview=True)
    shelf=[row for row in conn.execute("""SELECT i.code,i.name,i.category,i.kit_body,i.buyout_status
        FROM items i WHERE i.kind='equipment' AND i.is_archived=0 AND i.needs_repair=0
          AND trim(coalesce(i.buyout_status,''))<>'' AND EXISTS (
            SELECT 1 FROM stock s WHERE s.item_code=i.code AND s.quantity>0)
          AND NOT EXISTS (SELECT 1 FROM checkouts c WHERE c.item_code=i.code AND c.returned_at IS NULL)
        """) if held_camera_count(row)]
    groups=defaultdict(lambda:{'deliver':[],'held':[]})
    for venue,name in assignments:
        count=availability[name]
        if count is None:
            unmatched.append({'name':name,'reason':venue+' · несколько сотрудников с этой фамилией'})
            continue
        person={'name':name}
        if count:
            groups[venue]['held'].append(person)
        else:
            key=camera_name_key(name)
            cameras=[row for row in shelf if (camera_name_key(row['buyout_status'])==key
                or (' ' not in key and camera_name_key(row['buyout_status']).startswith(key+' ')))]
            if len(cameras)==1:
                camera=cameras[0]
                person['suggested_camera']={'code':camera['code'],'model':camera['kit_body'] or camera['name']}
            groups[venue]['deliver'].append(person)
    venues=[dict(name=name,**group) for name,group in sorted(
        groups.items(),key=lambda pair:(-len(pair[1]['deliver']),pair[0].casefold()))]
    return {'date':day, 'venues':venues, 'unmatched':unmatched,
        'deliver':sum(len(venue['deliver']) for venue in venues),
        'held':sum(len(venue['held']) for venue in venues),
        'delivery_venues':sum(bool(venue['deliver']) for venue in venues)}


def delivery_data(conn,work_date):
    meta=conn.execute('SELECT * FROM delivery_schedule_meta WHERE id=1').fetchone()
    rows=[dict(row) for row in conn.execute("""SELECT person,department,assignment,venue,venue_color,status
        FROM delivery_schedule WHERE work_date=? ORDER BY
        CASE status WHEN 'delivery' THEN 0 WHEN 'review' THEN 1 ELSE 2 END,department,person""",(work_date,))]
    availability=camera_availability(conn,{row['person'] for row in rows if row['status']=='delivery'})
    for row in rows:
        if row['status']=='delivery':
            row['camera_count']=availability[row['person']]
    notes=[dict(row) for row in conn.execute("""SELECT venue,equipment,supplies
        FROM delivery_schedule_notes WHERE work_date=?""",(work_date,))]
    return {'date':work_date,'rows':rows,'notes':notes,'meta':dict(meta) if meta else None}


def staff_data(conn,work_date):
    start=work_date-timedelta(days=work_date.weekday())
    end=start+timedelta(days=6)
    meta=conn.execute('SELECT first_date,last_date,format_version FROM delivery_schedule_meta WHERE id=1').fetchone()
    rows=[dict(row) for row in conn.execute("""SELECT work_date,person,department,
        venue,venue_color,status,assignment FROM delivery_schedule
        WHERE work_date BETWEEN ? AND ?""",(start.isoformat(),end.isoformat()))]
    return {'start':start.isoformat(),'end':end.isoformat(),'rows':rows,
            'meta':dict(meta) if meta else None}


def freeze_review_snapshot(conn):
    work_date=FROZEN_REVIEW_DATE.isoformat()
    delivery=delivery_data(conn,work_date)
    if not delivery['rows']:
        print('Beta delivery review snapshot unavailable for '+work_date,flush=True)
        return
    staff=staff_data(conn,FROZEN_REVIEW_DATE)
    delivery['review_date']=staff['review_date']=work_date
    conn.execute('INSERT INTO delivery_review_snapshot VALUES (?,?,?)',
                 (work_date,json.dumps(delivery,ensure_ascii=False),json.dumps(staff,ensure_ascii=False)))
    print(f"Beta delivery review frozen for {work_date}: {len(delivery['rows'])} day rows, "
          f"{len(staff['rows'])} week rows",flush=True)


def can_view_delivery_schedule(user):
    return bool(user.get('is_registered') and user.get('role') == 'admin' and not user.get('preview_role'))


def register_delivery_schedule(app,get_user,transaction,audit,session):
    def require_admin(init_data):
        user=get_user(init_data)
        if not can_view_delivery_schedule(user):
            raise HTTPException(403,'Недоступно для этой роли')
        return user

    def require_editor(init_data):
        user=require_admin(init_data)
        if FROZEN_REVIEW_DATE:
            raise HTTPException(403,'График заморожен до согласования')
        return user

    def review_snapshot(conn,key):
        work_date=FROZEN_REVIEW_DATE.isoformat()
        row=conn.execute('SELECT delivery_json,staff_json FROM delivery_review_snapshot WHERE work_date=?',
                         (work_date,)).fetchone()
        if row is None:
            raise HTTPException(503,'Снимок графика пока недоступен')
        return json.loads(row[key])

    @app.get('/api/delivery-schedule')
    def delivery_on_date(work_date:str=Query(alias='date'),x_init_data:str=Header(None)):
        require_admin(x_init_data)
        with transaction() as conn:
            if FROZEN_REVIEW_DATE:
                return review_snapshot(conn,'delivery_json')
            try:
                if date.fromisoformat(work_date).isoformat()!=work_date:
                    raise ValueError
            except ValueError:
                raise HTTPException(400,'Некорректная дата') from None
            return delivery_data(conn,work_date)

    @app.get('/api/delivery-schedule/week')
    def staff_week(work_date:date=Query(alias='date'),x_init_data:str=Header(None)):
        require_admin(x_init_data)
        with transaction() as conn:
            if FROZEN_REVIEW_DATE:
                return review_snapshot(conn,'staff_json')
            try:
                return staff_data(conn,work_date)
            except OverflowError:
                raise HTTPException(400,'Некорректная дата') from None

    @app.put('/api/delivery-schedule/venue-notes')
    def update_venue_notes(notes:VenueDeliveryNotes,work_date:date=Query(alias='date'),x_init_data:str=Header(None)):
        user=require_editor(x_init_data)
        venue=plain(notes.venue)
        day=work_date.isoformat()
        equipment=notes.equipment.strip()
        supplies=notes.supplies.strip()
        with transaction() as conn:
            if not venue or not conn.execute("""SELECT 1 FROM delivery_schedule
                    WHERE work_date=? AND venue=? AND status<>'excluded' LIMIT 1""",(day,venue)).fetchone():
                raise HTTPException(404,'Площадка не найдена в графике на эту дату')
            conn.execute("""INSERT INTO delivery_schedule_notes(work_date,venue,equipment,supplies)
                VALUES(?,?,?,?) ON CONFLICT(work_date,venue) DO UPDATE SET
                equipment=excluded.equipment,supplies=excluded.supplies""",(day,venue,equipment,supplies))
            audit(conn,user,'Уточнение плана площадки',day+' · '+venue)
        return {'status':'ok'}

    def read_upload(file, **options):
        if not file.filename or not file.filename.lower().endswith('.xlsx'):
            raise HTTPException(400,'Выберите файл .xlsx')
        raw=file.file.read(8000001)
        try:
            return parse_xlsx_schedule(raw,**options)
        except ValueError as error:
            raise HTTPException(400,str(error)) from None
        except (zipfile.BadZipFile,ET.ParseError,KeyError,IndexError,OSError,RuntimeError,zlib.error):
            raise HTTPException(400,'Не удалось прочитать Excel') from None

    @app.post('/api/delivery-schedule/camera-preview')
    def camera_preview(day:date=Form(...),file:UploadFile=File(...),x_init_data:str=Header(None)):
        require_admin(x_init_data)
        work_date=day.isoformat()
        upload=read_upload(file,preview=True,camera_day=work_date)
        with session() as conn:
            conn.execute('BEGIN')
            return apply_camera_overrides(conn,camera_preview_data(conn,work_date,upload['rows']))

    @app.post('/api/delivery-schedule/camera-correction')
    def camera_correction(day:date=Form(...),name:str=Form(...,max_length=160),
                          action:str=Form(...,max_length=16),venue:str=Form('',max_length=160),
                          file:UploadFile=File(...),x_init_data:str=Header(None)):
        user=require_admin(x_init_data)
        work_date=day.isoformat()
        upload=read_upload(file,preview=True,camera_day=work_date)
        rows=upload['rows']
        name=plain(name)
        if not name or not any(person_key(r['person'])==person_key(name) for r in rows):
            raise HTTPException(404,'Сотрудник не найден в графике на эту дату')
        venue=plain(venue)
        if action=='venue' and venue not in {r['venue'] for r in rows if r['venue']}:
            raise HTTPException(400,'Выберите площадку из графика на эту дату')
        with transaction() as conn:
            try:
                save_camera_override(conn,work_date,name,action,venue)
            except ValueError as exc:
                raise HTTPException(400,str(exc)) from None
            audit(conn,user,'Ручная корректировка сводки камер',work_date+' · '+name+' · '+action+(' · '+venue if action=='venue' else ''))
            return apply_camera_overrides(conn,camera_preview_data(conn,work_date,rows))

    @app.post('/api/delivery-schedule/week-preview')
    def staff_preview(file:UploadFile=File(...),x_init_data:str=Header(None)):
        require_admin(x_init_data)
        return read_upload(file,preview=True)

    @app.post('/api/delivery-schedule/upload')
    def upload_delivery(file:UploadFile=File(...),x_init_data:str=Header(None)):
        user=require_editor(x_init_data)
        data=read_upload(file)
        with transaction() as conn:
            save_schedule(conn,data,'Загружен Excel: '+os.path.basename(file.filename)[:100])
            audit(conn,user,'Обновление графика доставок',str(len(data['rows']))+' записей')
        return {'status':'ok','rows':len(data['rows']),
                'first_date':data['first_date'],'last_date':data['last_date']}
