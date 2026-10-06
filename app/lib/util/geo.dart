import 'dart:math' as math;

const _earthR = 6371008.8;

double haversineM(double lat1, double lon1, double lat2, double lon2) {
  final p1 = lat1 * math.pi / 180, p2 = lat2 * math.pi / 180;
  final dp = p2 - p1, dl = (lon2 - lon1) * math.pi / 180;
  final a = math.pow(math.sin(dp / 2), 2) + math.cos(p1) * math.cos(p2) * math.pow(math.sin(dl / 2), 2);
  return 2 * _earthR * math.asin(math.sqrt(a));
}

double bearingDeg(double lat1, double lon1, double lat2, double lon2) {
  final p1 = lat1 * math.pi / 180, p2 = lat2 * math.pi / 180;
  final dl = (lon2 - lon1) * math.pi / 180;
  final x = math.sin(dl) * math.cos(p2);
  final y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl);
  return (math.atan2(x, y) * 180 / math.pi + 360) % 360;
}

double angleDiff(double a, double b) {
  var d = (b - a + 180) % 360 - 180;
  if (d < -180) d += 360;
  return d;
}
