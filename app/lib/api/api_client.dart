import 'dart:async';
import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import '../config.dart';

class ApiException implements Exception {
  ApiException(this.status, this.code, this.message, [this.details = const {}]);
  final int status;
  final String code;
  final String message;
  final Map<String, dynamic> details;

  bool get isNetwork => status == 0;
  @override
  String toString() => 'ApiException($status, $code, $message)';
}

/// Abstract token store so tests can run without platform channels.
abstract class TokenStore {
  Future<String?> readRefresh();
  Future<void> writeRefresh(String? token);
}

class SecureTokenStore implements TokenStore {
  // Refresh token lives in Keychain/Keystore-backed storage (auth-design §5).
  static const _storage = FlutterSecureStorage();
  static const _key = 'lv_refresh_token';
  @override
  Future<String?> readRefresh() => _storage.read(key: _key);
  @override
  Future<void> writeRefresh(String? token) =>
      token == null ? _storage.delete(key: _key) : _storage.write(key: _key, value: token);
}

class ApiResponse {
  ApiResponse(this.status, this.body);
  final int status;
  final dynamic body;
  Map<String, dynamic> get json => (body as Map).cast<String, dynamic>();
}

/// HTTP client for the LocalVoice API. Access token in memory, refresh token in secure storage.
class ApiClient {
  ApiClient({http.Client? httpClient, TokenStore? tokenStore, String? baseUrl})
    : _http = httpClient ?? http.Client(),
      _store = tokenStore ?? SecureTokenStore(),
      baseUrl = baseUrl ?? AppConfig.apiBaseUrl;

  final http.Client _http;
  final TokenStore _store;
  final String baseUrl;
  String? _access;
  Future<bool>? _refreshing;

  /// Called when the login session can no longer be refreshed.
  void Function()? onSessionExpired;

  bool get hasAccessToken => _access != null;
  String? get accessToken => _access;

  Future<void> saveTokens(Map<String, dynamic> tokenResponse) async {
    _access = tokenResponse['access_token'] as String?;
    await _store.writeRefresh(tokenResponse['refresh_token'] as String?);
  }

  Future<void> clearTokens() async {
    _access = null;
    await _store.writeRefresh(null);
  }

  Future<bool> hasStoredSession() async => (await _store.readRefresh()) != null;

  Uri uri(String path, [Map<String, String>? query]) => Uri.parse('$baseUrl$path').replace(queryParameters: query);

  Map<String, String> authHeaders() => {if (_access != null) 'Authorization': 'Bearer $_access'};

  /// Refresh once even when several requests notice expiry at the same time.
  Future<bool> refresh() {
    return _refreshing ??= _doRefresh().whenComplete(() => _refreshing = null);
  }

  Future<bool> _doRefresh() async {
    final rt = await _store.readRefresh();
    if (rt == null) return false;
    http.Response r;
    try {
      r = await _http.post(
        uri('/api/v1/auth/refresh'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'refresh_token': rt}),
      );
    } catch (_) {
      return false; // offline: keep the stored token and retry later
    }
    if (r.statusCode == 200) {
      await saveTokens(jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>);
      return true;
    }
    if (r.statusCode == 401) {
      await clearTokens();
      onSessionExpired?.call();
    }
    return false;
  }

  Future<ApiResponse> request(
    String method,
    String path, {
    Object? body,
    Map<String, String>? query,
    bool auth = true,
    bool retried = false,
  }) async {
    if (auth && _access == null && !retried) {
      await refresh();
    }
    final headers = {'Content-Type': 'application/json', 'Accept': 'application/json', if (auth) ...authHeaders()};
    final req = http.Request(method, uri(path, query))..headers.addAll(headers);
    if (body != null) req.body = jsonEncode(body);
    http.Response r;
    try {
      r = await http.Response.fromStream(await _http.send(req).timeout(const Duration(seconds: 20)));
    } on TimeoutException {
      throw ApiException(0, 'timeout', 'request timed out');
    } catch (e) {
      throw ApiException(0, 'network', e.toString());
    }
    if (r.statusCode == 401 && auth && !retried) {
      final code = _code(r);
      if (code == 'token_expired' || code == 'invalid_token' || code == 'unauthorized') {
        if (await refresh()) {
          return request(method, path, body: body, query: query, auth: auth, retried: true);
        }
      }
    }
    final decoded = r.bodyBytes.isEmpty ? null : _tryJson(r);
    if (r.statusCode >= 400) {
      final m = decoded is Map ? decoded : const {};
      throw ApiException(
        r.statusCode,
        (m['code'] ?? 'http_${r.statusCode}') as String,
        (m['message'] ?? '') as String,
        ((m['details'] ?? {}) as Map).cast<String, dynamic>(),
      );
    }
    return ApiResponse(r.statusCode, decoded);
  }

  /// Raw bytes (audio). Same auth handling.
  Future<List<int>> getBytes(String path, {bool retried = false}) async {
    final r = await _http.get(uri(path), headers: authHeaders());
    if (r.statusCode == 401 && !retried && await refresh()) return getBytes(path, retried: true);
    if (r.statusCode != 200) throw ApiException(r.statusCode, _code(r), 'audio unavailable');
    return r.bodyBytes;
  }

  dynamic _tryJson(http.Response r) {
    try {
      return jsonDecode(utf8.decode(r.bodyBytes));
    } catch (_) {
      return null;
    }
  }

  String _code(http.Response r) {
    final j = _tryJson(r);
    return j is Map && j['code'] is String ? j['code'] as String : 'http_${r.statusCode}';
  }

  Future<ApiResponse> get(String path, {Map<String, String>? query}) => request('GET', path, query: query);
  Future<ApiResponse> post(String path, [Object? body]) => request('POST', path, body: body ?? {});
  Future<ApiResponse> patch(String path, Object body) => request('PATCH', path, body: body);
  Future<ApiResponse> put(String path, Object body) => request('PUT', path, body: body);
  Future<ApiResponse> delete(String path) => request('DELETE', path);
  Future<ApiResponse> postPublic(String path, Object body) => request('POST', path, body: body, auth: false);
}
