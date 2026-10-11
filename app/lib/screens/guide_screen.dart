import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../audio/audio_controller.dart';
import '../guide/guide_session.dart';
import '../location/track.dart';
import '../util/i18n.dart';
import '../widgets/common.dart';
import '../widgets/track_map.dart';
import '../widgets/visuals.dart';
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
  bool _finishing = false;

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
    setState(() => _finishing = true);
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
      appBar: LvAppBar(
        title: Text(tr('ガイド中', 'Guiding')),
        actions: [
          PopupMenuButton<String>(
            icon: const LvIcon(LvIconKind.other),
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
              PopupMenuItem(
                value: 'transport',
                child: Row(
                  children: [
                    LvIcon(transportIcon(s.trip?['manual_transport_mode'] as String?)),
                    const SizedBox(width: 10),
                    Expanded(child: Text(tr('移動手段を変更', 'Change transport'))),
                  ],
                ),
              ),
              PopupMenuItem(
                value: 'map',
                child: Row(
                  children: [
                    const LvIcon(LvIconKind.map),
                    const SizedBox(width: 10),
                    Expanded(child: Text(tr('地図を開く', 'Open map'))),
                  ],
                ),
              ),
              PopupMenuItem(
                value: 'people',
                child: Row(
                  children: [
                    const LvIcon(LvIconKind.companions),
                    const SizedBox(width: 10),
                    Expanded(child: Text(tr('同行者', 'Companions'))),
                  ],
                ),
              ),
            ],
          ),
          TextButton(
            onPressed: _finishing ? null : () => _finish(s),
            child: Text(tr('終了', 'Finish')),
          ),
        ],
      ),
      body: Stack(
        children: [
          Column(
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
              _ActivityBar(session: s, audio: audio),
              Expanded(
                child: g == null
                    ? LvEmptyState(
                        artwork: s.offline
                            ? LvArtwork.offlineLocalSave
                            : s.gps == GpsState.denied || s.gps == GpsState.serviceOff
                            ? LvArtwork.locationPermission
                            : LvArtwork.waitingForStory,
                        message: s.offline
                            ? tr(
                                '通信が戻るまで移動を端末に記録します。',
                                'Your movement is saved on this device until the connection returns.',
                              )
                            : tr(
                                '近くに話題があればお知らせします。画面を閉じてもガイドは続きます。',
                                'We will tell you when there is a story nearby. Guiding continues with the screen off.',
                              ),
                      )
                    : GuideStoryCard(guide: g, session: s, audio: audio),
              ),
            ],
          ),
          if (_finishing) ...[
            const Positioned.fill(
              child: ModalBarrier(dismissible: false, color: Color(0x66000000)),
            ),
            Center(
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2)),
                      const SizedBox(width: 16),
                      Text(tr('終了しています…', 'Finishing…')),
                    ],
                  ),
                ),
              ),
            ),
          ],
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
                leading: LvIcon(transportIcon(k)),
                title: Text(labelOf(transportLabels, k)),
                trailing: k == cur ? const LvIcon(LvIconKind.check) : null,
                onTap: () => Navigator.pop(c, k),
              ),
          ],
        ),
      ),
    );
    if (v != null && v != cur && mounted) {
      await guarded(context, () => s.updateTrip({'manual_transport_mode': v}));
    }
  }
}

