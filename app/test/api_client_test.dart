import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:localvoice/api/api_client.dart';

class MemStore implements TokenStore {
  String? v;
  @override
  Future<String?> readRefresh() async => v;
  @override
  Future<void> writeRefresh(String? token) async => v = token;
}

void main() {
  test('refreshes once on 401 and retries; concurrent calls share one refresh', () async {
    var refreshCalls = 0;
    final client = MockClient((req) async {
      if (req.url.path == '/api/v1/auth/refresh') {
        refreshCalls++;
        await Future.delayed(const Duration(milliseconds: 20));
        return http.Response(
          jsonEncode({
            'access_token': 'new',
            'refresh_token': 'r2',
            'user': {'id': 'u'},
          }),
          200,
        );
      }
      if (req.headers['Authorization'] == 'Bearer new') return http.Response(jsonEncode({'ok': true}), 200);
      return http.Response(jsonEncode({'code': 'token_expired', 'message': 'x'}), 401);
    });
    final store = MemStore()..v = 'r1';
    final api = ApiClient(httpClient: client, tokenStore: store, baseUrl: 'http://x');
    await api.saveTokens({'access_token': 'old', 'refresh_token': 'r1'});
    final rs = await Future.wait([api.get('/a'), api.get('/b')]);
    expect(rs.every((r) => r.json['ok'] == true), isTrue);
    expect(refreshCalls, 1);
    expect(store.v, 'r2');
  });

  test('failed refresh clears tokens and reports session expiry', () async {
    final client = MockClient((req) async {
      if (req.url.path == '/api/v1/auth/refresh') {
        return http.Response(jsonEncode({'code': 'invalid_token', 'message': ''}), 401);
      }
      return http.Response(jsonEncode({'code': 'token_expired', 'message': ''}), 401);
    });
    final store = MemStore()..v = 'r1';
    final api = ApiClient(httpClient: client, tokenStore: store, baseUrl: 'http://x');
    var expired = false;
    api.onSessionExpired = () => expired = true;
    await api.saveTokens({'access_token': 'old', 'refresh_token': 'r1'});
    await expectLater(api.get('/a'), throwsA(isA<ApiException>().having((e) => e.status, 'status', 401)));
    expect(expired, isTrue);
    expect(store.v, isNull);
  });

  test('error body becomes ApiException with code and details', () async {
    final client = MockClient(
      (req) async => http.Response(
        jsonEncode({
          'code': 'weak_password',
          'message': 'too short',
          'details': {'field': 'password'},
        }),
        400,
      ),
    );
    final api = ApiClient(httpClient: client, tokenStore: MemStore(), baseUrl: 'http://x');
    try {
      await api.postPublic('/api/v1/auth/register', {});
      fail('should throw');
    } on ApiException catch (e) {
      expect(e.code, 'weak_password');
      expect(e.details['field'], 'password');
    }
  });
}
