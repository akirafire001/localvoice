import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';
import 'package:uuid/uuid.dart';

import '../api/api_client.dart';
import '../audio/audio_controller.dart';
import '../config.dart';
import '../data/local_store.dart';
import '../location/motion_estimator.dart';
import '../util/geo.dart';
import 'notifier.dart';

/// Decides whether a new fix is worth sending (mvp-technical-design §3: thin before sending).
class SendThrottle {
  SendThrottle({this.minDistanceM = AppConfig.sendMinDistanceM, this.maxInterval = AppConfig.sendMaxInterval});
  final double minDistanceM;
  final Duration maxInterval;
  double? _lat, _lon;
  DateTime? _at;
  String? _mode;
  Duration? serverHint;

  bool shouldSend(DateTime t, double lat, double lon, String mode) {
    if (_at == null) return true;
    final elapsed = t.difference(_at!);
    if (serverHint != null && elapsed < serverHint! && mode == _mode) {
      // Respect next_check_after_sec unless we moved far or changed mode
      return haversineM(_lat!, _lon!, lat, lon) >= minDistanceM * 10;
    }
    if (mode != _mode) return true;
    if (elapsed >= maxInterval) return true;
    return haversineM(_lat!, _lon!, lat, lon) >= minDistanceM && elapsed >= const Duration(seconds: 10);
  }

  void sent(DateTime t, double lat, double lon, String mode) {
    _at = t;
    _lat = lat;
    _lon = lon;
    _mode = mode;
  }

  void reset() {
    _at = null;
    serverHint = null;
  }
}

enum GpsState { off, starting, on, denied, serviceOff }

/// The running trip: GPS → local store → /context → guide notification and audio.
class GuideSession extends ChangeNotifier {
  GuideSession(this.api, this.audio, this.notifier);
  final ApiClient api;
  final AudioController audio;
  final GuideNotifier notifier;
  final _uuid = const Uuid();
  final motion = MotionEstimator();
  final throttle = SendThrottle();

  LocalStore? store;
  Map<String, dynamic>? trip;
  final List<Map<String, dynamic>> guides = [];
  List<Map<String, dynamic>> overrides = [];
  List<Map<String, dynamic>> participants = [];
  Map<String, dynamic>? current;
  Position? lastPosition;
  Motion? lastMotion;
  GpsState gps = GpsState.off;
  String? lastDecision;
  bool offline = false;
  StreamSubscription<Position>? _sub;
  bool _sending = false;
  Timer? _retry;
  bool appInForeground = true;

  String? get tripId => trip?['trip_id'] as String?;
  bool get active => trip != null && trip!['ended_at'] == null;

  Future<void> attachUser(String userId) async {
    if (store?.userId == userId) return;
    await detach();
    store = await LocalStore.open(userId);
    final saved = await store!.get('active_trip_id');
    if (saved != null) {
      try {
        final t = (await api.get('/api/v1/trips/$saved')).json;
        if (t['ended_at'] == null) {
          trip = t;
          guides
            ..clear()
            ..addAll(await store!.guides(saved));
          current = guides.isEmpty ? null : guides.last;
          unawaited(refreshExtras());
        } else {
          await store!.set('active_trip_id', null);
        }
      } catch (_) {}
    }
    notifyListeners();
  }

  /// Sign-out / user change: stop GPS and audio, and drop every in-memory trace of the user.
  Future<void> detach() async {
    await stopGps();
    await audio.stop();
    await notifier.cancelAll();
    _retry?.cancel();
    trip = null;
    guides.clear();
    overrides = [];
    participants = [];
    current = null;
    lastPosition = null;
    motion.clear();
    throttle.reset();
    await store?.close();
    store = null;
    notifyListeners();
  }

  Future<void> startTrip(Map<String, dynamic> body) async {
    trip = (await api.post('/api/v1/trips', body)).json;
    guides.clear();
    overrides = [];
    participants = [];
    current = null;
    throttle.reset();
    motion.clear();
    await store!.set('active_trip_id', tripId);
    notifyListeners();
    await startGps();
  }