class _StatusBar extends StatelessWidget {
  const _StatusBar({required this.session});
  final GuideSession session;
  @override
  Widget build(BuildContext context) {
    final s = session;
    String text;
    LvIconKind icon;
    switch (s.gps) {
      case GpsState.denied:
        text = tr('位置情報が許可されていません。設定で許可してください。', 'Location permission is off. Allow it in Settings.');
        icon = LvIconKind.gpsDenied;
      case GpsState.serviceOff:
        text = tr('端末の位置情報がオフです。', 'Device location is turned off.');
        icon = LvIconKind.gpsOff;
      case GpsState.off:
      case GpsState.starting:
        text = tr('位置情報を待っています…', 'Waiting for location…');
        icon = LvIconKind.gpsSearching;
      case GpsState.on:
        final acc = s.lastPosition?.accuracy;
        text = acc == null
            ? tr('位置情報を待っています…', 'Waiting for location…')
            : acc > 100
            ? tr('位置の精度が低いため、案内を控えています（±${acc.round()}m）', 'Low accuracy (±${acc.round()} m); holding guides', {
                'zh': '定位不够精确（±${acc.round()} 米），先暂停讲解',
                'ko': '위치 오차가 커서 안내를 잠시 멈춥니다(±${acc.round()} m)',
                'es': 'Precisión baja (±${acc.round()} m); las guías esperan',
                'fr': 'Précision faible (±${acc.round()} m) ; les récits patientent',
              })
            : '${_modeLabel(s.lastMotion?.mode)} · ±${acc.round()}m';
        icon = LvIconKind.gps;
    }
    if (s.offline) {
      text = tr('オフライン：位置は端末に保存し、通信回復後に送ります', 'Offline: points are saved and sent later');
      icon = LvIconKind.offline;
    }
    return Container(
      width: double.infinity,
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Row(
        children: [
          LvIcon(icon, size: 24),
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

/// What the guide is doing right now, or why it is waiting and for how long, so it never just looks stopped.
class _ActivityBar extends StatefulWidget {
  const _ActivityBar({required this.session, required this.audio});
  final GuideSession session;
  final AudioController audio;
  @override
  State<_ActivityBar> createState() => _ActivityBarState();
}

class _ActivityBarState extends State<_ActivityBar> {
  late final Timer _tick;

  @override
  void initState() {
    super.initState();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {}); // the countdown
    });
  }

  @override
  void dispose() {
    _tick.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final a = activityOf(widget.session, widget.audio, DateTime.now());
    if (a == null) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Container(
      width: double.infinity,
      color: theme.colorScheme.secondaryContainer,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          if (a.busy)
            const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
          else
            LvIcon(a.icon, size: 24),
          const SizedBox(width: 10),
          Expanded(
            child: Text(a.text, style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSecondaryContainer)),
          ),
        ],
      ),
    );
  }
}

class Activity {
  const Activity(this.text, {this.busy = false, this.icon = LvIconKind.guide});
  final String text;
  final bool busy;
  final LvIconKind icon;
}

const _levelNames = {
  'quiet': ['900秒おき', 'every 900 s'],
  'normal': ['360秒おき', 'every 360 s'],
  'talkative': ['180秒おき', 'every 180 s'],
  'chatty': ['90秒おき', 'every 90 s'],
};

String _clock(Duration d) {
  final s = d.inSeconds < 0 ? 0 : d.inSeconds;
  return '${s ~/ 60}:${(s % 60).toString().padLeft(2, '0')}';
}

