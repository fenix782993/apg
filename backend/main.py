import os,secrets,hashlib,datetime as dt
from enum import Enum
from typing import Optional
from fastapi import FastAPI,Depends,HTTPException,Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,Field
from sqlalchemy import create_engine,String,Integer,Boolean,DateTime,Text,ForeignKey,Float
from sqlalchemy.orm import DeclarativeBase,Mapped,mapped_column,Session
from passlib.context import CryptContext
from jose import jwt

DB=os.getenv("DATABASE_URL","sqlite:///./apg.db")
if DB.startswith("postgres://"): DB=DB.replace("postgres://","postgresql://",1)
engine=create_engine(DB,connect_args={"check_same_thread":False} if DB.startswith("sqlite") else {})
pwd=CryptContext(schemes=["bcrypt"],deprecated="auto")
SECRET=os.getenv("JWT_SECRET","apg-dev-secret")
class Base(DeclarativeBase): pass
class Role(str,Enum): CLIENT="CLIENT";SELLER="SELLER";OWNER="OWNER"

class User(Base):
 __tablename__="users"
 id:Mapped[int]=mapped_column(primary_key=True);email:Mapped[str]=mapped_column(String(255),unique=True,index=True)
 password:Mapped[str]=mapped_column(String(255));name:Mapped[str]=mapped_column(String(120),default="APG User")
 phone:Mapped[str]=mapped_column(String(40),default="");avatar:Mapped[str]=mapped_column(String(500),default="")
 role:Mapped[str]=mapped_column(String(20),default="CLIENT");points:Mapped[int]=mapped_column(Integer,default=0);xp:Mapped[int]=mapped_column(Integer,default=0)
 created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow)

class Partner(Base):
 __tablename__="partners"
 id:Mapped[int]=mapped_column(primary_key=True);owner_id:Mapped[int]=mapped_column(ForeignKey("users.id"))
 company:Mapped[str]=mapped_column(String(180));address:Mapped[str]=mapped_column(String(300),default="")
 phone:Mapped[str]=mapped_column(String(60),default="");website:Mapped[str]=mapped_column(String(300),default="")
 hours:Mapped[str]=mapped_column(String(200),default="");category:Mapped[str]=mapped_column(String(100),default="Авто")
 rating:Mapped[float]=mapped_column(Float,default=5);active:Mapped[bool]=mapped_column(Boolean,default=True)

class Discount(Base):
 __tablename__="discounts"
 id:Mapped[int]=mapped_column(primary_key=True);seller_id:Mapped[int]=mapped_column(ForeignKey("users.id"))
 partner_id:Mapped[Optional[int]]=mapped_column(ForeignKey("partners.id"),nullable=True)
 title:Mapped[str]=mapped_column(String(180));description:Mapped[str]=mapped_column(Text,default="")
 image:Mapped[str]=mapped_column(String(500),default="");percent:Mapped[int]=mapped_column(Integer)
 expires_at:Mapped[Optional[dt.datetime]]=mapped_column(DateTime,nullable=True);address:Mapped[str]=mapped_column(String(300),default="")
 contacts:Mapped[str]=mapped_column(String(300),default="");enabled:Mapped[bool]=mapped_column(Boolean,default=True)
 status:Mapped[str]=mapped_column(String(20),default="PENDING");activations:Mapped[int]=mapped_column(Integer,default=0)
 created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow)

class Redemption(Base):
 __tablename__="redemptions"
 id:Mapped[int]=mapped_column(primary_key=True);discount_id:Mapped[int]=mapped_column(ForeignKey("discounts.id"));user_id:Mapped[int]=mapped_column(ForeignKey("users.id"))
 token_hash:Mapped[str]=mapped_column(String(128),unique=True);expires_at:Mapped[dt.datetime]=mapped_column(DateTime);used:Mapped[bool]=mapped_column(Boolean,default=False)

class Car(Base):
 __tablename__="cars"
 id:Mapped[int]=mapped_column(primary_key=True);user_id:Mapped[int]=mapped_column(ForeignKey("users.id"))
 brand:Mapped[str]=mapped_column(String(80));model:Mapped[str]=mapped_column(String(100));year:Mapped[int]=mapped_column(Integer)
 vin:Mapped[str]=mapped_column(String(80),default="");mileage:Mapped[int]=mapped_column(Integer,default=0)

