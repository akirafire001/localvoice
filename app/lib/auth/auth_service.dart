import 'dart:convert';
import 'dart:io' show Platform;
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';

import '../api/api_client.dart';
import '../config.dart';

class UserInfo {
  UserInfo(this.json);
  final Map<String, dynamic> json;
  String get id => json['id'] as String;
  String? get displayName => json['display_name'] as String?;
  List<String> get loginMethods => ((json['login_methods'] ?? []) as List).cast<String>();
  String? get loginId => json['login_id'] as String?;
  String? get recoveryEmail => json['recovery_email'] as String?;
  bool get recoveryEmailVerified => json['recovery_email_verified'] == true;
}

class AuthCancelled implements Exception {}

enum AuthState { unknown, signedOut, signedIn }

/// Login state and every authentication flow (auth-design).
class AuthService extends ChangeNotifier {
  AuthService(this.api) {
    api.onSessionExpired = _expired;
  }

  final ApiClient api;
  AuthState state = AuthState.unknown;
  UserInfo? user;
  bool _googleInitialized = false;

  /// Listeners (GPS, audio, local data) must stop and isolate data when the user changes.
  final List<Future<void> Function()> beforeSignOut = [];

  Future<void> restore() async {
    if (await api.hasStoredSession() && await api.refresh()) {
      try {
        await loadMe();
        state = AuthState.signedIn;
      } on ApiException catch (e) {
        state = e.isNetwork ? AuthState.signedIn : AuthState.signedOut;
      }
    } else {
      state = AuthState.signedOut;
    }
    notifyListeners();
  }

  Future<void> loadMe() async {
    user = UserInfo((await api.get('/api/v1/users/me')).json);
    notifyListeners();
  }

  Future<void> _signedIn(Map<String, dynamic> tokens) async {
    final newId = (tokens['user'] as Map)['id'] as String;
    if (user != null && user!.id != newId) {
      for (final cb in beforeSignOut) {
        await cb();
      }
    }
    await api.saveTokens(tokens);
    await loadMe();
    state = AuthState.signedIn;
    notifyListeners();
  }

  void _expired() {
    state = AuthState.signedOut;
    notifyListeners();
  }

  // ------------------------------------------------------------ ID / password

  Future<void> register(String loginId, String password, {String? displayName, String? recoveryEmail}) async {
    final r = await api.postPublic('/api/v1/auth/register', {
      'login_id': loginId,
      'password': password,
      if (displayName != null && displayName.isNotEmpty) 'display_name': displayName,
      if (recoveryEmail != null && recoveryEmail.isNotEmpty) 'recovery_email': recoveryEmail,
    });
    await _signedIn(r.json);
  }

  Future<void> login(String loginId, String password) async {
    final r = await api.postPublic('/api/v1/auth/login', {'login_id': loginId, 'password': password});
    await _signedIn(r.json);
  }

  Future<void> logout() async {
    for (final cb in beforeSignOut) {
      await cb();
    }
    try {
      await api.post('/api/v1/auth/logout');
    } catch (_) {}
    await api.clearTokens();
    user = null;
    state = AuthState.signedOut;
    notifyListeners();
  }

  Future<void> requestPasswordReset(String loginId) =>
      api.postPublic('/api/v1/auth/password/reset-request', {'login_id': loginId});

  Future<void> resetPassword(String token, String newPassword) =>
      api.postPublic('/api/v1/auth/password/reset', {'token': token, 'new_password': newPassword});

  Future<void> verifyEmail(String token) => api.postPublic('/api/v1/auth/email/verify', {'token': token});

  // ------------------------------------------------------------ Google

  Future<String> _googleIdToken() async {
    final gs = GoogleSignIn.instance;
    if (!_googleInitialized) {
      await gs.initialize(
        serverClientId: AppConfig.googleServerClientId.isEmpty ? null : AppConfig.googleServerClientId,
      );
      _googleInitialized = true;
    }
    try {
      final account = await gs.authenticate();
      final token = account.authentication.idToken;
      if (token == null) throw ApiException(0, 'google_no_token', 'Google did not return an ID token');
      return token;
    } on GoogleSignInException catch (e) {
      if (e.code == GoogleSignInExceptionCode.canceled) throw AuthCancelled();
      rethrow;
    }
  }

  Future<void> signInWithGoogle() async {
    final token = await _googleIdToken();
    final r = await api.postPublic('/api/v1/auth/google', {'id_token': token});
    await _signedIn(r.json);
  }

  Future<void> linkGoogle() async {
    final token = await _googleIdToken();
    await api.post('/api/v1/users/me/auth/google', {'id_token': token});
    await loadMe();
  }

  Future<void> unlinkGoogle() async {
    await api.delete('/api/v1/users/me/auth/google');
    await loadMe();
  }

  // ------------------------------------------------------------ Apple

