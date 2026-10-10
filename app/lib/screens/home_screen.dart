import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../auth/auth_service.dart';
import '../guide/guide_session.dart';
import '../util/i18n.dart';
import '../widgets/common.dart';
import '../widgets/visuals.dart';
import 'account_screen.dart';
import 'guide_screen.dart';
import 'history_screen.dart';
import 'map_screen.dart';
import 'preferences_screen.dart';

const purposeLabels = {
  'travel': ['旅行', 'Travel'],
  'walk': ['散歩', 'Walk'],
  'business': ['出張', 'Business trip'],
  'commute': ['通勤・通学', 'Commute'],
  'other': ['その他', 'Other'],
};

const transportLabels = {
  'auto': ['自動判定', 'Auto'],
  'walk': ['徒歩', 'Walk'],
  'bicycle': ['自転車', 'Bicycle'],
  'car': ['車', 'Car'],
  'train': ['電車', 'Train'],
  'shinkansen': ['新幹線', 'Shinkansen'],
  'ship': ['船', 'Ship'],
  'other': ['その他', 'Other'],
};

String labelOf(Map<String, List<String>> m, String? k) {
  final l = m[k];
  return l == null ? (k ?? '') : tr(l[0], l[1]);
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  String _purpose = 'travel';
  String _transport = 'auto';
  bool _busy = false;

  Future<void> _start() async {
    final s = context.read<GuideSession>();
    setState(() => _busy = true);
    final ok = await guarded(context, () async {
      await s.notifier.requestPermission();
      await s.startTrip({'purpose': _purpose, 'manual_transport_mode': _transport});
      return true;
    });
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok == true) {
      Navigator.push(context, MaterialPageRoute(builder: (_) => const GuideScreen()));
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = context.watch<GuideSession>();
    final user = context.watch<AuthService>().user;
    return Scaffold(
      appBar: LvAppBar(
        title: const LvBrandTitle(),
        actions: [
          IconButton(
            icon: const LvIcon(LvIconKind.settings),
            tooltip: tr('設定', 'Settings'),
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const PreferencesScreen())),
          ),
          IconButton(
            icon: const LvIcon(LvIconKind.account),
            tooltip: tr('アカウント', 'Account'),
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const AccountScreen())),
          ),
        ],
      ),
      body: ListView(
        padding: EdgeInsets.fromLTRB(20, 20, 20, bottomGap(context)),
        children: [
          Text(
            tr('こんにちは、${user?.displayName ?? ''}さん', 'Hello, ${user?.displayName ?? ''}', {
              'zh': '你好，${user?.displayName ?? ''}',
              'ko': '안녕하세요, ${user?.displayName ?? ''}님',
              'es': 'Hola, ${user?.displayName ?? ''}',
              'fr': 'Bonjour ${user?.displayName ?? ''}',
            }),
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 20),
          if (s.active)
            Card(
              child: ListTile(
                leading: const LvIcon(LvIconKind.guide, size: 40),
                title: Text(tr('ガイド中の旅行があります', 'A trip is in progress')),
                subtitle: Text(labelOf(purposeLabels, s.trip?['purpose'] as String?)),
                trailing: const LvIcon(LvIconKind.forward),
                onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const GuideScreen())),
              ),
            )
          else ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(16),
              child: AspectRatio(
                aspectRatio: 2,
                child: Image.asset(
                  LvArtwork.homeDiscoveryBanner.asset,
                  width: double.infinity,
                  fit: BoxFit.cover,
                  filterQuality: FilterQuality.medium,
                  excludeFromSemantics: true,
                ),
              ),
            ),
            const SizedBox(height: 16),
            Text(tr('目的', 'Purpose'), style: Theme.of(context).textTheme.titleSmall),
            Wrap(
              spacing: 8,
              children: [
                for (final k in purposeLabels.keys)
                  ChoiceChip(
                    avatar: LvIcon(purposeIcon(k), size: 24),
                    showCheckmark: false,
                    label: Text(labelOf(purposeLabels, k)),
                    selected: _purpose == k,
                    onSelected: (_) => setState(() => _purpose = k),
                  ),
              ],
            ),
            const SizedBox(height: 16),
            Text(tr('移動手段', 'Transport'), style: Theme.of(context).textTheme.titleSmall),
            Wrap(
              spacing: 8,
              children: [
                for (final k in transportLabels.keys)
                  ChoiceChip(
                    avatar: LvIcon(transportIcon(k), size: 24),
                    showCheckmark: false,
                    label: Text(labelOf(transportLabels, k)),
                    selected: _transport == k,
                    onSelected: (_) => setState(() => _transport = k),
                  ),
              ],
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              icon: const LvIcon(LvIconKind.play, color: Colors.white),
              onPressed: _busy ? null : _start,
              label: Text(tr('ガイドを開始', 'Start guide')),
            ),
            const SizedBox(height: 8),
            Text(
              tr('ガイド中だけ位置情報を使います。終了するといつでも止まります。', 'Location is used only while guiding and stops when you finish.'),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
          const Divider(height: 40),
          ListTile(
            leading: const LvIcon(LvIconKind.history, size: 32),
            title: Text(tr('これまでの旅行', 'Past trips')),
            onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const TripListScreen())),
          ),
          ListTile(
            leading: const LvIcon(LvIconKind.map, size: 32),
            title: Text(tr('地図で振り返る', 'Review on the map')),
            onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const MapScreen())),
          ),
        ],
      ),
    );
  }
}
