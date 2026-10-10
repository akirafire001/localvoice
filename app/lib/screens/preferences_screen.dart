import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../audio/audio_controller.dart';
import '../util/i18n.dart';
import '../widgets/common.dart';
import '../widgets/visuals.dart';

const _levels = {
  'quiet': ['控えめ', 'Quiet'],
  'normal': ['ふつう', 'Normal'],
  'talkative': ['多め', 'Talkative'],
  'chatty': ['たくさん', 'Chatty'],
};
const _details = {
  'auto': ['自動', 'Auto'],
  'short': ['短く', 'Short'],
  'summary': ['要約', 'Summary'],
  'detailed': ['詳しく', 'Detailed'],
};
// Countries offered for "where you live" (ISO 3166 codes, lower case). Manners common to a whole country are
// told only when the user is in a country other than this one.
const _countries = {
  'jp': ['日本', 'Japan'],
  'kr': ['韓国', 'South Korea'],
  'cn': ['中国', 'China'],
  'tw': ['台湾', 'Taiwan'],
  'hk': ['香港', 'Hong Kong'],
  'th': ['タイ', 'Thailand'],
  'vn': ['ベトナム', 'Vietnam'],
  'sg': ['シンガポール', 'Singapore'],
  'my': ['マレーシア', 'Malaysia'],
  'id': ['インドネシア', 'Indonesia'],
  'ph': ['フィリピン', 'Philippines'],
  'in': ['インド', 'India'],
  'au': ['オーストラリア', 'Australia'],
  'nz': ['ニュージーランド', 'New Zealand'],
  'us': ['アメリカ', 'United States'],
  'ca': ['カナダ', 'Canada'],
  'mx': ['メキシコ', 'Mexico'],
  'br': ['ブラジル', 'Brazil'],
  'gb': ['イギリス', 'United Kingdom'],
  'ie': ['アイルランド', 'Ireland'],
  'fr': ['フランス', 'France'],
  'de': ['ドイツ', 'Germany'],
  'it': ['イタリア', 'Italy'],
  'es': ['スペイン', 'Spain'],
  'pt': ['ポルトガル', 'Portugal'],
  'nl': ['オランダ', 'Netherlands'],
  'be': ['ベルギー', 'Belgium'],
  'ch': ['スイス', 'Switzerland'],
  'at': ['オーストリア', 'Austria'],
  'se': ['スウェーデン', 'Sweden'],
  'no': ['ノルウェー', 'Norway'],
  'dk': ['デンマーク', 'Denmark'],
  'fi': ['フィンランド', 'Finland'],
  'pl': ['ポーランド', 'Poland'],
  'cz': ['チェコ', 'Czechia'],
  'gr': ['ギリシャ', 'Greece'],
  'tr': ['トルコ', 'Türkiye'],
  'ae': ['アラブ首長国連邦', 'United Arab Emirates'],
  'eg': ['エジプト', 'Egypt'],
  'za': ['南アフリカ', 'South Africa'],
};

const _serendipity = {
  'low': ['少なめ', 'Low'],
  'normal': ['ふつう', 'Normal'],
  'high': ['多め', 'High'],
};

class PreferencesScreen extends StatefulWidget {
  const PreferencesScreen({super.key});
  @override
  State<PreferencesScreen> createState() => _PreferencesScreenState();
}

class _PreferencesScreenState extends State<PreferencesScreen> {
  Map<String, dynamic>? _prefs;
  List<Map<String, dynamic>> _interests = [];
  List<Map<String, dynamic>> _voices = [];
  bool _ttsAvailable = false;
  // From the server, so adding a language there needs no app change.
  List<Map<String, dynamic>> _uiLanguages = const [
    {'code': 'ja', 'name': '日本語'},
    {'code': 'en', 'name': 'English'},
  ];
  List<Map<String, dynamic>> _narrationLanguages = const [];
  int _maxNarrationLanguages = 4;

