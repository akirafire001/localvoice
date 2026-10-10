import 'package:flutter_test/flutter_test.dart';
import 'package:localvoice/util/i18n.dart';

void main() {
  test('screen language is Japanese only for a Japanese OS, otherwise English', () {
    expect(uiLanguageForCode('ja'), 'ja');
    expect(uiLanguageForCode('JA'), 'ja');
    expect(uiLanguageForCode('en'), 'en');
    expect(uiLanguageForCode('zh'), 'zh');
    expect(uiLanguageForCode('ko'), 'ko');
    expect(uiLanguageForCode('es'), 'es');
    expect(uiLanguageForCode('fr'), 'fr');
    expect(uiLanguageForCode('de'), 'en');
  });
}
