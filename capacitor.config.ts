# APG V11 mobile release

APG V11 keeps the web application as the shared UI/API and adds a Capacitor shell target.

## Android
1. Install Node.js LTS and Android Studio.
2. `cd mobile && npm install`.
3. `npx cap add android && npx cap sync android`.
4. Open Android Studio and create a signed AAB.
5. Add camera, location and notification permissions and test on a real phone.

## iOS
Requires macOS + Xcode.
1. `cd mobile && npm install`.
2. `npx cap add ios && npx cap sync ios`.
3. Open Xcode, set signing team/bundle ID, add usage descriptions and archive.

## Production requirements
- API must use HTTPS.
- `APG_SECRET_KEY` must be a strong random secret.
- PostgreSQL should be used on Render.
- Use S3-compatible storage for persistent images.
- Configure APNs/FCM credentials for push notifications before enabling them in production.
