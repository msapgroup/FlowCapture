"""FlowCapture early pilot: single-company, authenticated ticket intake."""
import base64, datetime, hashlib, hmac, json, mimetypes, os, secrets, sqlite3, threading, uuid
from email.parser import BytesParser
from email.policy import default
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('FLOWCAPTURE_DATA', ROOT / 'data')).resolve()
DB = DATA / 'flowcapture.sqlite3'
FILES = DATA / 'files'
MAX = 12 * 1024 * 1024
LOCK = threading.Lock()

def db():
    c = sqlite3.connect(DB, timeout=10); c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON'); return c

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def pw_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + '$' + hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 310000).hex()
def verify(password, hashed):
    try: return hmac.compare_digest(pw_hash(password, hashed.split('$')[0]), hashed)
    except (ValueError, TypeError): return False

def init():
    FILES.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','office','front')), active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY, number TEXT NOT NULL, vendor TEXT NOT NULL, date TEXT NOT NULL, customer TEXT NOT NULL, job TEXT NOT NULL, truck TEXT NOT NULL, carrier TEXT NOT NULL, material TEXT NOT NULL, gross TEXT NOT NULL, tare TEXT NOT NULL, net TEXT NOT NULL, quantity TEXT NOT NULL, notes TEXT NOT NULL, rate TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, filename TEXT NOT NULL, filetype TEXT NOT NULL, storage TEXT NOT NULL, owner TEXT NOT NULL REFERENCES users(id), created TEXT NOT NULL, updated TEXT NOT NULL, UNIQUE(number,vendor,date));''')
        name=os.environ.get('FLOWCAPTURE_ADMIN_USER','').strip(); password=os.environ.get('FLOWCAPTURE_ADMIN_PASSWORD','')
        if c.execute('SELECT count(*) FROM users').fetchone()[0] == 0:
            if not name or len(password)<12: raise SystemExit('Set FLOWCAPTURE_ADMIN_USER and FLOWCAPTURE_ADMIN_PASSWORD (at least 12 characters) before first start.')
            c.execute('INSERT INTO users(id,username,password,role) VALUES(?,?,?,?)',(str(uuid.uuid4()),name,pw_hash(password),'admin'))

def record(row):
    return {k:row[k] for k in ('id','number','vendor','date','customer','job','truck','carrier','material','gross','tare','net','quantity','notes','rate','status','filename','owner','created','updated')}
def safe_amount(v):
    from decimal import Decimal, InvalidOperation
    try:
        x=Decimal(str(v)); return x if x.is_finite() and x >= 0 else None
    except (InvalidOperation, ValueError): return None

