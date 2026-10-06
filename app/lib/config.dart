/// Build-time settings. Pass with --dart-define, e.g.
/// flutter run --dart-define=API_BASE_URL=https://api.example.com
class AppConfig {
  static const apiBaseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: 'http://10.0.2.2:8000');

  /// Google OAuth "web/server" client ID whose audience the server accepts.
  static const googleServerClientId = String.fromEnvironment('GOOGLE_SERVER_CLIENT_ID');

  /// OpenFreeMap style (map-provider-comparison: MapLibre + OpenFreeMap recommended)
  static const mapStyleUrl = String.fromEnvironment(
    'MAP_STYLE_URL',
    defaultValue: 'https://tiles.openfreemap.org/styles/liberty',
  );
  static const mapAttribution = 'OpenFreeMap © OpenMapTiles Data from OpenStreetMap';

  /// Track display rules (flutter-ux §4.1, PoC values)
  static const trackGapSplit = Duration(minutes: 5);
  static const trackMaxPlausibleSpeedMps = 90.0; // faster jumps are treated as GPS outliers

  /// Context sending (mvp-technical-design §3: never send raw GPS every second)
  static const sendMinDistanceM = 30.0;
  static const sendMaxInterval = Duration(seconds: 60);

  /// Audio generation wait limit before falling back (voice-design §7)
  static const speechWaitLimit = Duration(seconds: 5);
}
