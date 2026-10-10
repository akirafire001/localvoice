# Google Play 掲載素材

2026-10-10。LocalVoiceの日本語ストア掲載情報用。

- `short-description-ja.txt`：簡単な説明（39文字）。Play Consoleに下書き保存済み。
- `full-description-ja.txt`：詳しい説明（581文字）。Play Consoleに下書き保存済み。
- `feature-graphic-1024x500.png`：1024×500px、RGB PNG、約820KB。
- `screens/home.png`：ホーム。1080×1920px、RGB PNG。
- `screens/preferences.png`：表示言語・解説の言語・頻度などの設定。1080×1920px、RGB PNG。

画像は用意した段階で、Play Consoleへのアップロード・掲載情報の確定・審査は未完了。アイコンは `../branding/play-store-icon-512.png` を使う。

## 掲載画像の出所

ホームと設定は実装されたFlutterウィジェットをテスト環境で描画したキャプチャ。画像生成による画面案ではない。表示名「旅人」・設定値は表示例で、実機や本番ユーザーのデータではない。ローカルの日本語プレビューフォントを使用するため、Android実機のフォントとは差がある。端末・本番接続・Googleログインの動作確認を示す画像ではない。

`app/test/s1_ui_test.dart` の既存キャプチャ処理で作成する。ガイド画面は地図を含む実機キャプチャがまだないため掲載素材に含めない。

```powershell
Set-Location C:\work\git\localvoice\app
$env:LOCALVOICE_CAPTURE_STORE_UI = '1'
& C:\work\tools\flutter-localvoice\bin\flutter.bat test --no-pub test/s1_ui_test.dart
Remove-Item Env:\LOCALVOICE_CAPTURE_STORE_UI
```

出力は432×768論理ピクセルを2.5倍で描画した1080×1920px PNG。アップロード時はPillow等でRGBに変換し、寸法とファイルサイズを検証する。今回の描画テスト12件は成功。

## フィーチャーグラフィック

組み込みの画像生成ツールを使用。参照は既存の `app/assets/s1/illustrations/home-discovery.png`。深緑とアイボリーの旅の手帖のデザインを継承し、地図・イヤホン・町並みのイラストと「LocalVoice」「移動中に、その土地の話を。」を配置。生成結果は1795×876pxだったため、デザインを変更せず1024×500pxへ書き出し、RGB PNGで保存した。

生成プロンプト：

> Use case: ads-marketing. Create a finished Google Play feature graphic for LocalVoice, a location-aware audio story app for travel and walks. Output EXACTLY 1024 x 500 pixels, landscape aspect ratio 2.048:1, opaque background. The supplied illustration is STYLE REFERENCE only: refined travel-journal ink contours with restrained watercolor, folded local map, headphones, a quiet town building, foliage. Preserve the calm forest green #075747 and warm ivory #FBFAF5 identity, with pale sage, sand and water blue accents. Design a spacious, polished editorial banner: balanced typography left-of-center, small town/map/headphones artwork right-of-center, all essential content within generous 70px safe margins, no edge cropping. Exact text on two separate lines: 'LocalVoice' and '移動中に、その土地の話を。'. Crisp elegant legible Japanese sans-serif, title larger than tagline. The composition should communicate listening to local stories while exploring a place. No phone mockup, no invented app UI, no third-party logos, no store badge, no rankings, no prices, no buttons, no microphone/recording symbol, no arrow or navigation claim. Do not repeat the location-pin app icon; use illustration as an extension of the brand. Background is light warm ivory with subtle sage wash, never pure white. Style reference input image: existing home-discovery artwork.

## 規定

[Google Playの公式掲載素材ガイド](https://support.google.com/googleplay/android-developer/answer/9866151?hl=en)に沿い、フィーチャーグラフィックは1024×500px、スクリーンショットは9:16、透過なしのPNGとした。
