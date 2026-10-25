#!/usr/bin/env python3
"""Generate 420.menow.us law data from the cannabis_laws DB (the source of truth — never hand-edit the JSON).

Writes countries.json (full country cards), laws.json (map ❤️/☠️ markers) and
zone_laws.json (per-zone local cards) into the site's data dir, then prints a summary.
"""
import json, subprocess, sys, os

OUT = sys.argv[1] if len(sys.argv) > 1 else 'data'

# How to reach the database is configuration, not code: LAWS_DB_CMD is any command that reads SQL on stdin and
# prints raw rows (credentials belong in ~/.my.cnf or the container env, never here).
DB_CMD = os.environ.get('LAWS_DB_CMD', 'mariadb --batch --raw -N cannabis_laws')

def rows(sql):
    cmd = ['sh', '-c', DB_CMD]
    out = subprocess.run(cmd, input=sql, text=True, capture_output=True, check=True).stdout.strip()
    return json.loads(out) if out else []

countries = rows("""SELECT JSON_ARRAYAGG(JSON_OBJECT('iso2',c.iso2,'iso_n3',c.iso_n3,'name',c.name,'region',c.region,'status',c.status,
  'confidence',c.confidence,'headline',c.headline,'law',c.law,'punishment',c.punishment,'access',c.access,'tourists',c.tourists,
  'age',c.age,'possession_limit',c.possession_limit,'home_grow',c.home_grow,'medical',c.medical,'death_applies',c.death_applies,
  'death_detail',c.death_detail,'subnational',c.subnational,'at',IF(c.map_at_lon IS NULL,NULL,JSON_ARRAY(c.map_at_lon,c.map_at_lat)),
  'as_of',c.as_of,'sources',(SELECT JSON_ARRAYAGG(s.url) FROM sources s WHERE s.iso2=c.iso2 AND s.tzid IS NULL))) FROM countries c""")
zones = rows("""SELECT JSON_ARRAYAGG(JSON_OBJECT('tzid',z.tzid,'iso2',z.iso2,'where',z.where_text,'status',z.status,'headline',z.headline,
  'points',z.points,'varies',z.varies,'as_of',z.as_of,'source',(SELECT s.url FROM sources s WHERE s.tzid=z.tzid LIMIT 1))) FROM zones z""")
places = rows("""SELECT JSON_ARRAYAGG(JSON_OBJECT('tzid',p.tzid,'place',p.place,'iso2',p.iso2,'lat',p.lat,'lon',p.lon,'iana',p.iana,'where',p.where_text,
  'status',p.status,'headline',p.headline,'points',p.points,'varies',p.varies,'confidence',p.confidence,'death_evidence',p.death_evidence,'as_of',p.as_of,
  'sources',(SELECT JSON_ARRAYAGG(s.url) FROM sources s WHERE s.tzid=p.tzid AND s.place=p.place))) FROM places p""")
for pl in places:
    if isinstance(pl.get('points'), str): pl['points'] = json.loads(pl['points'])
as_of = max([c['as_of'] for c in countries] + [z['as_of'] for z in zones] + [p['as_of'] for p in places])

by = {c['iso2']: c for c in countries}
json.dump({'as_of': as_of, 'countries': by}, open(os.path.join(OUT, 'countries.json'), 'w'), ensure_ascii=False, separators=(',', ':'))

def marker(c):
    m = {'iso_n3': c['iso_n3'], 'iso2': c['iso2'], 'name': c['name'], 'status': c['status'], 'note': c['headline'],
         'source': (c['sources'] or [None])[0], 'confidence': c['confidence']}
    if c['at']: m['at'] = [float(x) for x in c['at']]
    return m
laws = {'as_of': as_of,
        'friendly': [marker(c) for c in countries if c['status'] in ('legal', 'decriminalized')],
        'death': [marker(c) for c in countries if c['status'] == 'death']}
json.dump(laws, open(os.path.join(OUT, 'laws.json'), 'w'), ensure_ascii=False, indent=0)

# Per-place cards: key "tzid|Place" (the zone card is each row's lead place).
json.dump({'as_of': as_of, 'places': {f"{pl['tzid']}|{pl['place']}": {k: v for k, v in pl.items() if k not in ('tzid', 'place')} for pl in places}},
          open(os.path.join(OUT, 'place_laws.json'), 'w'), ensure_ascii=False, indent=0)

zl = {'as_of': as_of, 'zones': {z['tzid']: {k: v for k, v in z.items() if k != 'tzid'} for z in zones}}
for z in zl['zones'].values():
    if isinstance(z.get('points'), str): z['points'] = json.loads(z['points'])
