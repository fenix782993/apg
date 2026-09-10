# APG V8 — Авто Партнёрская Группа

Полноценная responsive/PWA-версия APG с Owner, Seller и Customer.

## V8
- камера QR через BarcodeDetector + ручной токен
- история QR
- уведомления
- установка PWA
- маршрут компании через Google Maps
- share
- профили и визуальные настройки
- галерея, услуги, отзывы, гараж, история, избранное
- модерация скидок и роли

## Windows
```cmd
py -3.12 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Открой http://127.0.0.1:8000

## Demo
Owner: owner@apg.local / apg1234
Seller: seller@apg.local / seller1234
Customer: user@apg.local / user1234

Для камеры QR в production нужен HTTPS и разрешение браузера на камеру.
