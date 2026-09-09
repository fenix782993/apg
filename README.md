# APG FULL V2

Полноценный адаптивный APG Web/App прототип:
- PC Web с боковой навигацией;
- Mobile с нижней навигацией;
- APG PASS;
- скидки;
- партнёры и поиск;
- автомобиль;
- история;
- профиль;
- SQLite;
- API;
- настоящая генерация QR;
- одноразовый QR с 5-минутным сроком;
- endpoint для погашения QR партнёром;
- PWA manifest;
- Render Blueprint.

## Render
Build: `pip install -r requirements.txt`
Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

## Local
`python -m venv .venv`
`.venv\Scripts\activate`
`pip install -r requirements.txt`
`uvicorn app.main:app --reload`

Открыть http://127.0.0.1:8000

## Production
Для реального запуска заменить demo-данные на PostgreSQL, добавить полноценную авторизацию, роли customer/partner/admin, сканирование камерой, HTTPS, rate limiting, резервные копии и управление партнёрами из админки.
