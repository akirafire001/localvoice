import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:just_audio/just_audio.dart';

import '../api/api_client.dart';
import '../config.dart';

enum SpeechState { idle, preparing, playing, textOnly }

/// Plays a guide's speech (voice-design §7).
/// * Every request gets a generation number; audio that arrives for an older
///   guide, after stop, or after sign-out is never auto-played.
/// * Server audio is polled up to [AppConfig.speechWaitLimit]; then device TTS
///   if the user allowed it, otherwise text only.
class AudioController extends ChangeNotifier {
  AudioController(this.api);
  final ApiClient api;
  final _player = AudioPlayer();
  final _tts = FlutterTts();
  int _generation = 0;
  SpeechState state = SpeechState.idle;
  String? currentHistoryId;
  String? lastNote;

  bool enabled = false;
  bool allowDeviceTts = false;
  double rate = 1.0;
  Map<String, String> voices = {};

  void applyPrefs(Map<String, dynamic> prefs) {
    final v = (prefs['voice'] ?? {}) as Map;
    enabled = v['enabled'] == true;
    allowDeviceTts = v['allow_device_tts_fallback'] == true;
    rate = ((v['playback_rate'] ?? 1.0) as num).toDouble();
    voices = ((v['voices'] ?? {}) as Map).map((k, val) => MapEntry('$k', '$val'));
    notifyListeners();
  }

  void _set(SpeechState s, [String? note]) {
    state = s;
    lastNote = note;
    notifyListeners();
  }

  Future<void> stop() async {
    _generation++;
    await _player.stop();
    await _tts.stop();
    _set(SpeechState.idle);
  }

  /// Auto-play for a newly arrived guide; only when the user enabled audio. True when it was told to the end.
  Future<bool> autoPlay(Map<String, dynamic> guide) async {
    if (!enabled) return false;
    return play(guide);
  }

  /// The guide's languages in the order they are spoken (one entry for servers without narration languages).
  static List<Map<String, dynamic>> narrationsOf(Map<String, dynamic> guide) {
    final list = (guide['speech']?['narrations'] as List?)?.cast<Map>();
    if (list != null && list.isNotEmpty) return [for (final n in list) n.cast<String, dynamic>()];
    final lang = guide['language'] as String? ?? 'ja';
    return [
      {
        'language': lang,
        'text': (guide['speech']?['text'] as String?) ?? (guide['text'] as String? ?? ''),
        'voice_profile_id': guide['speech']?['voice_profile_id'],
      },
    ];
  }

  /// Tells the story in each narration language, one after another. Every language's audio is asked for at
  /// once, so a language that must first be translated is usually ready by the time the one before it ends.
  /// True when the story was told to the end (false when stopped, replaced by another, or shown as text only).
  Future<bool> play(Map<String, dynamic> guide, {void Function()? onSpoken}) async {
    final gen = ++_generation;
    await _player.stop();
    await _tts.stop();
    currentHistoryId = guide['history_id'] as String;
    _set(SpeechState.preparing);
    final narrations = narrationsOf(guide);
    final fetches = [for (final n in narrations) _SpeechFetch(this, guide, n, gen)..start()];
    var spoke = false;
    String? failure;
    for (var i = 0; i < narrations.length; i++) {
      final n = narrations[i];
      final fetch = fetches[i]..waitFromNow();
      final r = await fetch.result;
      if (gen != _generation) return false;
      if (r.failure == 'content_gone') {
        _set(SpeechState.textOnly, 'gone');
        return false;
      }
      if (r.paths != null && await _playFiles(r.paths!, gen)) {
        spoke = true;
        continue;
      }
      if (gen != _generation) return false;
      final text = n['text'] as String?;
      if (allowDeviceTts && text != null && text.isNotEmpty) {
        await _tts.setLanguage(n['tts_locale'] as String? ?? _deviceLocale(n['language'] as String?));
        await _tts.setSpeechRate((0.5 * rate).clamp(0.2, 1.0));
        await _tts.awaitSpeakCompletion(true);
        if (gen != _generation) return false;
        _set(SpeechState.playing, 'device_tts');
        await _tts.speak(text);
        if (gen != _generation) return false;
        spoke = true;
        continue;
      }
      failure ??= r.failure;
    }
    if (gen != _generation) return false;
    if (spoke) {
      onSpoken?.call();
      _set(SpeechState.idle);
    } else {
      _set(SpeechState.textOnly, failure);
    }
    return spoke;
  }