  static String _random(int len) {
    final r = Random.secure();
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._';
    return List.generate(len, (_) => chars[r.nextInt(chars.length)]).join();
  }

  static String _sha256(String s) => sha256.convert(utf8.encode(s)).toString();

  /// Runs the Apple sheet (iOS) or browser flow (Android) for a server challenge.
  Future<Map<String, dynamic>> _appleFlow(String purpose) async {
    final ios = Platform.isIOS;
    final verifier = _random(64);
    final start =
        (purpose == 'login'
                ? await api.postPublic('/api/v1/auth/apple/start', {
                    'platform': ios ? 'ios' : 'android',
                    'purpose': purpose,
                    'app_code_challenge': _sha256(verifier),
                  })
                : await api.post('/api/v1/auth/apple/start', {
                    'platform': ios ? 'ios' : 'android',
                    'purpose': purpose,
                    'app_code_challenge': _sha256(verifier),
                  }))
            .json;
    AuthorizationCredentialAppleID cred;
    try {
      cred = await SignInWithApple.getAppleIDCredential(
        scopes: purpose == 'login' ? [AppleIDAuthorizationScopes.fullName, AppleIDAuthorizationScopes.email] : [],
        nonce: _sha256(start['nonce'] as String),
        state: start['state'] as String?,
        webAuthenticationOptions: ios
            ? null
            : WebAuthenticationOptions(
                clientId: start['client_id'] as String,
                redirectUri: Uri.parse(start['redirect_uri'] as String),
              ),
      );
    } on SignInWithAppleAuthorizationException catch (e) {
      if (e.code == AuthorizationErrorCode.canceled) throw AuthCancelled();
      rethrow;
    }
    final name = [cred.givenName, cred.familyName].where((x) => x != null && x.isNotEmpty).join(' ');
    if (ios) {
      return {
        'challenge_id': start['challenge_id'],
        'id_token': cred.identityToken,
        'authorization_code': cred.authorizationCode,
        'code_verifier': verifier,
        if (name.isNotEmpty) 'display_name': name,
      };
    }
    // Android: the server's callback hands back only a one-time handoff code (as "code").
    return {
      '_android': true,
      'challenge_id': start['challenge_id'],
      'handoff_code': cred.authorizationCode,
      'code_verifier': verifier,
    };
  }

  Future<void> signInWithApple() async {
    final p = await _appleFlow('login');
    final r = p.remove('_android') == true
        ? await api.postPublic('/api/v1/auth/apple/complete', p)
        : await api.postPublic('/api/v1/auth/apple', p);
    await _signedIn(r.json);
  }

  Future<void> linkApple() async {
    final p = await _appleFlow('link');
    if (p.remove('_android') == true) {
      await api.post('/api/v1/auth/apple/complete', p);
    } else {
      await api.post('/api/v1/users/me/auth/apple', p);
    }
    await loadMe();
  }

  Future<String?> unlinkApple() async {
    final r = await api.delete('/api/v1/users/me/auth/apple');
    await loadMe();
    return r.json['revocation'] as String?;
  }

  // ------------------------------------------------------------ reauth / account

  Future<void> reauthWithPassword(String password) => api.post('/api/v1/auth/reauthenticate', {'password': password});

  Future<void> reauthWithGoogle() async {
    final token = await _googleIdToken();
    await api.post('/api/v1/auth/reauthenticate', {'google_id_token': token});
  }

  Future<void> reauthWithApple() async {
    final p = await _appleFlow('reauthenticate');
    if (p.remove('_android') == true) {
      await api.post('/api/v1/auth/apple/complete', p);
    } else {
      await api.post('/api/v1/auth/reauthenticate', p);
    }
  }

  /// Adds ID/password or changes the password; all sessions are revoked, so sign in again.
  Future<void> setPassword(String? loginId, String password) async {
    await api.put('/api/v1/users/me/auth/password', {'login_id': ?loginId, 'password': password});
    final id = loginId ?? user?.loginId;
    await api.clearTokens();
    if (id != null) {
      await login(id, password);
    } else {
      state = AuthState.signedOut;
      notifyListeners();
    }
  }

  Future<void> setRecoveryEmail(String email) async {
    await api.post('/api/v1/users/me/recovery-email', {'email': email});
    await loadMe();
  }

  Future<void> updateDisplayName(String name) async {
    await api.patch('/api/v1/users/me', {'display_name': name});
    await loadMe();
  }

  /// Returns "pending_revocation" when Apple revoke is still being retried.
  Future<String?> deleteAccount() async {
    for (final cb in beforeSignOut) {
      await cb();
    }
    final r = await api.delete('/api/v1/users/me');
    await api.clearTokens();
    user = null;
    state = AuthState.signedOut;
    notifyListeners();
    return r.json['revocation'] as String?;
  }
}
