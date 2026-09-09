from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from io import BytesIO
import sqlite3, secrets, hashlib, time, os
import qrcode

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"
DB = Path(os.getenv("APG_DB", BASE / "apg.sqlite3"))

app = FastAPI(title="APG — Авто Партнёрская Группа", version="2.0.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con=db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, apg_id TEXT UNIQUE, tier TEXT, discount INTEGER, savings REAL DEFAULT 247);
    CREATE TABLE IF NOT EXISTS partners(id INTEGER PRIMARY KEY, name TEXT, category TEXT, rating REAL, distance TEXT, discount INTEGER, address TEXT);
    CREATE TABLE IF NOT EXISTS discounts(id INTEGER PRIMARY KEY, partner_id INTEGER, title TEXT, discount INTEGER, valid_until TEXT);
    CREATE TABLE IF NOT EXISTS redemptions(id INTEGER PRIMARY KEY, user_id INTEGER, discount_id INTEGER, token TEXT UNIQUE, created_at INTEGER, status TEXT);
    CREATE TABLE IF NOT EXISTS cars(id INTEGER PRIMARY KEY, user_id INTEGER, brand TEXT, model TEXT, year INTEGER, fuel TEXT, mileage INTEGER, vin TEXT);
    """)
    if con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        con.execute("INSERT INTO users(name,apg_id,tier,discount,savings) VALUES(?,?,?,?,?)",("Fenix","APG-184729","GOLD",10,247))
        uid=con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.executemany("INSERT INTO cars(user_id,brand,model,year,fuel,mileage,vin) VALUES(?,?,?,?,?,?,?)",[
            (uid,"BMW","530d",2019,"Дизель",182430,"WBAAPG530D2019"),
        ])
        partners=[
            ("APG Auto Service","Сервис",4.9,"1.2 км",15,"Центральная, 12"),
            ("APG Tire","Шины",4.8,"2.4 км",20,"Автомобильная, 8"),
            ("APG Parts","Запчасти",4.7,"3.1 км",10,"Партнёрская, 5"),
            ("APG Wash","Мойка",4.9,"0.8 км",25,"Гаражная, 21"),
            ("APG Motors","Автосалон",4.8,"4.2 км",7,"Моторная, 4"),
            ("APG Detail","Детейлинг",4.9,"2.0 км",15,"Детейлинговая, 3"),
        ]
        con.executemany("INSERT INTO partners(name,category,rating,distance,discount,address) VALUES(?,?,?,?,?,?)",partners)
        for pid in range(1,len(partners)+1):
            con.execute("INSERT INTO discounts(partner_id,title,discount,valid_until) VALUES(?,?,?,?)",
                        (pid,["ТО и диагностика","Шиномонтаж и сезонная замена","Запчасти и аксессуары","Комплексная мойка","Покупка автомобиля","Детейлинг"][pid-1],partners[pid-1][4],"31.12.2026"))
    con.commit(); con.close()
init_db()

class QRRequest(BaseModel):
    user_id: str = "APG-184729"
    discount_id: int | None = None
    discount: int = 10

class RedeemRequest(BaseModel):
    token: str

@app.get("/")
def home(): return FileResponse(STATIC/"index.html")

@app.get("/api/health")
def health(): return {"status":"ok","service":"APG","version":"2.0.0"}

@app.get("/api/me")
def me():
    con=db()
    u=con.execute("SELECT * FROM users LIMIT 1").fetchone()
    car=con.execute("SELECT * FROM cars WHERE user_id=? LIMIT 1",(u["id"],)).fetchone()
    con.close()
    return {"user":dict(u),"car":dict(car) if car else None}

@app.get("/api/partners")
def partners(q: str = "", category: str = "Все"):
    con=db()
    if category=="Все":
        rows=con.execute("SELECT * FROM partners WHERE name LIKE ? OR category LIKE ? ORDER BY rating DESC",(f"%{q}%",f"%{q}%")).fetchall()
    else:
        rows=con.execute("SELECT * FROM partners WHERE category=? AND (name LIKE ? OR category LIKE ?) ORDER BY rating DESC",(category,f"%{q}%",f"%{q}%")).fetchall()
    con.close(); return [dict(x) for x in rows]

@app.get("/api/discounts")
def discount_list():
    con=db()
    rows=con.execute("""SELECT d.*,p.name partner,p.category,p.rating,p.distance
                        FROM discounts d JOIN partners p ON p.id=d.partner_id ORDER BY d.discount DESC""").fetchall()
    con.close(); return [dict(x) for x in rows]

@app.get("/api/history")
def history():
    con=db()
    rows=con.execute("""SELECT r.id,r.created_at,r.status,d.title,d.discount,p.name partner
                        FROM redemptions r JOIN discounts d ON d.id=r.discount_id
                        JOIN partners p ON p.id=d.partner_id ORDER BY r.id DESC""").fetchall()
    con.close(); return [dict(x) for x in rows]

@app.post("/api/qr")
def create_qr(data: QRRequest):
    con=db()
    uid=con.execute("SELECT id FROM users WHERE apg_id=?",(data.user_id,)).fetchone()
    if not uid: return JSONResponse({"error":"user_not_found"},404)
    did=data.discount_id
    if did:
        row=con.execute("SELECT discount FROM discounts WHERE id=?",(did,)).fetchone()
        if row: data.discount=int(row["discount"])
    token=secrets.token_urlsafe(24)
    con.execute("INSERT INTO redemptions(user_id,discount_id,token,created_at,status) VALUES(?,?,?,?,?)",
                (uid["id"],did,token,int(time.time()),"ACTIVE"))
    con.commit(); con.close()
    payload=f"APG|{data.user_id}|{data.discount}|{token}"
    img=qrcode.make(payload)
    buf=BytesIO(); img.save(buf,"PNG"); buf.seek(0)
    return StreamingResponse(buf,media_type="image/png",headers={"X-APG-Token":token})

@app.post("/api/redeem")
def redeem(data: RedeemRequest):
    con=db()
    row=con.execute("""SELECT r.*,d.discount,d.title,p.name partner FROM redemptions r
                       LEFT JOIN discounts d ON d.id=r.discount_id LEFT JOIN partners p ON p.id=d.partner_id
                       WHERE r.token=?""",(data.token,)).fetchone()
    if not row: return JSONResponse({"valid":False,"message":"QR не найден"},404)
    if row["status"]!="ACTIVE" or int(time.time())-row["created_at"]>300:
        return {"valid":False,"message":"QR истёк или уже использован"}
    con.execute("UPDATE redemptions SET status='USED' WHERE token=?",(data.token,)); con.commit(); con.close()
    return {"valid":True,"message":"Скидка применена","discount":row["discount"],"partner":row["partner"],"title":row["title"]}

@app.get("/api/stats")
def stats():
    con=db()
    return_data={
        "partners":con.execute("SELECT COUNT(*) FROM partners").fetchone()[0],
        "discounts":con.execute("SELECT COUNT(*) FROM discounts").fetchone()[0],
        "used":con.execute("SELECT COUNT(*) FROM redemptions WHERE status='USED'").fetchone()[0],
        "active":con.execute("SELECT COUNT(*) FROM redemptions WHERE status='ACTIVE'").fetchone()[0],
    }
    con.close(); return return_data
