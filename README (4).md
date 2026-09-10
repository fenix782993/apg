# Run from mobile/ after npm install + npx cap add android
$ErrorActionPreference='Stop'
npx cap sync android
Push-Location android
./gradlew.bat bundleRelease
Pop-Location
Write-Host 'AAB: mobile/android/app/build/outputs/bundle/release/app-release.aab'
