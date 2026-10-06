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
| `GOOGLE_SERVER_CLIENT_ID` | empty | Google OAuth client ID put into the ID token audience (must be in the server's `GOOGLE_CLIENT_IDS`) |
| `MAP_STYLE_URL` | OpenFreeMap liberty | MapLibre style |

External setup still needed per platform: Google Sign-In (Android SHA-1 / iOS URL scheme and `GIDClientID`), Sign in with Apple capability (iOS) and a Services ID + return URL (Android, see server `APPLE_*`).

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
