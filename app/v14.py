"""APG V14 commercial layer: CRM, orders, loyalty, payments abstraction and analytics."""
import os, secrets
from datetime import datetime, timezone
from fastapi import Request, HTTPException


def _id_insert(c, sql, params):
    if os.getenv('DATABASE_URL','').startswith(('postgres://','postgresql://')):
        r = c.execute(sql + ' RETURNING id', params).fetchone()
        return r['id']
    c.execute(sql, params)
    return c.execute('SELECT last_insert_rowid() id').fetchone()['id']


def init_v14(db):
    c=db()
    statements=[
      "CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,company_id INTEGER NOT NULL,service_id INTEGER,car_id INTEGER,booking_id INTEGER,status TEXT DEFAULT 'new',total TEXT DEFAULT '0',currency TEXT DEFAULT 'EUR',note TEXT DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)",
      "CREATE TABLE IF NOT EXISTS loyalty_accounts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER UNIQUE NOT NULL,points INTEGER DEFAULT 0,level TEXT DEFAULT 'Member',updated_at TEXT NOT NULL)",
      "CREATE TABLE IF NOT EXISTS loyalty_transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,points INTEGER NOT NULL,reason TEXT NOT NULL,ref_type TEXT DEFAULT '',ref_id INTEGER,created_at TEXT NOT NULL)",
      "CREATE TABLE IF NOT EXISTS crm_notes(id INTEGER PRIMARY KEY AUTOINCREMENT,company_id INTEGER NOT NULL,customer_id INTEGER NOT NULL,seller_id INTEGER NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)",
      "CREATE TABLE IF NOT EXISTS analytics_events(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,company_id INTEGER,event TEXT NOT NULL,object_id INTEGER,meta TEXT DEFAULT '',created_at TEXT NOT NULL)",
      "CREATE TABLE IF NOT EXISTS payment_intents(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,company_id INTEGER,amount TEXT NOT NULL,currency TEXT DEFAULT 'EUR',status TEXT DEFAULT 'created',provider TEXT DEFAULT 'mock',provider_ref TEXT DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)",
      "CREATE TABLE IF NOT EXISTS company_settings(company_id INTEGER PRIMARY KEY,booking_enabled INTEGER DEFAULT 1,chat_enabled INTEGER DEFAULT 1,loyalty_enabled INTEGER DEFAULT 1,accent TEXT DEFAULT 'white',updated_at TEXT NOT NULL)"
    ]
    for s in statements:
        c.execute(s)
    c.commit(); c.close()


