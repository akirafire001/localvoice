# LocalVoice MVP 技術設計 v0.1

対象: `product-spec-v0.1.md` / `implementation-feasibility-v0.1.md`

## 1. 目的
年末の実旅行で「位置と文脈に応じて、知らなかった面白い情報が自然に届く体験」を検証できる最小構成を定義する。全国対応や完全自動化より、宮島・広島・尾道・奈良等の実証対象地域で体験品質を確認することを優先する。

## 2. MVPスコープ

### P0: 年末PoC必須
1. Flutter Android/iOSアプリ
2. 旅行セッション開始/終了
3. GPS取得と位置履歴
4. 移動速度・進行方向の推定
5. 手動移動モード上書き
6. PostGISによる周辺KnowledgeItem検索
7. 日本語/英語の表示
8. 端末TTSによる読み上げ
9. アプリ内カード表示
10. OSローカル通知
11. 通知頻度制御とcooldown
12. 「もっと詳しく」
13. 「関連情報を増やす」
14. 「この話はもういい」
15. 長期趣向・セッション趣向・短期topic boost
16. セレンディピティ
17. 直近通知履歴とTripMemorySummary
18. 情報の出典・確度表示
19. 事前生成した英語コンテンツ
20. 最低限の利用ログ/コスト計測

### P1: PoCで余力があれば
- 自然言語による一時指示
- 「トイレ」「お腹が空いた」等のTemporaryState
- ホスト1台上の同行者プロフィール
- 天候/潮汐等のリアルタイムProvider
- 進行方向の短距離先読み
- ライセンス確認済み画像

### P2: 年末PoC後
- 複数端末グループ同期
- Google Calendar連携
- 本格的な店舗探索/営業情報
- map matching
- 音声クローン/著名人音声
- 全国自動Knowledge生成
- 課金

## 3. 全体アーキテクチャ

```text
Flutter App
  ├─ Location Service
  ├─ Motion Estimator
  ├─ Session State
  ├─ Local Cache
  ├─ Notification/TTS
  └─ API Client
        │ HTTPS/JSON
        ▼
Flask API
  ├─ Context Service
  ├─ Candidate Service
  ├─ Ranking Service
  ├─ Knowledge Service
  ├─ Feedback Service
  ├─ Trip Memory Service
  ├─ LLM Adapter
  └─ Provider Adapters
        │
        ▼
PostgreSQL + PostGIS
```

原則: GPSの生値を毎秒サーバーへ送らない。端末で短時間集約し、位置が一定距離変化した/一定時間経過した/状態変化した時だけContextSnapshotを送る。

## 4. 主要データモデル

### users
`id, locale, notification_level, detail_mode, serendipity_level, created_at`

### user_interests
`user_id, category, explicit_score, learned_score, knowledge_score, confidence, updated_at`

### trip_sessions
`id, user_id, purpose, started_at, ended_at, language, manual_transport_mode, memory_summary`

### participants
`id, trip_session_id, display_name, locale, home_region, profile_json`

MVPではアカウントを持たない同行者もホスト端末内のプロフィールとして扱える。

### context_snapshots
`id, trip_session_id, observed_at, position geography(Point,4326), accuracy_m, speed_mps, course_deg, inferred_transport_mode, confidence, context_json`

位置履歴は保持期間を設定し、不要な生ログを永久保存しない。

### knowledge_items
`id, canonical_key, title, category, body_ja, short_ja, body_en, short_en, position geography(Point,4326), radius_m, interestingness, novelty, confidence_level, fact_type, valid_from, valid_until, metadata_json`

### knowledge_sources
`id, knowledge_item_id, url, publisher, title, retrieved_at, source_type, reliability_score, license_info`

### knowledge_relations
`from_id, to_id, relation_type, weight`

### notification_history
`id, trip_session_id, knowledge_item_id, shown_at, channel, score, opened, spoken, feedback_type`

### topic_boosts
`id, trip_session_id, topic_key, strength, created_at, expires_at, decay_rate`

### temporary_states
`id, trip_session_id, state_type, payload_json, created_at, expires_at, source`

### intent_overrides
`id, trip_session_id, type, target, strength, created_at, expires_at, end_condition_json`

### api_usage_logs
`id, trip_session_id, provider, operation, request_units, estimated_cost, created_at`

## 5. PostGIS検索

基本検索は `ST_DWithin` を利用する。