  ApiClient get _api => context.read<ApiClient>();

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    await guarded(context, () async {
      final p = (await _api.get('/api/v1/users/me/preferences')).json;
      final i = (await _api.get('/api/v1/users/me/interests')).json;
      final v = (await _api.get('/api/v1/voices')).json;
      final l = (await _api.get('/api/v1/languages')).json;
      if (!mounted) return;
      setState(() {
        _uiLanguages = (l['ui'] as List).cast<Map<String, dynamic>>();
        _narrationLanguages = (l['narration'] as List).cast<Map<String, dynamic>>();
        _maxNarrationLanguages = (l['max_narration_languages'] as num?)?.toInt() ?? 4;
        _prefs = p;
        _interests = (i['interests'] as List).cast<Map<String, dynamic>>();
        _voices = (v['voices'] as List).cast<Map<String, dynamic>>();
        _ttsAvailable = v['tts_available'] == true;
      });
    });
  }

  Future<void> _patch(Map<String, dynamic> body) async {
    final audio = context.read<AudioController>();
    final r = await guarded(context, () => _api.patch('/api/v1/users/me/preferences', body));
    if (r == null || !mounted) return;
    setState(() => _prefs = r.json);
    audio.applyPrefs(r.json);
    lang.set(r.json['language'] as String? ?? 'ja');
  }

  Future<void> _setInterest(String cat, double? score) async {
    final r = await guarded(
      context,
      () => _api.patch('/api/v1/users/me/interests', {
        'interests': [
          {'category': cat, 'explicit_score': score},
        ],
      }),
    );
    if (r != null && mounted) {
      setState(() => _interests = (r.json['interests'] as List).cast<Map<String, dynamic>>());
    }
  }

  Widget _choice(
    String title,
    Map<String, List<String>> opts,
    String? cur,
    void Function(String) on, {
    LvIconKind? icon,
  }) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (icon != null) LvSectionTitle(title, icon) else Text(title, style: Theme.of(context).textTheme.titleSmall),
        Wrap(
          spacing: 8,
          children: [
            for (final e in opts.entries)
              ChoiceChip(label: Text(tr(e.value[0], e.value[1])), selected: cur == e.key, onSelected: (_) => on(e.key)),
          ],
        ),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) {
    final p = _prefs;
    if (p == null) {
      return Scaffold(
        appBar: LvAppBar(title: Text(tr('設定', 'Settings'))),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    final voice = (p['voice'] as Map).cast<String, dynamic>();
    final language = p['language'] as String? ?? 'ja';
    final narration = ((p['narration_languages'] ?? [language]) as List).cast<String>();
    return Scaffold(
      appBar: LvAppBar(title: Text(tr('設定', 'Settings'))),
      body: ListView(
        padding: EdgeInsets.fromLTRB(16, 16, 16, bottomGap(context)),
        children: [
          _choice(
            tr('表示言語', 'App language'),
            {
              for (final l in _uiLanguages) l['code'] as String: [l['name'] as String, l['name'] as String],
            },
            language,
            (v) => _patch({'language': v}),
            icon: LvIconKind.language,
          ),
          _NarrationLanguages(
            selected: narration,
            catalog: _narrationLanguages,
            max: _maxNarrationLanguages,
            voices: _voices,
            chosenVoices: ((voice['voices'] ?? {}) as Map).cast<String, dynamic>(),
            ttsAvailable: _ttsAvailable,
            onChanged: (langs) {
              setState(() => p['narration_languages'] = langs); // a reorder shows at once
              _patch({'narration_languages': langs});
            },
            onVoice: (lang, id) => _patch({
              'voice': {
                'voices': {lang: id},
              },
            }),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Row(
              children: [
                const LvIcon(LvIconKind.language),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(tr('住んでいる国', 'Country you live in'), style: Theme.of(context).textTheme.titleSmall),
                ),
                DropdownButton<String>(
                  value: _countries.containsKey(p['home_country']) ? p['home_country'] as String : null,
                  hint: Text((p['home_country'] as String? ?? '').toUpperCase()),
                  items: [
                    for (final e in _countries.entries)
                      DropdownMenuItem(value: e.key, child: Text(tr(e.value[0], e.value[1]))),
                  ],
                  onChanged: (v) {
                    if (v != null) _patch({'home_country': v});
                  },
                ),
              ],
            ),
          ),
          Text(
            tr('ほかの国にいるときは、その国のマナーや習慣の話もします。', 'Abroad, the guide also tells you about local manners and customs.'),
            style: Theme.of(context).textTheme.bodySmall,
          ),
          _choice(
            tr('話しかける頻度', 'How often to talk'),
            _levels,
            p['notification_level'] as String?,
            (v) => _patch({'notification_level': v}),
            icon: LvIconKind.frequency,
          ),
          _choice(
            tr('説明の長さ', 'Detail'),
            _details,
            p['detail_mode'] as String?,
            (v) => _patch({'detail_mode': v}),
            icon: LvIconKind.explanation,
          ),
          _choice(
            tr('意外な話題', 'Surprise topics'),
            _serendipity,
            p['serendipity'] as String?,
            (v) => _patch({'serendipity': v}),
            icon: LvIconKind.discovery,
          ),
          const Divider(height: 32),
          LvSectionTitle(tr('興味', 'Interests'), LvIconKind.nature),
          for (final i in _interests)
            Row(
              children: [
                SizedBox(
                  width: 132,
                  child: Row(
                    children: [
                      LvIcon(categoryIcon(i['category'] as String?), size: 28),
                      const SizedBox(width: 8),
                      Expanded(child: Text(categoryLabel(i['category'] as String?))),
                    ],
                  ),
                ),
                Expanded(
                  child: Slider(
                    value: ((i['explicit_score'] ?? 0.5) as num).toDouble(),
                    divisions: 4,
                    label: _interestLabel(((i['explicit_score'] ?? 0.5) as num).toDouble()),
                    onChanged: (v) => setState(() => i['explicit_score'] = v),
                    onChangeEnd: (v) => _setInterest(i['category'] as String, v),
                  ),
                ),
              ],
            ),
          const Divider(height: 32),
          LvSectionTitle(tr('音声', 'Voice'), LvIconKind.voice),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            secondary: const LvIcon(LvIconKind.guide),
            title: Text(tr('新しい話を自動で読み上げる', 'Read new stories aloud automatically')),
            subtitle: Text(tr('イヤホン利用時などに。初期設定はオフです。', 'Off by default. Useful with earphones.')),
            value: voice['enabled'] == true,
            onChanged: (v) => _patch({
              'voice': {'enabled': v},
            }),
          ),
          if (!_ttsAvailable)
            Text(
              tr(
                'サーバー音声は現在使えません。端末の読み上げを許可すると代わりに使います。',
                'Server voices are unavailable now. Allow device speech to use it instead.',
              ),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          Row(
            children: [
              const LvIcon(LvIconKind.speed),
              const SizedBox(width: 8),
              Text(tr('速さ', 'Speed')),
              Expanded(
                child: Slider(
                  min: 0.75,
                  max: 1.5,
                  divisions: 6,
                  value: ((voice['playback_rate'] ?? 1.0) as num).toDouble().clamp(0.75, 1.5),
                  label: '${((voice['playback_rate'] ?? 1.0) as num).toStringAsFixed(2)}x',
                  onChanged: (v) => setState(() => voice['playback_rate'] = v),
                  onChangeEnd: (v) => _patch({
                    'voice': {'playback_rate': v},
                  }),
                ),
              ),
            ],
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            secondary: const LvIcon(LvIconKind.offline),
            title: Text(tr('サーバー音声が使えないとき端末で読み上げる', 'Use device speech when server audio is unavailable')),
            value: voice['allow_device_tts_fallback'] == true,
            onChanged: (v) => _patch({
              'voice': {'allow_device_tts_fallback': v},
            }),
          ),
        ],
      ),
    );
  }

  static String _interestLabel(double v) {
    if (v < 0.125) return tr('興味なし', 'None');
    if (v < 0.375) return tr('少し', 'A little');
    if (v < 0.625) return tr('ふつう', 'Normal');
    if (v < 0.875) return tr('好き', 'Like');
    return tr('大好き', 'Love');
  }
}