json.dump(zl, open(os.path.join(OUT, 'zone_laws.json'), 'w'), ensure_ascii=False, indent=0)

# SQLite copy for the apps (bundled for offline use, re-downloaded when the law data changes) — same tables as the master.
import sqlite3, tempfile, shutil
hist = rows("""SELECT JSON_ARRAYAGG(JSON_OBJECT('iso2',iso2,'tzid',tzid,'old_status',old_status,'new_status',new_status,
  'old_headline',old_headline,'new_headline',new_headline,'changed_at',changed_at)) FROM history""")
srcs = rows("SELECT JSON_ARRAYAGG(JSON_OBJECT('iso2',iso2,'tzid',tzid,'place',place,'url',url)) FROM sources")
dbp = os.path.join(OUT, '420laws.sqlite'); tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite').name
db = sqlite3.connect(tmp)
db.executescript("""
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE countries (iso2 TEXT PRIMARY KEY, iso_n3 TEXT, name TEXT NOT NULL, region TEXT, status TEXT NOT NULL, confidence TEXT,
  headline TEXT, law TEXT, punishment TEXT, access TEXT, tourists TEXT, age TEXT, possession_limit TEXT, home_grow TEXT, medical TEXT,
  death_applies INTEGER, death_detail TEXT, subnational TEXT, map_at_lon REAL, map_at_lat REAL, as_of TEXT);
CREATE TABLE zones (tzid TEXT PRIMARY KEY, iso2 TEXT, where_text TEXT, status TEXT NOT NULL, headline TEXT, points TEXT, varies TEXT, as_of TEXT);
CREATE TABLE sources (iso2 TEXT, tzid TEXT, place TEXT, url TEXT NOT NULL);
CREATE TABLE places (tzid TEXT NOT NULL, place TEXT NOT NULL, iso2 TEXT, lat REAL, lon REAL, iana TEXT, where_text TEXT, status TEXT NOT NULL,
  headline TEXT, points TEXT, varies TEXT, confidence TEXT, death_evidence TEXT, as_of TEXT, PRIMARY KEY (tzid, place));
CREATE TABLE history (iso2 TEXT, tzid TEXT, old_status TEXT, new_status TEXT, old_headline TEXT, new_headline TEXT, changed_at TEXT);
CREATE INDEX sources_iso2 ON sources(iso2); CREATE INDEX sources_tz ON sources(tzid);
""")
db.execute("INSERT INTO meta VALUES ('as_of', ?)", (as_of,))
db.execute("INSERT INTO meta VALUES ('schema', '1')")
for c in countries:
    at = c['at'] or [None, None]
    db.execute("INSERT INTO countries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (c['iso2'], c['iso_n3'], c['name'], c['region'], c['status'],
        c['confidence'], c['headline'], c['law'], c['punishment'], c['access'], c['tourists'], c['age'], c['possession_limit'], c['home_grow'],
        c['medical'], c['death_applies'], c['death_detail'], c['subnational'], at[0], at[1], c['as_of']))
for z in zones:
    pts = z['points'] if isinstance(z['points'], str) else json.dumps(z['points'], ensure_ascii=False)
    db.execute("INSERT INTO zones VALUES (?,?,?,?,?,?,?,?)", (z['tzid'], z['iso2'], z['where'], z['status'], z['headline'], pts, z['varies'], z['as_of']))
db.executemany("INSERT INTO sources VALUES (?,?,?,?)", [(s['iso2'], s['tzid'], s.get('place'), s['url']) for s in srcs])
for pl in places:
    db.execute("INSERT INTO places VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (pl['tzid'], pl['place'], pl['iso2'], pl['lat'], pl['lon'], pl['iana'], pl['where'],
        pl['status'], pl['headline'], json.dumps(pl['points'], ensure_ascii=False), pl['varies'], pl['confidence'], pl['death_evidence'], pl['as_of']))
db.executemany("INSERT INTO history VALUES (?,?,?,?,?,?,?)", [(h['iso2'], h['tzid'], h['old_status'], h['new_status'], h['old_headline'], h['new_headline'], h['changed_at']) for h in hist])
db.commit(); db.close(); shutil.move(tmp, dbp); os.chmod(dbp, 0o644)

from collections import Counter
print('countries', len(countries), dict(Counter(c['status'] for c in countries)))
print('places', len(places), '|', 'zones', len(zones), '| markers legal/decrim', len(laws['friendly']), 'death', len(laws['death']), '| sqlite', os.path.getsize(dbp), 'bytes')
