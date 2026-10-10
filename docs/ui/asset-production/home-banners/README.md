# ホームのランダムバナー

2026-10-10から制作、2026-10-11完成。選択済みの鉛筆と淡彩の2枚を保持し、世界20か国の名所を同じ画風で追加。22枚をアプリに同梱。

- [22枚のギャラリーとホーム表示モック](index.html)
- 原本: `docs/ui/asset-production/home-banners/originals/*.png`。すべて1774×887px、不透明PNG、2:1。
- アプリ用: `app/assets/s1/home_banners/*.webp`。同じ1774×887pxのWebP、品質92。原本のPNGは変更せず保持。
- 組み込み `image_gen` を使用。[manifest.json](manifest.json) に各画像のプロンプトと参照素材を記録。
- 既存の `02a-pencil-brand.png` と `02b-pencil-brand-coast.png` は原本を保持し、`originals/` にはバイト単位で同一のコピーを保存。
- 共通の深緑 #075747、セージ #739C85、アイボリー #FBFAF5。折り地図とイヤホンを共通モチーフに使用。

`python tools/export_home_banners.py` で原本からアプリ用WebPを再出力できます（Pillowが必要）。寸法・不透明性を検証し、[exports.json](exports.json)に原本と出力のSHA256・容量を保存します。

22枚の原本は合計71.67MiB、アプリ用は合計12.41MiB（82.7%削減）。ピクセル寸法はすべて同じです。

## 起動時の動作

`LocalVoiceApp` の State を作る際に、`LvHomeBanner.pick()` で22枚から1枚を等確率で選びます。ホーム画面には選んだ値を渡します。

- アプリを終了して新しく起動すると再抽選。
- 画面の再描画、言語変更、設定や履歴から戻る操作、バックグラウンドからの復帰では再抽選しません。
- ランダム抽選のため、別の起動でも同じ画像になることがあります。
- 画像はすべてオフライン利用可能。選ばれた1枚だけを画面サイズに合わせてデコードします。
- ホームはコンテンツ幅いっぱい、縦横比2:1、角丸16px。ガイド中の旅行がある場合は既存の旅行再開カードを表示。

## 世界の20か所

- 日本 / 富士山 / `japan-fuji.png`
- 中国 / 万里の長城 / `china-great-wall.png`
- 韓国 / 景福宮 / `korea-gyeongbokgung.png`
- インド / タージ・マハル / `india-taj-mahal.png`
- カンボジア / アンコール・ワット / `cambodia-angkor-wat.png`
- タイ / ワット・アルン / `thailand-wat-arun.png`
- インドネシア / ボロブドゥール / `indonesia-borobudur.png`
- ヨルダン / ペトラ / `jordan-petra.png`
- エジプト / ギザのピラミッド / `egypt-giza.png`
- トルコ / カッパドキア / `turkey-cappadocia.png`
- フランス / エッフェル塔 / `france-eiffel.png`
- イタリア / コロッセオ / `italy-colosseum.png`
- イギリス / ウェストミンスター / `uk-westminster.png`
- スペイン / サグラダ・ファミリア / `spain-sagrada-familia.png`
- 南アフリカ / テーブルマウンテン / `south-africa-table-mountain.png`
- ペルー / マチュ・ピチュ / `peru-machu-picchu.png`
- ブラジル / リオ・デ・ジャネイロ / `brazil-rio.png`
- アメリカ / 自由の女神 / `usa-liberty.png`
- カナダ / レイク・ルイーズ / `canada-lake-louise.png`
- オーストラリア / シドニー・オペラハウス / `australia-sydney.png`

## 検証

- `flutter analyze --no-pub`: 問題なし。
- 標準の `flutter test --reporter expanded`: 28件成功。
- ホーム画面・起動中の画像維持・全アセット読み込みの3件を、画面キャプチャ用フォントでも確認。通常サイズと幅320px・文字1.6倍で描画エラーなし。
- Flutterのアセットバンドルから全22枚のWebPを読み込み、1774×887pxでデコードできることを確認。
- 原本PNGとWebPのサイズ・SHA256を `exports.json` に記録。保持した既存2枚の原本はコピー元とSHA256一致。
- [実際のFlutterホーム描画](../s1/screens/home.png)を更新（固定した海辺の画像での確認用）。