  Future<Map<String, dynamic>?> finishTrip() async {
    if (trip == null) return null;
    await stopGps();
    await audio.stop();
    await _flushUnsent();
    final r = (await api.post('/api/v1/trips/$tripId/finish')).json;
    trip = r;
    await store!.set('active_trip_id', null);
    notifyListeners();
    return r['summary'] as Map<String, dynamic>?;
  }

  Future<void> updateTrip(Map<String, dynamic> body) async {
    trip = (await api.patch('/api/v1/trips/$tripId', body)).json;
    throttle.reset();
    notifyListeners();
  }

  Future<GpsState> _checkPermission() async {
    if (!await Geolocator.isLocationServiceEnabled()) return GpsState.serviceOff;
    var p = await Geolocator.checkPermission();
    if (p == LocationPermission.denied) p = await Geolocator.requestPermission();
    if (p == LocationPermission.denied || p == LocationPermission.deniedForever) return GpsState.denied;
    return GpsState.on;
  }

  Future<void> startGps() async {
    if (_sub != null) return;
    gps = GpsState.starting;
    notifyListeners();
    final s = await _checkPermission();
    if (s != GpsState.on) {
      gps = s;
      notifyListeners();
      return;
    }
    final LocationSettings settings;
    if (defaultTargetPlatform == TargetPlatform.android) {
      settings = AndroidSettings(
        accuracy: LocationAccuracy.high,
        distanceFilter: 10,
        intervalDuration: const Duration(seconds: 5),
        foregroundNotificationConfig: const ForegroundNotificationConfig(
          notificationTitle: 'LocalVoice',
          notificationText: 'ガイド中（位置情報を使用しています）',
          enableWakeLock: false,
        ),
      );
    } else if (defaultTargetPlatform == TargetPlatform.iOS) {
      settings = AppleSettings(
        accuracy: LocationAccuracy.high,
        distanceFilter: 10,
        activityType: ActivityType.otherNavigation,
        pauseLocationUpdatesAutomatically: true,
        showBackgroundLocationIndicator: true,
        allowBackgroundLocationUpdates: true,
      );
    } else {
      settings = const LocationSettings(accuracy: LocationAccuracy.high, distanceFilter: 10);
    }
    _sub = Geolocator.getPositionStream(locationSettings: settings).listen(
      _onPosition,
      onError: (_) {
        gps = GpsState.off;
        notifyListeners();
      },
    );
    gps = GpsState.on;
    notifyListeners();
  }

  Future<void> stopGps() async {
    await _sub?.cancel();
    _sub = null;
    if (gps == GpsState.on || gps == GpsState.starting) gps = GpsState.off;
    notifyListeners();
  }

  Future<void> _onPosition(Position p) async {
    lastPosition = p;
    final t = p.timestamp.toUtc();
    motion.add(Fix(t, p.latitude, p.longitude, p.accuracy, speedMps: p.speed >= 0 ? p.speed : null));
    final m = motion.estimate();
    lastMotion = m;
    notifyListeners();
    if (!active || store == null) return;
    if (!throttle.shouldSend(t, p.latitude, p.longitude, m.mode)) return;
    throttle.sent(t, p.latitude, p.longitude, m.mode);
    final ctx = {
      'client_event_id': _uuid.v4(),
      'observed_at': t.toIso8601String(),
      'utc_offset_min': p.timestamp.toLocal().timeZoneOffset.inMinutes,
      'location': {'lat': p.latitude, 'lon': p.longitude, 'accuracy_m': p.accuracy},
      'motion': m.toJson(),
      'app_state': appInForeground ? 'foreground' : 'background',
    };
    await store!.addPoint(tripId!, ctx);
    await _send(ctx, live: true);
  }

  Future<void> _send(Map<String, dynamic> ctx, {required bool live}) async {
    final id = tripId;
    if (id == null) return;
    try {
      final r = (await api.post('/api/v1/trips/$id/context', ctx)).json;
      await store?.markSent(ctx['client_event_id'] as String);
      if (offline) {
        offline = false;
        unawaited(_flushUnsent());
      }
      final d = (r['decision'] ?? {}) as Map;
      lastDecision = d['reason'] as String?;
      final next = d['next_check_after_sec'];
      throttle.serverHint = next is num ? Duration(seconds: next.toInt()) : null;
      if (d['reason'] == 'trip_finished') {
        await stopGps();
      }
      final g = r['guide'];
      if (g is Map && live) await _onGuide(g.cast<String, dynamic>());
      notifyListeners();
    } on ApiException catch (e) {
      if (e.isNetwork || e.status >= 500) {
        offline = true;
        _retry ??= Timer(const Duration(seconds: 30), () {
          _retry = null;
          _flushUnsent();
        });
      } else if (e.status == 409 || e.status == 410 || e.status == 400) {
        await store?.markSent(ctx['client_event_id'] as String); // never resend a rejected point
      }
      notifyListeners();
    }
  }

