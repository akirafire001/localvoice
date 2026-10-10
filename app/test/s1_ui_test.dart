import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:localvoice/api/api_client.dart';
import 'package:localvoice/auth/auth_service.dart';
import 'package:localvoice/audio/audio_controller.dart';
import 'package:localvoice/guide/guide_session.dart';
import 'package:localvoice/guide/notifier.dart';
import 'package:localvoice/screens/auth_screens.dart';
import 'package:localvoice/screens/home_screen.dart';
import 'package:localvoice/screens/history_screen.dart';
import 'package:localvoice/screens/preferences_screen.dart';
import 'package:localvoice/screens/account_screen.dart';
import 'package:localvoice/screens/guide_screen.dart';
import 'package:localvoice/util/i18n.dart';
import 'package:localvoice/ui_theme.dart';
import 'package:localvoice/widgets/common.dart';
import 'package:localvoice/widgets/visuals.dart';
import 'package:localvoice/widgets/home_banner.dart';
import 'package:localvoice/main.dart';

final storeCapture = Platform.environment['LOCALVOICE_CAPTURE_STORE_UI'] == '1';
final capture = Platform.environment['LOCALVOICE_CAPTURE_UI'] == '1' || storeCapture;
final captureSize = storeCapture ? const Size(432, 768) : const Size(390, 844);
bool previewFont = false;

class _Tokens implements TokenStore {
  @override
  Future<String?> readRefresh() async => null;
  @override
  Future<void> writeRefresh(String? token) async {}
}

class _Fixture {
  _Fixture() {
    api = ApiClient(
      httpClient: MockClient((request) async {
        if (request.method == 'PATCH' && request.url.path.endsWith('/interests')) {
          final payload = jsonDecode(request.body) as Map;
          savedInterests.add(payload);
          for (final changed in payload['interests'] as List) {
            interests.firstWhere((i) => i['category'] == changed['category'])['explicit_score'] =
                changed['explicit_score'];
          }
          return response({'interests': interests});
        }
        return response(switch (request.url.path) {
          '/api/v1/users/me/preferences' => {
            'language': lang.code,
            'home_country': 'jp',
            'notification_level': 'normal',
            'detail_mode': 'auto',
            'serendipity': 'normal',
            'narration_languages': ['en', 'ja'],
            'voice': {'enabled': false, 'allow_device_tts_fallback': false, 'playback_rate': 1.0, 'voices': {}},
          },
          '/api/v1/users/me/interests' => {'interests': interests},
          '/api/v1/voices' => {'voices': [], 'tts_available': false},
          '/api/v1/languages' => {
            'ui': [
              {'code': 'ja', 'name': '日本語', 'name_ja': '日本語', 'name_en': 'Japanese'},
              {'code': 'en', 'name': 'English', 'name_ja': '英語', 'name_en': 'English'},
            ],
            'narration': [
              {'code': 'ja', 'name': '日本語', 'name_ja': '日本語', 'name_en': 'Japanese'},
              {'code': 'en', 'name': 'English', 'name_ja': '英語', 'name_en': 'English'},
              {'code': 'ko', 'name': '한국어', 'name_ja': '韓国語', 'name_en': 'Korean'},
            ],
            'max_narration_languages': 4,
          },
          '/api/v1/trips' => {'trips': []},
          _ => <String, dynamic>{},
        });
      }),
      tokenStore: _Tokens(),
      baseUrl: 'http://test.invalid',
    );
    auth = AuthService(api)..state = AuthState.signedIn;
    auth.user = UserInfo({
      'id': 'test-user',
      'display_name': storeCapture ? '旅行者' : 'Akira',
      'login_id': 'sample',
      'login_methods': ['password'],
      'recovery_email': 'sample@example.invalid',
      'recovery_email_verified': true,
    });
    audio = AudioController(api);
    session = GuideSession(api, audio, GuideNotifier());
  }
  late final ApiClient api;
  late final AuthService auth;
  late final AudioController audio;
  late final GuideSession session;
  final List<Map> savedInterests = [];
  final List<Map<String, dynamic>> interests = [
    for (final category in categoryLabels.keys) {'category': category, 'explicit_score': 0.5},
  ];
  http.Response response(Object data) =>
      http.Response(jsonEncode(data), 200, headers: {'content-type': 'application/json'});
  Widget app(Widget screen, GlobalKey boundary, {double scale = 1}) {
    var theme = localVoiceTheme();
    if (previewFont) {
      theme = theme.copyWith(textTheme: theme.textTheme.apply(fontFamily: 'PreviewJP'));
    }
    return MultiProvider(
      providers: [
        Provider<ApiClient>.value(value: api),
        ChangeNotifierProvider<AuthService>.value(value: auth),
        ChangeNotifierProvider<AudioController>.value(value: audio),
        ChangeNotifierProvider<GuideSession>.value(value: session),
      ],
      child: RepaintBoundary(
        key: boundary,
        child: MaterialApp(
          theme: theme,
          debugShowCheckedModeBanner: false,
          home: screen,
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)),
            child: child!,
          ),
        ),
      ),
    );
  }
}