/// Languages the guide speaks, in order: each story is told in the first, then the next, and so on.
/// The list comes from the server, so it grows without app changes; adding is a searchable sheet.
class _NarrationLanguages extends StatelessWidget {
  const _NarrationLanguages({
    required this.selected,
    required this.catalog,
    required this.max,
    required this.voices,
    required this.chosenVoices,
    required this.ttsAvailable,
    required this.onChanged,
    required this.onVoice,
  });

  final List<String> selected;
  final List<Map<String, dynamic>> catalog;
  final int max;
  final List<Map<String, dynamic>> voices;
  final Map<String, dynamic> chosenVoices;
  final bool ttsAvailable;
  final void Function(List<String>) onChanged;
  final void Function(String lang, String voiceId) onVoice;

  Map<String, dynamic>? _entry(String code) {
    for (final l in catalog) {
      if (l['code'] == code) return l;
    }
    return null;
  }

  /// Native name, with the name in the app language when it differs ("한국어 · 韓国語").
  String _label(String code) {
    final e = _entry(code);
    if (e == null) return code;
    final native = e['name'] as String;
    final local = tr(e['name_ja'] as String? ?? native, e['name_en'] as String? ?? native);
    return local == native ? native : '$native · $local';
  }

  Future<void> _add(BuildContext context) async {
    final rest = catalog.where((l) => !selected.contains(l['code'])).toList();
    final code = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _LanguagePicker(options: rest, label: _label),
    );
    if (code != null) onChanged([...selected, code]);
  }

  @override
  Widget build(BuildContext context) {
    final audio = context.read<AudioController>();
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LvSectionTitle(tr('解説の言語', 'Narration languages'), LvIconKind.voice),
          Text(
            tr(
              '選んだ言語で、上から順に続けて話します。ドラッグで順番を変えられます。',
              'Each story is told in every language below, top to bottom. Drag to reorder.',
            ),
            style: Theme.of(context).textTheme.bodySmall,
          ),
          ReorderableListView(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            buildDefaultDragHandles: false,
            onReorder: (from, to) {
              final next = [...selected];
              final moved = next.removeAt(from);
              next.insert(to > from ? to - 1 : to, moved);
              onChanged(next);
            },
            children: [
              for (var i = 0; i < selected.length; i++) _languageRow(context, audio, i, selected[i]),
            ],
          ),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              icon: const Icon(Icons.add),
              label: Text(
                selected.length >= max
                    ? tr('言語は$max個まで選べます', 'Up to $max languages')
                    : tr('言語を追加', 'Add a language'),
              ),
              onPressed: selected.length >= max || selected.length >= catalog.length ? null : () => _add(context),
            ),
          ),
        ],
      ),
    );
  }

  Widget _languageRow(BuildContext context, AudioController audio, int i, String code) {
    final langVoices = voices.where((v) => v['language'] == code).toList();
    final chosen = chosenVoices[code] as String?;
    final voiceId = langVoices.any((v) => v['voice_profile_id'] == chosen)
        ? chosen
        : (langVoices.isEmpty ? null : langVoices.first['voice_profile_id'] as String);
    return Card(
      key: ValueKey(code),
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 4, 4, 4),
        child: Row(
          children: [
            CircleAvatar(radius: 14, child: Text('${i + 1}')),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(_label(code), style: Theme.of(context).textTheme.titleSmall),
                  if (langVoices.isNotEmpty)
                    Row(
                      children: [
                        Flexible(
                          child: DropdownButton<String>(
                            isExpanded: true,
                            isDense: true,
                            underline: const SizedBox.shrink(),
                            value: voiceId,
                            items: [
                              for (final v in langVoices)
                                DropdownMenuItem(
                                  value: v['voice_profile_id'] as String,
                                  child: Text(
                                    v['display_name'] as String? ?? v['voice_profile_id'] as String,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                            ],
                            onChanged: (id) {
                              if (id != null) onVoice(code, id);
                            },
                          ),
                        ),
                        IconButton(
                          icon: const LvIcon(LvIconKind.play),
                          tooltip: tr('試聴', 'Sample'),
                          onPressed: ttsAvailable && voiceId != null
                              ? () async {
                                  final err = await audio.playSample(voiceId);
                                  if (err != null && context.mounted) {
                                    showInfo(context, tr('試聴できませんでした', 'Sample unavailable'));
                                  }
                                }
                              : null,
                        ),
                      ],
                    ),
                ],
              ),
            ),
            IconButton(
              icon: const LvIcon(LvIconKind.close),
              tooltip: tr('外す', 'Remove'),
              onPressed: selected.length > 1 ? () => onChanged([...selected]..remove(code)) : null,
            ),
            ReorderableDragStartListener(
              index: i,
              child: const Padding(padding: EdgeInsets.all(8), child: Icon(Icons.drag_handle)),
            ),
          ],
        ),
      ),
    );
  }
}

