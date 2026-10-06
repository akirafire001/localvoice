import 'package:flutter/widgets.dart';

/// Minimal two-language helper. The app language follows the user's preference.
class Lang extends ChangeNotifier {
  String _code = 'ja';
  String get code => _code;
  bool get isEn => _code == 'en';

  void set(String code) {
    if (code != _code && (code == 'ja' || code == 'en')) {
      _code = code;
      notifyListeners();
    }
  }

  String t(String ja, String en) => isEn ? en : ja;
}

final lang = Lang();

String tr(String ja, String en) => lang.t(ja, en);
