import os, hashlib, secrets, io, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.exc import IntegrityError
import qrcode
from .db import db, schema, IS_POSTGRES, DATABASE_URL
from .security import validate_email, validate_username, csrf_token, check_csrf
from .ratelimit import check as rate_check

BASE=Path(__file__).resolve().parent; UP=BASE/'static'/'uploads'; UP.mkdir(parents=True,exist_ok=True)
app=FastAPI(title='APG V14 — Авто Партнёрская Группа',version='14.0.0',docs_url='/api/docs',redoc_url='/api/redoc')
app.add_middleware(SessionMiddleware,secret_key=os.getenv('APG_SECRET_KEY','dev-apg-change-me'),max_age=60*60*24*7,same_site='lax',https_only=os.getenv('APG_COOKIE_SECURE','0')=='1')
app.mount('/static',StaticFiles(directory=BASE/'static'),name='static')

@app.middleware('http')
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(self), geolocation=(self), microphone=()'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response

def now(): return datetime.now(timezone.utc).isoformat()
def hashpw(p): return hashlib.pbkdf2_hmac('sha256',p.encode(),os.getenv('APG_PASSWORD_SALT','apg-v9-salt').encode(),180000).hex()
def clean(r): return dict(r) if r else None

def init():
    c=db(); c.executescript(schema()); t=now()
    def add(email,pw,name,role,username):
        if not c.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone():
            c.execute('INSERT INTO users(email,password,name,role,username,created_at) VALUES(?,?,?,?,?,?)',(email,hashpw(pw),name,role,username,t))
    add('owner@apg.local','apg1234','APG Owner','owner','apgowner'); add('seller@apg.local','seller1234','APG Seller','seller','apgseller'); add('user@apg.local','user1234','APG Client','customer','apgclient')
    if not c.execute('SELECT 1 FROM companies').fetchone():
        c.execute('INSERT INTO companies(name,description,address,phone,hours,category,created_at) VALUES(?,?,?,?,?,?,?)',('APG Partner Center','Партнёрский автомобильный центр APG','Адрес партнёра','+49 000 000000','Пн–Вс 09:00–20:00','Автосервис',t))
    cid=c.execute('SELECT id FROM companies ORDER BY id LIMIT 1').fetchone()['id']; sid=c.execute("SELECT id FROM users WHERE role='seller' LIMIT 1").fetchone()['id']
    c.execute('INSERT OR IGNORE INTO seller_companies VALUES(?,?)',(sid,cid))
    if not c.execute('SELECT id FROM partner_plans LIMIT 1').fetchone():
        for x in [('Start','Базовый тариф партнёра','0 €','month'),('Pro','Расширенный кабинет и аналитика','29 €','month'),('Business','Максимум инструментов APG','79 €','month')]:
            c.execute('INSERT INTO partner_plans(name,description,price,period,created_at) VALUES(?,?,?,?,?)',(*x,t))
    c.commit(); c.close()

@app.on_event('startup')
def startup():
    init()
    from .v14 import init_v14
    init_v14(db)

def current(req):
    uid=req.session.get('uid');
    if not uid:return None
    c=db(); r=c.execute('SELECT id,email,name,role,active,avatar,phone,username,created_at FROM users WHERE id=?',(uid,)).fetchone(); c.close(); return clean(r)
def require(req,roles):
    u=current(req)
    if not u or u['role'] not in roles or not u['active']: raise HTTPException(401,'Требуется авторизация')
    return u
def audit(uid,title,details=''):
    c=db(); c.execute('INSERT INTO audit(user_id,title,details,created_at) VALUES(?,?,?,?)',(uid,title,details,now())); c.commit(); c.close()
def notify(uid,title,body=''):
    c=db(); c.execute('INSERT INTO notifications(user_id,title,body,created_at) VALUES(?,?,?,?)',(uid,title,body,now())); c.commit(); c.close()
async def savefile(f:UploadFile|None):
    if not f or not f.filename:return ''
    ext=Path(f.filename).suffix.lower()
    if ext not in {'.jpg','.jpeg','.png','.webp'}: raise HTTPException(400,'Поддерживаются JPG, PNG, WEBP')
    data=await f.read()
    if len(data)>8*1024*1024: raise HTTPException(400,'Файл больше 8 МБ')
    name=secrets.token_hex(14)+ext
    bucket=os.getenv('S3_BUCKET','').strip()
    if bucket:
        try:
            import boto3
            client=boto3.client('s3',endpoint_url=os.getenv('S3_ENDPOINT') or None,
                aws_access_key_id=os.getenv('S3_ACCESS_KEY'),aws_secret_access_key=os.getenv('S3_SECRET_KEY'),
                region_name=os.getenv('S3_REGION','auto'))
            key=f"apg/{datetime.now(timezone.utc).strftime('%Y/%m')}/{name}"
            client.put_object(Bucket=bucket,Key=key,Body=data,ContentType=f.content_type or 'application/octet-stream')
            public=os.getenv('S3_PUBLIC_BASE','').rstrip('/')
            return f"{public}/{key}" if public else key
        except Exception as e:
            raise HTTPException(500,f'S3 upload failed: {e}')
    (UP/name).write_bytes(data); return '/static/uploads/'+name

@app.get('/',response_class=HTMLResponse)
def home(): return HTML

