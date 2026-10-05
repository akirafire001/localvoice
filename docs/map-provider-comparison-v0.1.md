# LocalVoice 地図方式の比較検討 v0.1

調査日: 2026-10-06
状態: 推奨案。実機検証・採用確定はこれから。
対象: MVPの現在地・移動履歴表示。Android/iOS、日英の利用者、年末の実旅行を想定。

## 推奨案

**地図データはOpenStreetMap系、表示はMapLibre Flutter（maplibre_gl）、背景地図の配信はOpenFreeMapを第一候補とする。**

現在地マーカー、精度円、時刻順の移動履歴の線をアプリで重ねる。カメラや画像認識は使わない。GPS取得と履歴保存は地図ライブラリから分離し、既存のLocation Service・ローカル記録・track APIを利用する。

判断理由:
- OpenFreeMapは商用利用可能で、公開配信は無料・APIキー不要・地図閲覧数/リクエスト数の制限なしと明記されている。一方でSLAはない。[公式案内](https://openfreemap.org/)
- OpenFreeMapのスタイルはモバイルのMapLibre Nativeでも利用でき、MapLibre FlutterはAndroid/iOSに対応する。[配信側の導入説明](https://openfreemap.org/quick_start/)、[Flutter表示ライブラリ](https://maplibre.org/flutter-maplibre-gl/)
- MapLibre Flutterには線・円・マーカーの描画と地図ラベルの言語変更機能がある。公式資料はOpenFreeMap Libertyの多言語ラベルにも言及している。各地名の翻訳が揃うことは保証せず、実証地域で日英表示を確認する。[機能一覧](https://maplibre.org/flutter-maplibre-gl/)、[言語設定](https://maplibre.org/flutter-maplibre-gl/advanced/map-language/)

これは資料に基づく選定案であり、描画性能・バッテリー・日本国内の細部の見やすさは実機未検証。ネイティブSDKの設定を伴う点は、pure Flutterのflutter_mapより実装時の確認箇所が増えると判断する。

## 3つを分ける

| 役割 | 推奨案 |
| --- | --- |
| 地図データ | OpenStreetMapを元にした地図 |
| Flutter上の表示 | MapLibre Flutter |
| 背景地図の配信 | OpenFreeMap |
| 現在地・移動履歴 | LocalVoiceの端末GPS・履歴データ |

「OSMを使う」だけでは、表示方法や配信元、料金、オフライン条件は決まらない。地図上に載せる位置履歴の取得・保存にも別の実装が必要。

## 比較

| 構成 | LocalVoiceでの利点 | 費用・制約 | 判断 |
| --- | --- | --- | --- |
| MapLibre Flutter + OpenFreeMap | ベクター地図、日英ラベル調整、独自の線・円・マーカーを重ねられる | 公開配信は無料・商用可・APIキー不要。SLAなし、帰属表示が必要 | 第一候補 |
| flutter_map + GeoapifyのOSM系ラスタタイル | pure Flutterで表示を組みやすく、GPS履歴をPolylineで描ける | 無料枠は商用可。3,000 credits/日、通常タイル1件0.25 credits。APIキー・帰属表示が必要 | 実装の単純さを優先する場合の代案 |
| flutter_map/MapLibre + MapTiler | ラスタ/ベクター双方の配信候補 | Freeは非商用・商用製品の研究開発等。Flexは30 USD/月（税別）＋超過分 | 有償配信の候補 |
| Google Maps for Flutter | Android/iOSの地図SDKを利用できる | map IDなしの基本Maps SDKは無料枠が無制限。請求設定とAPIキーが必要。map IDありのDynamic MapsやPlaces/Routes等は別料金 | 費用だけで排除しない代案 |

比較の根拠:
- [flutter_map](https://docs.fleaflet.dev/)、[移動履歴の線](https://docs.fleaflet.dev/layers/polyline-layer)
- [Geoapify料金・商用無料条件](https://www.geoapify.com/pricing/)、[タイルのcredit単価](https://www.geoapify.com/pricing-details/)、[タイルと帰属表示](https://apidocs.geoapify.com/docs/maps/map-tiles/)
- [MapTiler料金](https://www.maptiler.com/cloud/pricing/)、[Freeの用途制限](https://www.maptiler.com/terms/cloud/)
- [Google料金](https://developers.google.com/maps/billing-and-pricing/pricing)、[map IDとSKUの区別](https://developers.google.com/maps/billing-and-pricing/sku-details)、[Flutter設定](https://developers.google.com/maps/flutter-package/config)

Geoapifyで通常タイルだけを使う場合、3,000 / 0.25 = 12,000タイル/日が無料枠の計算上の目安。利用者全体で共有する枠であり、1人当たりではない。8時間の旅行で何枚必要かは地図を開く時間、移動、ズーム、キャッシュで変わるため、無料で収まると断定しない。

flutter_mapは標準でラスタタイルを表示する。ラスタは地名が画像に焼き込まれており、アプリ側で自由に日英のラベルを切り替えられない。ガイド本文の日英切替とは別の論点。[表示方式の説明](https://docs.fleaflet.dev/)

## OSM公式配信を採用する場合の区別

OSMの地図データが利用できることと、tile.openstreetmap.orgを無制限に利用できることは別。

公式ラスタ配信は、帰属表示、アプリを識別するUser-Agent、HTTPヘッダーに沿ったキャッシュ等を要求する。大量取得・地域の事前保存・オフライン用ダウンロードは認められず、可用性保証もない。少人数の通常閲覧でも条件を満たす必要がある。[公式タイル利用方針](https://operations.osmfoundation.org/policies/tiles/)

LocalVoiceの標準配信元にはOpenFreeMap等の別サービスを検討する。OSM公式ラスタの方針を、OpenFreeMapや他社配信にそのまま適用しない。

## MVP実装方針案

1. MapLibre FlutterにOpenFreeMapのスタイルを設定する。最初の候補はLiberty。
2. GPSの最新有効点で現在地・精度円を描く。ガイド中だけ測位し、過去セッションの最終地点と区別する。
3. track APIとローカル記録を統合し、GPS欠損や異常点で分断した移動履歴を線で描く。
4. 現在地へ戻る、全履歴へのズーム、手動操作時の追従解除を実装する。
5. 地図配信のスタイルURL・帰属表示を設定で切り替えられるようにする。OSM/OpenMapTiles等、実際の配信に必要な帰属表示を画面で確認する。
6. 履歴の全件や個人プロフィールは地図配信元に送らず、線・現在地の重ね合わせは端末で行う。ただし背景地図のリクエストにはタイル座標・IP等が含まれる。

初期スタイルURL: https://tiles.openfreemap.org/styles/liberty
[公式導入説明](https://openfreemap.org/quick_start/)

背景地図の完全オフライン対応は既存MVP方針どおり必須にしない。MapLibreにオフライン機能があっても、配信元の取得・保存条件が別途必要。OpenFreeMapの事前大量取得が無条件に許されるとは解釈しない。[MapLibre機能](https://maplibre.org/flutter-maplibre-gl/)、[OpenFreeMap利用条件](https://openfreemap.org/tos/)

## 採用前の実機確認

- Android/iOSの両方で、宮島・広島・尾道・奈良の地図・地名が読めるか。
- 現在地追従、全履歴表示、日英ラベル変更が意図どおり動くか。
- 8時間相当の履歴を表示して、操作・再描画・アプリ復帰が重くならないか。
- 地図閲覧時間と通信量を記録し、背景動作と地図描画の電池消費を分けて確認する。
- 通信断、背景地図取得失敗、測位欠損、再送、履歴の再表示で誤った線や重複点が出ないか。
- 地図の帰属表示が操作ボタンに隠れないか。

実機で支障が出た場合は、実装の単純さを優先するならflutter_map + Geoapify、有償の配信契約が必要ならMapLibreのままMapTiler等への配信元変更を検討する。