Future<void> settleImages(WidgetTester tester) async {
  await tester.pumpAndSettle();
  final context = tester.element(find.byType(Scaffold).first);
  final images = tester.widgetList<Image>(find.byType(Image)).map((i) => i.image).toList();
  await tester.runAsync(() => Future.wait(images.map((image) => precacheImage(image, context))));
  await tester.pumpAndSettle();
}

Future<void> saveScreen(GlobalKey boundary, String name, WidgetTester tester) async {
  if (!capture) return;
  if (storeCapture && !{'home', 'preferences'}.contains(name)) return;
  await tester.runAsync(() async {
    final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final image = await render.toImage(pixelRatio: storeCapture ? 2.5 : 2);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    final folder = Directory(storeCapture ? '../docs/play-store/screens' : '../docs/ui/asset-production/s1/screens')
      ..createSync(recursive: true);
    File('${folder.path}/$name.png').writeAsBytesSync(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    // Optional local preview font; the application bundles no proprietary font.
    if (capture && File('C:/Windows/Fonts/YuGothR.ttc').existsSync()) {
      final loader = FontLoader('PreviewJP')
        ..addFont(Future.value(ByteData.sublistView(File('C:/Windows/Fonts/YuGothR.ttc').readAsBytesSync())));
      await loader.load();
      final icons = FontLoader('MaterialIcons')..addFont(rootBundle.load('fonts/MaterialIcons-Regular.otf'));
      await icons.load();
      previewFont = true;
    }
  });
  setUp(() {
    lang.set('ja');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('flutter_tts'),
      (_) async => 1,
    );
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('com.ryanheise.audio_session'),
      (_) async => null,
    );
  });
  testWidgets('all S1 resources are bundled and decode in Flutter', (tester) async {
    await tester.runAsync(() async {
      for (final asset in [
        'assets/branding/app-icon.png',
        ...LvIconKind.values.map((i) => i.asset),
        ...LvArtwork.values.map((a) => a.asset),
        ...LvHomeBanner.values.map((b) => b.asset),
      ]) {
        final data = await rootBundle.load(asset);
        final codec = await ui.instantiateImageCodec(data.buffer.asUint8List());
        final frame = await codec.getNextFrame();
        expect(frame.image.width, greaterThan(0), reason: asset);
        if (asset.startsWith('assets/s1/home_banners/')) {
          expect(frame.image.width, 1774, reason: asset);
          expect(frame.image.height, 887, reason: asset);
        }
        frame.image.dispose();
        codec.dispose();
      }
    });
  });
  testWidgets(
    'launch banner remains stable through language rebuilds and navigation',
    (tester) async {
      final fixture = _Fixture();
      addTearDown(fixture.audio.dispose);
      addTearDown(() => lang.set('ja'));
      await tester.pumpWidget(
        LocalVoiceApp(
          api: fixture.api,
          auth: fixture.auth,
          audio: fixture.audio,
          session: fixture.session,
        ),
      );
      await settleImages(tester);
      final selected = tester
          .widget<LvHomeBannerImage>(find.byType(LvHomeBannerImage))
          .banner;
      for (var i = 0; i < 12; i++) {
        lang.set(i.isEven ? 'en' : 'ja');
        await tester.pumpAndSettle();
        expect(
          tester
              .widget<LvHomeBannerImage>(find.byType(LvHomeBannerImage))
              .banner,
          selected,
        );
      }
      await tester.tap(find.byTooltip('設定'));
      await settleImages(tester);
      await tester.pageBack();
      await settleImages(tester);
      expect(
        tester.widget<LvHomeBannerImage>(find.byType(LvHomeBannerImage)).banner,
        selected,
      );
      expect(tester.takeException(), isNull);
    },
  );

  final scenes = <String, Widget Function(_Fixture)>{
    'login': (_) => const LoginScreen(),
    'home': (_) => const HomeScreen(),
    'history-empty': (_) => const TripListScreen(),
    'preferences': (_) => const PreferencesScreen(),
    'account-verified': (_) => const AccountScreen(),
    'email-pending': (_) => const EmailVerifyScreen(),
    'password-reset': (_) => const PasswordResetScreen(),
    'guide-story': (f) => Scaffold(
      appBar: LvAppBar(title: Text(tr('ガイド中', 'Guiding'))),
      body: GuideStoryCard(
        session: f.session,
        audio: f.audio,
        guide: {
          'history_id': 'sample-guide',
          'category': 'culture',
          'origin': 'generated',
          'title': tr('地名に残る、土地の記憶', 'The stories kept in a place name'),
          'text': tr(
            '地名には、昔の暮らしや地形の手がかりが残っています。名前の由来から、この地域の話をたどってみましょう。',
            'Place names hold clues to the landscape and the lives of people who came before. Let us explore the stories behind this local name.',
          ),
          'sources': [
            {'title': tr('地域の資料（表示例）', 'Local source (example)')},
          ],
          'confidence': {'level': 'medium', 'fact_type': 'verified_fact'},
        },
      ),
    ),
  };
  for (final scene in scenes.entries) {
    testWidgets('${scene.key} renders at regular and narrow enlarged English sizes', (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = captureSize;
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      final fixture = _Fixture();
      addTearDown(fixture.audio.dispose);
      final boundary = GlobalKey();
      await tester.pumpWidget(fixture.app(scene.value(fixture), boundary));
      await settleImages(tester);
      expect(tester.takeException(), isNull);
      await saveScreen(boundary, scene.key, tester);
      lang.set('en');
      tester.view.physicalSize = const Size(320, 720);
      await tester.pumpWidget(fixture.app(scene.value(fixture), boundary, scale: 1.6));
      await settleImages(tester);
      expect(tester.takeException(), isNull);
    });
  }
  testWidgets('password eye still toggles obscuring with accessible labels', (tester) async {
    final fixture = _Fixture();
    addTearDown(fixture.audio.dispose);
    await tester.pumpWidget(fixture.app(const LoginScreen(), GlobalKey()));
    await settleImages(tester);
    expect(tester.widgetList<TextField>(find.byType(TextField)).where((f) => f.obscureText).length, 1);
    await tester.ensureVisible(find.byTooltip('パスワードを表示'));
    await tester.tap(find.byTooltip('パスワードを表示'));
    await tester.pump();
    expect(tester.widgetList<TextField>(find.byType(TextField)).where((f) => f.obscureText), isEmpty);
    expect(find.byTooltip('パスワードを隠す'), findsOneWidget);
  });
  testWidgets('nine weights remain adjustable and save the existing API payload', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = captureSize;
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    final fixture = _Fixture();
    addTearDown(fixture.audio.dispose);
    final boundary = GlobalKey();
    await tester.pumpWidget(fixture.app(const PreferencesScreen(), boundary));
    await settleImages(tester);
    // the outer list (the narration languages are a nested reorderable list)
    final page = find.byType(Scrollable).first;
    await tester.scrollUntilVisible(find.text('興味'), 200, scrollable: page);
    await tester.ensureVisible(find.text('歴史'));
    await settleImages(tester);
    await saveScreen(boundary, 'preferences-interests', tester);
    await tester.drag(find.byType(Slider).first, const Offset(35, 0));
    await tester.pumpAndSettle();
    expect(fixture.savedInterests, isNotEmpty);
    expect((fixture.savedInterests.last['interests'] as List).single['category'], 'history');
    expect((fixture.savedInterests.last['interests'] as List).single['explicit_score'], isNot(0.5));
    for (final label in categoryLabels.values) {
      await tester.scrollUntilVisible(find.text(label[0]), 120, scrollable: page);
      expect(find.text(label[0]), findsOneWidget);
    }
    expect(tester.takeException(), isNull);
  });
  testWidgets('empty states fit a short pane with enlarged text', (tester) async {
    for (final artwork in [LvArtwork.waitingForStory, LvArtwork.offlineLocalSave, LvArtwork.locationPermission]) {
      await tester.pumpWidget(
        MaterialApp(
          theme: localVoiceTheme(),
          home: Scaffold(
            body: Center(
              child: SizedBox(
                width: 280,
                height: 150,
                child: MediaQuery(
                  data: const MediaQueryData(textScaler: TextScaler.linear(2)),
                  child: LvEmptyState(
                    artwork: artwork,
                    message: 'Your movement is saved on this device until the connection returns.',
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await settleImages(tester);
      expect(tester.takeException(), isNull);
    }
  });
}