class GameResult(Base):
 __tablename__="game_results"
 id:Mapped[int]=mapped_column(primary_key=True);user_id:Mapped[int]=mapped_column(ForeignKey("users.id"))
 game:Mapped[str]=mapped_column(String(60));score:Mapped[int]=mapped_column(Integer);xp:Mapped[int]=mapped_column(Integer);points:Mapped[int]=mapped_column(Integer)
 created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow)

Base.metadata.create_all(engine)
app=FastAPI(title="APG V4 API")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

def db():
 with Session(engine) as s: yield s
def out(u): return {"id":u.id,"email":u.email,"name":u.name,"phone":u.phone,"avatar":u.avatar,"role":u.role,"points":u.points,"xp":u.xp}
def tok(u): return jwt.encode({"sub":str(u.id),"exp":dt.datetime.utcnow()+dt.timedelta(days=7)},SECRET,algorithm="HS256")
def me(authorization:Optional[str]=Header(None),s:Session=Depends(db)):
 if not authorization: raise HTTPException(401,"Требуется авторизация")
 try: uid=int(jwt.decode(authorization.replace("Bearer ",""),SECRET,algorithms=["HS256"])["sub"])
 except: raise HTTPException(401,"Сессия истекла")
 u=s.get(User,uid)
 if not u: raise HTTPException(401,"Пользователь не найден")
 return u

class Auth(BaseModel): email:str;password:str;name:str="APG User"
class Offer(BaseModel):
 title:str;description:str="";percent:int=Field(ge=1,le=99);expires_at:Optional[dt.datetime]=None;address:str="";contacts:str="";image:str="";partner_id:Optional[int]=None;enabled:bool=True
class CarIn(BaseModel): brand:str;model:str;year:int;vin:str="";mileage:int=0
class Game(BaseModel): game:str;score:int=Field(ge=0,le=1000000)

@app.get("/api/health")
def health(): return {"status":"ok","service":"APG V4"}

@app.post("/api/auth/register")
def register(x:Auth,s:Session=Depends(db)):
 if s.query(User).filter_by(email=x.email.lower()).first(): raise HTTPException(400,"Email уже зарегистрирован")
 u=User(email=x.email.lower(),password=pwd.hash(x.password),name=x.name);s.add(u);s.commit();s.refresh(u)
 return {"token":tok(u),"user":out(u)}
@app.post("/api/auth/login")
def login(x:Auth,s:Session=Depends(db)):
 u=s.query(User).filter_by(email=x.email.lower()).first()
 if not u or not pwd.verify(x.password,u.password): raise HTTPException(401,"Неверный email или пароль")
 return {"token":tok(u),"user":out(u)}
@app.get("/api/me")
def getme(u=Depends(me)): return out(u)

def dout(d): return {"id":d.id,"seller_id":d.seller_id,"partner_id":d.partner_id,"title":d.title,"description":d.description,"image":d.image,"percent":d.percent,"expires_at":d.expires_at.isoformat() if d.expires_at else None,"address":d.address,"contacts":d.contacts,"enabled":d.enabled,"status":d.status,"activations":d.activations}
@app.get("/api/discounts")
def list_discounts(s:Session=Depends(db)): return [dout(d) for d in s.query(Discount).filter_by(status="APPROVED",enabled=True).order_by(Discount.created_at.desc()).all()]
@app.get("/api/my/discounts")
def my_discounts(u=Depends(me),s:Session=Depends(db)):
 q=s.query(Discount) if u.role=="OWNER" else s.query(Discount).filter_by(seller_id=u.id)
 return [dout(d) for d in q.order_by(Discount.created_at.desc()).all()]
@app.post("/api/discounts")
def create(x:Offer,u=Depends(me),s:Session=Depends(db)):
 if u.role not in ("SELLER","OWNER"): raise HTTPException(403,"Недостаточно прав")
 d=Discount(**x.model_dump(),seller_id=u.id,status="APPROVED" if u.role=="OWNER" else "PENDING");s.add(d);s.commit();s.refresh(d);return dout(d)
@app.delete("/api/discounts/{did}")
def delete(did:int,u=Depends(me),s:Session=Depends(db)):
 d=s.get(Discount,did)
 if not d or (u.role!="OWNER" and d.seller_id!=u.id): raise HTTPException(404,"Скидка не найдена")
 s.delete(d);s.commit();return {"ok":True}
