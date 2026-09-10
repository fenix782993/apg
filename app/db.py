import os
import re
from pathlib import Path
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
SQLITE_PATH = BASE / 'apg.sqlite3'
RAW_URL = os.getenv('DATABASE_URL', '').strip()
if RAW_URL.startswith('postgres://'):
    RAW_URL = 'postgresql+psycopg://' + RAW_URL[len('postgres://'):]
elif RAW_URL.startswith('postgresql://'):
    RAW_URL = 'postgresql+psycopg://' + RAW_URL[len('postgresql://'):]

DATABASE_URL = RAW_URL or f'sqlite:///{SQLITE_PATH}'
IS_POSTGRES = DATABASE_URL.startswith('postgresql+')
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

class RowResult:
    def __init__(self, result):
        self._result = result
        self.rowcount = result.rowcount
    def fetchone(self):
        row = self._result.fetchone()
        return dict(row._mapping) if row else None
    def fetchall(self):
        return [dict(row._mapping) for row in self._result.fetchall()]

class DB:
    def __init__(self):
        self.conn = engine.connect()
    def execute(self, sql, params=()):
        original = sql.strip().upper()
        sql = sql.replace('INSERT OR IGNORE', 'INSERT')
        if original.startswith('INSERT OR IGNORE INTO SELLER_COMPANIES') or original.startswith('INSERT OR IGNORE INTO FAVORITES') or original.startswith('INSERT OR IGNORE INTO SETTINGS'):
            sql = sql.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
        if IS_POSTGRES:
            sql = sql.replace('?', '%s')
        # SQLAlchemy 2.x exec_driver_sql does not accept a bare list
        # as positional parameters. Normalize lists to tuples so endpoints
        # that build dynamic filters (for example /api/offers) work.
        if isinstance(params, list):
            params = tuple(params)
        result = self.conn.exec_driver_sql(sql, params)
        return RowResult(result)
    def executescript(self, script):
        for statement in [s.strip() for s in script.split(';') if s.strip()]:
            self.conn.exec_driver_sql(statement)
    def commit(self):
        self.conn.commit()
    def close(self):
        self.conn.close()

def db():
    return DB()

