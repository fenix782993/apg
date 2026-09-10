# APG Store Release Playbook

## Android
1. Install Node.js LTS and Android Studio.
2. `cd mobile && npm install`.
3. `npx cap add android` (first run only).
4. Set the production API URL in `capacitor.config.ts` or use a hosted web build.
5. `npx cap sync android`.
6. Open Android Studio and create a signed **Android App Bundle (.aab)**.
7. Upload the AAB to Google Play Console.

## iOS
1. macOS + Xcode is required for an iOS build/signing.
2. `cd mobile && npm install`.
3. `npx cap add ios` (first run only).
4. `npx cap sync ios`.
5. Open Xcode, configure Team + Bundle Identifier `de.apg.partner`.
6. Archive and distribute through App Store Connect.

## Production checklist
- Set a strong `APG_SECRET_KEY`.
- Set `APG_COOKIE_SECURE=1` behind HTTPS.
- Use PostgreSQL (`DATABASE_URL`).
- Configure S3-compatible storage for persistent uploads.
- Configure real push provider credentials/server endpoint.
- Configure a real domain and privacy policy.
- Test camera/geolocation permissions on physical devices.
- Test account deletion and data export requirements before store submission.
