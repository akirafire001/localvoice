import 'dart:io' show Platform;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../auth/auth_service.dart';
import '../util/i18n.dart';
import '../widgets/common.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _id = TextEditingController();
  final _pw = TextEditingController();
  bool _busy = false;

  Future<void> _run(Future<void> Function() fn) async {
    setState(() => _busy = true);
    await guarded(context, fn);
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.read<AuthService>();
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 32),
            Text('LocalVoice', style: Theme.of(context).textTheme.headlineLarge, textAlign: TextAlign.center),
            const SizedBox(height: 8),
            Text(tr('移動中に、その土地の話を。', 'Stories of the place you are passing.'), textAlign: TextAlign.center),
            const SizedBox(height: 32),
            AutofillGroup(
              child: Column(
                children: [
                  TextField(
                    controller: _id,
                    autofillHints: const [AutofillHints.username],
                    decoration: InputDecoration(labelText: tr('ログインID', 'Login ID')),
                  ),
                  PasswordField(controller: _pw, autofill: AutofillHints.password),
                ],
              ),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _busy ? null : () => _run(() => auth.login(_id.text.trim(), _pw.text)),
              child: Text(tr('ログイン', 'Sign in')),
            ),
            TextButton(
              onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const PasswordResetScreen())),
              child: Text(tr('パスワードを忘れた場合', 'Forgot password?')),
            ),
            const Divider(height: 32),
            OutlinedButton.icon(
              icon: const Icon(Icons.g_mobiledata),
              onPressed: _busy ? null : () => _run(auth.signInWithGoogle),
              label: Text(tr('Googleでログイン', 'Sign in with Google')),
            ),
            const SizedBox(height: 8),
            if (Platform.isIOS || Platform.isAndroid)
              OutlinedButton.icon(
                icon: const Icon(Icons.apple),
                onPressed: _busy ? null : () => _run(auth.signInWithApple),
                label: Text(tr('Appleでサインイン', 'Sign in with Apple')),
              ),
            const SizedBox(height: 24),
            TextButton(
              onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const RegisterScreen())),
              child: Text(tr('IDとパスワードで新規登録', 'Create an account with ID and password')),
            ),
            TextButton(
              onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const EmailVerifyScreen())),
              child: Text(tr('メール確認コードを入力', 'Enter email verification code')),
            ),
          ],
        ),
      ),
    );
  }
}

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});
  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _id = TextEditingController();
  final _pw = TextEditingController();
  final _name = TextEditingController();
  final _mail = TextEditingController();
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(tr('新規登録', 'Create account'))),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          TextField(
            controller: _id,
            autofillHints: const [AutofillHints.newUsername],
            decoration: InputDecoration(
              labelText: tr('ログインID', 'Login ID'),
              helperText: tr('英数字と . _ - の3〜32文字', '3–32 letters, digits, . _ -'),
            ),
          ),
          PasswordField(controller: _pw, autofill: AutofillHints.newPassword),
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              tr('15文字以上。単語を並べた長めのフレーズがおすすめです。', '15+ characters. A long phrase of words works well.'),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
          TextField(
            controller: _name,
            decoration: InputDecoration(labelText: tr('表示名（任意）', 'Display name (optional)')),
          ),
          TextField(
            controller: _mail,
            keyboardType: TextInputType.emailAddress,
            decoration: InputDecoration(
              labelText: tr('回復用メール（任意）', 'Recovery email (optional)'),
              helperText: tr('パスワードを忘れたときの再設定に使います', 'Used to reset a forgotten password'),
            ),
          ),
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _busy
                ? null
                : () async {
                    setState(() => _busy = true);
                    final auth = context.read<AuthService>();
                    final ok = await guarded(context, () async {
                      await auth.register(
                        _id.text.trim(),
                        _pw.text,
                        displayName: _name.text.trim(),
                        recoveryEmail: _mail.text.trim(),
                      );
                      return true;
                    });
                    if (!context.mounted) return;
                    setState(() => _busy = false);
                    if (ok == true) Navigator.of(context).popUntil((r) => r.isFirst);
                  },
            child: Text(tr('登録する', 'Create account')),
          ),
        ],
      ),
    );
  }
}

class PasswordResetScreen extends StatefulWidget {
  const PasswordResetScreen({super.key});
  @override
  State<PasswordResetScreen> createState() => _PasswordResetScreenState();
}

class _PasswordResetScreenState extends State<PasswordResetScreen> {
  final _id = TextEditingController();
  final _token = TextEditingController();
  final _pw = TextEditingController();
  bool _requested = false;

  @override
  Widget build(BuildContext context) {
    final auth = context.read<AuthService>();
    return Scaffold(
      appBar: AppBar(title: Text(tr('パスワード再設定', 'Reset password'))),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text(
            tr('確認済みの回復用メールがある場合、再設定コードを送ります。', 'If you have a verified recovery email, we will send a reset code.'),
          ),
          TextField(
            controller: _id,
            decoration: InputDecoration(labelText: tr('ログインID', 'Login ID')),
          ),
          const SizedBox(height: 8),
          OutlinedButton(
            onPressed: () async {
              await guarded(context, () => auth.requestPasswordReset(_id.text.trim()));
              if (!context.mounted) return;
              setState(() => _requested = true);
              showInfo(context, tr('登録があればメールを送りました。', 'If the account exists, an email was sent.'));
            },
            child: Text(tr('コードを送る', 'Send code')),
          ),
          if (_requested) ...[
            const Divider(height: 32),
            TextField(
              controller: _token,
              decoration: InputDecoration(labelText: tr('メールのコード', 'Code from the email')),
            ),
            PasswordField(controller: _pw, label: tr('新しいパスワード', 'New password'), autofill: AutofillHints.newPassword),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: () async {
                final ok = await guarded(context, () async {
                  await auth.resetPassword(_token.text.trim(), _pw.text);
                  return true;
                });
                if (ok == true && context.mounted) {
                  showInfo(context, tr('再設定しました。新しいパスワードでログインしてください。', 'Password reset. Please sign in.'));
                  Navigator.pop(context);
                }
              },
              child: Text(tr('再設定する', 'Reset')),
            ),
          ],
        ],
      ),
    );
  }
}

class EmailVerifyScreen extends StatefulWidget {
  const EmailVerifyScreen({super.key});
  @override
  State<EmailVerifyScreen> createState() => _EmailVerifyScreenState();
}

class _EmailVerifyScreenState extends State<EmailVerifyScreen> {
  final _token = TextEditingController();
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(tr('メール確認', 'Verify email'))),
    body: ListView(
      padding: const EdgeInsets.all(24),
      children: [
        TextField(
          controller: _token,
          decoration: InputDecoration(labelText: tr('メールのコード', 'Code from the email')),
        ),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: () async {
            final auth = context.read<AuthService>();
            final ok = await guarded(context, () async {
              await auth.verifyEmail(_token.text.trim());
              if (auth.state == AuthState.signedIn) await auth.loadMe();
              return true;
            });
            if (ok == true && context.mounted) {
              showInfo(context, tr('確認しました。', 'Verified.'));
              Navigator.pop(context);
            }
          },
          child: Text(tr('確認する', 'Verify')),
        ),
      ],
    ),
  );
}
