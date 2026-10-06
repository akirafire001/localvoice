import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:maplibre_gl/maplibre_gl.dart';

import '../config.dart';
import '../location/track.dart';
import '../util/i18n.dart';

class GuideMarker {
  GuideMarker(this.lat, this.lon, this.title);
  final double lat;
  final double lon;
  final String title;
}

/// MapLibre map with the trip track, current position (+accuracy), and guide spots.
/// Used as the mini map on the guide screen and full-size on the map screen (flutter-ux §4).
class TrackMap extends StatefulWidget {
  const TrackMap({
    super.key,
    required this.points,
    this.current,
    this.currentAccuracyM,
    this.guides = const [],
    this.follow = true,
    this.compact = false,
  });

  final List<TrackPoint> points;
  final TrackPoint? current;
  final double? currentAccuracyM;
  final List<GuideMarker> guides;
  final bool follow;
  final bool compact;

  @override
  State<TrackMap> createState() => _TrackMapState();
}

class _TrackMapState extends State<TrackMap> {
  MapLibreMapController? _c;
  bool _styleReady = false;
  bool _following = true;

  @override
  void initState() {
    super.initState();
    _following = widget.follow;
  }

  @override
  void didUpdateWidget(covariant TrackMap old) {
    super.didUpdateWidget(old);
    _redraw();
  }

  LatLng? get _center {
    final c = widget.current ?? (widget.points.isNotEmpty ? widget.points.last : null);
    return c == null ? null : LatLng(c.lat, c.lon);
  }

  Future<void> _redraw() async {
    final c = _c;
    if (c == null || !_styleReady) return;
    await c.clearLines();
    await c.clearCircles();
    for (final seg in segmentTrack(widget.points)) {
      if (seg.length < 2) continue;
      await c.addLine(
        LineOptions(
          geometry: [for (final p in seg) LatLng(p.lat, p.lon)],
          lineColor: '#1565C0',
          lineWidth: widget.compact ? 3 : 4,
          lineOpacity: 0.85,
          lineJoin: 'round',
        ),
      );
    }
    for (final g in widget.guides) {
      await c.addCircle(
        CircleOptions(
          geometry: LatLng(g.lat, g.lon),
          circleRadius: 6,
          circleColor: '#EF6C00',
          circleStrokeColor: '#FFFFFF',
          circleStrokeWidth: 2,
        ),
      );
    }
    final cur = widget.current;
    if (cur != null) {
      final acc = widget.currentAccuracyM;
      if (acc != null && acc > 0) {
        final zoom = c.cameraPosition?.zoom ?? 15;
        final mPerPx = 156543.03392 * math.cos(cur.lat * math.pi / 180) / math.pow(2, zoom);
        await c.addCircle(
          CircleOptions(
            geometry: LatLng(cur.lat, cur.lon),
            circleRadius: (acc / mPerPx).clamp(8, 400).toDouble(),
            circleColor: '#42A5F5',
            circleOpacity: 0.15,
          ),
        );
      }
      await c.addCircle(
        CircleOptions(
          geometry: LatLng(cur.lat, cur.lon),
          circleRadius: 7,
          circleColor: '#1E88E5',
          circleStrokeColor: '#FFFFFF',
          circleStrokeWidth: 3,
        ),
      );
      if (_following) {
        await c.animateCamera(CameraUpdate.newLatLng(LatLng(cur.lat, cur.lon)));
      }
    }
  }

  Future<void> recenter() async {
    final center = _center;
    if (center == null || _c == null) return;
    setState(() => _following = true);
    await _c!.animateCamera(CameraUpdate.newLatLngZoom(center, 15));
  }

  Future<void> fitAll() async {
    final pts = [...widget.points, if (widget.current != null) widget.current!];
    if (pts.isEmpty || _c == null) return;
    setState(() => _following = false);
    var minLat = pts.first.lat, maxLat = pts.first.lat, minLon = pts.first.lon, maxLon = pts.first.lon;
    for (final p in pts) {
      minLat = math.min(minLat, p.lat);
      maxLat = math.max(maxLat, p.lat);
      minLon = math.min(minLon, p.lon);
      maxLon = math.max(maxLon, p.lon);
    }
    if (maxLat - minLat < 0.001) {
      maxLat += 0.0005;
      minLat -= 0.0005;
    }
    if (maxLon - minLon < 0.001) {
      maxLon += 0.0005;
      minLon -= 0.0005;
    }
    await _c!.animateCamera(
      CameraUpdate.newLatLngBounds(
        LatLngBounds(southwest: LatLng(minLat, minLon), northeast: LatLng(maxLat, maxLon)),
        left: 40,
        right: 40,
        top: 40,
        bottom: 40,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final center = _center ?? const LatLng(34.3853, 132.4553); // Hiroshima as a neutral default
    return Stack(
      children: [
        MapLibreMap(
          styleString: AppConfig.mapStyleUrl,
          initialCameraPosition: CameraPosition(target: center, zoom: widget.compact ? 14 : 15),
          trackCameraPosition: true,
          compassEnabled: !widget.compact,
          rotateGesturesEnabled: !widget.compact,
          tiltGesturesEnabled: false,
          attributionButtonPosition: AttributionButtonPosition.bottomRight,
          onMapCreated: (c) => _c = c,
          onStyleLoadedCallback: () {
            _styleReady = true;
            _redraw();
          },
          onCameraTrackingDismissed: () => setState(() => _following = false),
          onMapClick: (_, _) {
            if (_following) setState(() => _following = false);
          },
        ),
        Positioned(
          right: 8,
          top: 8,
          child: Column(
            children: [
              _MapButton(icon: Icons.my_location, tooltip: tr('現在地へ', 'Recenter'), onTap: recenter),
              if (!widget.compact) ...[
                const SizedBox(height: 8),
                _MapButton(icon: Icons.zoom_out_map, tooltip: tr('全体を表示', 'Show whole track'), onTap: fitAll),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _MapButton extends StatelessWidget {
  const _MapButton({required this.icon, required this.tooltip, required this.onTap});
  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
    color: Theme.of(context).colorScheme.surface,
    shape: const CircleBorder(),
    elevation: 2,
    child: IconButton(icon: Icon(icon), tooltip: tooltip, onPressed: onTap),
  );
}
