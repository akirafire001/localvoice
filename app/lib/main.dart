import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'api/api_client.dart';
import 'audio/audio_controller.dart';
import 'auth/auth_service.dart';
import 'guide/guide_session.dart';
import 'guide/notifier.dart';
import 'screens/auth_screens.dart';
import 'screens/home_screen.dart';
import 'util/i18n.dart';
import 'ui_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  lang.set(uiLanguageForDevice());
  final api = ApiClient();
  final auth = AuthService(api);
  final audio = AudioController(api);
  final session = GuideSession(api, audio, GuideNotifier());
  // Sign-out / account switch: stop GPS and audio and close the previous user's local data first.
  auth.beforeSignOut.add(session.detach);
  runApp(LocalVoiceApp(api: api, auth: auth, audio: audio, session: session));
  auth.restore();
}

class LocalVoiceApp extends StatefulWidget {
  const LocalVoiceApp({super.key, required this.api, required this.auth, required this.audio, required this.session});
  final ApiClient api;
  final AuthService auth;
  final AudioController audio;
  final GuideSession session;

  @override
  State<LocalVoiceApp> createState() => _LocalVoiceAppState();
}

class _LocalVoiceAppState extends State<LocalVoiceApp> with WidgetsBindingObserver {
  String? _attachedUser;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    widget.auth.addListener(_onAuth);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    widget.auth.removeListener(_onAuth);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    widget.session.appInForeground = state == AppLifecycleState.resumed;
  }

  Future<void> _onAuth() async {
    final a = widget.auth;
    final uid = a.state == AuthState.signedIn ? a.user?.id : null;
    if (uid == _attachedUser) return;
    _attachedUser = uid;
    if (uid == null) {
      lang.set(uiLanguageForDevice());
      await widget.session.detach();
      return;
    }
    await widget.session.attachUser(uid);
    try {
      final prefs = (await widget.api.get('/api/v1/users/me/preferences')).json;
      widget.audio.applyPrefs(prefs);
      widget.session.applyPrefs(prefs);
      lang.set(prefs['language'] as String? ?? uiLanguageForDevice());
    } catch (_) {}
    if (widget.session.active) await widget.session.startGps();
  }

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        Provider<ApiClient>.value(value: widget.api),
        ChangeNotifierProvider<AuthService>.value(value: widget.auth),
        ChangeNotifierProvider<AudioController>.value(value: widget.audio),
        ChangeNotifierProvider<GuideSession>.value(value: widget.session),
        ChangeNotifierProvider<Lang>.value(value: lang),
      ],
      child: Consumer2<AuthService, Lang>(
        builder: (context, auth, _, _) => MaterialApp(
          title: 'LocalVoice',
          debugShowCheckedModeBanner: false,
          theme: localVoiceTheme(),
          home: switch (auth.state) {
            AuthState.unknown => const Scaffold(body: Center(child: CircularProgressIndicator())),
            AuthState.signedOut => const LoginScreen(),
            AuthState.signedIn => const HomeScreen(),
          },
        ),
      ),
    );
  }
}
