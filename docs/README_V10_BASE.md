# APG V10 — Авто Партнёрская Группа

Production-oriented APG build with PostgreSQL/SQLite, S3-compatible uploads, role separation, QR offers, PWA, security middleware and Docker.

## Roles
- Owner — full management and moderation.
- Seller — only assigned companies/offers.
- Customer — companies, offers, QR, garage, favourites, reviews.

## Local Windows
```cmd
py -3.12 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open `http://127.0.0.1:8000`.

## Docker + PostgreSQL
```cmd
docker compose up --build
```

## Render
Use the included `render.yaml`. PostgreSQL is provisioned as the database service. Set S3 variables if cloud image storage is required.

## Demo accounts
Owner: `owner@apg.local` / `apg1234`
Seller: `seller@apg.local` / `seller1234`
Customer: `user@apg.local` / `user1234`

## Production variables
`DATABASE_URL`, `APG_SECRET_KEY`, `APG_PASSWORD_SALT`, `APG_COOKIE_SECURE=1`, and optional `S3_BUCKET`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `S3_PUBLIC_BASE`.

## API docs
`/api/docs` and `/api/redoc` are enabled for integration/testing.