  /// Resend points stored while offline (the server stores old ones for the track only).
  Future<void> _flushUnsent() async {
    if (_sending || store == null || tripId == null) return;
    _sending = true;
    try {
      for (final ctx in await store!.unsent(tripId!)) {
        await _send(ctx, live: false);
        if (offline) break;
      }
    } finally {
      _sending = false;
    }
  }

  Future<void> _onGuide(Map<String, dynamic> g) async {
    guides.add(g);
    current = g;
    await store?.saveGuide(tripId!, g);
    notifyListeners();
    if (!appInForeground) await notifier.showGuide(g);
    await audio.autoPlay(g);
  }

  /// Feedback actions (api-design feedback). Returns the server response.
  Future<Map<String, dynamic>> feedback(Map<String, dynamic> guide, String action) async {
    final r = (await api.post('/api/v1/guides/${guide['history_id']}/feedback', {'action': action})).json;
    if (['interesting', 'knew_it', 'not_interesting', 'wrong_info'].contains(action)) {
      guide['rating'] = action;
      await store?.saveGuide(tripId ?? '', guide);
    }
    if (action == 'more_detail' && r['detail_text'] != null) {
      guide['detail_text'] = r['detail_text'];
    }
    if (action == 'skip_story' || action == 'wrong_info') await audio.stop();
    final g = r['guide'];
    if (g is Map) await _onGuide(g.cast<String, dynamic>());
    notifyListeners();
    return r;
  }

  // ------------------------------------------------------------ P1: instructions, states, companions

  Future<void> refreshExtras() async {
    if (tripId == null) return;
    try {
      overrides = ((await api.get('/api/v1/trips/$tripId/overrides')).json['active'] as List)
          .cast<Map<String, dynamic>>();
      participants = ((await api.get('/api/v1/trips/$tripId/participants')).json['participants'] as List)
          .cast<Map<String, dynamic>>();
      notifyListeners();
    } catch (_) {}
  }

  /// Natural-language instruction. Returns the server response (created, needs_confirmation, ...).
  Future<Map<String, dynamic>> sendCommand(String text) async {
    final r = (await api.post('/api/v1/trips/$tripId/commands', {'text': text})).json;
    overrides = (r['active'] as List).cast<Map<String, dynamic>>();
    throttle.reset(); // re-evaluate soon with the new instruction
    if (overrides.any((o) => o['type'] == 'quiet')) await audio.stop();
    notifyListeners();
    return r;
  }

  Future<void> removeOverride(String id) async {
    overrides = ((await api.delete('/api/v1/trips/$tripId/overrides/$id')).json['active'] as List)
        .cast<Map<String, dynamic>>();
    throttle.reset();
    notifyListeners();
  }

  bool get isQuiet => overrides.any((o) => o['type'] == 'quiet');

  Future<void> setQuiet(int minutes) async {
    final r = (await api.post('/api/v1/trips/$tripId/states', {'type': 'quiet', 'minutes': minutes})).json;
    overrides = (r['active'] as List).cast<Map<String, dynamic>>();
    await audio.stop();
    notifyListeners();
  }

  Future<void> addParticipant(String name, List<String> interests) async {
    await api.post('/api/v1/trips/$tripId/participants', {'display_name': name, 'interests': interests});
    await refreshExtras();
  }

  Future<void> removeParticipant(String id) async {
    await api.delete('/api/v1/trips/$tripId/participants/$id');
    await refreshExtras();
  }

  void playCurrent() {
    final g = current;
    if (g == null) return;
    audio.play(
      g,
      onSpoken: () {
        api.post('/api/v1/guides/${g['history_id']}/feedback', {'action': 'spoken'}).ignore();
      },
    );
  }
}
