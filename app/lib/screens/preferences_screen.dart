import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../audio/audio_controller.dart';
import '../util/i18n.dart';
import '../widgets/common.dart';

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
      if (!mounted) return;
      setState(() {
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
    if (r != null && mounted) setState(() => _interests = (r.json['interests'] as List).cast<Map<String, dynamic>>());
  }

  Widget _choice(String title, Map<String, List<String>> opts, String? cur, void Function(String) on) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: Theme.of(context).textTheme.titleSmall),
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
        appBar: AppBar(title: Text(tr('設定', 'Settings'))),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    final voice = (p['voice'] as Map).cast<String, dynamic>();
    final language = p['language'] as String? ?? 'ja';
    final selectedVoice = ((voice['voices'] ?? {}) as Map)[language] as String?;
    final langVoices = _voices.where((v) => v['language'] == language).toList();
    final audio = context.read<AudioController>();
    return Scaffold(
      appBar: AppBar(title: Text(tr('設定', 'Settings'))),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _choice(
            tr('言語', 'Language'),
            const {
              'ja': ['日本語', '日本語'],
              'en': ['English', 'English'],
            },
            language,
            (v) => _patch({'language': v}),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Row(
              children: [
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
          ),
          _choice(tr('説明の長さ', 'Detail'), _details, p['detail_mode'] as String?, (v) => _patch({'detail_mode': v})),
          _choice(
            tr('意外な話題', 'Surprise topics'),
            _serendipity,
            p['serendipity'] as String?,
            (v) => _patch({'serendipity': v}),
          ),
          const Divider(height: 32),
          Text(tr('興味', 'Interests'), style: Theme.of(context).textTheme.titleMedium),
          for (final i in _interests)
            Row(
              children: [
                SizedBox(width: 110, child: Text(categoryLabel(i['category'] as String?))),
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
          Text(tr('音声', 'Voice'), style: Theme.of(context).textTheme.titleMedium),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
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
          RadioGroup<String>(
            groupValue: selectedVoice ?? (langVoices.isEmpty ? null : langVoices.first['voice_profile_id'] as String),
            onChanged: (id) => _patch({
              'voice': {
                'voices': {language: id},
              },
            }),
            child: Column(
              children: [
                for (final v in langVoices)
                  RadioListTile<String>(
                    contentPadding: EdgeInsets.zero,
                    value: v['voice_profile_id'] as String,
                    title: Text(v['display_name'] as String? ?? v['voice_profile_id'] as String),
                    secondary: IconButton(
                      icon: const Icon(Icons.play_circle_outline),
                      tooltip: tr('試聴', 'Sample'),
                      onPressed: _ttsAvailable
                          ? () async {
                              final err = await audio.playSample(v['voice_profile_id'] as String);
                              if (err != null && context.mounted) {
                                showInfo(context, tr('試聴できませんでした', 'Sample unavailable'));
                              }
                            }
                          : null,
                    ),
                  ),
              ],
            ),
          ),
          Row(
            children: [
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
