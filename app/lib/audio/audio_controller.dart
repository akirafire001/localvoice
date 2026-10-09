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

  /// Auto-play for a newly arrived guide; only when the user enabled audio.
  Future<void> autoPlay(Map<String, dynamic> guide) async {
    if (!enabled) return;
    await play(guide);
  }

  Future<void> play(Map<String, dynamic> guide, {void Function()? onSpoken}) async {
    final gen = ++_generation;
    await _player.stop();
    await _tts.stop();
    currentHistoryId = guide['history_id'] as String;
    _set(SpeechState.preparing);
    final lang = guide['language'] as String? ?? 'ja';
    final voice =
        voices[lang] ??
        (guide['speech']?['voice_profile_id'] as String?) ??
        (lang == 'en' ? 'en-default' : 'ja-default');
    final deadline = DateTime.now().add(AppConfig.speechWaitLimit);
    String? audioPath;
    String? introPath; // short line fitted to this moment, played before the story's shared audio
    String? failure;
    while (gen == _generation) {
      try {
        final r = await api.post('/api/v1/guides/${guide['history_id']}/speech', {'voice_profile_id': voice});
        if (r.status == 200) {
          audioPath = r.json['audio_path'] as String;
          introPath = (r.json['intro'] as Map?)?['audio_path'] as String?;
          break;
        }
      } on ApiException catch (e) {
        failure = e.code;
        break; // 410 content_gone, 429, 503 tts_unavailable/failed: fall back now
      }
      if (DateTime.now().isAfter(deadline)) {
        failure = 'timeout';
        break;
      }
      await Future.delayed(const Duration(seconds: 1));
    }
    if (gen != _generation) return; // superseded
    if (failure == 'content_gone') {
      _set(SpeechState.textOnly, 'gone');
      return;
    }
    if (audioPath != null) {
      try {
        for (final path in [?introPath, audioPath]) {
          await _player.setAudioSource(AudioSource.uri(api.uri(path), headers: api.authHeaders()));
          if (gen != _generation) return;
          await _player.setSpeed(rate);
          _set(SpeechState.playing);
          await _player.play();
          await _player.processingStateStream.firstWhere((s) => s == ProcessingState.completed);
          if (gen != _generation) return;
        }
        if (gen == _generation) {
          onSpoken?.call();
          _set(SpeechState.idle);
        }
        return;
      } catch (_) {
        if (gen != _generation) return;
      }
    }
    final text = (guide['speech']?['text'] as String?) ?? (guide['text'] as String? ?? '');
    if (allowDeviceTts && text.isNotEmpty) {
      await _tts.setLanguage(lang == 'en' ? 'en-US' : 'ja-JP');
      await _tts.setSpeechRate((0.5 * rate).clamp(0.2, 1.0));
      await _tts.awaitSpeakCompletion(true);
      if (gen != _generation) return;
      _set(SpeechState.playing, 'device_tts');
      await _tts.speak(text);
      if (gen == _generation) {
        onSpoken?.call();
        _set(SpeechState.idle);
      }
      return;
    }
    _set(SpeechState.textOnly, failure);
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
