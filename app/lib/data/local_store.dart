import 'dart:convert';

import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

/// Per-user local database (flutter-ux §9: never mix data between accounts on one device).
/// Points are written here first, then sent; unsent ones are resent later.
class LocalStore {
  LocalStore._(this.db, this.userId);
  final Database db;
  final String userId;

  static Future<LocalStore> open(String userId) async {
    final dir = await getDatabasesPath();
    final safe = userId.replaceAll(RegExp(r'[^A-Za-z0-9-]'), '');
    final db = await openDatabase(
      p.join(dir, 'lv_$safe.db'),
      version: 1,
      onCreate: (db, _) async {
        await db.execute('''create table points(
        client_event_id text primary key, trip_id text not null, observed_at text not null,
        lat real not null, lon real not null, accuracy_m real, motion text, sent integer not null default 0)''');
        await db.execute('create index points_trip on points(trip_id, observed_at)');
        await db.execute(
          'create table guides(history_id text primary key, trip_id text not null, shown_at text, json text not null)',
        );
        await db.execute('create table kv(k text primary key, v text)');
      },
    );
    return LocalStore._(db, userId);
  }

  static Future<void> deleteFor(String userId) async {
    final dir = await getDatabasesPath();
    final safe = userId.replaceAll(RegExp(r'[^A-Za-z0-9-]'), '');
    await deleteDatabase(p.join(dir, 'lv_$safe.db'));
  }

  Future<void> close() => db.close();

  Future<void> addPoint(String tripId, Map<String, dynamic> ctx) => db.insert('points', {
    'client_event_id': ctx['client_event_id'],
    'trip_id': tripId,
    'observed_at': ctx['observed_at'],
    'lat': ctx['location']['lat'],
    'lon': ctx['location']['lon'],
    'accuracy_m': ctx['location']['accuracy_m'],
    'motion': jsonEncode(ctx['motion']),
  }, conflictAlgorithm: ConflictAlgorithm.ignore);

  Future<void> markSent(String eventId) =>
      db.update('points', {'sent': 1}, where: 'client_event_id = ?', whereArgs: [eventId]);

  Future<List<Map<String, dynamic>>> unsent(String tripId, {int limit = 100}) async {
    final rows = await db.query(
      'points',
      where: 'trip_id = ? and sent = 0',
      whereArgs: [tripId],
      orderBy: 'observed_at',
      limit: limit,
    );
    return rows
        .map(
          (r) => {
            'client_event_id': r['client_event_id'],
            'observed_at': r['observed_at'],
            'location': {'lat': r['lat'], 'lon': r['lon'], 'accuracy_m': r['accuracy_m']},
            'motion': r['motion'] == null ? null : jsonDecode(r['motion'] as String),
          },
        )
        .toList();
  }

  Future<List<Map<String, Object?>>> points(String tripId) =>
      db.query('points', where: 'trip_id = ?', whereArgs: [tripId], orderBy: 'observed_at');

  Future<void> saveGuide(String tripId, Map<String, dynamic> guide) => db.insert('guides', {
    'history_id': guide['history_id'],
    'trip_id': tripId,
    'shown_at': guide['shown_at'],
    'json': jsonEncode(guide),
  }, conflictAlgorithm: ConflictAlgorithm.replace);

  Future<List<Map<String, dynamic>>> guides(String tripId) async {
    final rows = await db.query('guides', where: 'trip_id = ?', whereArgs: [tripId], orderBy: 'shown_at');
    return rows.map((r) => (jsonDecode(r['json'] as String) as Map).cast<String, dynamic>()).toList();
  }

  Future<String?> get(String k) async {
    final r = await db.query('kv', where: 'k = ?', whereArgs: [k]);
    return r.isEmpty ? null : r.first['v'] as String?;
  }

  Future<void> set(String k, String? v) => v == null
      ? db.delete('kv', where: 'k = ?', whereArgs: [k])
      : db.insert('kv', {'k': k, 'v': v}, conflictAlgorithm: ConflictAlgorithm.replace);
}
