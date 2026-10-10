# ホーム画面の横長バナー

2026-10-10。組み込み image_gen で既存の `app/assets/s1/illustrations/home-discovery.png` を編集。出力は `app/assets/s1/illustrations/home-discovery-banner.png` に保存。

ホームでは縦横比2:1でコンテンツ幅いっぱいに表示。背景まで描かれた不透明画像で、元の透過挿絵は保持。アトラスからの切り出し対象ではなく、独立した素材。

## 生成プロンプト

```text
Use case: precise-object-edit
Asset type: LocalVoice mobile app home screen banner.
Input image: edit target, existing watercolor travel illustration.
Primary request: Recompose this illustration as a wide horizontal 2:1 landscape banner, 1536x768. Keep the folded street map, dark green headphones, pale cream house, trees, pastel blue and sage watercolor travel-journal style and hand-drawn outlines. Arrange these existing subjects naturally across the landscape frame with the map and headphones in the foreground, house and trees behind. Extend the existing scenery and a pale warm ivory watercolor paper background to fill every edge of the rectangle. This must look like a cohesive wide illustration made for full-width display, not a small centered cutout on a blank canvas. Keep all main objects comfortably inside the frame, visible at small mobile size. No people, text, lettering, logo, watermark, border or rounded corners. Opaque background.
```
