# APG FULL REAL

Полноценный расширенный MVP APG в чёрной теме.

## Основное
- Customer / Seller / Owner
- чёрный UI + жирная белая типографика
- каталог партнёров
- отдельная страница партнёра
- вкладки: Скидки / Галерея / Услуги / Отзывы
- галерею и услуги добавляет Owner
- отзывы проходят модерацию Owner
- предложения Seller отправляются на модерацию
- QR одноразовый, 5 минут
- автомобили без поля «марка»
- избранное, история, статистика
- загрузка JPG/PNG/WEBP
- регистрация
- Render-ready

## Windows
py -3.12 -m venv venv
venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload

Открыть http://127.0.0.1:8000

Demo:
owner@apg.local / apg1234
seller@apg.local / seller1234
user@apg.local / user1234
