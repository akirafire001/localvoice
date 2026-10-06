import 'package:flutter_local_notifications/flutter_local_notifications.dart';

/// Local notification for a new guide (title + first lines). Tapping opens the app.
class GuideNotifier {
  final _plugin = FlutterLocalNotificationsPlugin();
  bool _ready = false;

  Future<void> init() async {
    if (_ready) return;
    await _plugin.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        iOS: DarwinInitializationSettings(
          requestAlertPermission: false,
          requestBadgePermission: false,
          requestSoundPermission: false,
        ),
      ),
    );
    _ready = true;
  }

  Future<void> requestPermission() async {
    await init();
    await _plugin
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.requestNotificationsPermission();
    await _plugin.resolvePlatformSpecificImplementation<IOSFlutterLocalNotificationsPlugin>()?.requestPermissions(
      alert: true,
      sound: true,
    );
  }

  Future<void> showGuide(Map<String, dynamic> guide) async {
    await init();
    final text = (guide['text'] as String? ?? '');
    await _plugin.show(
      id: (guide['history_id'] as String).hashCode & 0x7fffffff,
      title: guide['title'] as String?,
      body: text.length > 120 ? '${text.substring(0, 120)}…' : text,
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails(
          'guides',
          'Guides',
          channelDescription: 'Nearby stories',
          importance: Importance.defaultImportance,
        ),
        iOS: DarwinNotificationDetails(),
      ),
      payload: guide['history_id'] as String?,
    );
  }

  Future<void> cancelAll() => _plugin.cancelAll();
}