class Handler(BaseHTTPRequestHandler):
    server_version='FlowCapture/0.1'
    def log_message(self, fmt, *args): pass
    def response(self,status,body,ctype='application/json',extra=None):
        if ctype=='application/json': body=json.dumps(body).encode()
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if extra:
            for k,v in extra.items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(body)
    def json(self):
        size=int(self.headers.get('Content-Length','0'))
        if size<1 or size>65536: raise ValueError('Invalid request size')
        value=json.loads(self.rfile.read(size))
        if not isinstance(value,dict): raise ValueError('Invalid request')
        return value
    def identity(self,c):
        try:
            jar=cookies.SimpleCookie(); jar.load(self.headers.get('Cookie','')); token=jar['fc_session'].value
            digest=hashlib.sha256(token.encode()).hexdigest()
            return c.execute('SELECT users.id,users.username,users.role,sessions.csrf FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token_hash=? AND sessions.expires>? AND users.active=1',(digest,now())).fetchone()
        except (KeyError,cookies.CookieError): return None
    def authorized(self,c,write=False,roles=None):
        u=self.identity(c)
        if not u: self.response(401,{'error':'Please sign in.'}); return None
        if write and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),u['csrf']): self.response(403,{'error':'Invalid session token.'}); return None
        if roles and u['role'] not in roles: self.response(403,{'error':'You do not have permission.'}); return None
        return u
    def do_GET(self):
        path=urlparse(self.path).path
        if path in ('/','/app.js','/style.css','/flowcapture-logo.png'):
            f=ROOT/'static'/('index.html' if path=='/' else path[1:]); self.response(200,f.read_bytes(),mimetypes.guess_type(f.name)[0] or 'application/octet-stream'); return
        with db() as c:
            u=self.authorized(c)
            if not u: return
            if path=='/api/me': self.response(200,{'id':u['id'],'username':u['username'],'role':u['role'],'csrf':u['csrf']}); return
            if path=='/api/tickets':
                rows=c.execute('SELECT * FROM tickets '+('WHERE owner=? ' if u['role']=='front' else '')+'ORDER BY created DESC', (u['id'],) if u['role']=='front' else ()).fetchall(); self.response(200,{'tickets':[record(r) for r in rows]}); return
            if path=='/api/users' and u['role']=='admin': self.response(200,{'users':[dict(r) for r in c.execute('SELECT id,username,role FROM users WHERE active=1 ORDER BY username')]}); return
            parts=path.strip('/').split('/')
            if len(parts)==4 and parts[:2]==['api','tickets'] and parts[3]=='file':
                row=c.execute('SELECT * FROM tickets WHERE id=?',(parts[2],)).fetchone()
                if not row or (u['role']=='front' and row['owner']!=u['id']): self.response(404,{'error':'Not found.'}); return
                f=FILES/row['storage']
                if not f.is_file(): self.response(404,{'error':'File not found.'}); return
                self.response(200,f.read_bytes(),row['filetype'],{'Content-Disposition':'attachment; filename="document'+('.pdf' if row['filetype']=='application/pdf' else '.jpg' if row['filetype']=='image/jpeg' else '.png')+'"','Content-Security-Policy':"default-src 'none'; sandbox"}); return
            self.response(404,{'error':'Not found.'})
    def do_POST(self):
        path=urlparse(self.path).path
        try:
            if path=='/api/login':
                body=self.json(); user=str(body.get('username','')).strip(); password=str(body.get('password',''))
                with db() as c:
                    row=c.execute('SELECT * FROM users WHERE username=? AND active=1',(user,)).fetchone()
                    if not row or not verify(password,row['password']): self.response(401,{'error':'Invalid username or password.'}); return
                    token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32); expiry=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=7)).isoformat()
                    c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row['id'],csrf,expiry))
                    secure='; Secure' if os.environ.get('FLOWCAPTURE_SECURE_COOKIES')=='1' else ''
                    self.response(200,{'ok':True},extra={'Set-Cookie':f'fc_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800{secure}'})
                return
            with db() as c:
                u=self.authorized(c,True)
                if not u: return
                if path=='/api/logout':
                    jar=cookies.SimpleCookie(); jar.load(self.headers.get('Cookie','')); c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(jar['fc_session'].value.encode()).hexdigest(),)); self.response(200,{'ok':True},extra={'Set-Cookie':'fc_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'}); return
                if path=='/api/users':
                    if u['role']!='admin': self.response(403,{'error':'Admin access required.'}); return
                    b=self.json(); username=str(b.get('username','')).strip(); password=str(b.get('password','')); role=b.get('role')
                    if not 3<=len(username)<=80 or len(password)<12 or role not in ('admin','office','front'): raise ValueError('Use a username of 3–80 characters and a password of at least 12 characters.')
                    c.execute('INSERT INTO users(id,username,password,role) VALUES(?,?,?,?)',(str(uuid.uuid4()),username,pw_hash(password),role)); self.response(201,{'ok':True}); return
                if path=='/api/tickets': self.upload(c,u); return
                parts=path.strip('/').split('/')
                if len(parts)==4 and parts[:2]==['api','tickets'] and parts[3]=='review':
                    if u['role'] not in ('admin','office'): self.response(403,{'error':'Office or Admin access required.'}); return
                    b=self.json(); row=c.execute('SELECT * FROM tickets WHERE id=?',(parts[2],)).fetchone()
                    if not row: self.response(404,{'error':'Not found.'}); return
                    rate=safe_amount(b.get('rate','')); qty=safe_amount(b.get('quantity',row['quantity']))
                    if rate is None or qty is None: raise ValueError('Enter a valid non-negative quantity and rate.')
                    c.execute('UPDATE tickets SET rate=?,quantity=?,status=?,updated=? WHERE id=?',(str(rate),str(qty),'Ready',now(),row['id'])); self.response(200,{'ok':True}); return
                self.response(404,{'error':'Not found.'})
        except sqlite3.IntegrityError: self.response(409,{'error':'That ticket (number, vendor, and date) or username already exists.'})
        except (ValueError,KeyError,json.JSONDecodeError): self.response(400,{'error':'Check the form and try again.'})
    def upload(self,c,u):
        n=int(self.headers.get('Content-Length','0'))
        if n<=0 or n>MAX: raise ValueError('Invalid file size')
        ct=self.headers.get('Content-Type','')
        if not ct.startswith('multipart/form-data;'): raise ValueError('Invalid upload')
        msg=BytesParser(policy=default).parsebytes(('Content-Type: '+ct+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+self.rfile.read(n))
        fields={}; file=None
        for part in msg.iter_parts():
            name=part.get_param('name',header='content-disposition'); payload=part.get_payload(decode=True)
            if name=='file': file=(part.get_filename() or '',payload)
            elif name: fields[name]=(payload or b'').decode('utf-8')[:2000].strip()
        keys=['number','vendor','date','customer','job','truck','carrier','material','gross','tare','net','quantity','notes']
        if any(not fields.get(k) for k in ['number','vendor','date','customer','quantity']) or not file or not file[1]: raise ValueError('Missing fields')
        if safe_amount(fields['quantity']) is None: raise ValueError('Invalid quantity')
        datetime.date.fromisoformat(fields['date'])
        raw=file[1]
        if raw.startswith(b'%PDF-'): typ='application/pdf'
        elif raw.startswith(b'\xff\xd8\xff'): typ='image/jpeg'
        elif raw.startswith(b'\x89PNG\r\n\x1a\n'): typ='image/png'
        else: raise ValueError('Unsupported file')
        tid=str(uuid.uuid4()); filename=Path(file[0]).name[:160]; stamp=now(); out=FILES/tid
        with LOCK:
            if c.execute('SELECT 1 FROM tickets WHERE number=? AND vendor=? COLLATE NOCASE AND date=?',(fields['number'],fields['vendor'],fields['date'])).fetchone(): self.response(409,{'error':'A ticket with that number, vendor and date already exists.'}); return
            out.write_bytes(raw)
            try:
                c.execute('INSERT INTO tickets(id,number,vendor,date,customer,job,truck,carrier,material,gross,tare,net,quantity,notes,status,filename,filetype,storage,owner,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (tid,*[fields.get(k,'') for k in keys],'Needs Review',filename,typ,tid,u['id'],stamp,stamp)); c.commit()
            except Exception:
                out.unlink(missing_ok=True); raise
        self.response(201,{'id':tid,'status':'Needs Review'})

def serve():
    init(); addr=os.environ.get('FLOWCAPTURE_HOST','127.0.0.1'); port=int(os.environ.get('PORT','8000'))
    print(f'FlowCapture listening on {addr}:{port}',flush=True); ThreadingHTTPServer((addr,port),Handler).serve_forever()
if __name__=='__main__': serve()