@app.get('/api/csrf')
def get_csrf(request:Request): return {'token':csrf_token(request)}
@app.get('/manifest.webmanifest')
def manifest(): return JSONResponse(json.loads((BASE/'static'/'manifest.webmanifest').read_text(encoding='utf-8')))
@app.get('/api/health')
def health(): return {'status':'ok','service':'APG','version':'13.0.0','database':'postgresql' if IS_POSTGRES else 'sqlite','storage': 's3' if os.getenv('S3_BUCKET') else 'local'}
@app.get('/api/me')
def me(request:Request): return {'user':current(request),'csrf':csrf_token(request)}
@app.post('/api/login')
def login(request:Request,email:str=Form(...),password:str=Form(...),csrf:str=Form('')):
    rate_check(request,'login',8,60)
    if request.session.get('csrf'): check_csrf(request,csrf)
    email=validate_email(email)
    c=db(); r=c.execute('SELECT * FROM users WHERE email=? AND password=? AND active=1',(email.strip().lower(),hashpw(password))).fetchone(); c.close()
    if not r: raise HTTPException(401,'Неверный email или пароль')
    request.session['uid']=r['id']; audit(r['id'],'Вход в аккаунт'); return {'ok':True,'user':current(request)}
@app.post('/api/register')
def register(request:Request,email:str=Form(...),password:str=Form(...),name:str=Form(...),csrf:str=Form('')):
    rate_check(request,'register',5,300)
    if request.session.get('csrf'): check_csrf(request,csrf)
    email=validate_email(email)
    if len(password)<8: raise HTTPException(400,'Пароль минимум 6 символов')
    c=db();
    try:c.execute('INSERT INTO users(email,password,name,role,username,created_at) VALUES(?,?,?,?,?,?)',(email.strip().lower(),hashpw(password),name.strip(),'customer','u'+secrets.token_hex(4),now())); c.commit(); uid=c.execute('SELECT id FROM users WHERE email=?',(email.strip().lower(),)).fetchone()['id']
    except IntegrityError:c.close(); raise HTTPException(400,'Email уже зарегистрирован')
    c.execute('INSERT OR IGNORE INTO settings(user_id) VALUES(?)',(uid,)); c.commit(); c.close(); request.session['uid']=uid; return {'ok':True,'user':current(request)}
@app.post('/api/logout')
def logout(request:Request,csrf:str=Form('')):
    check_csrf(request,csrf)
    request.session.clear(); return {'ok':True}

@app.get('/api/profile')
def profile(request:Request):
    u=require(request,['customer','seller','owner']); c=db(); s=c.execute('SELECT * FROM settings WHERE user_id=?',(u['id'],)).fetchone(); c.close(); return {'user':u,'settings':clean(s) or {'accent':'white','density':'comfortable','animations':1}}
@app.post('/api/profile')
async def profile_update(request:Request,name:str=Form(...),phone:str=Form(''),username:str=Form(''),avatar:UploadFile|None=File(None)):
    u=require(request,['customer','seller','owner']); av=await savefile(avatar); c=db()
    try:
        c.execute('UPDATE users SET name=?,phone=?,username=?,avatar=COALESCE(NULLIF(?,\'\'),avatar) WHERE id=?',(name.strip(),phone.strip(),username.strip(),av,u['id'])); c.commit()
    except IntegrityError:c.close(); raise HTTPException(400,'Username уже занят')
    c.close(); return {'user':current(request)}
@app.post('/api/settings')
def settings(request:Request,accent:str=Form('white'),density:str=Form('comfortable'),animations:int=Form(1)):
    u=require(request,['customer','seller','owner']); c=db(); c.execute('INSERT INTO settings(user_id,accent,density,animations) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET accent=excluded.accent,density=excluded.density,animations=excluded.animations',(u['id'],accent,density,animations)); c.commit(); c.close(); return {'ok':True}

@app.get('/api/companies')
def companies(request:Request,q:str='',category:str=''):
    c=db(); sql="SELECT * FROM companies WHERE active=1 AND (name LIKE ? OR description LIKE ? OR address LIKE ?)"; args=[f'%{q}%',f'%{q}%',f'%{q}%']
    if category: sql+=' AND category=?'; args.append(category)
    rows=c.execute(sql+' ORDER BY id DESC',args).fetchall(); uid=(current(request) or {}).get('id',0); out=[]
    for r in rows:
        d=clean(r); d['favorite']=bool(c.execute('SELECT 1 FROM favorites WHERE user_id=? AND company_id=?',(uid,r['id'])).fetchone()); d['offers']=c.execute("SELECT COUNT(*) n FROM offers WHERE company_id=? AND status='active'",(r['id'],)).fetchone()['n']; d['services']=c.execute('SELECT COUNT(*) n FROM services WHERE company_id=? AND active=1',(r['id'],)).fetchone()['n']; out.append(d)
    c.close(); return out
@app.get('/api/nearby')
def nearby(lat:float,lon:float,radius_km:float=25):
    c=db(); rows=c.execute('SELECT * FROM companies WHERE active=1 AND latitude IS NOT NULL AND longitude IS NOT NULL').fetchall(); c.close()
    from math import radians,sin,cos,asin,sqrt
    out=[]
    for r in rows:
        d=clean(r); la,lo=d.get('latitude'),d.get('longitude')
        qlat,qlo=radians(lat),radians(lon); a1=radians(la)-qlat; a2=radians(lo)-qlo
        a=sin(a1/2)**2+cos(qlat)*cos(radians(la))*sin(a2/2)**2
        km=6371*2*asin(sqrt(a))
        if km<=radius_km: d['distance_km']=round(km,1); out.append(d)
    return sorted(out,key=lambda x:x['distance_km'])

