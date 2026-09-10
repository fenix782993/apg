import os, sqlite3, secrets, hashlib, hmac, time, uuid, json
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
app=FastAPI(title='APG — Авто Партнёрская Группа',version='2.0.0')
app.add_middleware(SessionMiddleware,secret_key=os.getenv('APG_SECRET_KEY','dev-only-change-me'))
app.mount('/static',StaticFiles(directory=BASE/'static'),name='static')

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def now(): return datetime.now(timezone.utc).isoformat()
def hashpw(p):
    salt=secrets.token_hex(16); return salt+'$'+hashlib.pbkdf2_hmac('sha256',p.encode(),salt.encode(),180000).hex()
def checkpw(p,x):
    try:
        salt,d=x.split('$',1); return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',p.encode(),salt.encode(),180000).hex(),d)
    except: return False

def init():
    c=db(); c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL,company TEXT DEFAULT '',active INTEGER DEFAULT 1,avatar TEXT DEFAULT '',created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,description TEXT DEFAULT '',address TEXT DEFAULT '',phone TEXT DEFAULT '',hours TEXT DEFAULT '',logo TEXT DEFAULT '',cover TEXT DEFAULT '',rating REAL DEFAULT 0,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS offers(id INTEGER PRIMARY KEY AUTOINCREMENT,seller_id INTEGER NOT NULL,company_id INTEGER,title TEXT NOT NULL,description TEXT DEFAULT '',discount TEXT DEFAULT '',valid_until TEXT DEFAULT '',address TEXT DEFAULT '',phone TEXT DEFAULT '',image TEXT DEFAULT '',status TEXT DEFAULT 'pending',views INTEGER DEFAULT 0,redemptions INTEGER DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(seller_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS gallery(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT DEFAULT '',image TEXT NOT NULL,caption TEXT DEFAULT '',sort_order INTEGER DEFAULT 0,active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS services(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,description TEXT DEFAULT '',price TEXT DEFAULT '',image TEXT DEFAULT '',active INTEGER DEFAULT 1,sort_order INTEGER DEFAULT 0,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,company_id INTEGER,rating INTEGER NOT NULL,comment TEXT DEFAULT '',approved INTEGER DEFAULT 0,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS qr_tokens(id INTEGER PRIMARY KEY AUTOINCREMENT,token TEXT UNIQUE NOT NULL,offer_id INTEGER NOT NULL,customer_id INTEGER NOT NULL,expires_at INTEGER NOT NULL,used INTEGER DEFAULT 0,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS cars(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,model TEXT,year TEXT,plate TEXT,vin TEXT,mileage TEXT,photo TEXT DEFAULT '',created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS service_history(id INTEGER PRIMARY KEY AUTOINCREMENT,car_id INTEGER NOT NULL,date TEXT,service TEXT,mileage TEXT,amount TEXT,notes TEXT,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS favorites(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,offer_id INTEGER,company_id INTEGER,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,title TEXT,message TEXT,read INTEGER DEFAULT 0,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,event TEXT,meta TEXT,created_at TEXT NOT NULL);
    ''')
    n=now()
    for e,p,name,role in [('owner@apg.local','apg1234','APG Owner','owner'),('seller@apg.local','seller1234','Demo Seller','seller'),('user@apg.local','user1234','APG Customer','customer')]:
        if not c.execute('SELECT id FROM users WHERE email=?',(e,)).fetchone(): c.execute('INSERT INTO users(email,password,name,role,company,created_at) VALUES(?,?,?,?,?,?)',(e,hashpw(p),name,role,'',n))
    # Intentionally no demo gallery/services/offers/reviews: owner creates real content.
    c.commit(); c.close()

@app.on_event('startup')
def startup(): init()

def me(request):
    uid=request.session.get('uid')
    if not uid:return None
    c=db(); u=c.execute('SELECT id,email,name,role,company,active,avatar,created_at FROM users WHERE id=?',(uid,)).fetchone(); c.close()
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

def save_upload(f:UploadFile):
    if not f or not f.filename:return ''
    ext=Path(f.filename).suffix.lower()
    if ext not in {'.jpg','.jpeg','.png','.webp'}: raise HTTPException(400,'Разрешены JPG, PNG, WEBP')
    data=f.file.read()
    if len(data)>8*1024*1024: raise HTTPException(400,'Файл больше 8 МБ')
    name=uuid.uuid4().hex+ext; (UPLOADS/name).write_bytes(data); return '/static/uploads/'+name

@app.get('/')
def root(): return FileResponse(BASE/'static'/'index.html')
@app.get('/api/health')
def health(): return {'status':'ok','version':'2.0.0'}
@app.get('/api/me')
def api_me(request:Request): return me(request) or {'authenticated':False}
@app.post('/api/register')
def register(request:Request,email:str=Form(...),password:str=Form(...),name:str=Form(...)):
    if len(password)<6: raise HTTPException(400,'Пароль минимум 6 символов')
    c=db()
    try: c.execute('INSERT INTO users(email,password,name,role,created_at) VALUES(?,?,?,?,?)',(email.lower().strip(),hashpw(password),name.strip(),'customer',now())); c.commit()
    except sqlite3.IntegrityError: raise HTTPException(400,'Пользователь уже существует')
    u=c.execute('SELECT * FROM users WHERE email=?',(email.lower().strip(),)).fetchone(); c.close(); request.session['uid']=u['id']; return dict(u)
@app.post('/api/login')
def login(request:Request,email:str=Form(...),password:str=Form(...)):
    c=db(); u=c.execute('SELECT * FROM users WHERE email=?',(email.lower().strip(),)).fetchone(); c.close()
    if not u or not checkpw(password,u['password']) or not u['active']: raise HTTPException(401,'Неверный логин или пароль')
    request.session['uid']=u['id']; return me(request)
@app.post('/api/logout')
def logout(request:Request): request.session.clear(); return {'ok':True}

@app.get('/api/content')
def content():
    c=db()
    gallery=[dict(x) for x in c.execute('SELECT * FROM gallery WHERE active=1 ORDER BY sort_order,id DESC')]
    services=[dict(x) for x in c.execute('SELECT * FROM services WHERE active=1 ORDER BY sort_order,id DESC')]
    reviews=[dict(x) for x in c.execute('SELECT r.*,u.name FROM reviews r LEFT JOIN users u ON u.id=r.user_id WHERE r.approved=1 ORDER BY r.id DESC LIMIT 100')]
    c.close(); return {'gallery':gallery,'services':services,'reviews':reviews}

@app.get('/api/offers')
def offers(request:Request,q:str=''):
    c=db(); like='%'+q.strip()+'%'
    rows=c.execute('''SELECT o.*,u.name seller,COALESCE(co.name,u.company,'APG Partner') company_name,co.logo company_logo
      FROM offers o JOIN users u ON u.id=o.seller_id LEFT JOIN companies co ON co.id=o.company_id
      WHERE o.status='active' AND (?='' OR o.title LIKE ? OR o.description LIKE ? OR COALESCE(co.name,'') LIKE ?) ORDER BY o.id DESC''',(q.strip(),like,like,like)).fetchall(); c.close(); return [dict(r) for r in rows]
@app.get('/api/offers/{oid}')
def offer_detail(oid:int):
    c=db(); r=c.execute('''SELECT o.*,u.name seller,co.name company_name,co.description company_description,co.address company_address,co.phone company_phone,co.hours company_hours,co.logo company_logo,co.cover company_cover,co.rating company_rating FROM offers o JOIN users u ON u.id=o.seller_id LEFT JOIN companies co ON co.id=o.company_id WHERE o.id=?''',(oid,)).fetchone()
    if not r: raise HTTPException(404,'Предложение не найдено')
    c.execute('UPDATE offers SET views=views+1 WHERE id=?',(oid,)); c.commit(); c.close(); return dict(r)

@app.post('/api/offers/{oid}/qr')
def create_qr(request:Request,oid:int):
    u=require(request,'customer','owner','seller'); c=db(); o=c.execute('SELECT * FROM offers WHERE id=?',(oid,)).fetchone()
    if not o or o['status']!='active': raise HTTPException(404,'Скидка недоступна')
    if u['role']=='seller' and o['seller_id']!=u['id']: raise HTTPException(403,'Чужая скидка')
    t=secrets.token_urlsafe(24); exp=int(time.time())+300; c.execute('INSERT INTO qr_tokens(token,offer_id,customer_id,expires_at,created_at) VALUES(?,?,?,?,?)',(t,oid,u['id'],exp,now())); c.commit(); c.close(); return {'token':t,'expires_at':exp,'image':f'/api/qr-image/{t}'}
@app.get('/api/qr-image/{token}')
def qr_image(token:str):
    c=db(); r=c.execute('SELECT * FROM qr_tokens WHERE token=?',(token,)).fetchone(); c.close()
    if not r: raise HTTPException(404,'QR не найден')
    p=UPLOADS/f'qr_{token}.png'; qrcode.make('APG|'+token).save(p); return FileResponse(p,media_type='image/png')
@app.post('/api/redeem')
def redeem(request:Request,token:str=Form(...)):
    u=require(request,'seller','owner'); c=db(); r=c.execute('SELECT q.*,o.seller_id,o.title FROM qr_tokens q JOIN offers o ON o.id=q.offer_id WHERE q.token=?',(token,)).fetchone()
    if not r: raise HTTPException(404,'QR не найден')
    if r['used']: raise HTTPException(400,'QR уже использован')
    if r['expires_at']<int(time.time()): raise HTTPException(400,'QR истёк')
    if u['role']=='seller' and r['seller_id']!=u['id']: raise HTTPException(403,'QR другого продавца')
    c.execute('UPDATE qr_tokens SET used=1 WHERE id=?',(r['id'],)); c.execute('UPDATE offers SET redemptions=redemptions+1 WHERE id=?',(r['offer_id'],)); c.commit(); c.close(); return {'ok':True,'offer':r['title']}

@app.get('/api/favorites')
def favorites(request:Request):
    u=require(request); c=db(); rows=c.execute('''SELECT o.*,COALESCE(co.name,u.company,'APG Partner') company_name FROM favorites f JOIN offers o ON o.id=f.offer_id JOIN users u ON u.id=o.seller_id LEFT JOIN companies co ON co.id=o.company_id WHERE f.user_id=? ORDER BY f.id DESC''',(u['id'],)).fetchall(); c.close(); return [dict(x) for x in rows]
@app.post('/api/favorites/{oid}')
def toggle_fav(request:Request,oid:int):
    u=require(request,'customer'); c=db(); x=c.execute('SELECT id FROM favorites WHERE user_id=? AND offer_id=?',(u['id'],oid)).fetchone()
    if x: c.execute('DELETE FROM favorites WHERE id=?',(x['id'],)); result=False
    else: c.execute('INSERT INTO favorites(user_id,offer_id,created_at) VALUES(?,?,?)',(u['id'],oid,now())); result=True
    c.commit(); c.close(); return {'favorite':result}

@app.post('/api/reviews')
def add_review(request:Request,company_id:Optional[int]=Form(None),rating:int=Form(...),comment:str=Form('')):
    u=require(request,'customer'); rating=max(1,min(5,rating)); c=db(); c.execute('INSERT INTO reviews(user_id,company_id,rating,comment,created_at) VALUES(?,?,?,?,?)',(u['id'],company_id,rating,comment,now())); c.commit(); c.close(); return {'ok':True,'message':'Отзыв отправлен на модерацию'}

@app.get('/api/cars')
def cars(request:Request):
    u=require(request,'customer'); c=db(); rows=[dict(x) for x in c.execute('SELECT * FROM cars WHERE user_id=? ORDER BY id DESC',(u['id'],))]; c.close(); return rows
@app.post('/api/cars')
def add_car(request:Request,model:str=Form(''),year:str=Form(''),plate:str=Form(''),vin:str=Form(''),mileage:str=Form(''),photo:UploadFile=File(None)):
    u=require(request,'customer'); image=save_upload(photo) if photo else ''; c=db(); c.execute('INSERT INTO cars(user_id,model,year,plate,vin,mileage,photo,created_at) VALUES(?,?,?,?,?,?,?,?)',(u['id'],model,year,plate,vin,mileage,image,now())); c.commit(); c.close(); return {'ok':True}

@app.get('/api/notifications')
def notifications(request:Request):
    u=require(request); c=db(); rows=[dict(x) for x in c.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50',(u['id'],))]; c.close(); return rows

@app.get('/api/seller/offers')
def seller_offers(request:Request):
    u=require(request,'seller'); c=db(); rows=[dict(x) for x in c.execute('SELECT * FROM offers WHERE seller_id=? ORDER BY id DESC',(u['id'],))]; c.close(); return rows
@app.post('/api/seller/offers')
def seller_add(request:Request,title:str=Form(...),description:str=Form(''),discount:str=Form(''),valid_until:str=Form(''),address:str=Form(''),phone:str=Form(''),image:UploadFile=File(None)):
    u=require(request,'seller'); image_url=save_upload(image) if image else ''; c=db(); c.execute('INSERT INTO offers(seller_id,title,description,discount,valid_until,address,phone,image,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(u['id'],title,description,discount,valid_until,address,phone,image_url,'pending',now(),now())); c.commit(); c.close(); return {'ok':True,'status':'pending'}
@app.put('/api/seller/offers/{oid}')
def seller_edit(request:Request,oid:int,title:str=Form(...),description:str=Form(''),discount:str=Form(''),valid_until:str=Form(''),address:str=Form(''),phone:str=Form(''),image:UploadFile=File(None)):
    u=require(request,'seller'); c=db(); old=c.execute('SELECT * FROM offers WHERE id=? AND seller_id=?',(oid,u['id'])).fetchone()
    if not old: raise HTTPException(404,'Не найдено')
    img=save_upload(image) if image else old['image']; c.execute('UPDATE offers SET title=?,description=?,discount=?,valid_until=?,address=?,phone=?,image=?,status="pending",updated_at=? WHERE id=?',(title,description,discount,valid_until,address,phone,img,now(),oid)); c.commit(); c.close(); return {'ok':True,'status':'pending'}
@app.delete('/api/seller/offers/{oid}')
def seller_delete(request:Request,oid:int):
    u=require(request,'seller'); c=db(); c.execute('DELETE FROM offers WHERE id=? AND seller_id=?',(oid,u['id'])); c.commit(); c.close(); return {'ok':True}

@app.get('/api/owner/sellers')
def owner_sellers(request:Request):
    require(request,'owner'); c=db(); rows=[dict(x) for x in c.execute('SELECT id,email,name,role,company,active,created_at FROM users WHERE role="seller" ORDER BY id DESC')]; c.close(); return rows
@app.post('/api/owner/sellers')
def owner_add_seller(request:Request,email:str=Form(...),password:str=Form(...),name:str=Form(...),company:str=Form('')):
    u=require(request,'owner'); c=db();
    try: c.execute('INSERT INTO users(email,password,name,role,company,created_at) VALUES(?,?,?,?,?,?)',(email.lower(),hashpw(password),name,'seller',company,now())); c.commit()
    except sqlite3.IntegrityError: raise HTTPException(400,'Email уже занят')
    c.close(); return {'ok':True}
@app.patch('/api/owner/sellers/{sid}')
def owner_toggle_seller(request:Request,sid:int,active:int=Form(...)):
    require(request,'owner'); c=db(); c.execute('UPDATE users SET active=? WHERE id=? AND role="seller"',(1 if active else 0,sid)); c.commit(); c.close(); return {'ok':True}
@app.get('/api/owner/offers')
def owner_offers(request:Request):
    require(request,'owner'); c=db(); rows=[dict(x) for x in c.execute('SELECT o.*,u.name seller,u.email FROM offers o JOIN users u ON u.id=o.seller_id ORDER BY o.id DESC')]; c.close(); return rows
@app.patch('/api/owner/offers/{oid}')
def owner_status(request:Request,oid:int,status:str=Form(...)):
    u=require(request,'owner'); allowed={'pending','active','rejected','disabled'}
    if status not in allowed: raise HTTPException(400,'Неверный статус')
    c=db(); o=c.execute('SELECT * FROM offers WHERE id=?',(oid,)).fetchone();
    if not o: raise HTTPException(404,'Не найдено')
    c.execute('UPDATE offers SET status=?,updated_at=? WHERE id=?',(status,now(),oid)); c.commit(); c.close();
    notify(o['seller_id'],'Статус предложения изменён',f'Предложение «{o["title"]}»: {status}')
    return {'ok':True}
@app.delete('/api/owner/offers/{oid}')
def owner_delete(request:Request,oid:int):
    require(request,'owner'); c=db(); c.execute('DELETE FROM offers WHERE id=?',(oid,)); c.commit(); c.close(); return {'ok':True}

@app.get('/api/owner/content')
def owner_content(request:Request):
    require(request,'owner'); c=db();
    data={'gallery':[dict(x) for x in c.execute('SELECT * FROM gallery ORDER BY sort_order,id DESC')], 'services':[dict(x) for x in c.execute('SELECT * FROM services ORDER BY sort_order,id DESC')], 'reviews':[dict(x) for x in c.execute('SELECT r.*,u.name FROM reviews r LEFT JOIN users u ON u.id=r.user_id ORDER BY r.id DESC')]}
    c.close(); return data
@app.post('/api/owner/gallery')
def owner_gallery(request:Request,title:str=Form(''),caption:str=Form(''),sort_order:int=Form(0),image:UploadFile=File(...)):
    require(request,'owner'); img=save_upload(image); c=db(); c.execute('INSERT INTO gallery(title,image,caption,sort_order,created_at) VALUES(?,?,?,?,?)',(title,img,caption,sort_order,now())); c.commit(); c.close(); return {'ok':True}
@app.delete('/api/owner/gallery/{gid}')
def owner_gallery_del(request:Request,gid:int):
    require(request,'owner'); c=db(); c.execute('DELETE FROM gallery WHERE id=?',(gid,)); c.commit(); c.close(); return {'ok':True}
@app.post('/api/owner/services')
def owner_service(request:Request,title:str=Form(...),description:str=Form(''),price:str=Form(''),sort_order:int=Form(0),image:UploadFile=File(None)):
    require(request,'owner'); img=save_upload(image) if image else ''; c=db(); c.execute('INSERT INTO services(title,description,price,image,sort_order,created_at) VALUES(?,?,?,?,?,?)',(title,description,price,img,sort_order,now())); c.commit(); c.close(); return {'ok':True}
@app.delete('/api/owner/services/{sid}')
def owner_service_del(request:Request,sid:int):
    require(request,'owner'); c=db(); c.execute('DELETE FROM services WHERE id=?',(sid,)); c.commit(); c.close(); return {'ok':True}
@app.patch('/api/owner/reviews/{rid}')
def owner_review(request:Request,rid:int,approved:int=Form(...)):
    require(request,'owner'); c=db(); c.execute('UPDATE reviews SET approved=? WHERE id=?',(1 if approved else 0,rid)); c.commit(); c.close(); return {'ok':True}
@app.delete('/api/owner/reviews/{rid}')
def owner_review_del(request:Request,rid:int):
    require(request,'owner'); c=db(); c.execute('DELETE FROM reviews WHERE id=?',(rid,)); c.commit(); c.close(); return {'ok':True}

@app.get('/api/owner/stats')
def owner_stats(request:Request):
    require(request,'owner'); c=db();
    out={
      'users':c.execute('SELECT COUNT(*) n FROM users').fetchone()['n'],
      'sellers':c.execute('SELECT COUNT(*) n FROM users WHERE role="seller"').fetchone()['n'],
      'offers':c.execute('SELECT COUNT(*) n FROM offers').fetchone()['n'],
      'active_offers':c.execute('SELECT COUNT(*) n FROM offers WHERE status="active"').fetchone()['n'],
      'pending':c.execute('SELECT COUNT(*) n FROM offers WHERE status="pending"').fetchone()['n'],
      'redemptions':c.execute('SELECT COALESCE(SUM(redemptions),0) n FROM offers').fetchone()['n'],
      'gallery':c.execute('SELECT COUNT(*) n FROM gallery').fetchone()['n'],
      'services':c.execute('SELECT COUNT(*) n FROM services').fetchone()['n'],
      'reviews':c.execute('SELECT COUNT(*) n FROM reviews').fetchone()['n']}
    c.close(); return out
