# Service layer

Production business logic should be split into domain services here as the API grows:
- auth.py
- offers.py
- companies.py
- qr.py
- reviews.py
- notifications.py
- uploads.py
- analytics.py

The current V12 release keeps backward-compatible route handlers from V11 while this layer is introduced for the next refactor.