@app.post("/api/discounts/{did}/qr")
def qr(did:int,u=Depends(me),s:Session=Depends(db)):
 d=s.get(Discount,did)
 if not d or d.status!="APPROVED" or not d.enabled: raise HTTPException(404,"Скидка недоступна")
 raw=secrets.token_urlsafe(24);r=Redemption(discount_id=did,user_id=u.id,token_hash=hashlib.sha256(raw.encode()).hexdigest(),expires_at=dt.datetime.utcnow()+dt.timedelta(minutes=15))
 s.add(r);s.commit();return {"token":raw,"expires_at":r.expires_at.isoformat(),"discount":dout(d)}
@app.post("/api/discounts/redeem")
def redeem(data:dict,u=Depends(me),s:Session=Depends(db)):
 r=s.query(Redemption).filter_by(token_hash=hashlib.sha256(str(data.get("token","")).encode()).hexdigest()).first()
 if not r or r.used or r.expires_at<dt.datetime.utcnow() or r.user_id!=u.id: raise HTTPException(400,"QR недействителен")
 d=s.get(Discount,r.discount_id);r.used=True;d.activations+=1;s.commit();return {"ok":True}

@app.get("/api/partners")
def partners(s:Session=Depends(db)): return [{"id":p.id,"company":p.company,"address":p.address,"phone":p.phone,"website":p.website,"hours":p.hours,"category":p.category,"rating":p.rating} for p in s.query(Partner).filter_by(active=True).all()]

@app.get("/api/cars")
def cars(u=Depends(me),s:Session=Depends(db)): return [{"id":c.id,"brand":c.brand,"model":c.model,"year":c.year,"vin":c.vin,"mileage":c.mileage} for c in s.query(Car).filter_by(user_id=u.id).all()]
@app.post("/api/cars")
def addcar(x:CarIn,u=Depends(me),s:Session=Depends(db)):
 c=Car(user_id=u.id,**x.model_dump());s.add(c);s.commit();s.refresh(c);return {"id":c.id,**x.model_dump()}
@app.delete("/api/cars/{cid}")
def delcar(cid:int,u=Depends(me),s:Session=Depends(db)):
 c=s.get(Car,cid)
 if not c or c.user_id!=u.id: raise HTTPException(404,"Автомобиль не найден")
 s.delete(c);s.commit();return {"ok":True}

@app.post("/api/games/result")
def game(x:Game,u=Depends(me),s:Session=Depends(db)):
 xp=min(500,max(5,x.score//10));points=min(300,max(2,x.score//20))
 u.xp+=xp;u.points+=points;s.add(GameResult(user_id=u.id,game=x.game,score=x.score,xp=xp,points=points));s.commit()
 return {"score":x.score,"xp":xp,"points":points,"total_xp":u.xp,"total_points":u.points}
@app.get("/api/games/leaderboard")
def leaderboard(s:Session=Depends(db)):
 return [{"name":u.name,"points":u.points,"xp":u.xp} for u in s.query(User).order_by(User.points.desc()).limit(20).all()]

@app.get("/api/owner/queue")
def queue(u=Depends(me),s:Session=Depends(db)):
 if u.role!="OWNER": raise HTTPException(403,"Только OWNER")
 return [dout(d) for d in s.query(Discount).filter_by(status="PENDING").all()]
@app.patch("/api/owner/discount/{did}/{action}")
def moderate(did:int,action:str,u=Depends(me),s:Session=Depends(db)):
 if u.role!="OWNER": raise HTTPException(403,"Только OWNER")
 d=s.get(Discount,did)
 if not d: raise HTTPException(404,"Не найдено")
 if action not in ("approve","reject"): raise HTTPException(400,"Действие")
 d.status="APPROVED" if action=="approve" else "REJECTED";s.commit();return dout(d)
@app.get("/api/owner/users")
def users(u=Depends(me),s:Session=Depends(db)):
 if u.role!="OWNER": raise HTTPException(403,"Только OWNER")
 return [out(x) for x in s.query(User).all()]
@app.patch("/api/owner/users/{uid}/role")
def role(uid:int,role:str,u=Depends(me),s:Session=Depends(db)):
 if u.role!="OWNER" or role not in ("CLIENT","SELLER","OWNER"): raise HTTPException(403,"Недостаточно прав")
 x=s.get(User,uid)
 if not x: raise HTTPException(404,"Пользователь")
 x.role=role;s.commit();return out(x)

@app.on_event("startup")
def seed():
 with Session(engine) as s:
  if not s.query(User).filter_by(email="owner@apg.local").first():
   s.add(User(email="owner@apg.local",password=pwd.hash("owner123"),name="APG Owner",role="OWNER"));s.commit()
