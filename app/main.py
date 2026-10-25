"""api.420.menow.us — free, read-only API for The Official 420 World Clock.

Live 4:20 data is computed per request from the IANA time-zone database (tzdata package, pinned current);
law data is read from the site's exported files (the master is the law database on this server).
Every JSON response carries an attribution line. GET only; the edge adds rate limiting.
"""
import json, os, time, hashlib
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import tzdata
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

DATA = os.environ.get('DATA_DIR', '/data')
ATTRIBUTION = 'Data: The Official 420 World Clock (420.menow.us) · LIBCSystems LLC'
DISCLAIMER = 'Information and education only — not legal advice. Laws change; check official sources.'
TARGET, HALF = 4 * 60 + 20, 360

app = FastAPI(title='420 World Clock API', version='1.0.0', docs_url='/docs', redoc_url=None,
              description='Free, read-only. Where it is 4:20 right now, the countdown queue, world zones and the law reference.')
# Logo, icons and share image for the tutorial page (J's API artwork, 2026-10-25).
app.mount('/static', StaticFiles(directory=os.path.join(os.path.dirname(__file__), 'static')), name='static')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['GET', 'HEAD', 'OPTIONS'], allow_headers=['*'])

import html as _html, re as _re
from starlette.requests import Request
from starlette.responses import Response

def _linkify(js):
    esc = _html.escape(js)
    esc = _re.sub(r'(&quot;)(https?://[^&\s]+?)(&quot;)', lambda m: f'{m.group(1)}<a href="{m.group(2)}">{m.group(2)}</a>{m.group(3)}', esc)
    esc = _re.sub(r'^(\s*)(&quot;[^&]+?&quot;)(:)', r'\1<span class="k">\2</span>\3', esc, flags=_re.M)
    return esc

@app.middleware('http')
async def browser_view(request: Request, call_next):
    resp = await call_next(request)
    accept = request.headers.get('accept', '')
    if (request.method != 'GET' or not request.url.path.startswith('/v1/') or request.url.path.endswith('.sqlite')
            or 'text/html' not in accept or request.query_params.get('format') == 'json' or resp.headers.get('content-type', '').find('json') < 0):
        return resp
    body = b''.join([chunk async for chunk in resp.body_iterator])
    try: pretty = json.dumps(json.loads(body), indent=2, ensure_ascii=False)
    except Exception: return Response(body, status_code=resp.status_code, media_type='application/json')
    raw = str(request.url.include_query_params(format='json'))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html.escape(request.url.path)} · 420 World Clock API</title><link rel="icon" href="/static/favicon-32.png?v=2">
