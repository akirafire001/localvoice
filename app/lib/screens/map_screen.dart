import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../guide/guide_session.dart';
import '../location/track.dart';
import '../util/i18n.dart';
import '../widgets/common.dart';
import '../widgets/track_map.dart';
import '../widgets/visuals.dart';
import 'history_screen.dart';
import 'home_screen.dart';

/// Full map: pick a trip, see its track, guide spots, and the current position (flutter-ux §4).
class MapScreen extends StatefulWidget {
  const MapScreen({super.key, this.initialTripId});
  final String? initialTripId;
  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  List<Map<String, dynamic>> _trips = [];
  String? _tripId;
  List<TrackPoint> _points = [];
  List<GuideMarker> _guides = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _tripId = widget.initialTripId;
    _init();
  }

  Future<void> _init() async {
    final api = context.read<ApiClient>();
    final r = await guarded(context, () => api.get('/api/v1/trips'));
    _trips = r == null ? [] : (r.json['trips'] as List).cast<Map<String, dynamic>>();
    _tripId ??= _trips.isEmpty ? null : _trips.first['trip_id'] as String;
    await _loadTrip();
  }

  Future<void> _loadTrip() async {
    final id = _tripId;
    if (id == null) {
      if (mounted) setState(() => _loading = false);
      return;
    }
    setState(() => _loading = true);
    final api = context.read<ApiClient>();
    final session = context.read<GuideSession>();
    final pts = <TrackPoint>[];
    String? cursor;
    try {
      do {
        final r = (await api.get('/api/v1/trips/$id/track', query: {'limit': '1000', 'cursor': ?cursor})).json;
        for (final p in (r['points'] as List)) {
          final l = p['location'] as Map;
          pts.add(
            TrackPoint(
              DateTime.parse(p['observed_at'] as String),
              (l['lat'] as num).toDouble(),
              (l['lon'] as num).toDouble(),
              (l['accuracy_m'] as num?)?.toDouble(),
            ),
          );
        }
        cursor = r['next_cursor'] as String?;
      } while (cursor != null && pts.length < 20000);
      final h = (await api.get('/api/v1/trips/$id/history')).json;
      _guides = [
        for (final g in (h['items'] as List))
          if (g['location']?['lat'] != null)
            GuideMarker(
              (g['location']['lat'] as num).toDouble(),
              (g['location']['lon'] as num).toDouble(),
              g['title'] as String,
            ),
      ];
    } catch (e) {
      if (mounted) showError(context, e);
    }
    // Points not yet sent (offline) are still shown from the local store.
    final s = session;
    if (s.store != null && s.tripId == id) {
      final known = pts.map((p) => p.time.millisecondsSinceEpoch).toSet();
      for (final r in await s.store!.points(id)) {
        final t = DateTime.parse(r['observed_at'] as String);
        if (!known.contains(t.millisecondsSinceEpoch)) {
          pts.add(TrackPoint(t, r['lat'] as double, r['lon'] as double, r['accuracy_m'] as double?));
        }
      }
    }
    if (!mounted) return;
    setState(() {
      _points = pts;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final s = context.watch<GuideSession>();
    final pos = s.lastPosition;
    final showCurrent = s.active && s.tripId == _tripId && pos != null;
    return Scaffold(
      appBar: LvAppBar(
        title: Text(tr('地図', 'Map')),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(48),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: DropdownButton<String>(
              isExpanded: true,
              value: _tripId,
              hint: Text(tr('旅行を選択', 'Choose a trip')),
              items: [
                for (final t in _trips)
                  DropdownMenuItem(
                    value: t['trip_id'] as String,
                    child: Text(
                      '${labelOf(purposeLabels, t['purpose'] as String?)}  ${fmtTime(t['started_at'] as String?)}',
                    ),
                  ),
              ],
              onChanged: (v) {
                setState(() => _tripId = v);
                _loadTrip();
              },
            ),
          ),
        ),
      ),
      body: Stack(
        children: [
          TrackMap(
            points: _points,
            guides: _guides,
            follow: showCurrent,
            current: showCurrent ? TrackPoint(pos.timestamp, pos.latitude, pos.longitude, pos.accuracy) : null,
            currentAccuracyM: showCurrent ? pos.accuracy : null,
          ),
          if (_loading) const Center(child: CircularProgressIndicator()),
          if (!_loading && _points.isEmpty)
            Center(
              child: Card(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 320),
                  child: LvEmptyState(
                    artwork: LvArtwork.emptyMap,
                    compact: true,
                    message: tr('表示できる移動記録がありません', 'No track to show'),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
