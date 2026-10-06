import 'package:flutter_test/flutter_test.dart';
import 'package:localvoice/guide/guide_session.dart';
import 'package:localvoice/location/motion_estimator.dart';
import 'package:localvoice/location/track.dart';

void main() {
  final t0 = DateTime.utc(2026, 10, 6, 9);

  group('MotionEstimator', () {
    test('walking north gives walking class and a confident course', () {
      final m = MotionEstimator();
      // ~1.4 m/s north: 0.0000126 deg lat per second
      for (var i = 0; i <= 60; i += 5) {
        m.add(Fix(t0.add(Duration(seconds: i)), 34.3 + 0.0000126 * i, 132.3, 8));
      }
      final r = m.estimate();
      expect(r.mode, 'walking');
      expect(r.speedMps, closeTo(1.4, 0.2));
      expect(r.courseDeg! < 5 || r.courseDeg! > 355, isTrue);
      expect(r.courseConfidence, greaterThan(0.5));
    });

    test('jitter while standing still is stationary without a course', () {
      final m = MotionEstimator();
      for (var i = 0; i <= 60; i += 5) {
        m.add(Fix(t0.add(Duration(seconds: i)), 34.3 + (i.isEven ? 0.00002 : -0.00002), 132.3, 15, speedMps: 0.1));
      }
      final r = m.estimate();
      expect(r.mode, 'stationary');
      expect(r.courseDeg, isNull);
      expect(r.courseConfidence, 0);
    });

    test('inaccurate fixes are ignored', () {
      final m = MotionEstimator();
      m.add(Fix(t0, 34.3, 132.3, 500));
      expect(m.estimate().confidence, 0);
    });

    test('train speed is motorized', () {
      expect(MotionEstimator.classify(20), 'motorized');
      expect(MotionEstimator.classify(70), 'high_speed');
    });
  });

  group('segmentTrack', () {
    TrackPoint p(int sec, double lat, [double? acc]) => TrackPoint(t0.add(Duration(seconds: sec)), lat, 132.3, acc);

    test('splits on gaps longer than 5 minutes and sorts by time', () {
      final segs = segmentTrack([p(20, 34.3002), p(0, 34.3), p(10, 34.3001), p(10 + 600, 34.31), p(620, 34.3101)]);
      expect(segs.length, 2);
      expect(segs[0].map((e) => e.time.second).toList(), [0, 10, 20]);
      expect(segs[1].length, 2);
    });

    test('drops impossible jumps and inaccurate points', () {
      final segs = segmentTrack([p(0, 34.3), p(1, 35.3), p(2, 34.30001), p(3, 34.30002, 300)]);
      expect(segs.length, 1);
      expect(segs[0].length, 2);
    });
  });

  group('SendThrottle', () {
    test('sends first, then on distance or interval, and respects server hint', () {
      final th = SendThrottle();
      expect(th.shouldSend(t0, 34.3, 132.3, 'walking'), isTrue);
      th.sent(t0, 34.3, 132.3, 'walking');
      expect(th.shouldSend(t0.add(const Duration(seconds: 5)), 34.3001, 132.3, 'walking'), isFalse);
      expect(th.shouldSend(t0.add(const Duration(seconds: 15)), 34.3005, 132.3, 'walking'), isTrue); // ~55m
      expect(th.shouldSend(t0.add(const Duration(seconds: 61)), 34.3, 132.3, 'walking'), isTrue);
      expect(th.shouldSend(t0.add(const Duration(seconds: 5)), 34.3, 132.3, 'motorized'), isTrue);
      th.serverHint = const Duration(seconds: 300);
      expect(th.shouldSend(t0.add(const Duration(seconds: 120)), 34.3, 132.3, 'walking'), isFalse);
    });
  });
}
