import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../audio/audio_controller.dart';
import '../guide/guide_session.dart';
import '../location/track.dart';
import '../util/i18n.dart';
import '../widgets/common.dart';
import '../widgets/track_map.dart';
import 'home_screen.dart';
import 'map_screen.dart';

/// Main screen while guiding (flutter-ux §3): mini map on top third, current story card,
/// one-tap ratings and commands.
class GuideScreen extends StatefulWidget {
  const GuideScreen({super.key});
  @override
  State<GuideScreen> createState() => _GuideScreenState();
}

class _GuideScreenState extends State<GuideScreen> {
  List<TrackPoint> _track = [];
  int _trackLoadedFor = -1;

  Future<void> _loadTrack(GuideSession s) async {
    if (s.store == null || s.tripId == null) return;
    final rows = await s.store!.points(s.tripId!);
    if (!mounted) return;
    setState(() {
      _track = [
        for (final r in rows)
          TrackPoint(
            DateTime.parse(r['observed_at'] as String),
            r['lat'] as double,
            r['lon'] as double,
            r['accuracy_m'] as double?,
          ),
      ];
    });
  }

  Future<void> _finish(GuideSession s) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(tr('ガイドを終了しますか？', 'Finish the guide?')),
        content: Text(tr('位置情報の取得と音声を止めます。', 'Location tracking and audio will stop.')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: Text(tr('続ける', 'Continue'))),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: Text(tr('終了', 'Finish'))),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    await guarded(context, s.finishTrip);
    if (!mounted) return;
    // Back to home; the finished trip stays viewable from the history screen.
    Navigator.of(context).popUntil((r) => r.isFirst);
  }

  @override
  Widget build(BuildContext context) {
    final s = context.watch<GuideSession>();
    final audio = context.watch<AudioController>();
    if (s.guides.length + (s.lastPosition == null ? 0 : 1) != _trackLoadedFor) {
      _trackLoadedFor = s.guides.length + (s.lastPosition == null ? 0 : 1);
      _loadTrack(s);
    }
    final pos = s.lastPosition;
    final g = s.current;
    return Scaffold(
      appBar: AppBar(
        title: Text(tr('ガイド中', 'Guiding')),
        actions: [
          PopupMenuButton<String>(
            onSelected: (v) async {
              if (v == 'transport') await _pickTransport(s);
              if (v == 'people' && context.mounted) {
                await showModalBottomSheet(
                  context: context,
                  isScrollControlled: true,
                  builder: (_) => const _Companions(),
                );
              }
              if (v == 'map' && context.mounted) {
                Navigator.push(context, MaterialPageRoute(builder: (_) => MapScreen(initialTripId: s.tripId)));
              }
            },
            itemBuilder: (_) => [
              PopupMenuItem(value: 'transport', child: Text(tr('移動手段を変更', 'Change transport'))),
              PopupMenuItem(value: 'map', child: Text(tr('地図を開く', 'Open map'))),
              PopupMenuItem(value: 'people', child: Text(tr('同行者', 'Companions'))),
            ],
          ),
          TextButton(onPressed: () => _finish(s), child: Text(tr('終了', 'Finish'))),
        ],
      ),
      body: Column(
        children: [
          SizedBox(
            height: MediaQuery.of(context).size.height / 3,
            child: TrackMap(
              compact: true,
              points: _track,
              current: pos == null ? null : TrackPoint(pos.timestamp, pos.latitude, pos.longitude, pos.accuracy),
              currentAccuracyM: pos?.accuracy,
              guides: [
                for (final x in s.guides)
                  if (x['location']?['lat'] != null)
                    GuideMarker(
                      (x['location']['lat'] as num).toDouble(),
                      (x['location']['lon'] as num).toDouble(),
                      x['title'] as String,
                    ),
              ],
            ),
          ),
          _StatusBar(session: s),
          Expanded(
            child: g == null
                ? Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Text(
                        tr(
                          '近くに話題があればお知らせします。画面を閉じてもガイドは続きます。',
                          'We will tell you when there is a story nearby. Guiding continues with the screen off.',
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  )
                : _GuideCard(guide: g, session: s, audio: audio),
          ),
        ],
      ),
    );
  }

  Future<void> _pickTransport(GuideSession s) async {
    final cur = s.trip?['manual_transport_mode'] as String? ?? 'auto';
    final v = await showModalBottomSheet<String>(
      context: context,
      builder: (c) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            for (final k in transportLabels.keys)
              ListTile(
                title: Text(labelOf(transportLabels, k)),
                trailing: k == cur ? const Icon(Icons.check) : null,
                onTap: () => Navigator.pop(c, k),
              ),
          ],
        ),
      ),
    );
    if (v != null && v != cur && mounted) await guarded(context, () => s.updateTrip({'manual_transport_mode': v}));
  }
}