def register_v14(app, db, now, require, audit, notify):
    @app.get('/api/v14/dashboard')
    def dashboard(request: Request):
        u=require(request,['owner','seller','customer']); c=db()
        if u['role']=='customer':
            rows={
              'orders':c.execute('SELECT COUNT(*) n FROM orders WHERE user_id=?',(u['id'],)).fetchone()['n'],
              'bookings':c.execute('SELECT COUNT(*) n FROM bookings WHERE user_id=?',(u['id'],)).fetchone()['n'],
              'points':(c.execute('SELECT points FROM loyalty_accounts WHERE user_id=?',(u['id'],)).fetchone() or {'points':0})['points'],
              'unread':c.execute('SELECT COUNT(*) n FROM notifications WHERE user_id=? AND read=0',(u['id'],)).fetchone()['n']}
        else:
            where='1=1'; args=()
            if u['role']=='seller':
                where='o.company_id IN (SELECT company_id FROM seller_companies WHERE user_id=?)'; args=(u['id'],)
            rows={
              'orders':c.execute(f'SELECT COUNT(*) n FROM orders o WHERE {where}',args).fetchone()['n'],
              'bookings':c.execute(f'SELECT COUNT(*) n FROM bookings b WHERE '+('b.company_id IN (SELECT company_id FROM seller_companies WHERE user_id=?)' if u['role']=='seller' else '1=1'),args).fetchone()['n'],
              'customers':c.execute("SELECT COUNT(*) n FROM users WHERE role='customer'").fetchone()['n'],
              'payments':c.execute("SELECT COUNT(*) n FROM payment_intents WHERE status='succeeded'").fetchone()['n']}
        c.close(); return rows

    @app.post('/api/v14/analytics')
    async def analytics(request: Request):
        u=current = require(request,['owner','seller','customer']); body=await request.json(); event=str(body.get('event','view'))[:80]
        cid=body.get('company_id'); oid=body.get('object_id'); meta=str(body.get('meta',''))[:1000]
        c=db(); c.execute('INSERT INTO analytics_events(user_id,company_id,event,object_id,meta,created_at) VALUES(?,?,?,?,?,?)',(u['id'],cid,event,oid,meta,now())); c.commit(); c.close(); return {'ok':True}

    @app.get('/api/v14/analytics')
    def analytics_list(request: Request, company_id: int|None=None):
        u=require(request,['owner','seller']); c=db(); params=[]; clause=''
        if u['role']=='seller': clause=' AND company_id IN (SELECT company_id FROM seller_companies WHERE user_id=?)'; params.append(u['id'])
        if company_id: clause+=' AND company_id=?'; params.append(company_id)
        rows=c.execute('SELECT event,COUNT(*) count FROM analytics_events WHERE 1=1'+clause+' GROUP BY event ORDER BY count DESC',tuple(params)).fetchall(); c.close(); return rows

    @app.get('/api/v14/crm/customers')
    def crm_customers(request: Request, company_id:int|None=None):
        u=require(request,['owner','seller']); c=db(); params=[]; clause=''
        if u['role']=='seller': clause=' AND b.company_id IN (SELECT company_id FROM seller_companies WHERE user_id=?)'; params.append(u['id'])
        if company_id: clause+=' AND b.company_id=?'; params.append(company_id)
        rows=c.execute('''SELECT u.id,u.name,u.email,u.phone,COUNT(DISTINCT b.id) bookings,COUNT(DISTINCT o.id) orders,MAX(b.updated_at) last_seen
                          FROM users u LEFT JOIN bookings b ON b.user_id=u.id LEFT JOIN orders o ON o.user_id=u.id
                          WHERE u.role='customer' AND (b.id IS NOT NULL OR o.id IS NOT NULL)'''+clause+''' GROUP BY u.id ORDER BY last_seen DESC''',tuple(params)).fetchall(); c.close(); return rows

    @app.post('/api/v14/crm/notes')
    async def crm_note(request: Request):
        u=require(request,['owner','seller']); body=await request.json(); cid=int(body.get('company_id')); customer=int(body.get('customer_id')); note=str(body.get('note','')).strip()
        if not note: raise HTTPException(400,'Пустая заметка')
        c=db();
        if u['role']=='seller' and not c.execute('SELECT 1 FROM seller_companies WHERE user_id=? AND company_id=?',(u['id'],cid)).fetchone(): c.close(); raise HTTPException(403,'Компания не назначена')
        _id_insert(c,'INSERT INTO crm_notes(company_id,customer_id,seller_id,note,created_at,updated_at) VALUES(?,?,?,?,?,?)',(cid,customer,u['id'],note[:2000],now(),now())); c.commit(); c.close(); audit(u['id'],'CRM заметка',f'company={cid}, customer={customer}'); return {'ok':True}

    @app.get('/api/v14/crm/notes/{customer_id}')
    def crm_notes(request:Request, customer_id:int):
        u=require(request,['owner','seller']); c=db(); rows=c.execute('''SELECT n.*,co.name company_name FROM crm_notes n JOIN companies co ON co.id=n.company_id WHERE n.customer_id=? ORDER BY n.created_at DESC''',(customer_id,)).fetchall(); c.close(); return rows

    @app.post('/api/v14/orders')
    async def create_order(request:Request):
        u=require(request,['customer']); body=await request.json(); cid=int(body.get('company_id')); sid=body.get('service_id'); car=body.get('car_id'); total=str(body.get('total','0'))[:40]; note=str(body.get('note',''))[:1000]
        c=db();
        if not c.execute('SELECT 1 FROM companies WHERE id=? AND active=1',(cid,)).fetchone(): c.close(); raise HTTPException(404,'Компания не найдена')
        oid=_id_insert(c,'INSERT INTO orders(user_id,company_id,service_id,car_id,status,total,currency,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(u['id'],cid,sid,car,'new',total,'EUR',note,now(),now())); c.commit(); c.close(); notify(u['id'],'Заказ создан',f'Заказ #{oid} отправлен компании'); return {'ok':True,'id':oid}

    @app.get('/api/v14/orders')
    def orders(request:Request):
        u=require(request,['owner','seller','customer']); c=db();
        if u['role']=='customer': rows=c.execute('''SELECT o.*,co.name company_name,s.title service_name FROM orders o JOIN companies co ON co.id=o.company_id LEFT JOIN services s ON s.id=o.service_id WHERE o.user_id=? ORDER BY o.created_at DESC''',(u['id'],)).fetchall()
        elif u['role']=='seller': rows=c.execute('''SELECT o.*,co.name company_name,u.name customer_name FROM orders o JOIN companies co ON co.id=o.company_id JOIN users u ON u.id=o.user_id WHERE o.company_id IN (SELECT company_id FROM seller_companies WHERE user_id=?) ORDER BY o.created_at DESC''',(u['id'],)).fetchall()
        else: rows=c.execute('''SELECT o.*,co.name company_name,u.name customer_name FROM orders o JOIN companies co ON co.id=o.company_id JOIN users u ON u.id=o.user_id ORDER BY o.created_at DESC''').fetchall()
        c.close(); return rows

    @app.patch('/api/v14/orders/{oid}')
    async def order_status(request:Request,oid:int):
        u=require(request,['owner','seller']); body=await request.json(); status=str(body.get('status','new'))
        if status not in {'new','confirmed','in_progress','completed','cancelled'}: raise HTTPException(400,'Некорректный статус')
        c=db(); r=c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone();
        if not r: c.close(); raise HTTPException(404,'Заказ не найден')
        if u['role']=='seller' and not c.execute('SELECT 1 FROM seller_companies WHERE user_id=? AND company_id=?',(u['id'],r['company_id'])).fetchone(): c.close(); raise HTTPException(403,'Нет доступа')
        c.execute('UPDATE orders SET status=?,updated_at=? WHERE id=?',(status,now(),oid)); c.commit(); c.close(); notify(r['user_id'],'Статус заказа изменён',f'Заказ #{oid}: {status}'); audit(u['id'],'Изменён заказ',f'#{oid} → {status}'); return {'ok':True}

    @app.get('/api/v14/loyalty')
    def loyalty(request:Request):
        u=require(request,['customer']); c=db(); a=c.execute('SELECT * FROM loyalty_accounts WHERE user_id=?',(u['id'],)).fetchone(); tx=c.execute('SELECT * FROM loyalty_transactions WHERE user_id=? ORDER BY created_at DESC LIMIT 50',(u['id'],)).fetchall(); c.close(); return {'account':a or {'points':0,'level':'Member'},'transactions':tx}

    @app.post('/api/v14/loyalty/award')
    async def award(request:Request):
        u=require(request,['owner']); body=await request.json(); uid=int(body.get('user_id')); pts=int(body.get('points',0)); reason=str(body.get('reason','APG bonus'))[:200]
        if pts==0 or abs(pts)>100000: raise HTTPException(400,'Некорректное количество баллов')
        c=db(); a=c.execute('SELECT id,points FROM loyalty_accounts WHERE user_id=?',(uid,)).fetchone()
        if a: c.execute('UPDATE loyalty_accounts SET points=?,level=?,updated_at=? WHERE user_id=?',(max(0,a['points']+pts),'VIP' if a['points']+pts>=1000 else 'Member',now(),uid))
        else: c.execute('INSERT INTO loyalty_accounts(user_id,points,level,updated_at) VALUES(?,?,?,?)',(uid,max(0,pts),'VIP' if pts>=1000 else 'Member',now()))
        c.execute('INSERT INTO loyalty_transactions(user_id,points,reason,created_at) VALUES(?,?,?,?)',(uid,pts,reason,now())); c.commit(); c.close(); notify(uid,'APG бонусы',f'{pts:+d} баллов: {reason}'); audit(u['id'],'Начислены бонусы',f'user={uid}, points={pts}'); return {'ok':True}

    @app.post('/api/v14/payments/create')
    async def payment_create(request:Request):
        u=require(request,['customer']); body=await request.json(); amount=str(body.get('amount','0'))[:40]; cid=body.get('company_id')
        try:
            if float(amount)<=0: raise ValueError
        except ValueError: raise HTTPException(400,'Некорректная сумма')
        c=db(); ref='APG-'+secrets.token_hex(8).upper(); pid=_id_insert(c,'INSERT INTO payment_intents(user_id,company_id,amount,currency,status,provider,provider_ref,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(u['id'],cid,amount,'EUR','created','mock',ref,now(),now())); c.commit(); c.close(); return {'id':pid,'provider':'mock','status':'created','checkout_reference':ref,'message':'Платёжный адаптер готов к подключению Stripe/Adyen'}

    @app.get('/api/v14/payments')
    def payments(request:Request):
        u=require(request,['owner']); c=db(); rows=c.execute('SELECT p.*,u.name customer_name,co.name company_name FROM payment_intents p JOIN users u ON u.id=p.user_id LEFT JOIN companies co ON co.id=p.company_id ORDER BY p.created_at DESC').fetchall(); c.close(); return rows

    @app.get('/api/v14/settings/company/{cid}')
    def company_settings(request:Request,cid:int):
        u=require(request,['owner','seller']); c=db();
        if u['role']=='seller' and not c.execute('SELECT 1 FROM seller_companies WHERE user_id=? AND company_id=?',(u['id'],cid)).fetchone(): c.close(); raise HTTPException(403,'Нет доступа')
        r=c.execute('SELECT * FROM company_settings WHERE company_id=?',(cid,)).fetchone(); c.close(); return r or {'company_id':cid,'booking_enabled':1,'chat_enabled':1,'loyalty_enabled':1,'accent':'white'}

    @app.patch('/api/v14/settings/company/{cid}')
    async def update_company_settings(request:Request,cid:int):
        u=require(request,['owner','seller']); body=await request.json(); c=db();
        if u['role']=='seller' and not c.execute('SELECT 1 FROM seller_companies WHERE user_id=? AND company_id=?',(u['id'],cid)).fetchone(): c.close(); raise HTTPException(403,'Нет доступа')
        vals=(int(bool(body.get('booking_enabled',1))),int(bool(body.get('chat_enabled',1))),int(bool(body.get('loyalty_enabled',1))),str(body.get('accent','white'))[:30],now())
        if c.execute('SELECT 1 FROM company_settings WHERE company_id=?',(cid,)).fetchone(): c.execute('UPDATE company_settings SET booking_enabled=?,chat_enabled=?,loyalty_enabled=?,accent=?,updated_at=? WHERE company_id=?',(*vals,cid))
        else: c.execute('INSERT INTO company_settings(company_id,booking_enabled,chat_enabled,loyalty_enabled,accent,updated_at) VALUES(?,?,?,?,?,?)',(cid,*vals))
        c.commit(); c.close(); audit(u['id'],'Настройки компании',str(cid)); return {'ok':True}