@app.get('/api/categories')
def categories():
    c=db(); a=[x['category'] for x in c.execute('SELECT DISTINCT category FROM companies WHERE active=1 AND category<>\'\' ORDER BY category').fetchall()]; c.close(); return a
@app.get('/api/companies/{cid}')
def company(cid:int):
    c=db(); co=c.execute('SELECT * FROM companies WHERE id=? AND active=1',(cid,)).fetchone()
    if not co:c.close();raise HTTPException(404,'Компания не найдена')
    d=clean(co); d['gallery']=[clean(x) for x in c.execute('SELECT * FROM gallery WHERE company_id=? AND active=1 ORDER BY sort_order,id',(cid,))]; d['services']=[clean(x) for x in c.execute('SELECT * FROM services WHERE company_id=? AND active=1 ORDER BY sort_order,id',(cid,))]; d['offers']=[clean(x) for x in c.execute("SELECT * FROM offers WHERE company_id=? AND status='active' ORDER BY id DESC",(cid,))]; d['reviews']=[clean(x) for x in c.execute("SELECT r.*,u.name user_name,u.avatar FROM reviews r JOIN users u ON u.id=r.user_id WHERE r.company_id=? AND r.status='approved' ORDER BY r.id DESC",(cid,))]; c.close(); return d
@app.post('/api/favorites/{cid}')
def favorite(request:Request,cid:int):
    u=require(request,['customer']); c=db(); e=c.execute('SELECT 1 FROM favorites WHERE user_id=? AND company_id=?',(u['id'],cid)).fetchone()
    if e:c.execute('DELETE FROM favorites WHERE user_id=? AND company_id=?',(u['id'],cid)); on=False
    else:c.execute('INSERT OR IGNORE INTO favorites VALUES(?,?)',(u['id'],cid)); on=True
    c.commit(); c.close(); return {'favorite':on}
@app.get('/api/favorites')
def favorites(request:Request):
    u=require(request,['customer']); c=db(); r=c.execute('SELECT c.* FROM favorites f JOIN companies c ON c.id=f.company_id WHERE f.user_id=? ORDER BY c.name',(u['id'],)).fetchall(); c.close(); return [clean(x) for x in r]

@app.get('/api/offers')
def offers(q:str='',category:str=''):
    c=db(); sql="SELECT o.*,c.name company_name,c.logo company_logo,c.category FROM offers o JOIN companies c ON c.id=o.company_id WHERE o.status='active' AND c.active=1 AND (o.title LIKE ? OR o.description LIKE ? OR c.name LIKE ?)"; args=[f'%{q}%',f'%{q}%',f'%{q}%']
    if category: sql+=' AND c.category=?'; args.append(category)
    r=c.execute(sql+' ORDER BY o.id DESC',args).fetchall(); c.close(); return [clean(x) for x in r]
@app.post('/api/offers/{oid}/qr')
def makeqr(request:Request,oid:int):
    u=require(request,['customer']); c=db(); o=c.execute("SELECT id,title FROM offers WHERE id=? AND status='active'",(oid,)).fetchone()
    if not o:c.close();raise HTTPException(404,'Предложение недоступно')
    t=secrets.token_urlsafe(22); exp=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(); c.execute('INSERT INTO qr_tokens VALUES(?,?,?,?,0,\'\',NULL)',(t,oid,u['id'],exp)); c.commit(); c.close(); return {'token':t,'expires_at':exp,'image':f'/api/qr-image/{t}','title':o['title']}
@app.get('/api/qr-image/{token}')
def qrimg(token:str):
    c=db(); r=c.execute('SELECT token FROM qr_tokens WHERE token=?',(token,)).fetchone(); c.close()
    if not r:raise HTTPException(404,'QR не найден')
    img=qrcode.make('APG:'+token); b=io.BytesIO(); img.save(b,format='PNG'); b.seek(0); return StreamingResponse(b,media_type='image/png')
@app.post('/api/redeem')
def redeem(request:Request,token:str=Form(...)):
    u=require(request,['seller','owner']); c=db(); r=c.execute('SELECT q.*,o.company_id,o.title FROM qr_tokens q JOIN offers o ON o.id=q.offer_id WHERE q.token=?',(token.strip().removeprefix('APG:'),)).fetchone()
    if not r:c.close();raise HTTPException(404,'QR не найден')
    if r['used'] or datetime.fromisoformat(r['expires_at'])<datetime.now(timezone.utc):c.close();raise HTTPException(400,'QR уже использован или истёк')
    if u['role']=='seller' and not c.execute('SELECT 1 FROM seller_companies WHERE user_id=? AND company_id=?',(u['id'],r['company_id'])).fetchone():c.close();raise HTTPException(403,'Этот QR не относится к вашей компании')
    c.execute('UPDATE qr_tokens SET used=1,used_at=?,redeemed_by=? WHERE token=?',(now(),u['id'],r['token'])); c.commit(); c.close(); audit(u['id'],'QR погашён',r['title']); return {'ok':True,'message':'Скидка успешно подтверждена'}

@app.get('/api/cars')
def cars(request:Request):
    u=require(request,['customer']); c=db(); r=c.execute('SELECT * FROM cars WHERE user_id=? ORDER BY id DESC',(u['id'],)).fetchall(); c.close(); return [clean(x) for x in r]
