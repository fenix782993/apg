# APG V11 — Авто Партнёрская Группа

Production-oriented APG platform: Owner / Seller / Customer, PostgreSQL, S3-compatible media, moderation, one-time QR, notifications, PWA and mobile shell preparation.

## Local Windows
```cmd
py -3.12 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open `http://127.0.0.1:8000`.

## Demo accounts
- Owner: `owner@apg.local` / `apg1234`
- Seller: `seller@apg.local` / `seller1234`
- Customer: `user@apg.local` / `user1234`

## Production
Set `DATABASE_URL`, `APG_SECRET_KEY`, `APG_COOKIE_SECURE=1`. For persistent images configure S3 variables. Deploy the web service with Render and PostgreSQL.

## Mobile
The `mobile/` folder contains Capacitor configuration for Android/iOS. See `docs/MOBILE_RELEASE.md`.

## V14
Добавлены записи на услуги, чат клиент↔компания, промокоды, тарифы партнёров и коммерческий слой APG.
