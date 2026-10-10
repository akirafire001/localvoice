# LocalVoice アイコン

2026-10-10にA案「位置ピン＋音の波」を採用。ユーザーが選択した添付PNGを原本として保存しています。深緑の背景、アイボリーの位置ピン、3本の音声波形を組み合わせたデザインです。

原本は [localvoice-icon.png](localvoice-icon.png)。組み込み画像生成で作成した候補の選択後、再生成せずにサイズ変換だけを行っています。

## 書き出し

| ファイル | 用途 |
| --- | --- |
| [app-icon-1024.png](app-icon-1024.png) | 共通の1024pxアプリアイコン |
| [play-store-icon-512.png](play-store-icon-512.png) | Google Playのストア掲載用。512px、32bit PNG、完全不透明 |
| [favicon.ico](favicon.ico) | 16 / 32 / 48 / 64pxを格納したfavicon |
| [favicon-16.png](favicon-16.png), [favicon-32.png](favicon-32.png), [favicon-48.png](favicon-48.png) | PNG形式のfavicon |
| [apple-touch-icon.png](apple-touch-icon.png) | 180pxのWebクリップ用アイコン |

Androidは `app/android/app/src/main/res/mipmap-*/ic_launcher.png` の5密度、iOSは既存の `AppIcon.appiconset/Contents.json` が参照する全サイズに書き出しています。元の画像は角を丸めず、OSによるマスクに任せています。iOS用PNGは透過なしのRGBです。

faviconは画面一覧HTMLとアイコン比較HTMLに設定済みです。Flutterアプリは現在Android / iOS構成で、Flutter Webの設定はありません。将来のWebページでも以下のように参照できます（相対パスはページの場所に合わせて変更）。

```html
<link rel="icon" href="favicon.ico" sizes="any">
<link rel="icon" type="image/png" href="favicon-32.png" sizes="32x32">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
```

## 再書き出し

Pillowを導入したPython環境で、リポジトリのルートから実行します。

```powershell
python tools/export_icons.py
```

原本から各サイズを生成し、PNGの寸法・透過なし・読み込みとICO内の各サイズを検証します。デザイン候補とプロンプトは [icon-concepts/2026-10-10](icon-concepts/2026-10-10/index.html) に残しています。