@app.post('/api/cars')
async def add_car(request:Request,model:str=Form(''),year:str=Form(''),plate:str=Form(''),vin:str=Form(''),mileage:str=Form(''),photo:UploadFile|None=File(None)):
    u=require(request,['customer']); p=await savefile(photo); c=db(); c.execute('INSERT INTO cars(user_id,model,year,plate,vin,mileage,photo,created_at) VALUES(?,?,?,?,?,?,?,?)',(u['id'],model,year,plate,vin,mileage,p,now())); c.commit(); c.close(); return {'ok':True}
@app.delete('/api/cars/{cid}')
def del_car(request:Request,cid:int):
    u=require(request,['customer']); c=db(); c.execute('DELETE FROM cars WHERE id=? AND user_id=?',(cid,u['id'])); c.commit(); c.close(); return {'ok':True}
@app.get('/api/history')
def history(request:Request):
    u=require(request,['customer']); c=db(); r=c.execute('SELECT h.*,c.name company_name,ca.model car_model FROM history h LEFT JOIN companies c ON c.id=h.company_id LEFT JOIN cars ca ON ca.id=h.car_id WHERE h.user_id=? ORDER BY h.service_date DESC,h.id DESC',(u['id'],)).fetchall(); c.close(); return [clean(x) for x in r]
@app.post('/api/history')
def add_history(request:Request,car_id:int=Form(0),company_id:int=Form(0),title:str=Form(...),note:str=Form(''),service_date:str=Form('')):
    u=require(request,['customer']); c=db(); c.execute('INSERT INTO history(user_id,car_id,company_id,title,note,service_date,created_at) VALUES(?,?,?,?,?,?,?)',(u['id'],car_id or None,company_id or None,title,note,service_date or now()[:10],now())); c.commit(); c.close(); return {'ok':True}
@app.post('/api/reviews')
def add_review(request:Request,company_id:int=Form(...),rating:int=Form(...),body:str=Form('')):
    u=require(request,['customer']); rating=max(1,min(5,rating)); c=db(); c.execute('INSERT INTO reviews(company_id,user_id,rating,body,status,created_at) VALUES(?,?,?,?,\'pending\',?)',(company_id,u['id'],rating,body,now())); c.commit(); c.close(); notify(u['id'],'Отзыв отправлен','После модерации он появится на странице компании.'); return {'ok':True}

# Seller: only companies assigned to the seller and only own offers.
@app.get('/api/seller/companies')
def seller_companies(request:Request):
    u=require(request,['seller']); c=db(); r=c.execute('SELECT c.* FROM seller_companies s JOIN companies c ON c.id=s.company_id WHERE s.user_id=? AND c.active=1',(u['id'],)).fetchall(); c.close(); return [clean(x) for x in r]
@app.get('/api/seller/offers')
def seller_offers(request:Request):
    u=require(request,['seller']); c=db(); r=c.execute('SELECT o.*,c.name company_name FROM offers o JOIN companies c ON c.id=o.company_id WHERE o.created_by=? ORDER BY o.id DESC',(u['id'],)).fetchall(); c.close(); return [clean(x) for x in r]
@app.post('/api/seller/offers')
async def seller_add_offer(request:Request,company_id:int=Form(...),title:str=Form(...),description:str=Form(''),discount:str=Form(''),valid_until:str=Form(''),image:UploadFile|None=File(None)):
    u=require(request,['seller']); c=db()
    if not c.execute('SELECT 1 FROM seller_companies WHERE user_id=? AND company_id=?',(u['id'],company_id)).fetchone():c.close();raise HTTPException(403,'Компания не назначена продавцу')
    p=await savefile(image); c.execute('INSERT INTO offers(company_id,title,description,discount,valid_until,image,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,\'pending\',?,?,?)',(company_id,title,description,discount,valid_until,p,u['id'],now(),now())); c.commit(); c.close(); notify_admins('Новая скидка на модерацию',title); audit(u['id'],'Создана скидка',title); return {'ok':True}
@app.patch('/api/seller/offers/{oid}')
async def seller_edit_offer(request:Request,oid:int,title:str=Form(...),description:str=Form(''),discount:str=Form(''),valid_until:str=Form(''),image:UploadFile|None=File(None)):
    u=require(request,['seller']); c=db(); o=c.execute('SELECT * FROM offers WHERE id=? AND created_by=?',(oid,u['id'])).fetchone()
    if not o:c.close();raise HTTPException(404,'Скидка не найдена')
    p=await savefile(image); c.execute('UPDATE offers SET title=?,description=?,discount=?,valid_until=?,image=COALESCE(NULLIF(?,\'\'),image),status=\'pending\',updated_at=? WHERE id=? AND created_by=?',(title,description,discount,valid_until,p,now(),oid,u['id'])); c.commit(); c.close(); notify_admins('Изменена скидка на модерацию',title); return {'ok':True}
@app.delete('/api/seller/offers/{oid}')
def seller_delete_offer(request:Request,oid:int):
    u=require(request,['seller']); c=db(); c.execute('DELETE FROM offers WHERE id=? AND created_by=?',(oid,u['id'])); c.commit(); c.close(); return {'ok':True}

# Owner management.
def notify_admins(title,body):
    c=db(); ids=[x['id'] for x in c.execute("SELECT id FROM users WHERE role='owner'").fetchall()]; c.close()
    for uid in ids: notify(uid,title,body)
