# APG V10 deployment checklist

1. Set `APG_SECRET_KEY` and `APG_PASSWORD_SALT` to unique random values.
2. Use PostgreSQL in production.
3. Set `APG_COOKIE_SECURE=1` behind HTTPS.
4. Configure S3-compatible storage for persistent uploads on ephemeral hosts.
5. Change/remove demo credentials before public launch.
6. Restrict `/api/docs` in production if public API documentation is not desired.
7. Configure domain + HTTPS.
8. Add monitoring for `/api/health`.
