import 'package:flutter/material.dart';

/// S1 travel-journal artwork, shared by every screen.
enum LvIconKind {
  home('home'),
  guide('guide'),
  map('map'),
  history('history'),
  settings('settings'),
  account('account'),
  play('play'),
  stop('stop'),
  next('next'),
  detail('detail'),
  related('related'),
  enough('enough'),
  historyTopic('history-topic'),
  architecture('architecture'),
  nature('nature'),
  food('food'),
  culture('culture'),
  everydayLife('everyday-life'),
  industry('industry'),
  seasonal('seasonal'),
  practical('practical'),
  quiet('quiet'),
  companions('companions'),
  send('send'),
  autoTransport('auto-transport'),
  walk('walk'),
  bicycle('bicycle'),
  car('car'),
  train('train'),
  shinkansen('shinkansen'),
  ship('ship'),
  gps('gps'),
  offline('offline'),
  travel('travel'),
  business('business'),
  commute('commute'),
  interesting('interesting'),
  knewIt('knew-it'),
  notInterested('not-interested'),
  wrongInfo('wrong-info'),
  password('password'),
  other('other'),
  language('language'),
  voice('voice'),
  speed('speed'),
  frequency('frequency'),
  explanation('explanation'),
  discovery('discovery'),
  gpsSearching('gps-searching'),
  gpsOff('gps-off'),
  gpsDenied('gps-denied'),
  pause('pause'),
  bell('bell'),
  check('check'),
  close('close'),
  back('back'),
  forward('forward'),
  expand('expand'),
  visible('visible'),
  hidden('hidden'),
  email('email'),
  edit('edit'),
  logout('logout'),
  delete('delete'),
  info('info'),
  sources('sources');

  const LvIconKind(this.file);
  final String file;
  String get asset => 'assets/s1/icons/$file.png';
}

enum LvArtwork {
  loginLandscape('login-landscape'),
  homeDiscovery('home-discovery'),
  homeDiscoveryBanner('home-discovery-banner'),
  waitingForStory('waiting-for-story'),
  emptyHistory('empty-history'),
  offlineLocalSave('offline-local-save'),
  emailVerification('email-verification'),
  mailPending('mail-pending'),
  locationPermission('location-permission'),
  passwordReset('password-reset'),
  emptyMap('empty-map');

  const LvArtwork(this.file);
  final String file;
  String get asset => 'assets/s1/illustrations/$file.png';
}

LvIconKind categoryIcon(String? category) => switch (category) {
  'history' => LvIconKind.historyTopic,
  'architecture' => LvIconKind.architecture,
  'nature' => LvIconKind.nature,
  'food' => LvIconKind.food,
  'culture' => LvIconKind.culture,
  'everyday_life' => LvIconKind.everydayLife,
  'industry' => LvIconKind.industry,
  'seasonal' => LvIconKind.seasonal,
  'practical' => LvIconKind.practical,
  _ => LvIconKind.other,
};

LvIconKind purposeIcon(String? purpose) => switch (purpose) {
  'travel' => LvIconKind.travel,
  'walk' => LvIconKind.walk,
  'business' => LvIconKind.business,
  'commute' => LvIconKind.commute,
  _ => LvIconKind.other,
};

LvIconKind transportIcon(String? transport) => switch (transport) {
  'auto' => LvIconKind.autoTransport,
  'walk' => LvIconKind.walk,
  'bicycle' => LvIconKind.bicycle,
  'car' => LvIconKind.car,
  'train' => LvIconKind.train,
  'shinkansen' => LvIconKind.shinkansen,
  'ship' => LvIconKind.ship,
  _ => LvIconKind.other,
};

LvIconKind ratingIcon(String rating) => switch (rating) {
  'interesting' => LvIconKind.interesting,
  'knew_it' => LvIconKind.knewIt,
  'not_interesting' => LvIconKind.notInterested,
  'wrong_info' => LvIconKind.wrongInfo,
  _ => LvIconKind.other,
};