  static String _deviceLocale(String? lang) => lang == 'en' ? 'en-US' : (lang == null || lang == 'ja' ? 'ja-JP' : lang);

  /// Plays the intro (when there is one) then the story. False when playback failed.
  Future<bool> _playFiles(List<String> paths, int gen) async {
    try {
      for (final path in paths) {
        await _player.setAudioSource(AudioSource.uri(api.uri(path), headers: api.authHeaders()));
        if (gen != _generation) return false;
        await _player.setSpeed(rate);
        _set(SpeechState.playing);
        await _player.play();
        await _player.processingStateStream.firstWhere((s) => s == ProcessingState.completed);
        if (gen != _generation) return false;
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Voice sample for the settings screen (never uses the guide flow).
  Future<String?> playSample(String voiceId) async {
    final gen = ++_generation;
    await _player.stop();
    try {
      var r = await api.post('/api/v1/voices/$voiceId/sample');
      final deadline = DateTime.now().add(AppConfig.speechWaitLimit);
      while (r.status != 200 && DateTime.now().isBefore(deadline)) {
        await Future.delayed(const Duration(seconds: 1));
        if (gen != _generation) return null;
        r = await api.post('/api/v1/voices/$voiceId/sample');
      }
      if (r.status != 200) return 'timeout';
      await _player.setAudioSource(
        AudioSource.uri(api.uri(r.json['audio_path'] as String), headers: api.authHeaders()),
      );
      await _player.setSpeed(rate);
      if (gen != _generation) return null;
      await _player.play();
      return null;
    } on ApiException catch (e) {
      return e.code;
    }
  }

  @override
  void dispose() {
    _player.dispose();
    _tts.stop();
    super.dispose();
  }
}

class _SpeechResult {
  _SpeechResult({this.paths, this.failure});
  final List<String>? paths; // intro (if any) then the story
  final String? failure;
}

/// Server audio for one narration language. Polls until ready; the wait limit
/// ([AppConfig.speechWaitLimit]) only starts once this language is next to play.
class _SpeechFetch {
  _SpeechFetch(this.c, this.guide, this.narration, this.gen);
  final AudioController c;
  final Map<String, dynamic> guide;
  final Map<String, dynamic> narration;
  final int gen;
  DateTime? _deadline;
  late final Future<_SpeechResult> result;

  void start() => result = _run();

  void waitFromNow() => _deadline ??= DateTime.now().add(AppConfig.speechWaitLimit);

  Future<_SpeechResult> _run() async {
    final lang = narration['language'] as String? ?? 'ja';
    final voice = c.voices[lang] ?? (narration['voice_profile_id'] as String?) ?? '$lang-default';
    while (gen == c._generation) {
      try {
        final r = await c.api.post('/api/v1/guides/${guide['history_id']}/speech', {
          'voice_profile_id': voice,
          'language': lang,
        });
        if (r.status == 200) {
          final intro = (r.json['intro'] as Map?)?['audio_path'] as String?;
          return _SpeechResult(paths: [?intro, r.json['audio_path'] as String]);
        }
      } on ApiException catch (e) {
        // 410 content_gone, 429, 503 tts_unavailable/tts_failed/translation_unavailable: fall back now
        return _SpeechResult(failure: e.code);
      } catch (_) {
        return _SpeechResult(failure: 'error');
      }
      final deadline = _deadline;
      if (deadline != null && DateTime.now().isAfter(deadline)) return _SpeechResult(failure: 'timeout');
      await Future.delayed(const Duration(seconds: 1));
    }
    return _SpeechResult(failure: 'superseded');
  }
}
