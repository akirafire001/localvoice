# LocalVoice app (Flutter)

Android / iOS client for the [LocalVoice API](../server/README.md). Screens follow [Flutter UX設計](../docs/flutter-ux-design-v0.1.md).

## Run

```bash
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000 \
            --dart-define=GOOGLE_SERVER_CLIENT_ID=<web client id accepted by the server>
```

| dart-define | Default | Purpose |
|---|---|---|
| `API_BASE_URL` | `http://10.0.2.2:8000` | Server URL (Android emulator → host). Release builds need HTTPS; cleartext is allowed only in the debug manifest. |
| `GOOGLE_SERVER_CLIENT_ID` | project web client ID | Google OAuth client ID put into the ID token audience (must be in the server's `GOOGLE_CLIENT_IDS`) |
| `MAP_STYLE_URL` | OpenFreeMap liberty | MapLibre style |

The Android application ID is `tech.ideaworks.localvoice`, registered in Google Play Console. The Kotlin namespace remains `com.localvoice.localvoice`.

Debug builds use the shared development key `android/app/dev.keystore` (password `android`), with SHA-1 `49:F2:85:40:66:8F:2D:3C:F3:04:1C:9E:33:18:4D:32:A4:C0:72:52`.
Release builds use an upload key configured through the ignored `android/key.properties` file (`storeFile`, `storePassword`, `keyAlias`, `keyPassword`). Keep that file and the keystore private and backed up. Release builds do not fall back to the development key.

```powershell
C:\work\tools\flutter-localvoice\bin\flutter.bat build appbundle --release --dart-define=API_BASE_URL=https://localvoice.ideaworks.tech
```

The Play upload artifact is `build/app/outputs/bundle/release/app-release.aab`. Increase the build number for subsequent uploads.
The Google Play Android OAuth client was created and verified on 2026-10-10: `LocalVoice Android - Google Play`, client ID `380406027309-nsc2asbt61ntqas6gtobnakdvq55t547.apps.googleusercontent.com`, package `tech.ideaworks.localvoice`, and Play app signing SHA-1 `75:58:F6:C9:A1:43:93:44:24:F1:83:DF:AB:72:61:7A:8C:32:82:0E`. The existing web/server client ID remains unchanged, so this registration does not require rebuilding the AAB. Google login on a Play-installed device still needs an end-to-end check after configuration propagates.
The previous Android OAuth client covers only `com.localvoice.localvoice` with the development certificate. Directly installed debug/release builds of the new package require separate Android OAuth registrations for their respective local signing certificates.

Google Sign-In is configured for Google Cloud project `localvoice-510815` (web, Android and iOS clients; iOS `GIDClientID` and URL scheme are in `ios/Runner/Info.plist`). The OAuth app is in Testing mode. Basic Sign in with Google authentication using only name, email and profile is exempt from the OAuth test-user-list requirement; requesting additional scopes would change that ([Google's audience documentation](https://support.google.com/cloud/answer/15549945)). External setup still needed: Sign in with Apple capability (iOS) and a Services ID + return URL (Android, see server `APPLE_*`).

## iPhone / TestFlight

The iOS bundle identifier is `tech.ideaworks.localvoice`, matching the existing Google iOS OAuth client. The app targets iPhone and iOS 15 or later. The repository-root `codemagic.yaml` builds and uploads the signed app using the existing Codemagic Apple integration. See [iOS / TestFlight setup and device checks](../docs/ios-testflight.md) for signing, Apple login configuration, and tester distribution.

## S1 visual assets

The home banner uses 22 offline pencil-and-wash WebP images under `assets/s1/home_banners/`: the two selected existing sketches and 20 landmarks from different countries. Original PNGs are preserved with the artwork documentation. One banner is chosen once per app launch and kept through navigation and language changes. See the [gallery, prompts, and behavior](../docs/ui/asset-production/home-banners/README.md).

The selected travel-journal style uses shared transparent PNG icons and illustrations under `assets/s1/`. The generated source sheets, prompts, export script instructions, and rendered screen previews are recorded in [S1 visuals](../docs/ui/asset-production/s1/README.md). Run `python tools/export_s1_assets.py` from the repository root with Pillow and NumPy to reproduce the individual PNGs. The runtime uses `lib/widgets/visuals.dart` and `lib/ui_theme.dart`; no Python packages are needed by the app.

## Structure

- `lib/api/` — HTTP client (access token in memory, refresh token in secure storage, single-flight refresh)
- `lib/auth/` — ID/password, Google, Apple (iOS native, Android via server callback + handoff code), reauth, linking, delete
- `lib/location/` — motion estimate (speed/course/class with confidence) and track segmentation
- `lib/guide/` — running trip: GPS → per-user local SQLite → `/context` (thinned, resend when back online) → notification/audio
- `lib/audio/` — server speech with polling, stale-audio guard, device TTS fallback only if the user allowed it
- `lib/screens/` — login/register/reset, home, guide (mini map + story card + one-tap ratings), map, history, preferences, account
- `lib/widgets/track_map.dart` — MapLibre track/current position/guide spots

## Tests

```bash
flutter analyze
flutter test
```
