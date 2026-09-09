from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from io import BytesIO
import secrets
import qrcode

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"

app = FastAPI(title="APG — Авто Партнёрская Группа")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

discounts = [
    {"id": 1, "title": "ТО и диагностика", "partner": "APG Auto Service", "discount": 15, "category": "Сервис", "distance": "1.2 км"},
    {"id": 2, "title": "Шиномонтаж", "partner": "APG Tire", "discount": 20, "category": "Шины", "distance": "2.4 км"},
    {"id": 3, "title": "Запчасти", "partner": "APG Parts", "discount": 10, "category": "Запчасти", "distance": "3.1 км"},
    {"id": 4, "title": "Автомойка", "partner": "APG Wash", "discount": 25, "category": "Мойка", "distance": "0.8 км"},
]

class QRRequest(BaseModel):
    discount: int = 10
    user_id: str = "APG-184729"

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "APG"}

@app.get("/api/discounts")
def get_discounts():
    return discounts

@app.post("/api/qr")
def make_qr(data: QRRequest):
    token = secrets.token_urlsafe(18)
    payload = f"APG|{data.user_id}|{data.discount}|{token}"
    img = qrcode.make(payload)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png", headers={
        "X-APG-Token": token,
        "X-APG-User": data.user_id,
        "X-APG-Discount": str(data.discount),
    })