class _StatusBar extends StatelessWidget {
  const _StatusBar({required this.session});
  final GuideSession session;
  @override
  Widget build(BuildContext context) {
    final s = session;
    String text;
    IconData icon;
    switch (s.gps) {
      case GpsState.denied:
        text = tr('位置情報が許可されていません。設定で許可してください。', 'Location permission is off. Allow it in Settings.');
        icon = Icons.location_disabled;
      case GpsState.serviceOff:
        text = tr('端末の位置情報がオフです。', 'Device location is turned off.');
        icon = Icons.location_off;
      case GpsState.off:
      case GpsState.starting:
        text = tr('位置情報を待っています…', 'Waiting for location…');
        icon = Icons.location_searching;
      case GpsState.on:
        final acc = s.lastPosition?.accuracy;
        text = acc == null
            ? tr('位置情報を待っています…', 'Waiting for location…')
            : acc > 100
            ? tr('位置の精度が低いため、案内を控えています（±${acc.round()}m）', 'Low accuracy (±${acc.round()} m); holding guides')
            : '${_modeLabel(s.lastMotion?.mode)} · ±${acc.round()}m';
        icon = Icons.gps_fixed;
    }
    if (s.offline) {
      text = tr('オフライン：位置は端末に保存し、通信回復後に送ります', 'Offline: points are saved and sent later');
      icon = Icons.cloud_off;
    }
    return Container(
      width: double.infinity,
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Row(
        children: [
          Icon(icon, size: 16),
          const SizedBox(width: 8),
          Expanded(child: Text(text, style: Theme.of(context).textTheme.bodySmall)),
        ],
      ),
    );
  }

  static String _modeLabel(String? m) => switch (m) {
    'stationary' => tr('停止中', 'Stopped'),
    'walking' => tr('徒歩', 'Walking'),
    'cycling' => tr('自転車程度', 'Cycling speed'),
    'motorized' => tr('車・電車', 'Car / train'),
    'high_speed' => tr('高速移動', 'High speed'),
    _ => tr('移動を判定中', 'Detecting movement'),
  };
}

class _GuideCard extends StatelessWidget {
  const _GuideCard({required this.guide, required this.session, required this.audio});
  final Map<String, dynamic> guide;
  final GuideSession session;
  final AudioController audio;