class LvIcon extends StatelessWidget {
  const LvIcon(this.kind, {super.key, this.size = 28, this.color});
  final LvIconKind kind;
  final double size;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    Widget image = Image.asset(
      kind.asset,
      width: size,
      height: size,
      cacheWidth: (size * MediaQuery.devicePixelRatioOf(context)).ceil().clamp(96, 256).toInt(),
      filterQuality: FilterQuality.medium,
      excludeFromSemantics: true,
    );
    if (color != null) {
      image = ColorFiltered(colorFilter: ColorFilter.mode(color!, BlendMode.srcIn), child: image);
    }
    final theme = IconTheme.of(context);
    return ExcludeSemantics(
      child: Opacity(opacity: (theme.opacity ?? 1) * (theme.color?.a ?? 1), child: image),
    );
  }
}

class LvIllustration extends StatelessWidget {
  const LvIllustration(this.artwork, {super.key, this.height = 190});
  final LvArtwork artwork;
  final double height;

  @override
  Widget build(BuildContext context) => Image.asset(
    artwork.asset,
    height: height,
    fit: BoxFit.contain,
    filterQuality: FilterQuality.medium,
    excludeFromSemantics: true,
  );
}

class LvBrandTitle extends StatelessWidget {
  const LvBrandTitle({super.key, this.large = false});
  final bool large;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      ClipRRect(
        borderRadius: BorderRadius.circular(large ? 14 : 10),
        child: Image.asset(
          'assets/branding/app-icon.png',
          width: large ? 60 : 38,
          height: large ? 60 : 38,
          excludeFromSemantics: true,
        ),
      ),
      const SizedBox(width: 10),
      Flexible(
        child: Text(
          'LocalVoice',
          style: TextStyle(
            fontSize: large ? 28 : 21,
            fontWeight: FontWeight.w700,
            color: Theme.of(context).colorScheme.primary,
          ),
        ),
      ),
    ],
  );
}

/// Preserves the usual back navigation, with the shared S1 back arrow.
class LvAppBar extends StatelessWidget implements PreferredSizeWidget {
  const LvAppBar({super.key, required this.title, this.actions, this.bottom});
  final Widget title;
  final List<Widget>? actions;
  final PreferredSizeWidget? bottom;

  @override
  Size get preferredSize => Size.fromHeight(kToolbarHeight + (bottom?.preferredSize.height ?? 0));

  @override
  Widget build(BuildContext context) => AppBar(
    title: title,
    actions: actions,
    bottom: bottom,
    leading: Navigator.of(context).canPop()
        ? IconButton(
            icon: const LvIcon(LvIconKind.back),
            tooltip: MaterialLocalizations.of(context).backButtonTooltip,
            onPressed: () => Navigator.of(context).maybePop(),
          )
        : null,
  );
}

class LvSectionTitle extends StatelessWidget {
  const LvSectionTitle(this.title, this.icon, {super.key});
  final String title;
  final LvIconKind icon;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 10, top: 6),
    child: Row(
      children: [
        LvIcon(icon, size: 30),
        const SizedBox(width: 10),
        Expanded(child: Text(title, style: Theme.of(context).textTheme.titleMedium)),
      ],
    ),
  );
}

/// Scrolls in the guide's short pane or under a keyboard, rather than overflowing.
class LvEmptyState extends StatelessWidget {
  const LvEmptyState({super.key, required this.artwork, required this.message, this.compact = false});
  final LvArtwork artwork;
  final String message;
  final bool compact;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final preferred = compact ? 125.0 : 190.0;
      final height = constraints.hasBoundedHeight ? (constraints.maxHeight * 0.4).clamp(48.0, preferred) : preferred;
      return Center(
        child: SingleChildScrollView(
          padding: EdgeInsets.all(compact ? 16 : 24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 380),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                LvIllustration(artwork, height: height),
                const SizedBox(height: 16),
                Text(message, textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodyMedium),
              ],
            ),
          ),
        ),
      );
    },
  );
}
