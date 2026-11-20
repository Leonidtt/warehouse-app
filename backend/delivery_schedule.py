"""Import weekly Moscow rota and show who needs a camera. Beta only."""
import base64
import io
import json
import os
import posixpath
import re
import zipfile
import zlib
from datetime import date, datetime, timedelta
from xml.etree import ElementTree as ET
from fastapi import File, Header, HTTPException, Query, UploadFile

N='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RN='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
PN='{http://schemas.openxmlformats.org/package/2006/relationships}'
DEPARTMENTS={'АДМИН КЦ','АДМИН ТХ','ПЕЧАТНИК КЦ','ТХ','КЦ','РЕЗЕРВ'}
PHOTO=re.compile(r'(?<![А-ЯЁ])Ф(?![А-ЯЁ])',re.I)
ABSENCE=re.compile(r'\b(?:БОЛЕЕТ|БОЛЬНИЧ\w*|ОТПУСК\w*|ВЫХ|ВЫХОДН\w*|ОТГУЛ\w*)\b',re.I)

def plain(value):
    return ' '.join(str(value or '').split()).strip()

def sheets_from_xlsx(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        info=z.infolist()
        if len(info)>1500 or sum(x.file_size for x in info)>50_000_000:
            raise ValueError('Таблица слишком большая')
        names=set(z.namelist())
        if 'xl/workbook.xml' not in names or 'xl/_rels/workbook.xml.rels' not in names:
            raise ValueError('Файл не является таблицей Excel')
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
            cells={}
            for c in root.iter(N+'c'):
                address=c.get('r')
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
            yield sheet.get('name',''),cells,epoch

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

def classify(text):
    if ABSENCE.search(text):
        return 'excluded'
    if text.strip() in ('!','?','-','—'):
        return 'review'
    return 'delivery'

def parse_xlsx_schedule(raw):
    if len(raw)>8_000_000 or not raw.startswith(b'PK'):
        raise ValueError('Нужен файл Excel .xlsx не больше 8 МБ')
    rows,coverage=[],set()
    count=0
    for sheet,cells,epoch in sheets_from_xlsx(raw):
        count+=1
        days={}
        for col in 'DEFGHIJ':
            try:
                date_obj=excel_date(cells.get(col+'2',''),epoch)
                if date(2020,1,1)<=date_obj<=date(2040,12,31):
                    days[col]=date_obj.isoformat()
                    coverage.add(date_obj.isoformat())
            except (OverflowError,ValueError):
                continue
        if not days:
            continue
        venues=[cells.get('A'+str(row),'') for row in range(4,49)]
        venues=[name for name in venues if name and name.upper() not in ('МОСКВА','ПИТЕР','НИЖНИЙ НОВГОРОД','ТЕСТ')]
        department=''
        for row in range(49,350):
            person=cells.get('A'+str(row),'')
            if person.upper() in DEPARTMENTS:
                department=person.upper()
                continue
            if department not in DEPARTMENTS or not person:
                continue
            if not any(PHOTO.search(cells.get(col+str(row),'')) for col in 'BCK'):
                continue
            for col,day in days.items():
                assignment=cells.get(col+str(row),'')
                if assignment:
                    rows.append({
                        'work_date':day,'person':person,'department':department,
                        'assignment':assignment,'venue':guess_venue(assignment,venues),
                        'status':classify(assignment),'sheet':sheet
                    })
    if count<1 or len(coverage)<7 or len(rows)>12000:
        raise ValueError('Не удалось прочитать недельный график')
    if not rows:
        raise ValueError('В файле нет записей с отметкой «Ф»')
    return {'rows':rows,'first_date':min(coverage),'last_date':max(coverage)}

def save_schedule(conn,data,source):
    rows=data['rows']
    if not isinstance(rows,list) or not 0<len(rows)<=12000:
        raise ValueError('В файле нет записей с отметкой Ф')
    entries=[(r['work_date'],r['person'],r['department'],r['assignment'],
              r.get('venue',''),r['status'],r.get('sheet','')) for r in rows]
    first_date,last_date=data['first_date'],data['last_date']
    conn.execute('DELETE FROM delivery_schedule')
    conn.executemany("""INSERT INTO delivery_schedule
        (work_date,person,department,assignment,venue,status,sheet) VALUES (?,?,?,?,?,?,?)""",
        entries)
    conn.execute("""INSERT INTO delivery_schedule_meta(id,source,updated_at,first_date,last_date)
        VALUES(1,?,datetime('now'),?,?) ON CONFLICT(id) DO UPDATE SET
        source=excluded.source,updated_at=excluded.updated_at,
        first_date=excluded.first_date,last_date=excluded.last_date""",
        (source,first_date,last_date))

def init_delivery_schedule(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS delivery_schedule(
        id INTEGER PRIMARY KEY AUTOINCREMENT,work_date TEXT NOT NULL,
        person TEXT NOT NULL,department TEXT NOT NULL,assignment TEXT NOT NULL,
        venue TEXT NOT NULL DEFAULT '',status TEXT NOT NULL,sheet TEXT NOT NULL DEFAULT '')""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_delivery_schedule_date ON delivery_schedule(work_date,status)")
    conn.execute("""CREATE TABLE IF NOT EXISTS delivery_schedule_meta(
        id INTEGER PRIMARY KEY CHECK(id=1),source TEXT NOT NULL,
        updated_at TEXT NOT NULL,first_date TEXT NOT NULL,last_date TEXT NOT NULL)""")
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

def register_delivery_schedule(app,get_user,transaction,audit):
    def require_admin(init_data):
        user=get_user(init_data)
        if not user.get('is_registered') or user.get('role')!='admin':
            raise HTTPException(403,'Недоступно для этой роли')
        return user

    @app.get('/api/delivery-schedule')
    def delivery_on_date(work_date:str=Query(alias='date'),x_init_data:str=Header(None)):
        require_admin(x_init_data)
        try:
            if date.fromisoformat(work_date).isoformat()!=work_date:
                raise ValueError
        except ValueError:
            raise HTTPException(400,'Некорректная дата')
        with transaction() as conn:
            meta=conn.execute('SELECT * FROM delivery_schedule_meta WHERE id=1').fetchone()
            rows=[dict(row) for row in conn.execute("""SELECT person,department,assignment,venue,status
                FROM delivery_schedule WHERE work_date=? ORDER BY
                CASE status WHEN 'delivery' THEN 0 WHEN 'review' THEN 1 ELSE 2 END,department,person""",(work_date,))]
        return {'date':work_date,'rows':rows,'meta':dict(meta) if meta else None}

    @app.post('/api/delivery-schedule/upload')
    def upload_delivery(file:UploadFile=File(...),x_init_data:str=Header(None)):
        user=require_admin(x_init_data)
        if not file.filename or not file.filename.lower().endswith('.xlsx'):
            raise HTTPException(400,'Выберите файл .xlsx')
        raw=file.file.read(8000001)
        try:
            data=parse_xlsx_schedule(raw)
        except ValueError as error:
            raise HTTPException(400,str(error)) from None
        except (zipfile.BadZipFile,ET.ParseError,KeyError,IndexError,OSError,RuntimeError,zlib.error):
            raise HTTPException(400,'Не удалось прочитать Excel') from None
        with transaction() as conn:
            save_schedule(conn,data,'Загружен Excel: '+os.path.basename(file.filename)[:100])
            audit(conn,user,'Обновление графика доставок',str(len(data['rows']))+' записей')
        return {'status':'ok','rows':len(data['rows']),
                'first_date':data['first_date'],'last_date':data['last_date']}
