import 'dart:io' show Platform;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../auth/auth_service.dart';
import '../util/i18n.dart';
import '../widgets/common.dart';
import '../widgets/visuals.dart';

class AccountScreen extends StatefulWidget {
  const AccountScreen({super.key});
  @override
  State<AccountScreen> createState() => _AccountScreenState();
}

class _AccountScreenState extends State<AccountScreen> {
  /// Sensitive operations need a recent reauthentication (auth-design §6). Ask once, then retry.
  Future<T?> _withReauth<T>(Future<T> Function() op) async {
    try {
      return await op();
    } on ApiException catch (e) {
      if (e.code != 'reauthentication_required') {
        if (mounted) showError(context, e);
        return null;
      }
    } catch (e) {
      if (mounted) showError(context, e);
      return null;
    }
    if (!mounted) return null;
    final ok = await _reauth();
    if (!ok || !mounted) return null;
    return guarded(context, op);
  }

  Future<bool> _reauth() async {
    final auth = context.read<AuthService>();
    final methods = auth.user?.loginMethods ?? [];
    final choice = await showModalBottomSheet<String>(
      context: context,
      builder: (c) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(title: Text(tr('本人確認の方法', 'Confirm it is you'), style: Theme.of(context).textTheme.titleMedium)),
            if (methods.contains('password'))
              ListTile(
                leading: const LvIcon(LvIconKind.password),
                title: Text(tr('パスワード', 'Password')),
                onTap: () => Navigator.pop(c, 'password'),
              ),
            if (methods.contains('google'))
              ListTile(
                leading: const Icon(Icons.g_mobiledata),
                title: const Text('Google'),
                onTap: () => Navigator.pop(c, 'google'),
              ),
            if (methods.contains('apple'))
              ListTile(
                leading: const Icon(Icons.apple),
                title: const Text('Apple'),
                onTap: () => Navigator.pop(c, 'apple'),
              ),
          ],
        ),
      ),
    );
    if (choice == null || !mounted) return false;
    if (choice == 'password') {
      final pw = TextEditingController();
      final ok = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
          title: Text(tr('パスワードを入力', 'Enter your password')),
          content: PasswordField(controller: pw),
          actions: [
            TextButton(onPressed: () => Navigator.pop(c, false), child: Text(tr('キャンセル', 'Cancel'))),
            FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('OK')),
          ],
        ),
      );
      if (ok != true || !mounted) return false;
      return await guarded(context, () async {
            await auth.reauthWithPassword(pw.text);
            return true;
          }) ==
          true;
    }
    return await guarded(context, () async {
          if (choice == 'google') await auth.reauthWithGoogle();
          if (choice == 'apple') await auth.reauthWithApple();
          return true;
        }) ==
        true;
  }

  Future<void> _setPassword(UserInfo u) async {
    final id = TextEditingController(text: u.loginId ?? '');
    final pw = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(u.loginId == null ? tr('ID・パスワードを追加', 'Add ID and password') : tr('パスワードを変更', 'Change password')),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (u.loginId == null)
              TextField(
                controller: id,
                decoration: InputDecoration(labelText: tr('ログインID', 'Login ID')),
              ),
            PasswordField(
              controller: pw,
              label: tr('新しいパスワード（15文字以上）', 'New password (15+ chars)'),
              autofill: AutofillHints.newPassword,
            ),
            const SizedBox(height: 8),
            Text(
              tr('変更すると他の端末はログアウトされます。', 'Other devices will be signed out.'),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: Text(tr('キャンセル', 'Cancel'))),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('OK')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    final auth = context.read<AuthService>();
    final done = await _withReauth(() async {
      await auth.setPassword(u.loginId == null ? id.text.trim() : null, pw.text);
      return true;
    });
    if (done == true && mounted) showInfo(context, tr('保存しました', 'Saved'));
  }

  Future<void> _recoveryEmail(UserInfo u) async {
    final c = TextEditingController(text: u.recoveryEmail ?? '');
    final ok = await showDialog<bool>(
      context: context,
      builder: (d) => AlertDialog(
        title: Text(tr('回復用メール', 'Recovery email')),
        content: TextField(controller: c, keyboardType: TextInputType.emailAddress),
        actions: [
          TextButton(onPressed: () => Navigator.pop(d, false), child: Text(tr('キャンセル', 'Cancel'))),
          FilledButton(onPressed: () => Navigator.pop(d, true), child: const Text('OK')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    final auth = context.read<AuthService>();
    final done = await _withReauth(() async {
      await auth.setRecoveryEmail(c.text.trim());
      return true;
    });
    if (done == true && mounted) {
      showInfo(context, tr('確認メールを送りました', 'Verification email sent'));
    }
  }

  Future<void> _delete() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(tr('アカウントを削除しますか？', 'Delete your account?')),
        content: Text(
          tr(
            '旅行・位置・履歴・音声を含むすべてのデータを削除します。元に戻せません。',
            'All trips, locations, history and audio will be deleted. This cannot be undone.',
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: Text(tr('キャンセル', 'Cancel'))),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Theme.of(context).colorScheme.error),
            onPressed: () => Navigator.pop(c, true),
            child: Text(tr('削除する', 'Delete')),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    final auth = context.read<AuthService>();
    final nav = Navigator.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final res = await _withReauth(() async => (await auth.deleteAccount()) ?? 'done');
    if (res == null) return;
    nav.popUntil((r) => r.isFirst);
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          res == 'pending_revocation'
              ? tr('削除しました。Appleとの連携解除は自動で再試行します。', 'Deleted. Apple disconnection will be retried automatically.')
              : tr('削除しました', 'Deleted'),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthService>();
    final u = auth.user;
    if (u == null) return const Scaffold(body: SizedBox.shrink());
    final m = u.loginMethods;
    final onlyOne = m.length <= 1;
    return Scaffold(
      appBar: LvAppBar(title: Text(tr('アカウント', 'Account'))),
      body: ListView(
        padding: EdgeInsets.only(bottom: bottomGap(context)),
        children: [
          if (u.recoveryEmailVerified)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 16),
              child: LvIllustration(LvArtwork.emailVerification, height: 110),
            ),
          ListTile(
            leading: const LvIcon(LvIconKind.account),
            title: Text(tr('表示名', 'Display name')),
            subtitle: Text(u.displayName ?? '-'),
            trailing: const LvIcon(LvIconKind.edit),
            onTap: () async {
              final c = TextEditingController(text: u.displayName ?? '');
              final ok = await showDialog<bool>(
                context: context,
                builder: (d) => AlertDialog(
                  content: TextField(controller: c),
                  actions: [FilledButton(onPressed: () => Navigator.pop(d, true), child: const Text('OK'))],
                ),
              );
              if (ok == true && context.mounted) {
                await guarded(context, () => auth.updateDisplayName(c.text.trim()));
              }
            },
          ),
          const Divider(),
          ListTile(title: Text(tr('ログイン方法', 'Sign-in methods'), style: Theme.of(context).textTheme.titleSmall)),
          ListTile(
            leading: const LvIcon(LvIconKind.password),
            title: Text(u.loginId == null ? tr('ID・パスワード（未設定）', 'ID & password (not set)') : 'ID: ${u.loginId}'),
            trailing: TextButton(
              onPressed: () => _setPassword(u),
              child: Text(u.loginId == null ? tr('追加', 'Add') : tr('変更', 'Change')),
            ),
          ),
          ListTile(
            leading: const Icon(Icons.g_mobiledata),
            title: const Text('Google'),
            subtitle: Text(m.contains('google') ? tr('連携済み', 'Linked') : tr('未連携', 'Not linked')),
            trailing: m.contains('google')
                ? TextButton(
                    onPressed: onlyOne ? null : () => _withReauth(auth.unlinkGoogle),
                    child: Text(tr('解除', 'Unlink')),
                  )
                : TextButton(onPressed: () => _withReauth(auth.linkGoogle), child: Text(tr('連携', 'Link'))),
          ),
          if (Platform.isIOS || Platform.isAndroid)
            ListTile(
              leading: const Icon(Icons.apple),
              title: const Text('Apple'),
              subtitle: Text(m.contains('apple') ? tr('連携済み', 'Linked') : tr('未連携', 'Not linked')),
              trailing: m.contains('apple')
                  ? TextButton(
                      onPressed: onlyOne ? null : () => _withReauth(auth.unlinkApple),
                      child: Text(tr('解除', 'Unlink')),
                    )
                  : TextButton(onPressed: () => _withReauth(auth.linkApple), child: Text(tr('連携', 'Link'))),
            ),
          if (onlyOne)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                tr('最後のログイン方法は解除できません。', 'You cannot remove your last sign-in method.'),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          const Divider(),
          ListTile(
            leading: const LvIcon(LvIconKind.email),
            title: Text(tr('回復用メール', 'Recovery email')),
            subtitle: Text(
              u.recoveryEmail == null
                  ? tr('未設定', 'Not set')
                  : '${u.recoveryEmail}${u.recoveryEmailVerified ? '' : tr('（未確認）', ' (unverified)')}',
            ),
            onTap: () => _recoveryEmail(u),
          ),
          const Divider(),
          ListTile(
            leading: const LvIcon(LvIconKind.logout),
            title: Text(tr('ログアウト', 'Sign out')),
            onTap: () async {
              final nav = Navigator.of(context);
              await auth.logout();
              nav.popUntil((r) => r.isFirst);
            },
          ),
          ListTile(
            leading: const LvIcon(LvIconKind.delete),
            title: Text(tr('アカウントを削除', 'Delete account'), style: TextStyle(color: Theme.of(context).colorScheme.error)),
            onTap: _delete,
          ),
        ],
      ),
    );
  }
}
