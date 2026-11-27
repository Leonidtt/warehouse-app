"""Date-scoped manual camera-report corrections. Never changes stock or checkouts."""
from collections import defaultdict


def person_key(name):
    return ' '.join(str(name or '').split()).casefold().replace('ё', 'е')


def init_camera_overrides(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS camera_report_overrides(
        work_date TEXT NOT NULL, person_key TEXT NOT NULL,
        excluded INTEGER NOT NULL DEFAULT 0 CHECK(excluded IN (0,1)),
        state TEXT NOT NULL DEFAULT '' CHECK(state IN ('','held','delivery')),
        venue TEXT NOT NULL DEFAULT '', PRIMARY KEY(work_date,person_key))''')


def save_camera_override(conn, day, name, action, venue=''):
    key = person_key(name)
    if action == 'reset':
        conn.execute('DELETE FROM camera_report_overrides WHERE work_date=? AND person_key=?', (day,key))
        return
    if action not in ('exclude','held','delivery','venue') or not key or (action == 'venue' and not venue):
        raise ValueError('Некорректная корректировка')
    conn.execute('INSERT OR IGNORE INTO camera_report_overrides(work_date,person_key) VALUES (?,?)',(day,key))
    if action == 'exclude':
        conn.execute('UPDATE camera_report_overrides SET excluded=1 WHERE work_date=? AND person_key=?',(day,key))
    elif action in ('held','delivery'):
        conn.execute('UPDATE camera_report_overrides SET excluded=0,state=? WHERE work_date=? AND person_key=?',(action,day,key))
    else:
        conn.execute('UPDATE camera_report_overrides SET excluded=0,venue=? WHERE work_date=? AND person_key=?',(venue,day,key))


def apply_camera_overrides(conn, report):
    changes = {r['person_key']: dict(r) for r in conn.execute(
        'SELECT * FROM camera_report_overrides WHERE work_date=?',(report['date'],))}
    groups = defaultdict(lambda: {'deliver': [], 'held': []})
    excluded, corrections, unmatched = [], [], []

    def place(person, venue, state, reason=None):
        person = dict(person)
        change = changes.get(person_key(person['name']))
        if change:
            if change['excluded']:
                excluded.append({'name':person['name'],'venue':venue})
                return
            venue = change['venue'] or venue
            state = change['state'] or state
            person['manual'] = True
            corrections.append({'name':person['name'],'venue':change['venue'],'state':change['state']})
        if not venue or state not in ('delivery','held'):
            unmatched.append({'name':person['name'],'reason':reason or 'Уточните площадку и наличие камеры'})
            return
        if state == 'held' or (change and change['state'] == 'delivery'):
            person.pop('suggested_camera',None)
        groups[venue]['held' if state == 'held' else 'deliver'].append(person)

    for group in report['venues']:
        for person in group['deliver']:
            place(person,group['name'],'delivery')
        for person in group['held']:
            place(person,group['name'],'held')
    for person in report['unmatched']:
        place({'name':person['name']},'', '',person['reason'])
    venues = [dict(name=name, **group) for name,group in sorted(groups.items(),key=lambda p:(-len(p[1]['deliver']),p[0].casefold()))]
    return dict(report,venues=venues,unmatched=unmatched,excluded=excluded,corrections=corrections,
                deliver=sum(len(v['deliver']) for v in venues),held=sum(len(v['held']) for v in venues),
                delivery_venues=sum(bool(v['deliver']) for v in venues))
