import 'dart:ui';

import 'package:flutter/widgets.dart';

import 'ui_copy.dart';

/// App screens are written in these languages. Any other OS language starts in English.
const uiLanguageCodes = {'ja', 'en', 'zh', 'ko', 'es', 'fr'};

String uiLanguageForCode(String languageCode) =>
    uiLanguageCodes.contains(languageCode.toLowerCase()) ? languageCode.toLowerCase() : 'en';

/// BCP 47 tag of the OS locale, sent once when an account is created.
String deviceLanguageTag() => PlatformDispatcher.instance.locale.toLanguageTag();

/// Screen language to use before the account has a saved preference.
String uiLanguageForDevice() => uiLanguageForCode(PlatformDispatcher.instance.locale.languageCode);

/// The app language follows the user's preference, then the strings in [uiCopy].
class Lang extends ChangeNotifier {
  String _code = 'ja';
  String get code => _code;
  bool get isEn => _code == 'en';

  void set(String code) {
    if (code != _code && uiLanguageCodes.contains(code)) {
      _code = code;
      notifyListeners();
    }
  }

  /// [more] is for strings that already contain a filled-in name or number.
  String t(String ja, String en, [Map<String, String>? more]) {
    if (_code == 'ja') return ja;
    if (_code == 'en') return en;
    return more?[_code] ?? uiCopy['$ja||$en']?[_code] ?? en;
  }
}

final lang = Lang();

String tr(String ja, String en, [Map<String, String>? more]) => lang.t(ja, en, more);
