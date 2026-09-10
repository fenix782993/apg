import os, re, secrets
from fastapi import HTTPException, Request

EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
USERNAME_RE = re.compile(r'^[A-Za-z0-9_]{3,32}$')


def validate_email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL_RE.fullmatch(value):
        raise HTTPException(400, 'Некорректный email')
    return value


def validate_username(value: str) -> str:
    value = value.strip().lower()
    if not USERNAME_RE.fullmatch(value):
        raise HTTPException(400, 'Username: 3–32 символа, только a-z, 0-9 и _')
    return value


def csrf_token(request: Request) -> str:
    token = request.session.get('csrf')
    if not token:
        token = secrets.token_urlsafe(32)
        request.session['csrf'] = token
    return token


def check_csrf(request: Request, token: str = ''):
    expected = request.session.get('csrf')
    if not expected or not token or not secrets.compare_digest(expected, token):
        raise HTTPException(403, 'CSRF token недействителен')