  @override
  Widget build(BuildContext context) {
    final g = guide;
    final theme = Theme.of(context);
    final rating = g['rating'] as String?;
    final playingThis = audio.currentHistoryId == g['history_id'] && audio.state != SpeechState.idle;
    final loc = g['location'] as Map?;
    return ListView(
      // Keep the rating buttons clear of the system navigation bar.
      padding: EdgeInsets.fromLTRB(16, 16, 16, 32 + MediaQuery.paddingOf(context).bottom),
      children: [
        Row(
          children: [
            Chip(label: Text(categoryLabel(g['category'] as String?)), visualDensity: VisualDensity.compact),
            const SizedBox(width: 8),
            if (g['origin'] == 'generated') const GeneratedBadge(),
            const Spacer(),
            if (loc?['relative_direction'] != null)
              Text(_dir(loc!['relative_direction'] as String), style: theme.textTheme.bodySmall),
          ],
        ),
        Text(g['title'] as String? ?? '', style: theme.textTheme.titleLarge),
        const SizedBox(height: 8),
        Text(g['text'] as String? ?? '', style: theme.textTheme.bodyLarge),
        if (g['detail_text'] != null && g['_showDetail'] == true) ...[
          const SizedBox(height: 8),
          Text(g['detail_text'] as String, style: theme.textTheme.bodyMedium),
        ],
        const SizedBox(height: 8),
        _Sources(guide: g),
        if (audio.state == SpeechState.textOnly && audio.currentHistoryId == g['history_id'])
          Text(
            tr('音声を用意できなかったため、文字で表示しています。', 'Audio is unavailable; showing text.'),
            style: theme.textTheme.bodySmall,
          ),
        const SizedBox(height: 12),
        Row(
          children: [
            IconButton.filledTonal(
              icon: Icon(playingThis ? Icons.stop : Icons.volume_up),
              tooltip: playingThis ? tr('停止', 'Stop') : tr('読み上げ', 'Play'),
              onPressed: () => playingThis ? audio.stop() : session.playCurrent(),
            ),
            if (audio.state == SpeechState.preparing && audio.currentHistoryId == g['history_id'])
              const Padding(
                padding: EdgeInsets.only(left: 8),
                child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
              ),
            const Spacer(),
            TextButton(
              onPressed: () async {
                await guarded(context, () => session.feedback(g, 'more_detail'));
                g['_showDetail'] = true;
              },
              child: Text(tr('詳しく', 'More')),
            ),
            TextButton(
              onPressed: () async {
                final r = await guarded(context, () => session.feedback(g, 'skip_story'));
                // No untold story nearby: the server queues the surrounding area for generation
                if (r != null && r['guide'] == null && context.mounted) {
                  showInfo(context, tr('近くの話はもうありません。周りの話を準備しています',
                      'No more stories nearby. Preparing stories around you'));
                }
              },
              child: Text(tr('次の話', 'Next')),
            ),
          ],
        ),
        Wrap(
          spacing: 8,
          children: [
            ActionChip(
              label: Text(tr('関連する話を', 'More like this')),
              onPressed: () => _act(context, 'more_related', tr('関連する話を増やします', 'More related stories')),
            ),
            ActionChip(
              label: Text(tr('この話題はもう十分', 'Enough of this topic')),
              onPressed: () => _act(context, 'enough_topic', tr('しばらくこの話題を控えます', 'This topic will pause for a while')),
            ),
          ],
        ),
        const Divider(height: 24),
        Text(tr('この話はどうでしたか？', 'How was this story?'), style: theme.textTheme.titleSmall),
        const SizedBox(height: 4),
        Wrap(
          spacing: 8,
          children: [
            for (final r in const [
              ['interesting', '面白い', 'Interesting'],
              ['knew_it', '知ってた', 'Knew it'],
              ['not_interesting', '興味なし', 'Not for me'],
              ['wrong_info', '情報が違う', 'Wrong info'],
            ])
              ChoiceChip(
                label: Text(tr(r[1], r[2])),
                selected: rating == r[0],
                onSelected: (_) => _act(
                  context,
                  r[0],
                  r[0] == 'wrong_info' ? tr('報告しました。確認まで表示を止めます。', 'Reported; hidden until reviewed.') : null,
                ),
              ),
          ],
        ),
      ],
    );
  }

  Future<void> _act(BuildContext context, String action, String? done) async {
    final r = await guarded(context, () => session.feedback(guide, action));
    if (r != null && done != null && context.mounted) showInfo(context, done);
  }

  static String _dir(String d) => switch (d) {
    'ahead' => tr('前方', 'ahead'),
    'left' => tr('左手', 'on the left'),
    'right' => tr('右手', 'on the right'),
    'behind' => tr('後方', 'behind'),
    'here' => tr('この辺り', 'around here'),
    _ => '',
  };
}

