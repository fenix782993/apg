
import os, sqlite3, random
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE=Path(__file__).parent
DB=BASE/"apg.sqlite3"
app=FastAPI(title="APG Community V16")

def db():
    c=sqlite3.connect(DB)
    c.row_factory=sqlite3.Row
    return c

def init():
    c=db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, public_id INTEGER UNIQUE, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, streak INTEGER DEFAULT 0, title TEXT DEFAULT 'Новичок', avatar TEXT DEFAULT '', background TEXT DEFAULT 'aurora');
    CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY, user_id INTEGER, text TEXT, image TEXT DEFAULT '', likes INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS scores(id INTEGER PRIMARY KEY, user_id INTEGER, game TEXT, score INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS missions(id INTEGER PRIMARY KEY, title TEXT, reward INTEGER, progress INTEGER DEFAULT 0, goal INTEGER DEFAULT 1);
    """)
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0]==0:
        for i,name in enumerate(["APG Rider","NightFox","RacerX"],1):
            c.execute("INSERT INTO users(username,password,public_id,xp,level,title,background) VALUES(?,?,?,?,?,?,?)",
                      (name.lower().replace(" ",""),"demo",random.randint(1,1_000_000_000),i*420,1+i,"Night Rider" if i==2 else "Новичок",["aurora","sunset","ice"][i-1]))
    if c.execute("SELECT COUNT(*) FROM missions").fetchone()[0]==0:
        c.executemany("INSERT INTO missions(title,reward,progress,goal) VALUES(?,?,?,?)",[
            ("Зайти в APG",50,1,1),("Сыграть 3 игры",120,1,3),("Поставить 5 лайков",80,2,5),("Добавить фото в галерею",150,0,1)])
    c.commit(); c.close()
init()

@app.get("/", response_class=HTMLResponse)
def index():
    return (BASE/"static/index.html").read_text(encoding="utf-8")

@app.get("/api/me")
def me():
    c=db(); u=c.execute("SELECT * FROM users ORDER BY id LIMIT 1").fetchone(); c.close()
    return dict(u)

@app.get("/api/feed")
def feed():
    c=db()
    rows=c.execute("""SELECT posts.*,users.username,users.public_id,users.avatar,users.title
                      FROM posts JOIN users ON users.id=posts.user_id ORDER BY posts.id DESC LIMIT 30""").fetchall()
    c.close()
    return [dict(x) for x in rows]

@app.post("/api/posts")
async def create_post(request:Request):
    data=await request.json(); c=db()
    u=c.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
    c.execute("INSERT INTO posts(user_id,text,image) VALUES(?,?,?)",(u["id"],data.get("text",""),data.get("image","")))
    c.commit(); c.close(); return {"ok":True}

@app.post("/api/like/{pid}")
def like(pid:int):
    c=db(); c.execute("UPDATE posts SET likes=likes+1 WHERE id=?",(pid,)); c.commit(); c.close(); return {"ok":True}

@app.get("/api/leaderboard")
def leaderboard():
    c=db(); rows=c.execute("SELECT username,public_id,xp,level,title FROM users ORDER BY xp DESC LIMIT 50").fetchall(); c.close()
    return [dict(x) for x in rows]

@app.get("/api/games/{game}")
def game_lb(game:str):
    c=db(); rows=c.execute("""SELECT users.username,users.public_id,scores.score FROM scores JOIN users ON users.id=scores.user_id
                              WHERE scores.game=? ORDER BY scores.score DESC LIMIT 20""",(game,)).fetchall(); c.close()
    return [dict(x) for x in rows]

@app.post("/api/games/{game}")
async def play(game:str, request:Request):
    data=await request.json(); score=int(data.get("score",0))
    c=db(); u=c.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
    c.execute("INSERT INTO scores(user_id,game,score) VALUES(?,?,?)",(u["id"],game,score))
    c.execute("UPDATE users SET xp=xp+? WHERE id=?",(max(5,min(score,500)),u["id"]))
    c.commit(); c.close(); return {"ok":True,"score":score}

@app.get("/api/missions")
def missions():
    c=db(); r=[dict(x) for x in c.execute("SELECT * FROM missions")]; c.close(); return r

@app.get("/api/pass")
def pass_api():
    c=db(); u=c.execute("SELECT xp,level FROM users ORDER BY id LIMIT 1").fetchone(); c.close()
    return {"season":"NIGHT DRIVE","free":True,"levels":50,"xp":u["xp"],"level":u["level"],
            "rewards":[{"level":1,"name":"Рамка APG"},{"level":5,"name":"Титул Racer"},{"level":10,"name":"Эффект Neon"},{"level":20,"name":"Фон Night Drive"},{"level":50,"name":"APG Legend"}]}

@app.get("/api/titles")
def titles():
    return [{"name":x,"rarity":r} for x,r in [
        ("Новичок","common"),("Фотограф","rare"),("Night Rider","epic"),("Racer","epic"),
        ("Collector","legendary"),("Car Lover","rare"),("APG Legend","mythic")]]

@app.get("/api/gallery")
def gallery():
    return [
        {"id":1,"title":"Night Drive","author":"APG Rider","image":"https://images.unsplash.com/photo-1504215680853-026ed2a45def?auto=format&fit=crop&w=900&q=80","likes":248},
        {"id":2,"title":"Urban Motion","author":"NightFox","image":"https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?auto=format&fit=crop&w=900&q=80","likes":184},
        {"id":3,"title":"After Rain","author":"RacerX","image":"https://images.unsplash.com/photo-1553440569-bcc63803a83d?auto=format&fit=crop&w=900&q=80","likes":129},
        {"id":4,"title":"Midnight","author":"APG Rider","image":"https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?auto=format&fit=crop&w=900&q=80","likes":96},
    ]

app.mount("/static",StaticFiles(directory=BASE/"static"),name="static")
