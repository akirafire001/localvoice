import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../auth/auth_service.dart';
import '../util/i18n.dart';
import 'visuals.dart';

/// Bottom padding for a screen's scrolling body, so the last controls stay clear of the
/// system navigation bar (Android gesture/button bar, iOS home indicator) with some margin.
double bottomGap(BuildContext context) => MediaQuery.paddingOf(context).bottom + 32;

String errorText(Object e) {
  if (e is AuthCancelled) return '';
  if (e is ApiException) {
    switch (e.code) {
      case 'network':
      case 'timeout':
        return tr('通信できません。電波の良い場所で再度お試しください。', 'Cannot reach the server. Please try again.');
      case 'invalid_credentials':
        return tr('IDまたはパスワードが違います。', 'Wrong ID or password.');
      case 'rate_limited':
        return tr('試行回数が多すぎます。しばらく待ってください。', 'Too many attempts. Please wait a while.');
      case 'login_id_taken':
        return tr('このIDは使われています。', 'This ID is already taken.');
      case 'weak_password':
        return tr('パスワードが弱すぎます（15文字以上、よくある語句は不可）。', 'Password too weak (15+ chars, not a common phrase).');
      case 'reauthentication_required':
        return tr('もう一度本人確認してください。', 'Please confirm it is you again.');
      case 'last_login_method':
        return tr('最後のログイン方法は解除できません。', 'You cannot remove your last sign-in method.');
      case 'identity_in_use':
        return tr('このアカウントは別のLocalVoiceユーザーに連携済みです。', 'That account is linked to another LocalVoice user.');
      case 'provider_already_linked':
        return tr('すでに連携されています。', 'Already linked.');
      case 'reauthentication_failed':
        return tr('本人確認に失敗しました。', 'Could not confirm your identity.');
      case 'provider_unavailable':
        return tr('ログイン先のサービスに接続できません。', 'The sign-in provider is unavailable.');
    }
    return e.message.isNotEmpty ? e.message : e.code;
  }
  return e.toString();
}

void showError(BuildContext context, Object e) {
  final t = errorText(e);
  if (t.isEmpty || !context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t)));
}

void showInfo(BuildContext context, String text) {
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
}

/// Runs [fn] while showing a progress state on the caller; reports errors as a snackbar.
Future<T?> guarded<T>(BuildContext context, Future<T> Function() fn) async {
  try {
    return await fn();
  } catch (e) {
    if (context.mounted) showError(context, e);
    return null;
  }
}

const categoryLabels = {
  'history': ['歴史', 'History'],
  'architecture': ['建築', 'Architecture'],
  'nature': ['自然', 'Nature'],
  'food': ['食', 'Food'],
  'culture': ['文化', 'Culture'],
  'everyday_life': ['暮らし', 'Everyday life'],
  'industry': ['産業', 'Industry'],
  'seasonal': ['季節', 'Seasonal'],
  'practical': ['実用', 'Practical'],
};

String categoryLabel(String? c) {
  final l = categoryLabels[c];
  return l == null ? (c ?? '') : tr(l[0], l[1]);
}

/// Shown when content is runtime-generated (realtime-llm-design: make generated content visible).
class GeneratedBadge extends StatelessWidget {
  const GeneratedBadge({super.key});
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.tertiaryContainer,
      borderRadius: BorderRadius.circular(4),
    ),
    child: Text(tr('自動生成', 'Auto-generated'), style: Theme.of(context).textTheme.labelSmall),
  );
}

/// Marks a story told while the stories of this place were not ready yet (server guide.waiting).
class WaitingBadge extends StatelessWidget {
  const WaitingBadge(this.kind, {super.key});
  final String kind;

  static String? label(String? kind) => switch (kind) {
    'tutorial' => tr('使い方', 'How to use'),
    'nearby' => tr('少し離れた場所の話', 'From a little further away'),
    'global' => tr('どこでも通じる話', 'Holds anywhere'),
    _ => null,
  };

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.secondaryContainer,
      borderRadius: BorderRadius.circular(4),
    ),
    child: Text(label(kind) ?? kind, style: Theme.of(context).textTheme.labelSmall),
  );
}

class PasswordField extends StatefulWidget {
  const PasswordField({super.key, required this.controller, this.label, this.autofill});
  final TextEditingController controller;
  final String? label;
  final String? autofill;
  @override
  State<PasswordField> createState() => _PasswordFieldState();
}

class _PasswordFieldState extends State<PasswordField> {
  bool _hidden = true;
  @override
  Widget build(BuildContext context) => TextField(
    controller: widget.controller,
    obscureText: _hidden,
    autofillHints: widget.autofill == null ? null : [widget.autofill!],
    decoration: InputDecoration(
      labelText: widget.label ?? tr('パスワード', 'Password'),
      prefixIcon: const Padding(padding: EdgeInsets.all(12), child: LvIcon(LvIconKind.password)),
      suffixIcon: IconButton(
        icon: LvIcon(_hidden ? LvIconKind.visible : LvIconKind.hidden),
        tooltip: _hidden ? tr('パスワードを表示', 'Show password') : tr('パスワードを隠す', 'Hide password'),
        onPressed: () => setState(() => _hidden = !_hidden),
      ),
    ),
  );
}