class _Sources extends StatelessWidget {
  const _Sources({required this.guide});
  final Map<String, dynamic> guide;
  @override
  Widget build(BuildContext context) {
    final src = (guide['sources'] as List?) ?? const [];
    final conf = guide['confidence'] as Map?;
    if (src.isEmpty && conf == null) return const SizedBox.shrink();
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      title: Text(tr('出典・信頼度', 'Sources & confidence'), style: Theme.of(context).textTheme.bodySmall),
      children: [
        if (conf != null)
          Align(
            alignment: Alignment.centerLeft,
            child: Text(
              '${tr('信頼度', 'Confidence')}: ${conf['level']} · ${conf['fact_type'] ?? ''}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        for (final s in src)
          Align(
            alignment: Alignment.centerLeft,
            child: Text(
              '• ${s['title'] ?? s['url'] ?? ''}${s['license'] != null ? ' (${s['license']})' : ''}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
      ],
    );
  }
}

/// Free-text temporary instruction (flutter-ux §7) plus a one-tap quiet button.
class _CommandBar extends StatefulWidget {
  const _CommandBar({required this.session});
  final GuideSession session;
  @override
  State<_CommandBar> createState() => _CommandBarState();
}

class _CommandBarState extends State<_CommandBar> {
  final _c = TextEditingController();
  bool _busy = false;

  Future<void> _send() async {
    final text = _c.text.trim();
    if (text.isEmpty) return;
    setState(() => _busy = true);
    try {
      final r = await widget.session.sendCommand(text);
      _c.clear();
      if (!mounted) return;
      final labels = (r['created'] as List).map((e) => e['label']).join('、');
      showInfo(
        context,
        r['needs_confirmation'] == true
            ? tr('「$labels」として短時間だけ反映しました。違う場合は×で解除してください。', 'Applied "$labels" briefly. Tap × if that is wrong.')
            : r['resumed'] == true && labels.isEmpty
            ? tr('ガイドを再開します', 'Guiding resumed')
            : tr('「$labels」にしました', 'Set: $labels'),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      if (e.code == 'command_not_understood') {
        showInfo(
          context,
          tr(
            'うまく理解できませんでした。例:「しばらく建築を多めに」「30分静かに」',
            'Not understood. Try "more architecture for a while" or "quiet for 30 min".',
          ),
        );
      } else {
        showError(context, e);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.session;
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 4, 8, 8),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _c,
                enabled: !_busy,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _send(),
                decoration: InputDecoration(
                  isDense: true,
                  hintText: tr('例: しばらく建築を多めに', 'e.g. more architecture for a while'),
                  border: const OutlineInputBorder(),
                ),
              ),
            ),
            IconButton(icon: const Icon(Icons.send), tooltip: tr('送信', 'Send'), onPressed: _busy ? null : _send),
            IconButton(
              icon: Icon(s.isQuiet ? Icons.notifications_off : Icons.notifications_paused_outlined),
              tooltip: tr('30分静かに', 'Quiet for 30 min'),
              onPressed: s.isQuiet ? null : () => guarded(context, () => s.setQuiet(30)),
            ),
          ],
        ),
      ),
    );
  }
}

class _Companions extends StatefulWidget {
  const _Companions();
  @override
  State<_Companions> createState() => _CompanionsState();
}

class _CompanionsState extends State<_Companions> {
  final _name = TextEditingController();
  final Set<String> _interests = {};

  @override
  Widget build(BuildContext context) {
    final s = context.watch<GuideSession>();
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 16, 16, MediaQuery.of(context).viewInsets.bottom + 16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(tr('同行者', 'Companions'), style: Theme.of(context).textTheme.titleMedium),
          Text(
            tr('同行者の興味も話題選びに反映します。この旅行の中だけで使います。', 'Their interests are used for this trip only.'),
            style: Theme.of(context).textTheme.bodySmall,
          ),
          for (final p in s.participants)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(p['display_name'] as String),
              subtitle: Text(((p['interests'] as List?) ?? []).map((c) => categoryLabel(c as String)).join('・')),
              trailing: IconButton(
                icon: const Icon(Icons.close),
                onPressed: () => guarded(context, () => s.removeParticipant(p['participant_id'] as String)),
              ),
            ),
          const Divider(),
          TextField(
            controller: _name,
            decoration: InputDecoration(labelText: tr('名前', 'Name')),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            children: [
              for (final c in categoryLabels.keys)
                FilterChip(
                  label: Text(categoryLabel(c)),
                  selected: _interests.contains(c),
                  onSelected: (v) => setState(() => v ? _interests.add(c) : _interests.remove(c)),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerRight,
            child: FilledButton(
              onPressed: () async {
                if (_name.text.trim().isEmpty) return;
                final ok = await guarded(context, () async {
                  await s.addParticipant(_name.text.trim(), _interests.toList());
                  return true;
                });
                if (ok == true && mounted) {
                  setState(() {
                    _name.clear();
                    _interests.clear();
                  });
                }
              },
              child: Text(tr('追加', 'Add')),
            ),
          ),
        ],
      ),
    );
  }
}