def schema():
    if IS_POSTGRES:
        return '''
        CREATE TABLE IF NOT EXISTS users(id BIGSERIAL PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL,active INTEGER DEFAULT 1,avatar TEXT DEFAULT '',phone TEXT DEFAULT '',username TEXT UNIQUE,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS companies(id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL,description TEXT DEFAULT '',logo TEXT DEFAULT '',cover TEXT DEFAULT '',address TEXT DEFAULT '',phone TEXT DEFAULT '',hours TEXT DEFAULT '',category TEXT DEFAULT 'Авто',active INTEGER DEFAULT 1,latitude REAL,longitude REAL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS seller_companies(user_id BIGINT NOT NULL,company_id BIGINT NOT NULL,PRIMARY KEY(user_id,company_id),FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS offers(id BIGSERIAL PRIMARY KEY,company_id BIGINT NOT NULL,title TEXT NOT NULL,description TEXT DEFAULT '',discount TEXT DEFAULT '',valid_until TEXT DEFAULT '',image TEXT DEFAULT '',status TEXT DEFAULT 'pending',created_by BIGINT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(company_id) REFERENCES companies(id));
        CREATE TABLE IF NOT EXISTS gallery(id BIGSERIAL PRIMARY KEY,company_id BIGINT NOT NULL,title TEXT DEFAULT '',caption TEXT DEFAULT '',image TEXT NOT NULL,sort_order INTEGER DEFAULT 0,active INTEGER DEFAULT 1,created_at TEXT NOT NULL,FOREIGN KEY(company_id) REFERENCES companies(id));
        CREATE TABLE IF NOT EXISTS services(id BIGSERIAL PRIMARY KEY,company_id BIGINT NOT NULL,title TEXT NOT NULL,description TEXT DEFAULT '',price TEXT DEFAULT '',image TEXT DEFAULT '',sort_order INTEGER DEFAULT 0,active INTEGER DEFAULT 1,created_at TEXT NOT NULL,FOREIGN KEY(company_id) REFERENCES companies(id));
        CREATE TABLE IF NOT EXISTS reviews(id BIGSERIAL PRIMARY KEY,company_id BIGINT NOT NULL,user_id BIGINT NOT NULL,rating INTEGER NOT NULL,body TEXT DEFAULT '',status TEXT DEFAULT 'pending',created_at TEXT NOT NULL,FOREIGN KEY(company_id) REFERENCES companies(id));
        CREATE TABLE IF NOT EXISTS cars(id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL,model TEXT DEFAULT '',year TEXT DEFAULT '',plate TEXT DEFAULT '',vin TEXT DEFAULT '',mileage TEXT DEFAULT '',photo TEXT DEFAULT '',created_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS history(id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL,car_id BIGINT,company_id BIGINT,title TEXT NOT NULL,note TEXT DEFAULT '',service_date TEXT DEFAULT '',created_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS favorites(user_id BIGINT NOT NULL,company_id BIGINT NOT NULL,PRIMARY KEY(user_id,company_id));
        CREATE TABLE IF NOT EXISTS qr_tokens(token TEXT PRIMARY KEY,offer_id BIGINT NOT NULL,user_id BIGINT NOT NULL,expires_at TEXT NOT NULL,used INTEGER DEFAULT 0,used_at TEXT DEFAULT '',redeemed_by BIGINT,FOREIGN KEY(offer_id) REFERENCES offers(id));
        CREATE TABLE IF NOT EXISTS notifications(id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL,title TEXT NOT NULL,body TEXT DEFAULT '',read INTEGER DEFAULT 0,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id BIGSERIAL PRIMARY KEY,user_id BIGINT,title TEXT NOT NULL,details TEXT DEFAULT '',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS push_tokens(id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL,token TEXT UNIQUE NOT NULL,platform TEXT DEFAULT 'web',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(user_id BIGINT PRIMARY KEY,accent TEXT DEFAULT 'white',density TEXT DEFAULT 'comfortable',animations INTEGER DEFAULT 1,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS bookings(id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL,company_id BIGINT NOT NULL,service_id BIGINT,car_id BIGINT,slot TEXT NOT NULL,note TEXT DEFAULT '',status TEXT DEFAULT 'pending',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS conversations(id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL,company_id BIGINT NOT NULL,status TEXT DEFAULT 'open',updated_at TEXT NOT NULL,UNIQUE(user_id,company_id),FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS messages(id BIGSERIAL PRIMARY KEY,conversation_id BIGINT NOT NULL,sender_id BIGINT NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL,FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS promo_codes(id BIGSERIAL PRIMARY KEY,code TEXT UNIQUE NOT NULL,description TEXT DEFAULT '',discount TEXT DEFAULT '',expires_at TEXT DEFAULT '',max_uses INTEGER DEFAULT 0,used_count INTEGER DEFAULT 0,active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS promo_redemptions(id BIGSERIAL PRIMARY KEY,promo_id BIGINT NOT NULL,user_id BIGINT NOT NULL,created_at TEXT NOT NULL,UNIQUE(promo_id,user_id),FOREIGN KEY(promo_id) REFERENCES promo_codes(id) ON DELETE CASCADE,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS partner_plans(id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL,description TEXT DEFAULT '',price TEXT DEFAULT '',period TEXT DEFAULT 'month',active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS company_subscriptions(id BIGSERIAL PRIMARY KEY,company_id BIGINT NOT NULL,plan_id BIGINT NOT NULL,status TEXT DEFAULT 'trial',starts_at TEXT NOT NULL,ends_at TEXT DEFAULT '',created_at TEXT NOT NULL,FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE,FOREIGN KEY(plan_id) REFERENCES partner_plans(id));

        '''
    return '''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL,active INTEGER DEFAULT 1,avatar TEXT DEFAULT '',phone TEXT DEFAULT '',username TEXT UNIQUE,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,description TEXT DEFAULT '',logo TEXT DEFAULT '',cover TEXT DEFAULT '',address TEXT DEFAULT '',phone TEXT DEFAULT '',hours TEXT DEFAULT '',category TEXT DEFAULT 'Авто',active INTEGER DEFAULT 1,latitude REAL,longitude REAL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS seller_companies(user_id INTEGER NOT NULL,company_id INTEGER NOT NULL,PRIMARY KEY(user_id,company_id),FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS offers(id INTEGER PRIMARY KEY AUTOINCREMENT,company_id INTEGER NOT NULL,title TEXT NOT NULL,description TEXT DEFAULT '',discount TEXT DEFAULT '',valid_until TEXT DEFAULT '',image TEXT DEFAULT '',status TEXT DEFAULT 'pending',created_by INTEGER,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(company_id) REFERENCES companies(id));
    CREATE TABLE IF NOT EXISTS gallery(id INTEGER PRIMARY KEY AUTOINCREMENT,company_id INTEGER NOT NULL,title TEXT DEFAULT '',caption TEXT DEFAULT '',image TEXT NOT NULL,sort_order INTEGER DEFAULT 0,active INTEGER DEFAULT 1,created_at TEXT NOT NULL,FOREIGN KEY(company_id) REFERENCES companies(id));
    CREATE TABLE IF NOT EXISTS services(id INTEGER PRIMARY KEY AUTOINCREMENT,company_id INTEGER NOT NULL,title TEXT NOT NULL,description TEXT DEFAULT '',price TEXT DEFAULT '',image TEXT DEFAULT '',sort_order INTEGER DEFAULT 0,active INTEGER DEFAULT 1,created_at TEXT NOT NULL,FOREIGN KEY(company_id) REFERENCES companies(id));
    CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,company_id INTEGER NOT NULL,user_id INTEGER NOT NULL,rating INTEGER NOT NULL,body TEXT DEFAULT '',status TEXT DEFAULT 'pending',created_at TEXT NOT NULL,FOREIGN KEY(company_id) REFERENCES companies(id));
    CREATE TABLE IF NOT EXISTS cars(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,model TEXT DEFAULT '',year TEXT DEFAULT '',plate TEXT DEFAULT '',vin TEXT DEFAULT '',mileage TEXT DEFAULT '',photo TEXT DEFAULT '',created_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,car_id INTEGER,company_id INTEGER,title TEXT NOT NULL,note TEXT DEFAULT '',service_date TEXT DEFAULT '',created_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS favorites(user_id INTEGER NOT NULL,company_id INTEGER NOT NULL,PRIMARY KEY(user_id,company_id));
    CREATE TABLE IF NOT EXISTS qr_tokens(token TEXT PRIMARY KEY,offer_id INTEGER NOT NULL,user_id INTEGER NOT NULL,expires_at TEXT NOT NULL,used INTEGER DEFAULT 0,used_at TEXT DEFAULT '',redeemed_by INTEGER,FOREIGN KEY(offer_id) REFERENCES offers(id));
    CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,title TEXT NOT NULL,body TEXT DEFAULT '',read INTEGER DEFAULT 0,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,title TEXT NOT NULL,details TEXT DEFAULT '',created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS push_tokens(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,token TEXT UNIQUE NOT NULL,platform TEXT DEFAULT 'web',created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS settings(user_id INTEGER PRIMARY KEY,accent TEXT DEFAULT 'white',density TEXT DEFAULT 'comfortable',animations INTEGER DEFAULT 1,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);

        CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,company_id INTEGER NOT NULL,service_id INTEGER,car_id INTEGER,slot TEXT NOT NULL,note TEXT DEFAULT '',status TEXT DEFAULT 'pending',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS conversations(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,company_id INTEGER NOT NULL,status TEXT DEFAULT 'open',updated_at TEXT NOT NULL,UNIQUE(user_id,company_id),FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,conversation_id INTEGER NOT NULL,sender_id INTEGER NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL,FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS promo_codes(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE NOT NULL,description TEXT DEFAULT '',discount TEXT DEFAULT '',expires_at TEXT DEFAULT '',max_uses INTEGER DEFAULT 0,used_count INTEGER DEFAULT 0,active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS promo_redemptions(id INTEGER PRIMARY KEY AUTOINCREMENT,promo_id INTEGER NOT NULL,user_id INTEGER NOT NULL,created_at TEXT NOT NULL,UNIQUE(promo_id,user_id),FOREIGN KEY(promo_id) REFERENCES promo_codes(id) ON DELETE CASCADE,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS partner_plans(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,description TEXT DEFAULT '',price TEXT DEFAULT '',period TEXT DEFAULT 'month',active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS company_subscriptions(id INTEGER PRIMARY KEY AUTOINCREMENT,company_id INTEGER NOT NULL,plan_id INTEGER NOT NULL,status TEXT DEFAULT 'trial',starts_at TEXT NOT NULL,ends_at TEXT DEFAULT '',created_at TEXT NOT NULL,FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE,FOREIGN KEY(plan_id) REFERENCES partner_plans(id));

    '''
