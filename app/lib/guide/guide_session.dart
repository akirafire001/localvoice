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
  /// True while a story button is waiting for the server. Audio playback is not included.
  bool feedbackBusy = false;
  String? feedbackAction;
  bool offline = false;
  StreamSubscription<Position>? _sub;
  bool _sending = false;
  Timer? _retry;
  bool appInForeground = true;

  /// "How often to talk" (server NOTIFICATION_LEVELS key). "continuous" asks for the next story as one ends.
  String notificationLevel = 'normal';
  bool get continuous => notificationLevel == 'continuous';

  /// The server's latest answer on why nothing is being told (reason, cooldown_sec, searching, ...) and when
  /// the app will ask again. The guide screen explains the wait from these.
  Map<String, dynamic>? decision;
  DateTime? nextCheckAt;

  /// True while the server is choosing a story for the current position.
  bool get selecting => _liveSends > 0;
  int _liveSends = 0;

  /// True while continuous mode is fetching the story after the one that just ended.
  bool continuing = false;

  /// Asks again when the server said to, even when standing still (the GPS stream is silent then).
  Timer? _heartbeat;

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
    _cancelHeartbeat();
    decision = null;
    nextCheckAt = null;
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
    decision = null;
    nextCheckAt = null;
    throttle.reset();
    motion.clear();
    await store!.set('active_trip_id', tripId);
    notifyListeners();
    await startGps();
  }

  Future<Map<String, dynamic>?> finishTrip() async {
    if (trip == null) return null;
    _cancelHeartbeat();
    await stopGps();
    await audio.stop();
    // Close the trip before uploading leftover points. A fresh point sent first would
    // run another full story selection, and finish itself no longer waits on the summary model.
    final r = (await api.post('/api/v1/trips/$tripId/finish')).json;
    trip = r;
    await store!.set('active_trip_id', null);
    notifyListeners();
    unawaited(_flushUnsent());
    return r['summary'] as Map<String, dynamic>?;
  }

  Future<void> updateTrip(Map<String, dynamic> body) async {
    trip = (await api.patch('/api/v1/trips/$tripId', body)).json;
    throttle.reset();
    _scheduleHeartbeat(const Duration(seconds: 2));
    notifyListeners();
  }

  /// Settings that change the guide's pace (from the preferences API).
  void applyPrefs(Map<String, dynamic> prefs) {
    final level = prefs['notification_level'];
    if (level is! String || level == notificationLevel) return;
    notificationLevel = level;
    if (active) _scheduleHeartbeat(const Duration(seconds: 2)); // the wait shown is for the old pace
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
    await _sendPosition(p, t, m);
  }

  Future<void> _sendPosition(Position p, DateTime t, Motion m) async {
    throttle.sent(t, p.latitude, p.longitude, m.mode);
    final ctx = {
      'client_event_id': _uuid.v4(),
      'observed_at': t.toIso8601String(),
      'utc_offset_min': t.toLocal().timeZoneOffset.inMinutes,
      'location': {'lat': p.latitude, 'lon': p.longitude, 'accuracy_m': p.accuracy},
      'motion': m.toJson(),
      'app_state': appInForeground ? 'foreground' : 'background',
      // the server never starts a new story over one that is still being told
      'speaking': audio.state == SpeechState.preparing || audio.state == SpeechState.playing,
    };
    await store!.addPoint(tripId!, ctx);
    await _send(ctx, live: true);
  }

  void _cancelHeartbeat() {
    _heartbeat?.cancel();
    _heartbeat = null;
  }

  void _scheduleHeartbeat(Duration after) {
    _cancelHeartbeat();
    if (!active) return;
    _heartbeat = Timer(after, _pulse);
  }

  /// Re-sends the last known position when the server's wait is over and no new fix has come
  /// (standing still, or moving less than the send distance).
  Future<void> _pulse() async {
    _heartbeat = null;
    final p = lastPosition;
    if (!active || store == null || p == null || gps != GpsState.on) {
      _scheduleHeartbeat(const Duration(seconds: 15));
      return;
    }
    if (selecting || continuing || feedbackBusy) {
      _scheduleHeartbeat(const Duration(seconds: 5));
      return;
    }
    await _sendPosition(p, DateTime.now().toUtc(), lastMotion ?? motion.estimate());
  }

  /// Remembers why nothing is being told and asks again when the server says to.
  void _applyDecision(Map d) {
    final reason = d['reason'] as String?;
    if (reason == 'trip_finished') {
      _cancelHeartbeat();
      return;
    }
    final level = d['notification_level'];
    if (level is String) notificationLevel = level;
    // answers about an older point or story say nothing about now
    if (reason == 'duplicate_event' || reason == 'stale_event' || reason == 'superseded') return;
    decision = d.cast<String, dynamic>();
    final next = d['next_check_after_sec'];
    final wait = Duration(seconds: next is num ? next.toInt().clamp(1, 24 * 3600) : 60);
    nextCheckAt = DateTime.now().add(wait);
    _scheduleHeartbeat(wait);
  }

  Future<void> _send(Map<String, dynamic> ctx, {required bool live}) async {
    final id = tripId;
    if (id == null) return;
    if (live) {
      _liveSends++;
      notifyListeners();
    }
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
      if (live) _applyDecision(d);
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
        if (live) _scheduleHeartbeat(const Duration(seconds: 30));
      } else if (e.status == 409 || e.status == 410 || e.status == 400) {
        await store?.markSent(ctx['client_event_id'] as String); // never resend a rejected point
      }
      notifyListeners();
    } finally {
      if (live) {
        _liveSends--;
        notifyListeners();
      }
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

  /// Shows a new story and starts telling it. Returns once it is on screen; playback runs on.
  Future<void> _onGuide(Map<String, dynamic> g) async {
    guides.add(g);
    current = g;
    await store?.saveGuide(tripId!, g);
    notifyListeners();
    if (!appInForeground) await notifier.showGuide(g);
    unawaited(() async {
      var toTheEnd = false;
      try {
        toTheEnd = await audio.autoPlay(g);
      } catch (_) {}
      // Continuous mode: heard to the end (not stopped or replaced), so go straight on to the next one.
      if (toTheEnd && continuous && active && identical(current, g)) await _continueAfter(g);
    }());
  }

  Future<void> _continueAfter(Map<String, dynamic> g) async {
    if (continuing || feedbackBusy) return;
    continuing = true;
    _cancelHeartbeat();
    notifyListeners();
    try {
      final r = (await api.post('/api/v1/guides/${g['history_id']}/feedback', {'action': 'continue'})).json;
      final d = r['decision'];
      if (d is Map) _applyDecision(d);
      final next = r['guide'];
      if (next is Map && active) await _onGuide(next.cast<String, dynamic>());
    } catch (_) {
      _scheduleHeartbeat(const Duration(seconds: 10)); // ask through a location update instead
    } finally {
      continuing = false;
      if (_heartbeat == null && active) _scheduleHeartbeat(const Duration(seconds: 60));
      notifyListeners();
    }
  }

  /// Feedback actions (api-design feedback). Returns the server response.
  /// The future completes when the new story is on screen, not when its audio ends.
  Future<Map<String, dynamic>?> feedback(Map<String, dynamic> guide, String action) async {
    if (feedbackBusy) return null;
    feedbackBusy = true;
    feedbackAction = action;
    notifyListeners();
    try {
      // Stop the current voice before the round trip, so the tap is audible immediately.
      if (action == 'skip_story' || action == 'wrong_info') await audio.stop();
      final r = (await api.post('/api/v1/guides/${guide['history_id']}/feedback', {'action': action})).json;
      if (['interesting', 'knew_it', 'not_interesting', 'wrong_info'].contains(action)) {
        guide['rating'] = action;
        await store?.saveGuide(tripId ?? '', guide);
      }
      if (action == 'more_detail' && r['detail_text'] != null) {
        guide['detail_text'] = r['detail_text'];
      }
      final d = r['decision'];
      if (d is Map) _applyDecision(d);
      final g = r['guide'];
      if (g is Map) await _onGuide(g.cast<String, dynamic>());
      notifyListeners();
      return r;
    } finally {
      feedbackBusy = false;
      feedbackAction = null;
      notifyListeners();
    }
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
    _scheduleHeartbeat(const Duration(seconds: 2));
    if (overrides.any((o) => o['type'] == 'quiet')) await audio.stop();
    notifyListeners();
    return r;
  }

  Future<void> removeOverride(String id) async {
    overrides = ((await api.delete('/api/v1/trips/$tripId/overrides/$id')).json['active'] as List)
        .cast<Map<String, dynamic>>();
    throttle.reset();
    _scheduleHeartbeat(const Duration(seconds: 2));
    notifyListeners();
  }

  bool get isQuiet => overrides.any((o) => o['type'] == 'quiet');

  Future<void> setQuiet(int minutes) async {
    final r = (await api.post('/api/v1/trips/$tripId/states', {'type': 'quiet', 'minutes': minutes})).json;
    overrides = (r['active'] as List).cast<Map<String, dynamic>>();
    await audio.stop();
    _scheduleHeartbeat(const Duration(seconds: 2)); // so the screen shows the quiet time left
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
