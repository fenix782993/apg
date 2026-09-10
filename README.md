# APG V7 — Авто Партнёрская Группа

Полноценная responsive/PWA-версия APG: Owner, Seller и Customer, компании, галерея, услуги, отзывы, скидки с модерацией, одноразовые QR, гараж, история, избранное, поиск/фильтры, профили, настройки визуала, уведомления и аудит.

## Локальный запуск Windows
```cmd
py -3.12 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Открыть `http://127.0.0.1:8000`.

## Тестовые аккаунты
- Owner: `owner@apg.local` / `apg1234`
- Seller: `seller@apg.local` / `seller1234`
- Customer: `user@apg.local` / `user1234`

## Render
Build: `pip install -r requirements.txt`
Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

> Для production рекомендуется PostgreSQL + S3/Cloudinary вместо локального SQLite/uploads.
