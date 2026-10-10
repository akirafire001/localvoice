import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../util/i18n.dart';
import '../widgets/common.dart';
import '../widgets/visuals.dart';
import 'home_screen.dart';
import 'map_screen.dart';

String fmtTime(String? iso) {
  if (iso == null) return '';
  final t = DateTime.tryParse(iso)?.toLocal();
  return t == null ? '' : DateFormat('yyyy/MM/dd HH:mm').format(t);
}

class TripListScreen extends StatefulWidget {
  const TripListScreen({super.key});
  @override
  State<TripListScreen> createState() => _TripListScreenState();
}

class _TripListScreenState extends State<TripListScreen> {
  List<Map<String, dynamic>>? _trips;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final r = await guarded(context, () => context.read<ApiClient>().get('/api/v1/trips'));
    if (!mounted) return;
    setState(() => _trips = r == null ? [] : ((r.json['trips'] as List).cast<Map<String, dynamic>>()));
  }

  @override
  Widget build(BuildContext context) {
    final trips = _trips;
    return Scaffold(
      appBar: LvAppBar(title: Text(tr('これまでの旅行', 'Past trips'))),
      body: trips == null
          ? const Center(child: CircularProgressIndicator())
          : trips.isEmpty
          ? LvEmptyState(artwork: LvArtwork.emptyHistory, message: tr('まだ旅行がありません', 'No trips yet'))
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: EdgeInsets.only(bottom: bottomGap(context)),
                children: [
                  for (final t in trips)
                    ListTile(
                      leading: LvIcon(purposeIcon(t['purpose'] as String?), size: 30),
                      trailing: LvIcon(t['ended_at'] == null ? LvIconKind.guide : LvIconKind.check, size: 20),
                      title: Text(
                        '${labelOf(purposeLabels, t['purpose'] as String?)}  ${fmtTime(t['started_at'] as String?)}',
                      ),
                      subtitle: Text(
                        t['ended_at'] == null ? tr('ガイド中', 'In progress') : '〜 ${fmtTime(t['ended_at'] as String?)}',
                      ),
                      onTap: () => Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => TripDetailScreen(tripId: t['trip_id'] as String)),
                      ),
                    ),
                ],
              ),
            ),
    );
  }
}

/// Guides received in one trip, with a short summary (flutter-ux §5).
class TripDetailScreen extends StatefulWidget {
  const TripDetailScreen({super.key, required this.tripId, this.summary});
  final String tripId;
  final Map<String, dynamic>? summary;
  @override
  State<TripDetailScreen> createState() => _TripDetailScreenState();
}

class _TripDetailScreenState extends State<TripDetailScreen> {
  List<Map<String, dynamic>>? _items;
  Map<String, dynamic>? _summary;

  @override
  void initState() {
    super.initState();
    _summary = widget.summary;
    _load();
  }

  Future<void> _load() async {
    final api = context.read<ApiClient>();
    final r = await guarded(context, () => api.get('/api/v1/trips/${widget.tripId}/history'));
    if (!mounted) return;
    final s = _summary ?? (await guarded(context, () => api.get('/api/v1/trips/${widget.tripId}/summary')))?.json;
    if (!mounted) return;
    setState(() {
      _items = r == null ? [] : (r.json['items'] as List).cast<Map<String, dynamic>>();
      _summary = s;
    });
  }

  Future<void> _rate(Map<String, dynamic> g, String action) async {
    final api = context.read<ApiClient>();
    final r = await guarded(context, () => api.post('/api/v1/guides/${g['history_id']}/feedback', {'action': action}));
    if (r != null && mounted) setState(() => g['rating'] = action);
  }

  @override
  Widget build(BuildContext context) {
    final items = _items;
    final s = _summary;
    return Scaffold(
      appBar: LvAppBar(
        title: Text(tr('旅行の記録', 'Trip record')),
        actions: [
          IconButton(
            icon: const LvIcon(LvIconKind.map),
            tooltip: tr('地図で見る', 'View on map'),
            onPressed: () =>
                Navigator.push(context, MaterialPageRoute(builder: (_) => MapScreen(initialTripId: widget.tripId))),
          ),
        ],
      ),
      body: items == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: EdgeInsets.fromLTRB(12, 12, 12, bottomGap(context)),
              children: [
                if (s != null)
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            tr('ガイド ${s['guides']}件', '${s['guides']} guides'),
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                          if ((s['memory_summary'] as String?)?.isNotEmpty == true) ...[
                            const SizedBox(height: 6),
                            Text(s['memory_summary'] as String),
                          ],
                        ],
                      ),
                    ),
                  ),
                if (items.isEmpty)
                  LvEmptyState(
                    artwork: LvArtwork.emptyHistory,
                    compact: true,
                    message: tr('この旅行ではまだガイドがありません', 'No guides in this trip'),
                  ),
                for (final g in items)
                  Card(
                    child: ExpansionTile(
                      leading: LvIcon(categoryIcon(g['category'] as String?), size: 28),
                      title: Text(g['title'] as String? ?? ''),
                      subtitle: Wrap(
                        spacing: 6,
                        runSpacing: 4,
                        children: [
                          Text('${categoryLabel(g['category'] as String?)} · ${fmtTime(g['shown_at'] as String?)}'),
                          if (g['origin'] == 'generated') const GeneratedBadge(),
                        ],
                      ),
                      childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                      children: [
                        Align(alignment: Alignment.centerLeft, child: Text(g['text'] as String? ?? '')),
                        if (g['detail_text'] != null) ...[
                          const SizedBox(height: 6),
                          Align(alignment: Alignment.centerLeft, child: Text(g['detail_text'] as String)),
                        ],
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 6,
                          children: [
                            for (final r in const [
                              ['interesting', '面白い', 'Interesting'],
                              ['knew_it', '知ってた', 'Knew it'],
                              ['not_interesting', '興味なし', 'Not for me'],
                              ['wrong_info', '情報が違う', 'Wrong info'],
                            ])
                              ChoiceChip(
                                avatar: LvIcon(ratingIcon(r[0]), size: 20),
                                showCheckmark: false,
                                label: Text(tr(r[1], r[2])),
                                selected: g['rating'] == r[0],
                                onSelected: (_) => _rate(g, r[0]),
                              ),
                          ],
                        ),
                        for (final src in (g['sources'] as List? ?? const []))
                          Align(
                            alignment: Alignment.centerLeft,
                            child: Text(
                              '• ${src['title'] ?? src['url'] ?? ''}',
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                          ),
                      ],
                    ),
                  ),
              ],
            ),
    );
  }
}
