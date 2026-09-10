# APG FULL

Полноценная расширенная версия APG — Авто Партнёрская Группа на FastAPI без Node/npm.

## Что внутри
- Клиент / Продавец / Владелец
- регистрация и вход
- продавцы добавляются владельцем
- продавец создаёт только свои предложения
- фото предложения JPG/PNG/WEBP до 8 МБ
- модерация pending → active/rejected/disabled
- каталог показывает только активные предложения
- QR-токен на 5 минут, одноразовое погашение
- продавец может погасить только QR своего предложения
- владелец может управлять всеми предложениями
- статистика
- автомобили клиента
- история обслуживания
- уведомления в БД
- адаптивный PC/mobile UI
- SQLite для локального запуска
- Render config

## Windows
```cmd
cd C:\Users\Admin\Downloads\APG_FULL
py -3.12 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Открыть http://127.0.0.1:8000

## Demo
owner@apg.local / apg1234
seller@apg.local / seller1234
user@apg.local / user1234

## Render
Build: `pip install -r requirements.txt`
Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Для production заменить SQLite на PostgreSQL и локальные uploads на persistent object storage.