@app.get('/api/owner/users')
def owner_users(request:Request):
    require(request,['owner']); c=db(); r=c.execute('SELECT id,email,name,role,active,avatar,phone,username,created_at FROM users ORDER BY id DESC').fetchall(); c.close(); return [clean(x) for x in r]
@app.patch('/api/owner/users/{uid}')
def owner_user(request:Request,uid:int,role:str=Form(None),active:int=Form(None)):
    u=require(request,['owner']); c=db(); r=c.execute('SELECT id FROM users WHERE id=?',(uid,)).fetchone()
    if not r:c.close();raise HTTPException(404,'Пользователь не найден')
    if uid==u['id'] and active==0:c.close();raise HTTPException(400,'Нельзя отключить свой аккаунт')
    if role and role not in ('customer','seller','owner'):c.close();raise HTTPException(400,'Неверная роль')
    if role is not None:c.execute('UPDATE users SET role=? WHERE id=?',(role,uid))
    if active is not None:c.execute('UPDATE users SET active=? WHERE id=?',(active,uid))
    c.commit(); c.close(); audit(u['id'],'Изменён пользователь',str(uid)); return {'ok':True}
@app.get('/api/owner/companies')
def owner_companies(request:Request):
    require(request,['owner']); c=db(); r=c.execute('SELECT c.*,COUNT(DISTINCT s.user_id) seller_count,COUNT(DISTINCT o.id) offer_count FROM companies c LEFT JOIN seller_companies s ON s.company_id=c.id LEFT JOIN offers o ON o.company_id=c.id GROUP BY c.id ORDER BY c.id DESC').fetchall(); c.close(); return [clean(x) for x in r]
