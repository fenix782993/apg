import secrets, random
from datetime import datetime, timezone
from fastapi import Request, HTTPException

def now(): return datetime.now(timezone.utc).isoformat()
def rid(): return random.randint(1,1_000_000_000)
def row(c, q, p=()): return c.execute(q,p).fetchone()
def init_community(db):
    c=db()
    stmts=[
    "CREATE TABLE IF NOT EXISTS community_profiles(user_id INTEGER PRIMARY KEY,xp INTEGER DEFAULT 0,level INTEGER DEFAULT 1,streak INTEGER DEFAULT 0,bio TEXT DEFAULT '',background TEXT DEFAULT 'midnight',gradient TEXT DEFAULT 'violet',frame TEXT DEFAULT 'basic',effect TEXT DEFAULT 'none',updated_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS public_ids(user_id INTEGER PRIMARY KEY,public_id BIGINT UNIQUE NOT NULL)",
    "CREATE TABLE IF NOT EXISTS titles(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE,title TEXT,description TEXT,rarity TEXT,icon TEXT,condition_type TEXT,condition_value INTEGER DEFAULT 1)",
    "CREATE TABLE IF NOT EXISTS user_titles(user_id INTEGER,title_id INTEGER,earned_at TEXT,PRIMARY KEY(user_id,title_id))",
    "CREATE TABLE IF NOT EXISTS achievements(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE,title TEXT,description TEXT,icon TEXT,condition_type TEXT,condition_value INTEGER DEFAULT 1)",
    "CREATE TABLE IF NOT EXISTS user_achievements(user_id INTEGER,achievement_id INTEGER,earned_at TEXT,PRIMARY KEY(user_id,achievement_id))",
    "CREATE TABLE IF NOT EXISTS pass_seasons(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,subtitle TEXT,active INTEGER DEFAULT 1,levels INTEGER DEFAULT 50,created_at TEXT)",
    "CREATE TABLE IF NOT EXISTS pass_rewards(id INTEGER PRIMARY KEY AUTOINCREMENT,season_id INTEGER,level INTEGER,title TEXT,kind TEXT,value TEXT,UNIQUE(season_id,level))",
    "CREATE TABLE IF NOT EXISTS user_pass(user_id INTEGER,season_id INTEGER,xp INTEGER DEFAULT 0,claimed TEXT DEFAULT '',PRIMARY KEY(user_id,season_id))",
    "CREATE TABLE IF NOT EXISTS daily_missions(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,description TEXT,kind TEXT,target INTEGER,xp INTEGER,active INTEGER DEFAULT 1)",
    "CREATE TABLE IF NOT EXISTS mission_progress(user_id INTEGER,mission_id INTEGER,day TEXT,progress INTEGER DEFAULT 0,claimed INTEGER DEFAULT 0,PRIMARY KEY(user_id,mission_id,day))",
    "CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,car_id INTEGER,caption TEXT,image TEXT,kind TEXT DEFAULT 'photo',created_at TEXT)",
    "CREATE TABLE IF NOT EXISTS post_likes(post_id INTEGER,user_id INTEGER,created_at TEXT,PRIMARY KEY(post_id,user_id))",
    "CREATE TABLE IF NOT EXISTS follows(follower_id INTEGER,following_id INTEGER,created_at TEXT,PRIMARY KEY(follower_id,following_id))",
    "CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY AUTOINCREMENT,post_id INTEGER,user_id INTEGER,body TEXT,created_at TEXT)",
    "CREATE TABLE IF NOT EXISTS game_scores(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,game TEXT,score INTEGER,xp INTEGER,created_at TEXT)",
    "CREATE TABLE IF NOT EXISTS game_daily(user_id INTEGER,game TEXT,day TEXT,plays INTEGER DEFAULT 0,PRIMARY KEY(user_id,game,day))",
    ]
    for s in stmts:
        try:c.execute(s)
        except Exception:pass
    # migration for public id on existing users
    try:c.execute("ALTER TABLE users ADD COLUMN public_id BIGINT")
    except Exception:pass
    # seed ids
    users=c.execute('SELECT id,public_id FROM users').fetchall()
    for u in users:
        if not u.get('public_id'):
            used={x['public_id'] for x in c.execute('SELECT public_id FROM users WHERE public_id IS NOT NULL').fetchall()}
            x=rid()
            while x in used:x=rid()
            c.execute('UPDATE users SET public_id=? WHERE id=?',(x,u['id']))
    for u in users:
        c.execute('INSERT OR IGNORE INTO community_profiles(user_id,updated_at) VALUES(?,?)',(u['id'],now()))
    titles=[('newbie','Новичок','Добавь первую машину','common','🚗','cars',1),('photographer','Фотограф','Опубликуй 25 фото','rare','📸','posts',25),('popular','Популярный','Получи 500 лайков','epic','🔥','likes',500),('night_rider','Night Rider','Собери 10 ночных публикаций','rare','🌙','night_posts',10),('racer','Racer','Выиграй 20 игр','epic','🏁','wins',20),('collector','Collector','Получи 25 достижений','legendary','💎','achievements',25),('car_lover','Car Lover','Активность 30 дней','rare','❤️','streak',30),('apg_legend','APG Legend','Достигни 50 уровня Pass','legendary','👑','pass_level',50)]
    for x in titles:c.execute('INSERT OR IGNORE INTO titles(code,title,description,rarity,icon,condition_type,condition_value) VALUES(?,?,?,?,?,?,?)',x)
    ach=[('first_photo','Первая фотография','Опубликуй первое фото','📷','posts',1),('first_game','Первая игра','Сыграй первую игру','🎮','games',1),('ten_games','Игрок','Сыграй 10 игр','🕹️','games',10),('hundred_likes','Первые 100','Получи 100 лайков','❤️','likes',100),('week_streak','Неделя','7 дней подряд','🔥','streak',7),('pass_10','Pass 10','Дойди до 10 уровня','🎫','pass_level',10)]
    for x in ach:c.execute('INSERT OR IGNORE INTO achievements(code,title,description,icon,condition_type,condition_value) VALUES(?,?,?,?,?,?)',x)
    if not row(c,'SELECT id FROM pass_seasons WHERE active=1'):
        c.execute('INSERT INTO pass_seasons(name,subtitle,levels,active,created_at) VALUES(?,?,?,?,?)',('SEASON 01 — NIGHT DRIVE','50 уровней. Бесплатный сезон APG.',50,1,now()))
        sid=row(c,'SELECT id FROM pass_seasons WHERE name=? ORDER BY id DESC LIMIT 1',('SEASON 01 — NIGHT DRIVE',))['id']
        for lvl in range(1,51):
            kind='title' if lvl in (10,20,30,40,50) else ('frame' if lvl%10==0 else 'xp')
            value=('APG LEGEND' if lvl==50 else f'Награда уровня {lvl}')
            c.execute('INSERT INTO pass_rewards(season_id,level,title,kind,value) VALUES(?,?,?,?,?)',(sid,lvl,f'Уровень {lvl}',kind,value))
    missions=[('Войти в APG','Открой приложение','login',1,10),('Фотограф','Опубликуй фото','posts',1,50),('Игрок','Сыграй 3 игры','games',3,100),('Социальный','Поставь 5 лайков','likes_given',5,40)]
    if not row(c,'SELECT id FROM daily_missions LIMIT 1'):
        for x in missions:c.execute('INSERT INTO daily_missions(title,description,kind,target,xp) VALUES(?,?,?,?,?)',x)
    c.commit();c.close()

