# APG FULL BLACK — V2

Большая тёмная версия APG: Customer / Seller / Owner, каталог, галерея, услуги, отзывы, QR, избранное, гараж без марки автомобиля, продавцы, модерация и управление контентом.

## Главное правило контента
- В каталоге нет старых демонстрационных скидок.
- Информация о предложении задаётся продавцом, а публикация проходит через Owner.
- Галерею, услуги и опубликованные отзывы контролирует Owner.
- Марка автомобиля удалена из формы и модели автомобиля.

## Демо
- owner@apg.local / apg1234
- seller@apg.local / seller1234
- user@apg.local / user1234

## Windows
```cmd
cd C:\Users\Admin\Downloads\APG_FULL_BLACK
py -3.12 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000

## Render
Build: `pip install -r requirements.txt`
Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

SQLite is intended for testing. Production should use PostgreSQL and persistent file storage.