@app.post('/api/owner/companies')
async def owner_add_company(request:Request,name:str=Form(...),description:str=Form(''),address:str=Form(''),phone:str=Form(''),hours:str=Form(''),category:str=Form('Авто'),logo:UploadFile|None=File(None),cover:UploadFile|None=File(None)):
    u=require(request,['owner']); l=await savefile(logo); cv=await savefile(cover); c=db(); c.execute('INSERT INTO companies(name,description,logo,cover,address,phone,hours,category,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(name,description,l,cv,address,phone,hours,category,now())); c.commit(); c.close(); audit(u['id'],'Создана компания',name); return {'ok':True}
@app.patch('/api/owner/companies/{cid}')
async def owner_edit_company(request:Request,cid:int,name:str=Form(...),description:str=Form(''),address:str=Form(''),phone:str=Form(''),hours:str=Form(''),category:str=Form(''),active:int=Form(1),logo:UploadFile|None=File(None),cover:UploadFile|None=File(None)):
    u=require(request,['owner']); l=await savefile(logo); cv=await savefile(cover); c=db(); c.execute('UPDATE companies SET name=?,description=?,address=?,phone=?,hours=?,category=?,active=?,logo=COALESCE(NULLIF(?,\'\'),logo),cover=COALESCE(NULLIF(?,\'\'),cover) WHERE id=?',(name,description,address,phone,hours,category,active,l,cv,cid)); c.commit(); c.close(); audit(u['id'],'Изменена компания',name); return {'ok':True}
@app.delete('/api/owner/companies/{cid}')
def owner_delete_company(request:Request,cid:int):
    u=require(request,['owner']); c=db(); c.execute('DELETE FROM companies WHERE id=?',(cid,)); c.commit(); c.close(); audit(u['id'],'Удалена компания',str(cid)); return {'ok':True}
@app.post('/api/owner/assign-seller')
def assign_seller(request:Request,seller_id:int=Form(...),company_id:int=Form(...)):
    u=require(request,['owner']); c=db(); r=c.execute("SELECT id FROM users WHERE id=? AND role='seller'",(seller_id,)).fetchone()
    if not r:c.close();raise HTTPException(400,'Пользователь не является Seller')
    c.execute('INSERT OR IGNORE INTO seller_companies VALUES(?,?)',(seller_id,company_id)); c.commit(); c.close(); notify(seller_id,'Вам назначена компания','Теперь вы можете создавать предложения этой компании.'); audit(u['id'],'Назначен Seller',f'{seller_id}->{company_id}'); return {'ok':True}
@app.get('/api/owner/offers')
def owner_offers(request:Request):
    require(request,['owner']); c=db(); r=c.execute('SELECT o.*,c.name company_name,u.name creator_name FROM offers o JOIN companies c ON c.id=o.company_id LEFT JOIN users u ON u.id=o.created_by ORDER BY CASE o.status WHEN \'pending\' THEN 0 ELSE 1 END,o.id DESC').fetchall(); c.close(); return [clean(x) for x in r]
@app.patch('/api/owner/offers/{oid}')
def owner_offer(request:Request,oid:int,status:str=Form(...)):
    u=require(request,['owner']);
    if status not in ('pending','active','rejected','disabled'):raise HTTPException(400,'Неверный статус')
    c=db(); o=c.execute('SELECT * FROM offers WHERE id=?',(oid,)).fetchone();
    if not o:c.close();raise HTTPException(404,'Скидка не найдена')
    c.execute('UPDATE offers SET status=?,updated_at=? WHERE id=?',(status,now(),oid)); c.commit(); creator=o['created_by']; c.close();
    if creator:notify(creator,'Статус скидки изменён',f'Новый статус: {status}')
    audit(u['id'],'Модерация скидки',f'{oid}: {status}'); return {'ok':True}
@app.delete('/api/owner/offers/{oid}')
def owner_delete_offer(request:Request,oid:int):
    u=require(request,['owner']); c=db(); c.execute('DELETE FROM offers WHERE id=?',(oid,)); c.commit(); c.close(); audit(u['id'],'Удалена скидка',str(oid)); return {'ok':True}

@app.post('/api/owner/gallery')
async def owner_gallery(request:Request,company_id:int=Form(...),title:str=Form(''),description:str=Form(''),caption:str=Form(''),sort_order:int=Form(0),image:UploadFile=File(...)):
    u=require(request,['owner']); p=await savefile(image); c=db(); c.execute('INSERT INTO gallery(company_id,title,caption,image,sort_order,created_at) VALUES(?,?,?,?,?,?)',(company_id,title,caption or description,p,sort_order,now())); c.commit(); c.close(); audit(u['id'],'Добавлено фото',str(company_id)); return {'ok':True}
@app.delete('/api/owner/gallery/{gid}')
def owner_gallery_delete(request:Request,gid:int):
    u=require(request,['owner']); c=db(); c.execute('DELETE FROM gallery WHERE id=?',(gid,)); c.commit(); c.close(); return {'ok':True}
@app.post('/api/owner/services')
async def owner_service(request:Request,company_id:int=Form(...),title:str=Form(...),description:str=Form(''),price:str=Form(''),sort_order:int=Form(0),image:UploadFile|None=File(None)):
    u=require(request,['owner']); p=await savefile(image); c=db(); c.execute('INSERT INTO services(company_id,title,description,price,image,sort_order,created_at) VALUES(?,?,?,?,?,?,?)',(company_id,title,description,price,p,sort_order,now())); c.commit(); c.close(); return {'ok':True}
@app.delete('/api/owner/services/{sid}')
def owner_service_delete(request:Request,sid:int):
    require(request,['owner']); c=db(); c.execute('DELETE FROM services WHERE id=?',(sid,)); c.commit(); c.close(); return {'ok':True}
@app.get('/api/owner/reviews')
def owner_reviews(request:Request):
    require(request,['owner']); c=db(); r=c.execute('SELECT r.*,c.name company_name,u.name user_name FROM reviews r JOIN companies c ON c.id=r.company_id JOIN users u ON u.id=r.user_id ORDER BY CASE r.status WHEN \'pending\' THEN 0 ELSE 1 END,r.id DESC').fetchall(); c.close(); return [clean(x) for x in r]
@app.patch('/api/owner/reviews/{rid}')
def owner_review(request:Request,rid:int,status:str=Form(...)):
    u=require(request,['owner']);
    if status not in ('pending','approved','rejected'):raise HTTPException(400,'Неверный статус')
    c=db(); c.execute('UPDATE reviews SET status=? WHERE id=?',(status,rid)); c.commit(); c.close(); audit(u['id'],'Модерация отзыва',f'{rid}: {status}'); return {'ok':True}
@app.delete('/api/owner/reviews/{rid}')
def owner_review_delete(request:Request,rid:int):
    require(request,['owner']); c=db(); c.execute('DELETE FROM reviews WHERE id=?',(rid,)); c.commit(); c.close(); return {'ok':True}
@app.get('/api/owner/audit')
def owner_audit(request:Request):
    require(request,['owner']); c=db(); r=c.execute('SELECT a.*,u.name user_name FROM audit a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 150').fetchall(); c.close(); return [clean(x) for x in r]

@app.get('/api/notifications')
def notifications(request:Request):
    u=require(request,['customer','seller','owner']); c=db(); r=c.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50',(u['id'],)).fetchall(); c.close(); return [clean(x) for x in r]
@app.post('/api/notifications/read')
def notifications_read(request:Request):
    u=require(request,['customer','seller','owner']); c=db(); c.execute('UPDATE notifications SET read=1 WHERE user_id=?',(u['id'],)); c.commit(); c.close(); return {'ok':True}
@app.get('/api/qr-history')
def qr_history(request:Request):
    u=require(request,['seller','owner']); c=db()
    if u['role']=='owner':
        r=c.execute('SELECT q.*,o.title offer_title,c.name company_name,cu.name customer_name,su.name redeemed_name FROM qr_tokens q JOIN offers o ON o.id=q.offer_id JOIN companies c ON c.id=o.company_id JOIN users cu ON cu.id=q.user_id LEFT JOIN users su ON su.id=q.redeemed_by ORDER BY q.used_at DESC,q.token DESC LIMIT 200').fetchall()
    else:
        r=c.execute('SELECT q.*,o.title offer_title,c.name company_name,cu.name customer_name,su.name redeemed_name FROM qr_tokens q JOIN offers o ON o.id=q.offer_id JOIN companies c ON c.id=o.company_id JOIN users cu ON cu.id=q.user_id LEFT JOIN users su ON su.id=q.redeemed_by JOIN seller_companies sc ON sc.company_id=c.id AND sc.user_id=? ORDER BY q.used_at DESC,q.token DESC LIMIT 200',(u['id'],)).fetchall()
    c.close(); return [clean(x) for x in r]

@app.get('/api/companies/{cid}/directions')
def company_directions(cid:int):
    c=db(); r=c.execute('SELECT id,name,address,latitude,longitude FROM companies WHERE id=? AND active=1',(cid,)).fetchone(); c.close()
    if not r: raise HTTPException(404,'Компания не найдена')
    d=clean(r); addr=d.get('address') or ''
    d['google_maps']=f'https://www.google.com/maps/search/?api=1&query={__import__("urllib.parse").parse.quote(addr)}'
    d['openstreetmap']=f'https://www.openstreetmap.org/search?query={__import__("urllib.parse").parse.quote(addr)}'
    return d

@app.post('/api/push/register')
def push_register(request:Request,token:str=Form(...),platform:str=Form('web')):
    u=require(request,['customer','seller','owner']); c=db(); c.execute('INSERT OR IGNORE INTO push_tokens(user_id,token,platform,created_at) VALUES(?,?,?,?)',(u['id'],token[:512],platform[:32],now())); c.commit(); c.close(); return {'ok':True}


@app.get('/api/bookings')
def bookings(request:Request):
    u=require(request,['customer','seller','owner']); c=db()
    if u['role']=='customer':
        rows=c.execute('SELECT b.*,co.name company_name,s.title service_name,ca.model car_model FROM bookings b JOIN companies co ON co.id=b.company_id LEFT JOIN services s ON s.id=b.service_id LEFT JOIN cars ca ON ca.id=b.car_id WHERE b.user_id=? ORDER BY b.created_at DESC',(u['id'],)).fetchall()
    elif u['role']=='seller':
        rows=c.execute('SELECT b.*,co.name company_name,s.title service_name,u.name user_name,ca.model car_model FROM bookings b JOIN companies co ON co.id=b.company_id LEFT JOIN services s ON s.id=b.service_id LEFT JOIN users u ON u.id=b.user_id LEFT JOIN cars ca ON ca.id=b.car_id JOIN seller_companies sc ON sc.company_id=b.company_id AND sc.user_id=? ORDER BY b.created_at DESC',(u['id'],)).fetchall()
    else:
        rows=c.execute('SELECT b.*,co.name company_name,s.title service_name,u.name user_name,ca.model car_model FROM bookings b JOIN companies co ON co.id=b.company_id LEFT JOIN services s ON s.id=b.service_id LEFT JOIN users u ON u.id=b.user_id LEFT JOIN cars ca ON ca.id=b.car_id ORDER BY b.created_at DESC').fetchall()
    c.close(); return rows

@app.post('/api/bookings')
def create_booking(request:Request,company_id:int=Form(...),service_id:int=Form(0),car_id:int=Form(0),slot:str=Form(...),note:str=Form(''),csrf:str=Form('')):
    u=require(request,['customer']); check_csrf(request,csrf); c=db()
    if not c.execute('SELECT id FROM companies WHERE id=? AND active=1',(company_id,)).fetchone(): c.close(); raise HTTPException(404,'Компания не найдена')
    c.execute('INSERT INTO bookings(user_id,company_id,service_id,car_id,slot,note,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(u['id'],company_id,service_id or None,car_id or None,slot,note[:1000],'pending',now(),now())); c.commit(); c.close(); audit(u['id'],'Новая запись',f'company={company_id}'); return {'ok':True}

@app.patch('/api/bookings/{bid}')
def booking_status(request:Request,bid:int,status:str=Form(...),csrf:str=Form('')):
    u=require(request,['seller','owner']); check_csrf(request,csrf)
    if status not in {'confirmed','completed','cancelled','pending'}: raise HTTPException(400,'Недопустимый статус')
    c=db(); q='UPDATE bookings SET status=?,updated_at=? WHERE id=?'
    if u['role']=='seller': q+=' AND company_id IN (SELECT company_id FROM seller_companies WHERE user_id=?)'; params=(status,now(),bid,u['id'])
    else: params=(status,now(),bid)
    c.execute(q,params); c.commit(); c.close(); return {'ok':True}

@app.get('/api/chat/{company_id}')
def chat(request:Request,company_id:int):
    u=require(request,['customer','seller','owner']); c=db()
    if u['role']=='customer':
        c.execute('INSERT OR IGNORE INTO conversations(user_id,company_id,updated_at) VALUES(?,?,?)',(u['id'],company_id,now())); c.commit(); conv=c.execute('SELECT id FROM conversations WHERE user_id=? AND company_id=?',(u['id'],company_id)).fetchone()
    else:
        conv=c.execute('SELECT id FROM conversations WHERE company_id=? ORDER BY updated_at DESC LIMIT 1',(company_id,)).fetchone()
    rows=[] if not conv else c.execute('SELECT m.*,u.name sender_name FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.conversation_id=? ORDER BY m.created_at ASC',(conv['id'],)).fetchall()
    c.close(); return {'conversation_id':conv['id'] if conv else None,'messages':rows}

@app.post('/api/chat/{company_id}')
def send_chat(request:Request,company_id:int,body:str=Form(...),csrf:str=Form('')):
    u=require(request,['customer','seller','owner']); check_csrf(request,csrf); body=body.strip()
    if not body or len(body)>2000: raise HTTPException(400,'Сообщение 1–2000 символов')
    c=db()
    conv=c.execute('SELECT id FROM conversations WHERE user_id=? AND company_id=?',(u['id'],company_id)).fetchone() if u['role']=='customer' else c.execute('SELECT id FROM conversations WHERE company_id=? ORDER BY updated_at DESC LIMIT 1',(company_id,)).fetchone()
    if not conv:
        c.close(); raise HTTPException(404,'Диалог не найден')
    c.execute('INSERT INTO messages(conversation_id,sender_id,body,created_at) VALUES(?,?,?,?)',(conv['id'],u['id'],body,now())); c.execute('UPDATE conversations SET updated_at=? WHERE id=?',(now(),conv['id'])); c.commit(); c.close(); return {'ok':True}

@app.get('/api/promo')
def promo_list(request:Request):
    require(request,['customer','owner']); c=db(); rows=c.execute("SELECT * FROM promo_codes WHERE active=1 ORDER BY created_at DESC").fetchall(); c.close(); return rows

@app.post('/api/promo/redeem')
def promo_redeem(request:Request,code:str=Form(...),csrf:str=Form('')):
    u=require(request,['customer']); check_csrf(request,csrf); code=code.strip().upper(); c=db(); p=c.execute('SELECT * FROM promo_codes WHERE code=? AND active=1',(code,)).fetchone()
    if not p: c.close(); raise HTTPException(404,'Промокод не найден')
    if p['expires_at'] and p['expires_at']<now(): c.close(); raise HTTPException(400,'Промокод истёк')
    if p['max_uses'] and p['used_count']>=p['max_uses']: c.close(); raise HTTPException(400,'Лимит использований исчерпан')
    try:
        c.execute('INSERT INTO promo_redemptions(promo_id,user_id,created_at) VALUES(?,?,?)',(p['id'],u['id'],now())); c.execute('UPDATE promo_codes SET used_count=used_count+1 WHERE id=?',(p['id'],)); c.commit()
    except IntegrityError: c.close(); raise HTTPException(400,'Ты уже использовал этот промокод')
    c.close(); return {'ok':True,'promo':p}

@app.post('/api/owner/promo')
def owner_promo(request:Request,code:str=Form(...),description:str=Form(''),discount:str=Form(''),expires_at:str=Form(''),max_uses:int=Form(0),csrf:str=Form('')):
    u=require(request,['owner']); check_csrf(request,csrf); code=code.strip().upper()
    if not code or len(code)>40: raise HTTPException(400,'Некорректный код')
    c=db()
    try:c.execute('INSERT INTO promo_codes(code,description,discount,expires_at,max_uses,created_at) VALUES(?,?,?,?,?,?)',(code,description[:500],discount[:100],expires_at,max_uses,now())); c.commit()
    except IntegrityError:c.close(); raise HTTPException(400,'Такой промокод уже есть')
    c.close(); audit(u['id'],'Создан промокод',code); return {'ok':True}

@app.get('/api/plans')
def plans(request:Request):
    require(request,['owner','seller']); c=db(); rows=c.execute('SELECT * FROM partner_plans WHERE active=1 ORDER BY id').fetchall(); c.close(); return rows

@app.post('/api/owner/plans')
def owner_plan(request:Request,name:str=Form(...),description:str=Form(''),price:str=Form(''),period:str=Form('month'),csrf:str=Form('')):
    u=require(request,['owner']); check_csrf(request,csrf); c=db(); c.execute('INSERT INTO partner_plans(name,description,price,period,created_at) VALUES(?,?,?,?,?)',(name[:100],description[:500],price[:50],period[:30],now())); c.commit(); c.close(); return {'ok':True}

@app.get('/api/stats')
def stats(request:Request):
    u=require(request,['seller','owner']); c=db();
    base={'companies':c.execute('SELECT COUNT(*) n FROM companies WHERE active=1').fetchone()['n'],'offers':c.execute("SELECT COUNT(*) n FROM offers WHERE status='active'").fetchone()['n'],'pending_offers':c.execute("SELECT COUNT(*) n FROM offers WHERE status='pending'").fetchone()['n'],'reviews_pending':c.execute("SELECT COUNT(*) n FROM reviews WHERE status='pending'").fetchone()['n'],'qr_issued':c.execute('SELECT COUNT(*) n FROM qr_tokens').fetchone()['n'],'qr_used':c.execute('SELECT COUNT(*) n FROM qr_tokens WHERE used=1').fetchone()['n'],'customers':c.execute("SELECT COUNT(*) n FROM users WHERE role='customer'").fetchone()['n'],'sellers':c.execute("SELECT COUNT(*) n FROM users WHERE role='seller'").fetchone()['n']}
    if u['role']=='seller':
        base['my_offers']=c.execute('SELECT COUNT(*) n FROM offers WHERE created_by=?',(u['id'],)).fetchone()['n']; base['my_active']=c.execute("SELECT COUNT(*) n FROM offers WHERE created_by=? AND status='active'",(u['id'],)).fetchone()['n']
    c.close(); return base



from .v14 import register_v14
register_v14(app, db, now, require, audit, notify)

HTML='''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#050505"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-capable" content="yes"><link rel="manifest" href="/manifest.webmanifest"><link rel="stylesheet" href="/static/style.css"><title>APG</title></head><body><div id="app"><div class="boot"><b>APG</b><span>Загрузка платформы…</span></div></div><script src="/static/app.js"></script></body></html>'''

@app.get('/api/v12/status')
def v12_status():
    return {
        'release': 'APG V12',
        'status': 'production-ready scaffold',
        'mobile': True,
        'pwa': True,
        'postgresql': IS_POSTGRES,
        'persistent_storage': bool(os.getenv('S3_BUCKET')),
        'features': ['roles','offers','qr','gallery','services','reviews','garage','favorites','notifications','audit','pwa','capacitor']
    }
