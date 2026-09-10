import os, sqlite3, secrets, hashlib, hmac, time, uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import qrcode

BASE=Path(__file__).resolve().parent
DB=BASE/'apg.sqlite3'
UPLOADS=BASE/'static'/'uploads'; UPLOADS.mkdir(parents=True,exist_ok=True)
app=FastAPI(title='APG — Авто Партнёрская Группа', version='1.0.0')
app.add_middleware(SessionMiddleware, secret_key=os.getenv('APG_SECRET_KEY','dev-only-change-me'))
app.mount('/static', StaticFiles(directory=BASE/'static'), name='static')

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init():
    c=db(); c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL,company TEXT DEFAULT '',active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS offers(id INTEGER PRIMARY KEY AUTOINCREMENT,seller_id INTEGER NOT NULL,title TEXT NOT NULL,description TEXT DEFAULT '',discount TEXT NOT NULL,valid_until TEXT DEFAULT '',address TEXT DEFAULT '',phone TEXT DEFAULT '',image TEXT DEFAULT '',status TEXT DEFAULT 'pending',views INTEGER DEFAULT 0,redemptions INTEGER DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(seller_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS qr_tokens(id INTEGER PRIMARY KEY AUTOINCREMENT,token TEXT UNIQUE NOT NULL,offer_id INTEGER NOT NULL,customer_id INTEGER NOT NULL,expires_at INTEGER NOT NULL,used INTEGER DEFAULT 0,created_at TEXT NOT NULL,FOREIGN KEY(offer_id) REFERENCES offers(id),FOREIGN KEY(customer_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS cars(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,brand TEXT,model TEXT,year TEXT,plate TEXT,vin TEXT,mileage TEXT,created_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS service_history(id INTEGER PRIMARY KEY AUTOINCREMENT,car_id INTEGER NOT NULL,date TEXT,service TEXT,mileage TEXT,amount TEXT,notes TEXT,created_at TEXT NOT NULL,FOREIGN KEY(car_id) REFERENCES cars(id));
    CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,title TEXT,message TEXT,read INTEGER DEFAULT 0,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,event TEXT,meta TEXT,created_at TEXT NOT NULL);
    ''')
    now=datetime.now(timezone.utc).isoformat()
    for e,p,n,r in [('owner@apg.local','apg1234','APG Owner','owner'),('seller@apg.local','seller1234','Demo Seller','seller'),('user@apg.local','user1234','APG Customer','customer')]:
        if not c.execute('SELECT id FROM users WHERE email=?',(e,)).fetchone(): c.execute('INSERT INTO users(email,password,name,role,company,created_at) VALUES(?,?,?,?,?,?)',(e,hashpw(p),n,r,'',now))
    c.commit(); c.close()

def hashpw(p):
    salt=secrets.token_hex(16); return salt+'$'+hashlib.pbkdf2_hmac('sha256',p.encode(),salt.encode(),180000).hex()
def checkpw(p,x):
    try: salt,d=x.split('$',1); return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',p.encode(),salt.encode(),180000).hex(),d)
    except: return False
def now(): return datetime.now(timezone.utc).isoformat()
def me(request):
    uid=request.session.get('uid');
    if not uid:return None
    c=db(); u=c.execute('SELECT id,email,name,role,company,active FROM users WHERE id=?',(uid,)).fetchone(); c.close()
    return dict(u) if u else None
def require(request,*roles):
    u=me(request)
    if not u or not u['active']: raise HTTPException(401,'Требуется авторизация')
    if roles and u['role'] not in roles: raise HTTPException(403,'Недостаточно прав')
    return u
def log(uid,event,meta=''):
    c=db(); c.execute('INSERT INTO logs(user_id,event,meta,created_at) VALUES(?,?,?,?)',(uid,event,meta,now())); c.commit(); c.close()
def notify(uid,title,msg):
    c=db(); c.execute('INSERT INTO notifications(user_id,title,message,created_at) VALUES(?,?,?,?)',(uid,title,msg,now())); c.commit(); c.close()

@app.on_event('startup')
def startup(): init()
@app.get('/')
def root(): return FileResponse(BASE/'static'/'index.html')
@app.get('/api/health')
def health(): return {'service':'APG','status':'online','version':'full-1.0'}
@app.get('/api/me')
def api_me(request:Request): return me(request) or {'authenticated':False}
@app.post('/api/register')
def register(request:Request,email:str=Form(...),password:str=Form(...),name:str=Form(...)):
    if len(password)<6: raise HTTPException(400,'Пароль минимум 6 символов')
    c=db()
    try:
        cur=c.execute('INSERT INTO users(email,password,name,role,created_at) VALUES(?,?,?,?,?)',(email.strip().lower(),hashpw(password),name.strip() or 'Пользователь','customer',now())); uid=cur.lastrowid; c.commit()
    except sqlite3.IntegrityError: c.close(); raise HTTPException(409,'Email уже зарегистрирован')
    c.close(); request.session['uid']=uid; return {'ok':True,'user':me(request)}
@app.post('/api/login')
def login(request:Request,email:str=Form(...),password:str=Form(...)):
    c=db(); u=c.execute('SELECT * FROM users WHERE email=?',(email.strip().lower(),)).fetchone(); c.close()
    if not u or not checkpw(password,u['password']) or not u['active']: raise HTTPException(401,'Неверный логин или пароль')
    request.session['uid']=u['id']; log(u['id'],'login'); return {'ok':True,'user':me(request)}
@app.post('/api/logout')
def logout(request:Request): request.session.clear(); return {'ok':True}

@app.get('/api/offers')
def offers(request:Request,q:str='',category:str=''):
    u=me(request); c=db(); rows=c.execute("SELECT o.*,u.name seller,u.company FROM offers o JOIN users u ON u.id=o.seller_id WHERE o.status='active' AND u.active=1 AND (o.title LIKE ? OR o.description LIKE ? OR o.address LIKE ?) ORDER BY o.id DESC",(f'%{q}%',f'%{q}%',f'%{q}%')).fetchall(); c.close(); return [dict(x) for x in rows]
@app.get('/api/offers/{oid}')
def offer(oid:int):
    c=db(); c.execute('UPDATE offers SET views=views+1 WHERE id=?',(oid,)); r=c.execute("SELECT o.*,u.name seller,u.company FROM offers o JOIN users u ON u.id=o.seller_id WHERE o.id=? AND o.status='active'",(oid,)).fetchone(); c.commit(); c.close()
    if not r: raise HTTPException(404,'Предложение не найдено')
    return dict(r)

async def save_upload(file:Optional[UploadFile]):
    if not file or not file.filename:return ''
    ext=Path(file.filename).suffix.lower()
    if ext not in {'.jpg','.jpeg','.png','.webp'}: raise HTTPException(400,'Разрешены JPG, PNG, WEBP')
    data=await file.read()
    if len(data)>8*1024*1024: raise HTTPException(400,'Файл больше 8 МБ')
    name=uuid.uuid4().hex+ext; (UPLOADS/name).write_bytes(data); return '/static/uploads/'+name

@app.get('/api/seller/offers')
def seller_offers(request:Request):
    u=require(request,'seller'); c=db(); r=c.execute('SELECT * FROM offers WHERE seller_id=? ORDER BY id DESC',(u['id'],)).fetchall(); c.close(); return [dict(x) for x in r]
@app.post('/api/seller/offers')
async def create_offer(request:Request,title:str=Form(...),description:str=Form(''),discount:str=Form(...),valid_until:str=Form(''),address:str=Form(''),phone:str=Form(''),image:Optional[UploadFile]=File(None)):
    u=require(request,'seller'); img=await save_upload(image); c=db(); cur=c.execute('INSERT INTO offers(seller_id,title,description,discount,valid_until,address,phone,image,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(u['id'],title,description,discount,valid_until,address,phone,img,'pending',now(),now())); oid=cur.lastrowid; c.commit(); c.close(); log(u['id'],'offer_create',str(oid));
    owners=db().execute("SELECT id FROM users WHERE role='owner' AND active=1").fetchall()
    for x in owners: notify(x['id'],'Новое предложение',f'Предложение «{title}» ожидает модерации')
    return {'ok':True,'id':oid}
@app.put('/api/seller/offers/{oid}')
async def edit_offer(request:Request,oid:int,title:str=Form(...),description:str=Form(''),discount:str=Form(...),valid_until:str=Form(''),address:str=Form(''),phone:str=Form(''),image:Optional[UploadFile]=File(None)):
    u=require(request,'seller'); c=db(); old=c.execute('SELECT * FROM offers WHERE id=? AND seller_id=?',(oid,u['id'])).fetchone()
    if not old:c.close();raise HTTPException(404,'Предложение не найдено')
    img=await save_upload(image) or old['image']; c.execute('UPDATE offers SET title=?,description=?,discount=?,valid_until=?,address=?,phone=?,image=?,status="pending",updated_at=? WHERE id=?',(title,description,discount,valid_until,address,phone,img,now(),oid));c.commit();c.close();return {'ok':True}
@app.delete('/api/seller/offers/{oid}')
def delete_offer(request:Request,oid:int):
    u=require(request,'seller'); c=db(); r=c.execute('DELETE FROM offers WHERE id=? AND seller_id=?',(oid,u['id'],));c.commit();c.close();return {'ok':bool(r.rowcount)}

@app.get('/api/owner/sellers')
def sellers(request:Request):
    require(request,'owner'); c=db();r=c.execute("SELECT id,email,name,role,company,active,created_at FROM users WHERE role='seller' ORDER BY id DESC").fetchall();c.close();return [dict(x) for x in r]
@app.post('/api/owner/sellers')
def add_seller(request:Request,email:str=Form(...),password:str=Form(...),name:str=Form(...),company:str=Form('')):
    require(request,'owner');c=db()
    try:c.execute('INSERT INTO users(email,password,name,role,company,created_at) VALUES(?,?,?,?,?,?)',(email.strip().lower(),hashpw(password),name,'seller',company,now()));c.commit()
    except sqlite3.IntegrityError:c.close();raise HTTPException(409,'Email уже существует')
    c.close();return {'ok':True}
@app.patch('/api/owner/sellers/{sid}')
def toggle_seller(request:Request,sid:int,active:bool):
    require(request,'owner');c=db();c.execute('UPDATE users SET active=? WHERE id=? AND role="seller"',(1 if active else 0,sid));c.commit();c.close();return {'ok':True}
@app.get('/api/owner/offers')
def owner_offers(request:Request):
    require(request,'owner');c=db();r=c.execute('SELECT o.*,u.name seller,u.email seller_email,u.company FROM offers o JOIN users u ON u.id=o.seller_id ORDER BY CASE status WHEN "pending" THEN 0 ELSE 1 END,o.id DESC').fetchall();c.close();return [dict(x) for x in r]
@app.patch('/api/owner/offers/{oid}')
def moderate(request:Request,oid:int,status:str):
    u=require(request,'owner');
    if status not in {'pending','active','rejected','disabled'}:raise HTTPException(400,'Недопустимый статус')
    c=db();r=c.execute('SELECT * FROM offers WHERE id=?',(oid,)).fetchone();c.execute('UPDATE offers SET status=?,updated_at=? WHERE id=?',(status,now(),oid));c.commit();c.close()
    if r: notify(r['seller_id'],'Статус предложения',f'Предложение «{r["title"]}»: {status}')
    return {'ok':True}
@app.delete('/api/owner/offers/{oid}')
def owner_delete(request:Request,oid:int):
    require(request,'owner');c=db();c.execute('DELETE FROM offers WHERE id=?',(oid,));c.commit();c.close();return {'ok':True}

@app.post('/api/offers/{oid}/qr')
def make_qr(request:Request,oid:int):
    u=require(request,'customer');c=db();r=c.execute("SELECT * FROM offers WHERE id=? AND status='active'",(oid,)).fetchone()
    if not r:c.close();raise HTTPException(404,'Акция недоступна')
    token=secrets.token_urlsafe(24);exp=int(time.time())+300;c.execute('INSERT INTO qr_tokens(token,offer_id,customer_id,expires_at,created_at) VALUES(?,?,?,?,?)',(token,oid,u['id'],exp,now()));c.commit();c.close();return {'token':token,'expires_at':exp,'image':f'/api/qr-image/{token}'}
@app.get('/api/qr-image/{token}')
def qr_image(token:str):
    c=db();r=c.execute('SELECT * FROM qr_tokens WHERE token=?',(token,)).fetchone();c.close()
    if not r:raise HTTPException(404,'QR не найден')
    p=UPLOADS/f'qr_{token}.png';qrcode.make(f'APG:{token}').save(p);return FileResponse(p,media_type='image/png')
@app.post('/api/redeem')
def redeem(request:Request,token:str=Form(...)):
    u=require(request,'seller','owner');c=db();r=c.execute('SELECT q.*,o.title,o.seller_id FROM qr_tokens q JOIN offers o ON o.id=q.offer_id WHERE q.token=?',(token,)).fetchone()
    if not r:c.close();raise HTTPException(404,'QR не найден')
    if r['used']:c.close();raise HTTPException(400,'QR уже использован')
    if r['expires_at']<int(time.time()):c.close();raise HTTPException(400,'QR истёк')
    if u['role']=='seller' and r['seller_id']!=u['id']:c.close();raise HTTPException(403,'Этот QR не для вашего предложения')
    c.execute('UPDATE qr_tokens SET used=1 WHERE id=?',(r['id'],));c.execute('UPDATE offers SET redemptions=redemptions+1 WHERE id=?',(r['offer_id'],));c.commit();c.close();return {'ok':True,'offer':r['title']}

@app.get('/api/cars')
def cars(request:Request):
    u=require(request,'customer');c=db();r=c.execute('SELECT * FROM cars WHERE user_id=? ORDER BY id DESC',(u['id'],)).fetchall();c.close();return [dict(x) for x in r]
@app.post('/api/cars')
def add_car(request:Request,brand:str=Form(''),model:str=Form(''),year:str=Form(''),plate:str=Form(''),vin:str=Form(''),mileage:str=Form('')):
    u=require(request,'customer');c=db();c.execute('INSERT INTO cars(user_id,brand,model,year,plate,vin,mileage,created_at) VALUES(?,?,?,?,?,?,?,?)',(u['id'],brand,model,year,plate,vin,mileage,now()));c.commit();c.close();return {'ok':True}
@app.delete('/api/cars/{cid}')
def del_car(request:Request,cid:int):
    u=require(request,'customer');c=db();c.execute('DELETE FROM cars WHERE id=? AND user_id=?',(cid,u['id']));c.commit();c.close();return {'ok':True}
@app.get('/api/cars/{cid}/history')
def history(request:Request,cid:int):
    u=require(request,'customer');c=db();ok=c.execute('SELECT id FROM cars WHERE id=? AND user_id=?',(cid,u['id'])).fetchone();r=c.execute('SELECT * FROM service_history WHERE car_id=? ORDER BY date DESC,id DESC',(cid,)).fetchall();c.close();
    if not ok:raise HTTPException(404,'Авто не найдено')
    return [dict(x) for x in r]
@app.post('/api/cars/{cid}/history')
def add_history(request:Request,cid:int,date:str=Form(''),service:str=Form(...),mileage:str=Form(''),amount:str=Form(''),notes:str=Form('')):
    u=require(request,'customer');c=db();ok=c.execute('SELECT id FROM cars WHERE id=? AND user_id=?',(cid,u['id'])).fetchone()
    if not ok:c.close();raise HTTPException(404,'Авто не найдено')
    c.execute('INSERT INTO service_history(car_id,date,service,mileage,amount,notes,created_at) VALUES(?,?,?,?,?,?,?)',(cid,date,service,mileage,amount,notes,now()));c.commit();c.close();return {'ok':True}

@app.get('/api/notifications')
def notifications(request:Request):
    u=require(request);c=db();r=c.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50',(u['id'],)).fetchall();c.close();return [dict(x) for x in r]
@app.post('/api/notifications/read')
def notifications_read(request:Request):
    u=require(request);c=db();c.execute('UPDATE notifications SET read=1 WHERE user_id=?',(u['id'],));c.commit();c.close();return {'ok':True}
@app.get('/api/stats')
def stats(request:Request):
    u=require(request);c=db()
    if u['role']=='owner':
        s={'sellers':c.execute("SELECT COUNT(*) n FROM users WHERE role='seller'").fetchone()['n'],'offers':c.execute('SELECT COUNT(*) n FROM offers').fetchone()['n'],'pending':c.execute("SELECT COUNT(*) n FROM offers WHERE status='pending'").fetchone()['n'],'active':c.execute("SELECT COUNT(*) n FROM offers WHERE status='active'").fetchone()['n'],'redemptions':c.execute('SELECT COALESCE(SUM(redemptions),0) n FROM offers').fetchone()['n']}
    elif u['role']=='seller':
        s={'offers':c.execute('SELECT COUNT(*) n FROM offers WHERE seller_id=?',(u['id'],)).fetchone()['n'],'pending':c.execute("SELECT COUNT(*) n FROM offers WHERE seller_id=? AND status='pending'",(u['id'],)).fetchone()['n'],'active':c.execute("SELECT COUNT(*) n FROM offers WHERE seller_id=? AND status='active'",(u['id'],)).fetchone()['n'],'views':c.execute('SELECT COALESCE(SUM(views),0) n FROM offers WHERE seller_id=?',(u['id'],)).fetchone()['n'],'redemptions':c.execute('SELECT COALESCE(SUM(redemptions),0) n FROM offers WHERE seller_id=?',(u['id'],)).fetchone()['n']}
    else:
        s={'offers':c.execute("SELECT COUNT(*) n FROM offers WHERE status='active'").fetchone()['n'],'cars':c.execute('SELECT COUNT(*) n FROM cars WHERE user_id=?',(u['id'],)).fetchone()['n']}
    c.close();return s
