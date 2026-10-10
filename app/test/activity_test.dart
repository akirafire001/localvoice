import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:localvoice/api/api_client.dart';
import 'package:localvoice/audio/audio_controller.dart';
import 'package:localvoice/guide/guide_session.dart';
import 'package:localvoice/guide/notifier.dart';
import 'package:localvoice/screens/guide_screen.dart';
import 'package:localvoice/util/i18n.dart';

class _Store implements TokenStore {
  @override
  Future<String?> readRefresh() async => null;
  @override
  Future<void> writeRefresh(String? token) async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late GuideSession s;
  late AudioController audio;
  final now = DateTime(2026, 10, 10, 12);

  setUp(() {
    lang.set('ja');
    final api = ApiClient(httpClient: MockClient((_) async => http.Response('{}', 200)), tokenStore: _Store(), baseUrl: 'http://x');
    audio = AudioController(api);
    s = GuideSession(api, audio, GuideNotifier())
      ..trip = {'trip_id': 't1', 'ended_at': null}
      ..gps = GpsState.on;
  });

  test('cooldown shows the time left and the pace in seconds', () {
    s.decision = {'reason': 'selected', 'cooldown_sec': 360, 'notification_level': 'normal'};
    s.nextCheckAt = now.add(const Duration(seconds: 135));
    final a = activityOf(s, audio, now)!;
    expect(a.text, contains('あと 2:15'));
    expect(a.text, contains('360秒おき'));
  });

  test('no stories here says whether new ones are being looked for', () {
    s.nextCheckAt = now.add(const Duration(seconds: 30));
    s.decision = {'reason': 'no_candidates', 'searching': true};
    final searching = activityOf(s, audio, now)!;
    expect(searching.text, contains('新しい話を探しています'));
    expect(searching.busy, isTrue);
    s.decision = {'reason': 'no_candidates', 'searching': false};
    expect(activityOf(s, audio, now)!.text, contains('もうありません'));
  });

  test('when the wait is over it says it is checking, never a silent stop', () {
    s.decision = {'reason': 'cooldown'};
    s.nextCheckAt = now.subtract(const Duration(seconds: 1));
    expect(activityOf(s, audio, now)!.text, contains('まもなく'));
    s.decision = null;
    expect(activityOf(s, audio, now)!.busy, isTrue);
  });

  test('continuous mode follows the server and explains itself', () {
    s.applyPrefs({'notification_level': 'continuous'});
    expect(s.continuous, isTrue);
    s.continuing = true;
    expect(activityOf(s, audio, now)!.text, contains('続けて次の話'));
  });
}
