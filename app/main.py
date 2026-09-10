import os, sqlite3, hashlib, secrets, base64, io
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import qrcode

BASE=Path(__file__).resolve().parent
DB=BASE/'apg.sqlite3'; UP=BASE/'static'/'uploads'; UP.mkdir(parents=True,exist_ok=True)
app=FastAPI(title='APG — Авто Партнёрская Группа')
app.add_middleware(SessionMiddleware, secret_key=os.getenv('APG_SECRET_KEY','dev-apg-change-me'))
app.mount('/static',StaticFiles(directory=BASE/'static'),name='static')

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init():
    c=db(); c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL,active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,description TEXT DEFAULT '',logo TEXT DEFAULT '',address TEXT DEFAULT '',phone TEXT DEFAULT '',hours TEXT DEFAULT '',active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS offers(id INTEGER PRIMARY KEY AUTOINCREMENT,company_id INTEGER NOT NULL,title TEXT NOT NULL,description TEXT DEFAULT '',discount TEXT DEFAULT '',valid_until TEXT DEFAULT '',image TEXT DEFAULT '',status TEXT DEFAULT 'pending',created_at TEXT NOT NULL,FOREIGN KEY(company_id) REFERENCES companies(id));
    CREATE TABLE IF NOT EXISTS gallery(id INTEGER PRIMARY KEY AUTOINCREMENT,company_id INTEGER NOT NULL,title TEXT DEFAULT '',caption TEXT DEFAULT '',image TEXT NOT NULL,sort_order INTEGER DEFAULT 0,active INTEGER DEFAULT 1,FOREIGN KEY(company_id) REFERENCES companies(id));
    CREATE TABLE IF NOT EXISTS services(id INTEGER PRIMARY KEY AUTOINCREMENT,company_id INTEGER NOT NULL,title TEXT NOT NULL,description TEXT DEFAULT '',price TEXT DEFAULT '',image TEXT DEFAULT '',sort_order INTEGER DEFAULT 0,active INTEGER DEFAULT 1,FOREIGN KEY(company_id) REFERENCES companies(id));
    CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,company_id INTEGER NOT NULL,user_id INTEGER NOT NULL,rating INTEGER NOT NULL,body TEXT DEFAULT '',status TEXT DEFAULT 'pending',created_at TEXT NOT NULL,FOREIGN KEY(company_id) REFERENCES companies(id));
    CREATE TABLE IF NOT EXISTS cars(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,model TEXT DEFAULT '',year TEXT DEFAULT '',plate TEXT DEFAULT '',vin TEXT DEFAULT '',mileage TEXT DEFAULT '',photo TEXT DEFAULT '',FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,car_id INTEGER,company_id INTEGER,title TEXT NOT NULL,note TEXT DEFAULT '',service_date TEXT DEFAULT '',FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS favorites(user_id INTEGER NOT NULL,company_id INTEGER NOT NULL,PRIMARY KEY(user_id,company_id));
    CREATE TABLE IF NOT EXISTS qr_tokens(token TEXT PRIMARY KEY,offer_id INTEGER NOT NULL,user_id INTEGER NOT NULL,expires_at TEXT NOT NULL,used INTEGER DEFAULT 0);
    ''')
    now=datetime.now(timezone.utc).isoformat()
    def add(email,pw,name,role):
        if not c.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone(): c.execute('INSERT INTO users(email,password,name,role,created_at) VALUES(?,?,?,?,?)',(email,hashpw(pw),name,role,now))
    add('owner@apg.local','apg1234','APG Owner','owner'); add('seller@apg.local','seller1234','APG Seller','seller'); add('user@apg.local','user1234','APG Client','customer')
    if not c.execute('SELECT 1 FROM companies').fetchone(): c.execute("INSERT INTO companies(name,description,address,phone,hours,created_at) VALUES(?,?,?,?,?,?)",('APG Partner Center','Автомобильный партнёр APG','—','—','Пн–Вс 09:00–20:00',now))
    c.commit(); c.close()

def hashpw(p): return hashlib.pbkdf2_hmac('sha256',p.encode(),b'apg-salt',120000).hex()
def user(req):
    uid=req.session.get('uid');
    if not uid:return None
    c=db(); r=c.execute('SELECT id,email,name,role,active FROM users WHERE id=?',(uid,)).fetchone(); c.close(); return dict(r) if r else None
def require(req,roles):
    u=user(req)
    if not u or u['role'] not in roles: raise HTTPException(401,'Требуется авторизация')
    return u
async def savefile(f:UploadFile|None):
    if not f or not f.filename:return ''
    ext=Path(f.filename).suffix.lower()
    if ext not in {'.jpg','.jpeg','.png','.webp'}: raise HTTPException(400,'Поддерживаются JPG, PNG, WEBP')
    data=await f.read()
    if len(data)>8*1024*1024: raise HTTPException(400,'Файл больше 8 МБ')
    name=secrets.token_hex(12)+ext; (UP/name).write_bytes(data); return '/static/uploads/'+name

@app.on_event('startup')
def startup(): init()

@app.get('/',response_class=HTMLResponse)
def home(): return HTML
@app.get('/api/health')
def health(): return {'status':'ok','service':'APG','version':'FULL'}
@app.get('/api/me')
def me(request:Request): return {'user':user(request)}
@app.post('/api/login')
def login(request:Request,email:str=Form(...),password:str=Form(...)):
    c=db(); r=c.execute('SELECT * FROM users WHERE email=? AND password=? AND active=1',(email,hashpw(password))).fetchone(); c.close()
    if not r: raise HTTPException(401,'Неверный email или пароль')
    request.session['uid']=r['id']; return {'ok':True,'user':user(request)}
@app.post('/api/register')
def register(request:Request,email:str=Form(...),password:str=Form(...),name:str=Form(...)):
    if len(password)<6: raise HTTPException(400,'Пароль минимум 6 символов')
    c=db()
    try:c.execute('INSERT INTO users(email,password,name,role,created_at) VALUES(?,?,?,?,?)',(email,hashpw(password),name,'customer',datetime.now(timezone.utc).isoformat())); c.commit()
    except sqlite3.IntegrityError: c.close(); raise HTTPException(400,'Email уже зарегистрирован')
    r=c.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone(); c.close(); request.session['uid']=r['id']; return {'ok':True,'user':user(request)}
@app.post('/api/logout')
def logout(request:Request): request.session.clear(); return {'ok':True}

@app.get('/api/companies')
def companies(request:Request,q:str=''):
    c=db(); rows=c.execute("SELECT * FROM companies WHERE active=1 AND (name LIKE ? OR description LIKE ?)",(f'%{q}%',f'%{q}%')).fetchall(); out=[]
    uid=user(request); uid=uid['id'] if uid else 0
    for r in rows:
        d=dict(r); d['favorite']=bool(c.execute('SELECT 1 FROM favorites WHERE user_id=? AND company_id=?',(uid,r['id'])).fetchone());
        d['offers']=c.execute("SELECT COUNT(*) n FROM offers WHERE company_id=? AND status='active'",(r['id'],)).fetchone()['n']; out.append(d)
    c.close(); return out
@app.get('/api/companies/{cid}')
def company(cid:int):
    c=db(); co=c.execute('SELECT * FROM companies WHERE id=?',(cid,)).fetchone()
    if not co: c.close(); raise HTTPException(404,'Компания не найдена')
    d=dict(co); d['gallery']=[dict(x) for x in c.execute('SELECT * FROM gallery WHERE company_id=? AND active=1 ORDER BY sort_order,id',(cid,))]; d['services']=[dict(x) for x in c.execute('SELECT * FROM services WHERE company_id=? AND active=1 ORDER BY sort_order,id',(cid,))]; d['offers']=[dict(x) for x in c.execute("SELECT * FROM offers WHERE company_id=? AND status='active' ORDER BY id DESC",(cid,))]; d['reviews']=[dict(x) for x in c.execute("SELECT r.*,u.name FROM reviews r JOIN users u ON u.id=r.user_id WHERE r.company_id=? AND r.status='approved' ORDER BY r.id DESC",(cid,))]; c.close(); return d
@app.post('/api/favorites/{cid}')
def favorite(request:Request,cid:int):
    u=require(request,['customer']); c=db(); exists=c.execute('SELECT 1 FROM favorites WHERE user_id=? AND company_id=?',(u['id'],cid)).fetchone();
    if exists:c.execute('DELETE FROM favorites WHERE user_id=? AND company_id=?',(u['id'],cid)); on=False
    else:c.execute('INSERT OR IGNORE INTO favorites VALUES(?,?)',(u['id'],cid)); on=True
    c.commit(); c.close(); return {'favorite':on}

@app.get('/api/offers')
def offers(q:str=''):
    c=db(); r=c.execute("SELECT o.*,c.name company_name,c.logo company_logo FROM offers o JOIN companies c ON c.id=o.company_id WHERE o.status='active' AND c.active=1 AND (o.title LIKE ? OR o.description LIKE ? OR c.name LIKE ?) ORDER BY o.id DESC",(f'%{q}%',f'%{q}%',f'%{q}%')).fetchall(); c.close(); return [dict(x) for x in r]
@app.post('/api/offers/{oid}/qr')
def makeqr(request:Request,oid:int):
    u=require(request,['customer']); c=db(); o=c.execute("SELECT id FROM offers WHERE id=? AND status='active'",(oid,)).fetchone()
    if not o:c.close();raise HTTPException(404,'Предложение недоступно')
    t=secrets.token_urlsafe(18); exp=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(); c.execute('INSERT INTO qr_tokens VALUES(?,?,?,?,0)',(t,oid,u['id'],exp)); c.commit(); c.close(); return {'token':t,'expires_at':exp,'image':f'/api/qr-image/{t}'}
@app.get('/api/qr-image/{token}')
def qrimg(token:str):
    c=db(); r=c.execute('SELECT token FROM qr_tokens WHERE token=?',(token,)).fetchone(); c.close()
    if not r: raise HTTPException(404,'QR не найден')
    img=qrcode.make('APG:'+token); b=io.BytesIO(); img.save(b,format='PNG'); b.seek(0); return StreamingResponse(b,media_type='image/png')
@app.post('/api/redeem')
def redeem(request:Request,token:str=Form(...)):
    u=require(request,['seller','owner']); c=db(); r=c.execute('SELECT q.*,o.company_id FROM qr_tokens q JOIN offers o ON o.id=q.offer_id WHERE q.token=?',(token,)).fetchone()
    if not r:c.close();raise HTTPException(404,'QR не найден')
    if r['used'] or datetime.fromisoformat(r['expires_at'])<datetime.now(timezone.utc):c.close();raise HTTPException(400,'QR уже использован или истёк')
    c.execute('UPDATE qr_tokens SET used=1 WHERE token=?',(token,)); c.commit(); c.close(); return {'ok':True,'message':'Скидка подтверждена'}

@app.get('/api/cars')
def cars(request:Request):
    u=require(request,['customer']); c=db(); r=c.execute('SELECT * FROM cars WHERE user_id=? ORDER BY id DESC',(u['id'],)).fetchall(); c.close(); return [dict(x) for x in r]
@app.post('/api/cars')
async def addcar(request:Request,model:str=Form(''),year:str=Form(''),plate:str=Form(''),vin:str=Form(''),mileage:str=Form(''),photo:UploadFile|None=File(None)):
    u=require(request,['customer']); p=await savefile(photo); c=db(); c.execute('INSERT INTO cars(user_id,model,year,plate,vin,mileage,photo) VALUES(?,?,?,?,?,?,?)',(u['id'],model,year,plate,vin,mileage,p));c.commit();c.close();return {'ok':True}
@app.get('/api/history')
def hist(request:Request):
    u=require(request,['customer']);c=db();r=c.execute('SELECT h.*,c.name company_name FROM history h LEFT JOIN companies c ON c.id=h.company_id WHERE h.user_id=? ORDER BY h.id DESC',(u['id'],)).fetchall();c.close();return [dict(x) for x in r]

@app.get('/api/seller/offers')
def seller_offers(request:Request):
    u=require(request,['seller','owner']);c=db();r=c.execute('SELECT o.*,c.name company_name FROM offers o JOIN companies c ON c.id=o.company_id ORDER BY o.id DESC').fetchall();c.close();return [dict(x) for x in r]
@app.post('/api/seller/offers')
async def seller_add(request:Request,title:str=Form(...),description:str=Form(''),discount:str=Form(''),valid_until:str=Form(''),company_id:int=Form(1),image:UploadFile|None=File(None)):
    u=require(request,['seller','owner']); p=await savefile(image);c=db();c.execute('INSERT INTO offers(company_id,title,description,discount,valid_until,image,status,created_at) VALUES(?,?,?,?,?,?,?,?)',(company_id,title,description,discount,valid_until,p,'pending',datetime.now(timezone.utc).isoformat()));c.commit();c.close();return {'ok':True}
@app.delete('/api/seller/offers/{oid}')
def seller_delete(request:Request,oid:int):
    require(request,['seller','owner']);c=db();c.execute('DELETE FROM offers WHERE id=?',(oid,));c.commit();c.close();return {'ok':True}

@app.get('/api/owner/companies')
def owner_companies(request:Request):
    require(request,['owner']);c=db();r=c.execute('SELECT * FROM companies ORDER BY id DESC').fetchall();c.close();return [dict(x) for x in r]
@app.post('/api/owner/companies')
async def owner_company(request:Request,name:str=Form(...),description:str=Form(''),address:str=Form(''),phone:str=Form(''),hours:str=Form(''),logo:UploadFile|None=File(None)):
    require(request,['owner']);p=await savefile(logo);c=db();c.execute('INSERT INTO companies(name,description,address,phone,hours,logo,created_at) VALUES(?,?,?,?,?,?,?)',(name,description,address,phone,hours,p,datetime.now(timezone.utc).isoformat()));c.commit();c.close();return {'ok':True}
@app.get('/api/owner/offers')
def owner_offers(request:Request):
    require(request,['owner']);c=db();r=c.execute('SELECT o.*,c.name company_name FROM offers o JOIN companies c ON c.id=o.company_id ORDER BY o.id DESC').fetchall();c.close();return [dict(x) for x in r]
@app.patch('/api/owner/offers/{oid}')
def owner_offer(request:Request,oid:int,status:str):
    require(request,['owner']);
    if status not in {'pending','active','rejected','disabled'}:raise HTTPException(400,'Неверный статус')
    c=db();c.execute('UPDATE offers SET status=? WHERE id=?',(status,oid));c.commit();c.close();return {'ok':True}

@app.post('/api/owner/gallery')
async def gallery_add(request:Request,company_id:int=Form(...),title:str=Form(''),caption:str=Form(''),sort_order:int=Form(0),image:UploadFile|None=File(None)):
    require(request,['owner']);p=await savefile(image)
    if not p:raise HTTPException(400,'Нужна фотография')
    c=db();c.execute('INSERT INTO gallery(company_id,title,caption,image,sort_order) VALUES(?,?,?,?,?)',(company_id,title,caption,p,sort_order));c.commit();c.close();return {'ok':True}
@app.delete('/api/owner/gallery/{gid}')
def gallery_del(request:Request,gid:int):
    require(request,['owner']);c=db();c.execute('DELETE FROM gallery WHERE id=?',(gid,));c.commit();c.close();return {'ok':True}
@app.post('/api/owner/services')
async def service_add(request:Request,company_id:int=Form(...),title:str=Form(...),description:str=Form(''),price:str=Form(''),sort_order:int=Form(0),image:UploadFile|None=File(None)):
    require(request,['owner']);p=await savefile(image);c=db();c.execute('INSERT INTO services(company_id,title,description,price,image,sort_order) VALUES(?,?,?,?,?,?)',(company_id,title,description,price,p,sort_order));c.commit();c.close();return {'ok':True}
@app.delete('/api/owner/services/{sid}')
def service_del(request:Request,sid:int):
    require(request,['owner']);c=db();c.execute('DELETE FROM services WHERE id=?',(sid,));c.commit();c.close();return {'ok':True}
@app.post('/api/reviews/{cid}')
def review(request:Request,cid:int,rating:int=Form(...),body:str=Form('')):
    u=require(request,['customer']); rating=max(1,min(5,rating));c=db();c.execute('INSERT INTO reviews(company_id,user_id,rating,body,status,created_at) VALUES(?,?,?,?,?,?)',(cid,u['id'],rating,body,'pending',datetime.now(timezone.utc).isoformat()));c.commit();c.close();return {'ok':True}
@app.get('/api/owner/reviews')
def owner_reviews(request:Request):
    require(request,['owner']);c=db();r=c.execute('SELECT r.*,u.name user_name,c.name company_name FROM reviews r JOIN users u ON u.id=r.user_id JOIN companies c ON c.id=r.company_id ORDER BY r.id DESC').fetchall();c.close();return [dict(x) for x in r]
@app.patch('/api/owner/reviews/{rid}')
def owner_review(request:Request,rid:int,status:str):
    require(request,['owner']);c=db();c.execute('UPDATE reviews SET status=? WHERE id=?',(status,rid));c.commit();c.close();return {'ok':True}

@app.get('/api/stats')
def stats(request:Request):
    require(request,['owner','seller']);c=db(); out={}
    for k,q in [('companies','SELECT COUNT(*) n FROM companies'),('offers','SELECT COUNT(*) n FROM offers'),('active_offers',"SELECT COUNT(*) n FROM offers WHERE status='active'"),('reviews','SELECT COUNT(*) n FROM reviews'),('gallery','SELECT COUNT(*) n FROM gallery'),('services','SELECT COUNT(*) n FROM services')]:out[k]=c.execute(q).fetchone()['n']
    c.close();return out

HTML='''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#050505"><title>APG — Авто Партнёрская Группа</title><link rel="stylesheet" href="/static/style.css"></head><body><div id="app"><div class="boot"><b>APG</b><span>Загрузка системы…</span></div></div><script src="/static/app.js"></script></body></html>'''
