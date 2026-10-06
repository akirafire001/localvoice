import '../config.dart';
import '../util/geo.dart';

class TrackPoint {
  TrackPoint(this.time, this.lat, this.lon, [this.accuracyM]);
  final DateTime time;
  final double lat;
  final double lon;
  final double? accuracyM;
}

/// Splits a track into drawable segments (flutter-ux §4.1): sort by time, drop
/// inaccurate fixes and impossible jumps, and break the line on long gaps.
List<List<TrackPoint>> segmentTrack(
  List<TrackPoint> points, {
  Duration gap = AppConfig.trackGapSplit,
  double maxSpeedMps = AppConfig.trackMaxPlausibleSpeedMps,
  double maxAccuracyM = 100,
}) {
  final sorted = points.where((p) => p.accuracyM == null || p.accuracyM! <= maxAccuracyM).toList()
    ..sort((a, b) => a.time.compareTo(b.time));
  final segments = <List<TrackPoint>>[];
  List<TrackPoint>? cur;
  TrackPoint? prev;
  for (final p in sorted) {
    if (prev != null) {
      final dt = p.time.difference(prev.time);
      if (dt.inMilliseconds <= 0) continue; // duplicate timestamp
      final v = haversineM(prev.lat, prev.lon, p.lat, p.lon) / (dt.inMilliseconds / 1000);
      if (v > maxSpeedMps) continue; // outlier: skip the point, keep the previous anchor
      if (dt > gap) cur = null;
    }
    if (cur == null) {
      cur = [];
      segments.add(cur);
    }
    cur.add(p);
    prev = p;
  }
  return segments;
}
