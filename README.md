# APG App V1

Мобильная web-app / PWA-ready версия APG — Авто Партнёрская Группа.

## Что уже работает
- адаптивный интерфейс под телефон и ПК;
- APG PASS;
- каталог скидок;
- партнёры;
- «Мой автомобиль»;
- профиль;
- генерация реального PNG QR через backend;
- API `/api/discounts`;
- API `/api/qr`;
- healthcheck `/api/health`;
- Render конфигурация.

## Локальный запуск

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Открыть: http://127.0.0.1:8000

## Render

Подключить репозиторий GitHub и выбрать Blueprint / `render.yaml`.
Или вручную:

Build:
`pip install -r requirements.txt`

Start:
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`

## Следующая версия
Для production нужно добавить PostgreSQL, настоящую авторизацию, одноразовые QR-токены, кабинет партнёра со сканером и админ-панель.
