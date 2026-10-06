import 'dart:math' as math;

import '../util/geo.dart';

class Fix {
  Fix(this.time, this.lat, this.lon, this.accuracyM, {this.speedMps});
  final DateTime time;
  final double lat;
  final double lon;
  final double? accuracyM;
  final double? speedMps; // device-reported, may be null/negative
}

class Motion {
  Motion({this.speedMps, this.courseDeg, required this.mode, required this.confidence, required this.courseConfidence});
  final double? speedMps;
  final double? courseDeg;
  final String mode; // stationary/walking/cycling/motorized/high_speed/unknown
  final double confidence;
  final double courseConfidence;

  Map<String, dynamic> toJson() => {
    'speed_mps': speedMps,
    'course_deg': courseDeg,
    'transport_mode': mode,
    'confidence': double.parse(confidence.toStringAsFixed(2)),
    'course_confidence': double.parse(courseConfidence.toStringAsFixed(2)),
  };
}

/// Estimates speed/course/transport class from recent fixes (mvp-technical-design §4.2).
/// Uses a 60–180s window, drops inaccurate fixes, and takes medians to avoid GPS jitter.
class MotionEstimator {
  MotionEstimator({this.window = const Duration(seconds: 180), this.maxAccuracyM = 100});
  final Duration window;
  final double maxAccuracyM;
  final List<Fix> _fixes = [];

  void add(Fix f) {
    if (f.accuracyM != null && f.accuracyM! > maxAccuracyM) return;
    if (_fixes.isNotEmpty && !f.time.isAfter(_fixes.last.time)) return;
    _fixes.add(f);
    final cutoff = f.time.subtract(window);
    _fixes.removeWhere((x) => x.time.isBefore(cutoff));
  }

  void clear() => _fixes.clear();

  static double? _median(List<double> v) {
    if (v.isEmpty) return null;
    final s = [...v]..sort();
    final m = s.length ~/ 2;
    return s.length.isOdd ? s[m] : (s[m - 1] + s[m]) / 2;
  }

  static String classify(double? speed) {
    if (speed == null) return 'unknown';
    if (speed < 0.5) return 'stationary';
    if (speed < 2.5) return 'walking';
    if (speed < 7) return 'cycling';
    if (speed < 45) return 'motorized';
    return 'high_speed';
  }

  Motion estimate() {
    if (_fixes.length < 2) {
      final s = _fixes.isNotEmpty ? _fixes.last.speedMps : null;
      final sp = (s != null && s >= 0) ? s : null;
      return Motion(speedMps: sp, mode: classify(sp), confidence: sp == null ? 0 : 0.3, courseConfidence: 0);
    }
    final speeds = <double>[];
    for (var i = 1; i < _fixes.length; i++) {
      final a = _fixes[i - 1], b = _fixes[i];
      final dt = b.time.difference(a.time).inMilliseconds / 1000;
      if (dt <= 0) continue;
      final d = haversineM(a.lat, a.lon, b.lat, b.lon);
      final v = d / dt;
      if (v < 120) speeds.add(v); // drop impossible jumps
    }
    final reported = _fixes.map((f) => f.speedMps).whereType<double>().where((s) => s >= 0).toList();
    final speed = _median(reported.length >= speeds.length && reported.isNotEmpty ? reported : speeds);
    final first = _fixes.first, last = _fixes.last;
    final dist = haversineM(first.lat, first.lon, last.lat, last.lon);
    final span = last.time.difference(first.time).inSeconds;

    // Course from overall displacement; confidence grows with distance relative to accuracy
    // and with consistency of segment bearings.
    double? course;
    var courseConf = 0.0;
    final acc = _median(_fixes.map((f) => f.accuracyM ?? 30).toList()) ?? 30;
    if (dist > math.max(20, acc * 2)) {
      course = bearingDeg(first.lat, first.lon, last.lat, last.lon);
      final diffs = <double>[];
      for (var i = 1; i < _fixes.length; i++) {
        final a = _fixes[i - 1], b = _fixes[i];
        if (haversineM(a.lat, a.lon, b.lat, b.lon) < 5) continue;
        diffs.add(angleDiff(course, bearingDeg(a.lat, a.lon, b.lat, b.lon)).abs());
      }
      final spread = _median(diffs) ?? 90;
      courseConf = (1 - spread / 90).clamp(0.0, 1.0) * (dist / (dist + acc * 3)).clamp(0.0, 1.0);
    }
    final timeConf = (span / 60).clamp(0.0, 1.0);
    final countConf = (_fixes.length / 5).clamp(0.0, 1.0);
    final accConf = (1 - acc / maxAccuracyM).clamp(0.0, 1.0);
    final conf = 0.4 * timeConf + 0.3 * countConf + 0.3 * accConf;
    return Motion(
      speedMps: speed == null ? null : double.parse(speed.toStringAsFixed(2)),
      courseDeg: course == null ? null : double.parse(course.toStringAsFixed(1)),
      mode: classify(speed),
      confidence: conf,
      courseConfidence: courseConf,
    );
  }
}