<style>body{{margin:0;background:#0d1210;color:#eafff0;font:17px/1.5 system-ui,-apple-system,sans-serif}}main{{max-width:900px;margin:0 auto;padding:16px}}
header{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px}}header img{{width:52px;height:52px;border-radius:12px}}
h1{{font-size:1.15rem;margin:0;word-break:break-all}}nav a,a{{color:#7cc8ff}}nav{{display:flex;gap:14px;flex-wrap:wrap;font-size:.95rem}}
pre{{background:#0a0f0d;border:1px solid #26332d;border-radius:12px;padding:14px;overflow-x:auto;font:15px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap;word-break:break-word}}
.k{{color:#8dffa8}}.note{{color:#a9bdb2;font-size:.9rem}}</style></head><body><main>
<header><img src="/static/icon-64.png?v=2" alt=""><div><h1>GET {_html.escape(request.url.path)}</h1>
<nav><a href="{_html.escape(raw)}">Raw JSON</a><a href="/">How to use this API</a><a href="/docs">Reference</a><a href="https://420.menow.us/">420.menow.us</a></nav></div></header>
<p class="note">This is the clickable view for people. Programs calling this same address receive plain JSON.</p>
<pre>{_linkify(pretty)}</pre></main></body></html>"""
    return HTMLResponse(page, status_code=resp.status_code, headers={'Cache-Control': resp.headers.get('cache-control', 'no-store'), 'Vary': 'Accept'})

_cache = {}
def load(name):
    """Read a data file, re-reading only when the export tool replaces it."""
    p = os.path.join(DATA, name); m = os.path.getmtime(p)
    if name not in _cache or _cache[name][0] != m:
        _cache[name] = (m, json.load(open(p, encoding='utf-8')))
    return _cache[name][1]

LINKS = {'site': 'https://420.menow.us/', 'docs': 'https://api.420.menow.us/', 'reference': 'https://api.420.menow.us/docs'}
def out(body, max_age=60):
    body = {**body, 'links': LINKS, 'attribution': ATTRIBUTION}
    return JSONResponse(body, headers={'Cache-Control': f'public, max-age={max_age}'})

def place(tzid):
    """Short place name for a zone (first part of the site's label, parentheses dropped)."""
    lab = load('zones.json').get(tzid, tzid.split('/')[-1].replace('_', ' '))
    return lab.split(' (')[0].split(' · ')[0]

def dial(local):
    """Signed minutes from the nearest 4:20 on a 12-hour dial (−360…360) and minutes until the next one."""
    m = (local.hour % 12) * 60 + local.minute
    d = m - TARGET
    if d > HALF: d -= 720
    if d < -HALF: d += 720
    return d, (0 if d == 0 else (TARGET - m) % 720)

def zone_rows(now):
    rows = []
    for tzid in load('zones.json'):
        if tzid.startswith('Etc/'): continue                       # UTC−12 is uninhabited
        lt = now.astimezone(ZoneInfo(tzid)); d, u = dial(lt)
        off = int(lt.utcoffset().total_seconds() // 60)
        c = load('places.json').get(tzid)
        rows.append({'tzid': tzid, 'place': place(tzid), 'local_time': lt.strftime('%-I:%M %p'), 'local_iso': lt.isoformat(timespec='minutes'),
                     'earth_url': f'https://earth.google.com/web/@{c[0]},{c[1]},0a,400000d,35y,0h,0t,0r' if c else None,
                     'law_url': f'https://api.420.menow.us/v1/zones/{tzid}/law',
                     'utc_offset': ('UTC' if off == 0 else f"UTC{'+' if off > 0 else '−'}{abs(off) // 60}" + (f":{abs(off) % 60:02d}" if off % 60 else '')),
                     'minutes_from_420': d, 'minutes_until_next_420': u, 'is_420_now': d == 0})
    return rows

@app.get('/', response_class=HTMLResponse, include_in_schema=False)
def home():
    return HTMLResponse(open(os.path.join(os.path.dirname(__file__), 'static', 'index.html'), encoding='utf-8').read())

SITEMAP_PATHS = ['/', '/docs', '/v1/now', '/v1/zones', '/v1/laws', '/v1/meta']
@app.get('/robots.txt', include_in_schema=False)
def robots():
    return Response("User-agent: *\nAllow: /\nSitemap: https://api.420.menow.us/sitemap.xml\n", media_type='text/plain')

@app.get('/sitemap.xml', include_in_schema=False)
def sitemap():
    day = datetime.now(timezone.utc).date().isoformat()
    urls = ''.join(f'<url><loc>https://api.420.menow.us{u}</loc><lastmod>{day}</lastmod></url>' for u in SITEMAP_PATHS)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>', media_type='application/xml')

@app.get('/health', include_in_schema=False)
def health():
    return {'ok': True}

@app.get('/v1/time', summary='Server clock (cross-checked against the US Naval Observatory)')
def server_time():
    t = time.time()
    return JSONResponse({'t': round(t * 1000), 'utc': datetime.fromtimestamp(t, timezone.utc).isoformat(timespec='milliseconds'),
                         'note': 'Server time from authenticated NTP, cross-checked against the US Naval Observatory master clock.', 'attribution': ATTRIBUTION},
                        headers={'Cache-Control': 'no-store'})

@app.get('/v1/now', summary='Where it is 4:20 right now, the closest place, what is next, and the countdown queue')
def now_view():
    now = datetime.now(timezone.utc); rows = zone_rows(now)
    at420 = [r for r in rows if r['is_420_now']]
    closest = min(rows, key=lambda r: (abs(r['minutes_from_420']), r['minutes_from_420']))
    upcoming = sorted([r for r in rows if r['minutes_from_420'] < 0], key=lambda r: r['minutes_until_next_420'])
    # Places that hit 4:20 in the same minute share one queue slot ("moment").
    moments = {}
    for r in upcoming:
        moments.setdefault(r['minutes_until_next_420'], []).append(r['place'])
    queue = [{'in_minutes': k, 'at_utc': (now.replace(second=0, microsecond=0) + timedelta(minutes=k)).isoformat(timespec='minutes'), 'places': v}
             for k, v in sorted(moments.items())][:7]
    return out({'time_utc': now.isoformat(timespec='seconds'), 'is_420_somewhere': bool(at420),
                'seconds_left_in_420_minute': (60 - now.second) if at420 else None,
                'now_at_420': [{'place': r['place'], 'tzid': r['tzid'], 'local_time': r['local_time']} for r in at420],
                'closest': closest, 'next': upcoming[0] if upcoming else None, 'queue': queue}, max_age=15)

@app.get('/v1/zones', summary='Every map zone with its local time and distance from 4:20')
def zones():
    rows = zone_rows(datetime.now(timezone.utc))
    return out({'count': len(rows), 'zones': sorted(rows, key=lambda r: abs(r['minutes_from_420']))}, max_age=15)

@app.get('/v1/zones/{tzid:path}/places', summary='Every place named in one zone row, each with its own law card')
def zone_places(tzid: str):
    labels = load('zones.json')
    if tzid not in labels: raise HTTPException(404, f'Unknown zone {tzid!r}. See /v1/zones for valid tzid values.')
    names = labels[tzid].split(' (')[0].split(' · ')
    pl = load('place_laws.json')['places']; lead = load('zone_laws.json')['zones'].get(tzid)
    rows = [{'place': names[0], 'lead': True, **(lead or {})}] + [{'place': n, 'lead': False, **pl[f'{tzid}|{n}']} for n in names[1:] if f'{tzid}|{n}' in pl]
    return out({'tzid': tzid, 'count': len(rows), 'places': rows, 'disclaimer': DISCLAIMER}, max_age=3600)

@app.get('/v1/zones/{tzid:path}/law', summary='Local law card for one zone (e.g. Europe/Paris)')
def zone_law(tzid: str):
    z = load('zone_laws.json')['zones'].get(tzid)
    if not z: raise HTTPException(404, f'Unknown zone {tzid!r}. See /v1/zones for valid tzid values.')
    return out({'tzid': tzid, **z, 'disclaimer': DISCLAIMER}, max_age=3600)

@app.get('/v1/zones/{tzid:path}', summary='One zone: local time and minutes until its next 4:20 (e.g. America/New_York)')
def one_zone(tzid: str):
    # Declared after /law and /places so those more specific addresses match first.
    row = next((r for r in zone_rows(datetime.now(timezone.utc)) if r['tzid'] == tzid), None)
    if not row: raise HTTPException(404, f'Unknown zone {tzid!r}. See /v1/zones for valid tzid values.')
    return out(row, max_age=15)

SUMMARY = ('iso2', 'name', 'region', 'status', 'headline', 'confidence', 'as_of')
@app.get('/v1/laws', summary='Law status for every country (summary)')
def laws(status: str | None = None):
    c = load('countries.json')
    rows = [{k: v.get(k) for k in SUMMARY} for v in c['countries'].values() if not status or v.get('status') == status]
    return out({'as_of': c['as_of'], 'count': len(rows), 'statuses': ['legal', 'decriminalized', 'medical', 'illegal', 'death'],
                'countries': sorted(rows, key=lambda r: r['name']), 'disclaimer': DISCLAIMER}, max_age=3600)

@app.get('/v1/laws/{iso2}', summary='Full law card for one country (ISO 3166 two-letter code, e.g. NL)')
def law(iso2: str):
    c = load('countries.json')['countries'].get(iso2.upper())
    if not c: raise HTTPException(404, f'Unknown country code {iso2!r}. Use a two-letter ISO code, e.g. NL, CA, SG.')
    return out({**c, 'disclaimer': DISCLAIMER}, max_age=3600)

@app.get('/v1/meta', summary='Data version and the offline database for apps')
def meta():
    p = os.path.join(DATA, '420laws.sqlite'); b = open(p, 'rb').read()
    return out({'data_as_of': load('countries.json')['as_of'], 'schema': 1, 'tzdata': tzdata.IANA_VERSION,
                'sqlite_url': 'https://api.420.menow.us/v1/laws.sqlite', 'sqlite_bytes': len(b), 'sqlite_sha256': hashlib.sha256(b).hexdigest()}, max_age=300)

@app.get('/v1/laws.sqlite', summary='The whole law database as one SQLite file (for offline apps)')
def sqlite_file():
    return FileResponse(os.path.join(DATA, '420laws.sqlite'), media_type='application/vnd.sqlite3', filename='420laws.sqlite',
                        headers={'Cache-Control': 'public, max-age=3600'})