探索半径の初期値例:
- 停止/徒歩: 300〜700m
- 自転車: 1〜2km
- 車: 3〜8km
- 高速移動: 5〜20km

値は固定仕様ではなくPoC調整値とする。候補取得後に距離、進行方向、趣向、重複等で再スコアリングする。

## 6. ContextSnapshot

Flutterから送る例:

```json
{
  "session_id": "uuid",
  "observed_at": "2026-12-28T15:30:00+09:00",
  "location": {"lat": 34.0, "lon": 132.0, "accuracy_m": 12},
  "motion": {"speed_mps": 1.2, "course_deg": 240, "transport_mode": "walking", "confidence": 0.83},
  "ui": {"detail_mode": "auto", "notification_level": "normal"},
  "active_topics": ["architecture"],
  "temporary_states": []
}
```

## 7. 候補選択パイプライン

1. PostGISで空間候補を取得
2. valid_from/valid_untilで期限切れ除外
3. 今日既に出した項目/類似項目を除外または減点
4. 距離スコア
5. 進行方向スコア
6. 長期interest
7. session interest
8. topic boost
9. timeliness
10. interestingness/novelty
11. repetition penalty
12. cooldown/通知上限判定
13. 上位候補だけ必要に応じLLMで再ランキング/表現調整
14. 閾値未満なら何も通知しない

初期スコア例:
`score = 0.25*location + 0.20*interest + 0.15*topic + 0.15*interestingness + 0.10*timeliness + 0.10*novelty + 0.05*direction - penalties`

係数はPoC計測用の初期値であり仕様確定値ではない。

## 8. 「黙る」ロジック

以下のどれかで通知を抑止する。
- 前回通知からcooldown未経過
- 1時間上限超過
- 候補scoreが閾値未満
- 同カテゴリ連続回数超過
- 同一/類似KnowledgeItem既出
- 「静かにして」状態
- GPS精度が悪く位置依存説明が危険

LLMに毎位置更新で問い合わせない。

## 9. 移動状態推定

端末側で直近60〜180秒の位置サンプルから速度中央値、最大速度、停止率、course変化を算出する。瞬間値では分類しない。

MVPの自動分類は `stationary / walking / cycling / motorized / high_speed` 程度に留める。車/バス/電車をGPSだけで断定しない。UIではユーザーが `auto / walk / bicycle / car / train / shinkansen / ship / other` を上書き可能にする。

## 10. 方向判定

速度が十分ある時はGPS courseを優先し、低速時は複数位置からbearingを算出する。方位のconfidenceが低い時は「右側」「左側」を文章に使わない。

候補へのbearingとの差分で前方/右/左を分類するが、建物や山が実際に見えるかは別問題なのでMVPでは「見えます」と断定せず「進行方向右手側にあります」等にする。

## 11. Flutter画面

### Home
- 「ガイドを開始」
- 現在の旅行/散歩目的
- 言語
- 通知頻度
- 情報量

### Guide
- 最新ガイドカード
- タイトル/本文/画像(任意)
- 確度
- 出典
- もっと詳しく
- 関連情報を増やす
- この話はもういい
- 音声再生/停止
- 現在有効なtopic/temporary stateチップ

### History
- 今日通知した内容を時系列表示
- 再表示/再読み上げ

### Preferences
- カテゴリ趣向
- セレンディピティ
- 通知頻度
- 言語
- 移動モード上書き

### Participants(P1)
- 同行者追加
- 言語/居住地域/簡易趣向

## 12. API設計

### Session
- `POST /api/v1/trips` 旅行開始
- `PATCH /api/v1/trips/{id}` 設定変更
- `POST /api/v1/trips/{id}/finish` 終了

### Context / Guide
- `POST /api/v1/trips/{id}/context` ContextSnapshot送信。通知候補がなければ `guide=null`
- `GET /api/v1/trips/{id}/history`

### Feedback
- `POST /api/v1/guides/{history_id}/feedback`
  - `more_detail`
  - `more_related`
  - `enough_topic`
  - `like`
  - `dislike`

### Preferences
- `GET/PATCH /api/v1/users/me/preferences`
- `GET/PATCH /api/v1/users/me/interests`

### Temporary/P1
- `POST /api/v1/trips/{id}/commands` 自然言語またはUIコマンド
- `DELETE /api/v1/trips/{id}/overrides/{override_id}`

## 13. LLM利用方針