/// The line under the status bar. Null when the status bar already says everything (no GPS, offline).
Activity? activityOf(GuideSession s, AudioController audio, DateTime now) {
  if (!s.active || s.offline || s.gps != GpsState.on) return null;
  if (s.feedbackBusy && s.feedbackAction == 'skip_story') {
    return Activity(tr('次の話を選んでいます…', 'Choosing the next story…'), busy: true);
  }
  if (s.continuing) return Activity(tr('続けて次の話を用意しています…', 'Getting the next story ready…'), busy: true);
  if (audio.state == SpeechState.preparing) return Activity(tr('音声を準備しています…', 'Preparing the audio…'), busy: true);
  if (audio.state == SpeechState.playing) {
    return Activity(
      s.continuous
          ? tr('再生中です。終わったら続けて次の話に進みます。', 'Playing. The next story follows right after.')
          : tr('再生中です。', 'Playing.'),
      icon: LvIconKind.play,
    );
  }
  if (s.selecting) return Activity(tr('近くの話を選んでいます…', 'Choosing a story nearby…'), busy: true);
  final d = s.decision;
  if (d == null) {
    return Activity(tr('位置を送って、近くの話を探しています…', 'Looking for stories around you…'), busy: true);
  }
  final left = s.nextCheckAt == null ? Duration.zero : s.nextCheckAt!.difference(now);
  if (left.inSeconds <= 0) return Activity(tr('まもなく次の話を確認します…', 'Checking for the next story…'), busy: true);
  final t = _clock(left);
  final reason = d['reason'] as String?;
  switch (reason) {
    case 'selected':
    case 'cooldown':
    case 'speaking':
      if (s.continuous) {
        return Activity(tr('あと $t で次の話を確認します（連続）', 'Checking for the next story in $t (continuous)'), icon: LvIconKind.frequency);
      }
      final cool = d['cooldown_sec'];
      final name = _levelNames[s.notificationLevel];
      final pace = name != null
          ? tr(name[0], name[1])
          : cool is num
          ? tr('${cool.toInt()}秒おき', 'every ${cool.toInt()} s')
          : '';
      return Activity(
        tr('次の話まで あと $t（話しかける頻度：$pace）', 'Next story in $t (pace: $pace)'),
        icon: LvIconKind.frequency,
      );
    case 'no_candidates':
    case 'below_threshold':
      if (d['searching'] == true) {
        return Activity(
          tr(
            'この辺りの話は今ありません。新しい話を探しています。見つかったらガイドを再開します（次の確認まで $t）',
            'No stories here right now. Looking for new ones; the guide resumes when they are found (next check in $t).',
          ),
          busy: true,
        );
      }
      return Activity(
        tr(
          'この辺りでお話しできる話はもうありません。移動すると、その場所の話をお届けします（次の確認まで $t）',
          'No more stories here. Move on and you will hear about the next place (next check in $t).',
        ),
        icon: LvIconKind.map,
      );
    case 'llm_silent':
      return Activity(
        tr('今の状況に合う話がなかったので見送りました。あと $t でもう一度選びます', 'Nothing fitted this moment, so the guide held back. Choosing again in $t.'),
        icon: LvIconKind.frequency,
      );
    case 'quiet_mode':
      return Activity(tr('静かにするモード中です。あと $t で再開します', 'Quiet mode. The guide resumes in $t.'), icon: LvIconKind.quiet);
    case 'hourly_limit':
      final n = d['hourly_limit'];
      return Activity(
        tr('1時間の上限（${n ?? '-'}話）に達しました。あと $t で再開します', 'Hourly limit (${n ?? '-'} stories) reached. Resuming in $t.'),
        icon: LvIconKind.frequency,
      );
    case 'low_accuracy':
      return Activity(tr('位置の精度が低いため待っています。あと $t で確認します', 'Location is too rough; checking again in $t.'), icon: LvIconKind.gpsSearching);
    case 'no_context':
      return Activity(tr('位置情報を待っています…', 'Waiting for location…'), busy: true);
    default:
      return Activity(tr('次の確認まで あと $t', 'Next check in $t'), icon: LvIconKind.frequency);
  }
}

class GuideStoryCard extends StatelessWidget {
  const GuideStoryCard({super.key, required this.guide, required this.session, required this.audio});
  final Map<String, dynamic> guide;
  final GuideSession session;
  final AudioController audio;