class _LanguagePicker extends StatefulWidget {
  const _LanguagePicker({required this.options, required this.label});
  final List<Map<String, dynamic>> options;
  final String Function(String code) label;

  @override
  State<_LanguagePicker> createState() => _LanguagePickerState();
}

class _LanguagePickerState extends State<_LanguagePicker> {
  String _query = '';

  bool _matches(Map<String, dynamic> l) {
    final q = _query.trim().toLowerCase();
    if (q.isEmpty) return true;
    return [l['code'], l['name'], l['name_ja'], l['name_en']].any((v) => '${v ?? ''}'.toLowerCase().contains(q));
  }

  @override
  Widget build(BuildContext context) {
    final shown = widget.options.where(_matches).toList();
    return SafeArea(
      child: SizedBox(
        height: MediaQuery.of(context).size.height * 0.6,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: TextField(
                autofocus: false,
                decoration: InputDecoration(
                  prefixIcon: const Icon(Icons.search),
                  hintText: tr('言語を検索', 'Search languages'),
                ),
                onChanged: (v) => setState(() => _query = v),
              ),
            ),
            Expanded(
              child: ListView(
                children: [
                  for (final l in shown)
                    ListTile(
                      title: Text(widget.label(l['code'] as String)),
                      onTap: () => Navigator.of(context).pop(l['code'] as String),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