LLMを必須にする箇所:
- 自然言語指示→structured intent(P1)
- 複数候補の最終的な「今面白い」再ランキング（候補が拮抗した場合のみ）
- 検証済み事実から状況に合った短文を作る
- TripMemorySummary更新

LLMを使わない箇所:
- 距離/方向/速度
- cooldown
- 重複排除
- 基本ランキング
- topic decay
- DB検索

LLMには原則として検証済みKnowledgeItemを与え、未知の事実を自由生成させない。

## 14. 日本語/英語

MVP対象地域の主要KnowledgeItemは事前に `ja/en` を生成・レビューしてDB保存する。実行時翻訳を標準経路にしない。動的文言だけ必要に応じ生成する。

## 15. TTS

MVPはFlutterからOS標準TTSを利用する。クラウドTTSは使わず、音声品質が体験上不足する場合にのみ比較検証する。これにより通知ごとのTTS API原価をほぼゼロにできる。

## 16. 情報信頼性

`fact_type`: `verified_fact / likely / tradition / legend / current_dynamic`

`confidence_level`: `high / medium / low`

Highの目安は公的/一次資料を含む複数根拠、Mediumは独立した複数根拠、伝承は事実確度とは別カテゴリとして扱う。機械的スコアだけでHighを決定しない。

## 17. Knowledge作成パイプライン

年末PoCでは全国自動生成を行わない。

1. 実証旅行ルート/地域を指定
2. 情報候補を収集
3. AIでカテゴリ化/要約/関連候補生成
4. 出典保存
5. 矛盾チェック
6. confidence/fact_type付与
7. 日本語短文/詳細文生成
8. 英語版生成
9. 人または別モデルでレビュー
10. DB投入

## 18. バックグラウンド動作

最もリスクが高い部分の一つ。MVPでは「旅行中にガイドモードを明示開始した時だけ」位置追跡を行う。常時追跡はしない。

端末側は距離フィルタ/時間フィルタを使い、サーバー送信頻度を抑える。OSによりバックグラウンド更新が間引かれることを前提とし、秒単位リアルタイム性を要件にしない。

## 19. キャッシュ/オフライン

旅行開始時またはWi-Fi時に、予定地域のKnowledgeItemを端末へ先読み可能な設計にする。MVPではSQLite/FlutterローカルDB等に最近のKnowledgeItemと履歴をキャッシュ。通信断時は既存KnowledgeItemだけで簡易ガイドを継続できることを将来目標とする。

## 20. プライバシー

- 旅行セッション開始時のみ位置利用
- 位置利用目的を明示
- 生GPS履歴の保存期間を設定
- 必要がなければ精密位置履歴を削除/集約
- 同行者プロフィールは必要最小限
- 「過去の居住地」等は任意入力
- 分析ログと個人情報を可能な限り分離

## 21. 観測性/PoC計測

最低限計測する:
- 旅行時間
- ContextSnapshot数
- 候補件数
- 通知件数
- 通知抑止件数/理由
- カテゴリ別通知数
- more_detail率
- more_related率
- enough_topic率
- 明示like/dislike
- LLM呼出回数/トークン/原価
- 外部API原価
- バッテリー開始/終了値（利用者申告または取得可能範囲）

## 22. 年末PoCの成功条件

技術成功だけでなく体験を評価する。

- 8時間利用して致命的な停止がない
- GPS/バックグラウンド制約で体験が破綻しない
- 通知が多すぎる/少なすぎるを調整可能
- 誤情報を事実として断定する重大事故がない
- 日本語/英語で意味が通る
- 「知らなかった。面白い」と感じる通知が一定割合ある
- API原価を測定できる

面白さの合格率はPoC後に数値化する。最初から恣意的な目標値を置かない。

## 23. 推奨実装順

1. PostgreSQL + PostGIS schema
2. KnowledgeItem投入用seed/管理スクリプト
3. Flask `/context` APIとPostGIS周辺検索
4. ranking/cooldown/重複排除
5. Flutter GPS + Guide画面
6. Flutter→API ContextSnapshot
7. 履歴/feedback
8. OS TTS
9. バックグラウンド位置
10. topic boost/セレンディピティ
11. 英語
12. TripMemorySummary
13. LLM再ランキング/表現生成
14. P1機能

重要: 最初からLLMを接続しない。固定KnowledgeItem＋ルールランキングでEnd-to-Endを完成させてからAIを差し込む。これによりAIなしでも成立する部分とAIによる改善量を比較できる。