  @override
  Widget build(BuildContext context) {
    final g = guide;
    final theme = Theme.of(context);
    final rating = g['rating'] as String?;
    final playingThis = audio.currentHistoryId == g['history_id'] && audio.state != SpeechState.idle;
    final busy = session.feedbackBusy;
    final loc = g['location'] as Map?;
    return ListView(
      padding: EdgeInsets.fromLTRB(16, 16, 16, bottomGap(context)),
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 4,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Chip(
              avatar: LvIcon(categoryIcon(g['category'] as String?), size: 24),
              label: Text(categoryLabel(g['category'] as String?)),
              visualDensity: VisualDensity.compact,
            ),
            if (g['origin'] == 'generated') const GeneratedBadge(),
            if (WaitingBadge.label(g['waiting'] as String?) != null) WaitingBadge(g['waiting'] as String),
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
        if (busy) ...[
          Row(
            children: [
              const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
              const SizedBox(width: 8),
              Expanded(child: Text(_busyLabel(session.feedbackAction), style: theme.textTheme.bodySmall)),
            ],
          ),
          const SizedBox(height: 8),
        ],
        Wrap(
          spacing: 8,
          runSpacing: 4,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            IconButton.filledTonal(
              icon: LvIcon(playingThis ? LvIconKind.stop : LvIconKind.guide),
              tooltip: playingThis ? tr('停止', 'Stop') : tr('読み上げ', 'Play'),
              onPressed: () => playingThis ? audio.stop() : session.playCurrent(),
            ),
            if (audio.state == SpeechState.preparing && audio.currentHistoryId == g['history_id'])
              const Padding(
                padding: EdgeInsets.only(left: 8),
                child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
              ),
            TextButton.icon(
              icon: const LvIcon(LvIconKind.detail, size: 24),
              onPressed: busy
                  ? null
                  : () async {
                      await guarded(context, () => session.feedback(g, 'more_detail'));
                      g['_showDetail'] = true;
                    },
              label: Text(tr('詳しく', 'More')),
            ),
            TextButton.icon(
              icon: const LvIcon(LvIconKind.next, size: 24),
              onPressed: busy
                  ? null
                  : () async {
                      final r = await guarded(context, () => session.feedback(g, 'skip_story'));
                      // No untold story nearby: the server queues the surrounding area for generation
                      if (r != null && r['guide'] == null && context.mounted) {
                        showInfo(
                          context,
                          tr('近くの話はもうありません。周りの話を準備しています', 'No more stories nearby. Preparing stories around you'),
                        );
                      }
                    },
              label: Text(tr('次の話', 'Next')),
            ),
          ],
        ),
        Wrap(
          spacing: 8,
          children: [
            ActionChip(
              avatar: const LvIcon(LvIconKind.related, size: 24),
              label: Text(tr('関連する話を', 'More like this')),
              onPressed: busy ? null : () => _act(context, 'more_related', tr('関連する話を増やします', 'More related stories')),
            ),
            ActionChip(
              avatar: const LvIcon(LvIconKind.enough, size: 24),
              label: Text(tr('この話題はもう十分', 'Enough of this topic')),
              onPressed: busy
                  ? null
                  : () => _act(context, 'enough_topic', tr('しばらくこの話題を控えます', 'This topic will pause for a while')),
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
                avatar: LvIcon(ratingIcon(r[0]), size: 24),
                showCheckmark: false,
                label: Text(tr(r[1], r[2])),
                selected: rating == r[0],
                onSelected: busy
                    ? null
                    : (_) => _act(
                        context,
                        r[0],
                        r[0] == 'wrong_info'
                            ? tr('報告しました。確認まで表示を止めます。', 'Reported; hidden until reviewed.')
                            : null,
                      ),
              ),
          ],
        ),
      ],
    );
  }

  static String _busyLabel(String? action) => switch (action) {
    'skip_story' => tr('次の話を選んでいます…', 'Choosing the next story…'),
    'more_detail' => tr('詳しい内容を読み込んでいます…', 'Loading more detail…'),
    _ => tr('反映しています…', 'Saving…'),
  };

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
      leading: const LvIcon(LvIconKind.sources, size: 26),
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
            ? tr('「$labels」として短時間だけ反映しました。違う場合は×で解除してください。', 'Applied "$labels" briefly. Tap × if that is wrong.', {
                'zh': '已暂时设为「$labels」。如果不是这个意思，请点 × 取消。',
                'ko': '「$labels」(으)로 잠시 반영했습니다. 다르면 ×로 해제하세요.',
                'es': 'Se aplicó «$labels» un momento. Pulse × si no es eso.',
                'fr': '« $labels » est appliqué brièvement. Touchez × si ce n’est pas ça.',
              })
            : r['resumed'] == true && labels.isEmpty
            ? tr('ガイドを再開します', 'Guiding resumed')
            : tr('「$labels」にしました', 'Set: $labels', {
                'zh': '已设为「$labels」',
                'ko': '「$labels」(으)로 설정했습니다',
                'es': 'Listo: $labels',
                'fr': 'Réglé : $labels',
              }),
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
            IconButton(icon: const LvIcon(LvIconKind.send), tooltip: tr('送信', 'Send'), onPressed: _busy ? null : _send),
            IconButton(
              icon: LvIcon(s.isQuiet ? LvIconKind.quiet : LvIconKind.bell),
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
      padding: EdgeInsets.fromLTRB(16, 16, 16, MediaQuery.of(context).viewInsets.bottom + bottomGap(context)),
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
              leading: const LvIcon(LvIconKind.companions),
              title: Text(p['display_name'] as String),
              subtitle: Text(((p['interests'] as List?) ?? []).map((c) => categoryLabel(c as String)).join('・')),
              trailing: IconButton(
                icon: const LvIcon(LvIconKind.close),
                tooltip: tr('同行者を外す', 'Remove companion'),
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
                  avatar: LvIcon(categoryIcon(c), size: 24),
                  showCheckmark: false,
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