def install(app,db,notify=None):
    def me(req):
        uid=req.session.get('uid');
        if not uid: raise HTTPException(401,'Требуется авторизация')
        return uid
    def grant(uid,xp,reason='Активность'):
        c=db(); p=row(c,'SELECT * FROM community_profiles WHERE user_id=?',(uid,)); old=p['xp'] if p else 0; new=old+max(0,int(xp)); level=min(50,1+new//250); c.execute('INSERT OR IGNORE INTO community_profiles(user_id,updated_at) VALUES(?,?)',(uid,now())); c.execute('UPDATE community_profiles SET xp=?,level=?,updated_at=? WHERE user_id=?',(new,level,now(),uid)); sid=row(c,'SELECT id FROM pass_seasons WHERE active=1');
        if sid:c.execute('INSERT OR IGNORE INTO user_pass(user_id,season_id,xp) VALUES(?,?,?)',(uid,sid['id'],new)); c.execute('UPDATE user_pass SET xp=? WHERE user_id=? AND season_id=?',(new,uid,sid['id']))
        c.commit();c.close();return {'xp':new,'level':level,'reason':reason}
    @app.get('/api/community/me')
    def community_me(request:Request):
        uid=me(request); c=db(); u=row(c,'SELECT id,public_id,name,username,avatar,email FROM users WHERE id=?',(uid,)); p=row(c,'SELECT * FROM community_profiles WHERE user_id=?',(uid,)); sid=row(c,'SELECT id FROM pass_seasons WHERE active=1'); pp=row(c,'SELECT xp FROM user_pass WHERE user_id=? AND season_id=?',(uid,sid['id'])) if sid else None; titles=c.execute('SELECT t.* FROM titles t JOIN user_titles ut ON ut.title_id=t.id WHERE ut.user_id=?',(uid,)).fetchall(); c.close(); return {'user':u,'profile':p,'pass':{'season':sid,'xp':pp['xp'] if pp else 0},'titles':titles}
    @app.get('/api/community/feed')
    def feed(request:Request,limit:int=30):
        uid=me(request); c=db(); rows=c.execute('''SELECT p.*,u.name,u.username,u.avatar,u.public_id,(SELECT COUNT(*) FROM post_likes l WHERE l.post_id=p.id) likes,(SELECT COUNT(*) FROM comments x WHERE x.post_id=p.id) comments,(SELECT 1 FROM post_likes l2 WHERE l2.post_id=p.id AND l2.user_id=? ) liked FROM posts p JOIN users u ON u.id=p.user_id ORDER BY p.created_at DESC LIMIT ?''',(uid,min(limit,50))).fetchall();c.close();return rows
    @app.post('/api/community/posts')
    async def post_create(request:Request):
        uid=me(request); b=await request.json(); image=str(b.get('image',''))[:500];caption=str(b.get('caption',''))[:1000];car=b.get('car_id');c=db(); c.execute('INSERT INTO posts(user_id,car_id,caption,image,kind,created_at) VALUES(?,?,?,?,?,?)',(uid,car,caption,image,'photo',now()));pid=c.execute('SELECT id FROM posts WHERE user_id=? ORDER BY id DESC LIMIT 1',(uid,)).fetchone()['id'];c.commit();c.close();grant(uid,20,'Фото');return {'ok':True,'id':pid}
    @app.post('/api/community/posts/{pid}/like')
    def like(request:Request,pid:int):
        uid=me(request);c=db(); exists=row(c,'SELECT 1 FROM post_likes WHERE post_id=? AND user_id=?',(pid,uid));
        if exists:c.execute('DELETE FROM post_likes WHERE post_id=? AND user_id=?',(pid,uid));delta=-1
        else:c.execute('INSERT INTO post_likes(post_id,user_id,created_at) VALUES(?,?,?)',(pid,uid,now()));delta=1
        c.commit();owner=row(c,'SELECT user_id FROM posts WHERE id=?',(pid,));c.close();
        if delta>0:grant(uid,3,'Лайк');
        return {'liked':delta>0}
    @app.post('/api/community/follow/{target}')
    def follow(request:Request,target:int):
        uid=me(request);c=db(); ex=row(c,'SELECT 1 FROM follows WHERE follower_id=? AND following_id=?',(uid,target));
        if ex:c.execute('DELETE FROM follows WHERE follower_id=? AND following_id=?',(uid,target));v=False
        else:c.execute('INSERT INTO follows(follower_id,following_id,created_at) VALUES(?,?,?)',(uid,target,now()));v=True
        c.commit();c.close();return {'following':v}
    @app.get('/api/community/titles')
    def titles(request:Request):
        uid=me(request);c=db();r=c.execute('SELECT t.*,CASE WHEN ut.user_id IS NULL THEN 0 ELSE 1 END earned,ut.earned_at FROM titles t LEFT JOIN user_titles ut ON ut.title_id=t.id AND ut.user_id=? ORDER BY t.id',(uid,)).fetchall();c.close();return r
    @app.get('/api/community/achievements')
    def achievements(request:Request):
        uid=me(request);c=db();r=c.execute('SELECT a.*,CASE WHEN ua.user_id IS NULL THEN 0 ELSE 1 END earned,ua.earned_at FROM achievements a LEFT JOIN user_achievements ua ON ua.achievement_id=a.id AND ua.user_id=? ORDER BY a.id',(uid,)).fetchall();c.close();return r
    @app.get('/api/community/leaderboard')
    def leaderboard(request:Request):
        me(request);c=db();r=c.execute('SELECT u.public_id,u.name,u.username,u.avatar,p.xp,p.level FROM users u JOIN community_profiles p ON p.user_id=u.id WHERE u.active=1 ORDER BY p.xp DESC LIMIT 100').fetchall();c.close();return r
    @app.get('/api/community/games/{game}/leaderboard')
    def game_leader(request:Request,game:str):
        me(request);c=db();r=c.execute('SELECT u.public_id,u.name,MAX(g.score) score FROM game_scores g JOIN users u ON u.id=g.user_id WHERE g.game=? GROUP BY u.id ORDER BY score DESC LIMIT 50',(game,)).fetchall();c.close();return r
    @app.post('/api/community/games/{game}/play')
    async def game_play(request:Request,game:str):
        uid=me(request);b=await request.json();score=max(0,min(100000,int(b.get('score',0))));xp=min(100,10+score//20);c=db();c.execute('INSERT INTO game_scores(user_id,game,score,xp,created_at) VALUES(?,?,?,?,?)',(uid,game,score,xp,now()));c.commit();c.close();grant(uid,xp,f'Игра {game}');return {'ok':True,'score':score,'xp':xp}
    @app.get('/api/community/missions')
    def missions(request:Request):
        uid=me(request);day=datetime.now(timezone.utc).date().isoformat();c=db();rows=c.execute('SELECT m.*,COALESCE(p.progress,0) progress,COALESCE(p.claimed,0) claimed FROM daily_missions m LEFT JOIN mission_progress p ON p.mission_id=m.id AND p.user_id=? AND p.day=? WHERE m.active=1',(uid,day)).fetchall();c.close();return rows
    @app.get('/api/community/pass')
    def pass_page(request:Request):
        uid=me(request);c=db();s=row(c,'SELECT * FROM pass_seasons WHERE active=1');rewards=c.execute('SELECT * FROM pass_rewards WHERE season_id=? ORDER BY level',(s['id'],)).fetchall() if s else [];p=row(c,'SELECT * FROM user_pass WHERE user_id=? AND season_id=?',(uid,s['id'])) if s else None;c.close();return {'season':s,'xp':p['xp'] if p else 0,'rewards':rewards}
    @app.patch('/api/community/profile')
    async def customize(request:Request):
        uid=me(request);b=await request.json();allowed={k:str(b.get(k,''))[:40] for k in ('bio','background','gradient','frame','effect')};c=db();c.execute('UPDATE community_profiles SET bio=?,background=?,gradient=?,frame=?,effect=?,updated_at=? WHERE user_id=?',(*[allowed[k] for k in ('bio','background','gradient','frame','effect')],now(),uid));c.commit();c.close();return {'ok':True}
