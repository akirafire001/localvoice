# LocalVoice MVP 技術設計 v0.1

対象: `product-spec-v0.1.md` / `implementation-feasibility-v0.1.md`

## 1. 目的
年末の実旅行で「位置と文脈に応じて、知らなかった面白い情報が自然に届く体験」を検証できる最小構成を定義する。宮島・広島・尾道・奈良等の実証対象地域では事前に作成・レビューしたKnowledgeItemで体験品質の基準を作り、それ以外の場所では実行時にLLMで出典付きのKnowledgeItemを生成して話題を届ける。全ユーザーの全旅行先を事前に作ることはできないため、MVPの最初から実行時のLLMを組み込む。詳細は[リアルタイムLLM設計](realtime-llm-design-v0.1.md)。

初期版はカメラや画像認識を使わない。話題選択の入力は位置情報・移動状況・ユーザーの興味等と事前に準備したKnowledgeItemであり、ユーザーの視界や目の前の対象物を認識することはMVPに含めない。

## 2. MVPスコープ

### P0: 年末PoC必須
1. Flutter Android/iOSアプリ
2. 旅行セッション開始/終了
3. GPS取得と位置履歴
4. 移動速度・進行方向の推定
5. 手動移動モード上書き
6. PostGISによる周辺KnowledgeItem検索
7. 日本語/英語の表示
8. 品質確認済みChirp 3 HD音声の再生、VoiceProvider、事前生成/キャッシュ、端末TTSへの代替
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
21. 現在地とセッション中の移動履歴の地図表示（終了後の見返しを含む）
22. Google / Apple / ID・パスワード認証、登録・ログアウト・復旧・連携
23. 個人データの所有者チェックとアプリ内アカウント削除
24. 実行時LLMによる候補の選択と状況に合わせた語り（黙る判断を含む）
25. 事前KnowledgeItemのない場所での、出典付きKnowledgeItemの実行時生成（セル単位・非同期）
26. 全通知判定の決定ログ、ガイドカードのワンタップ評価、LLM/ルール選択の切り替え

P0のコンテンツは名所の説明に限定せず、土地の小話を十分に用意する。学校沿革・過去ニュース・施設概要だけの項目を自動案内の主力にしない。詳細は[コンテンツ品質方針](content-quality-policy-v0.1.md)。Chirp 3 HD内の比較試聴と声・話速選択はP0に含める。MVPの通常TTS接続はChirp 3 HDに限定する。

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
- 全国の事前一括Knowledge生成（MVPは実行時のセル単位生成）
- 課金

## 3. 全体アーキテクチャ

```text
Flutter App
  ├─ Location Service
  ├─ Motion Estimator
  ├─ Session State
  ├─ Local Cache
  ├─ Notification / Audio Player / Device TTS Fallback
  └─ API Client
        │ HTTPS/JSON
        ▼
Flask API
  ├─ Authentication/Authorization Service
  ├─ Context Service
  ├─ Candidate Service
  ├─ Ranking Service
  ├─ Knowledge Service
  ├─ Feedback Service
  ├─ Trip Memory Service
  ├─ Guide Selector（LLM選択・語り、検証、フォールバック）
  ├─ LLM Adapter（Claude API）
  ├─ Knowledge Generation Worker（実行時知識生成ジョブ）
  ├─ Voice Service / Audio Cache
  └─ Provider Adapters（Wikipedia / Wikidata / OSM / web検索 / Google Cloud TTS・Chirp 3 HD）
        │
        ▼
PostgreSQL + PostGIS
```

原則: GPSの生値を毎秒サーバーへ送らない。端末で短時間集約し、位置が一定距離変化した/一定時間経過した/状態変化した時だけContextSnapshotを送る。

## 4. 主要データモデル

### users
`id, display_name, status, recovery_email, recovery_email_verified_at, locale, notification_level, detail_mode, serendipity_level, voice_settings_json, created_at`

### 認証データ
`auth_identities`, `password_credentials`, `auth_sessions`, `auth_refresh_tokens`, `auth_action_tokens`, `auth_challenges`, `apple_credentials`, `oauth_revocation_jobs` を利用する。Google/Appleの検証済みsubとLocalVoiceの正規化login_idを内部user_idへ紐づけ、パスワードはArgon2id、LocalVoiceのセッションtokenはランダム値のハッシュとして保存する。Appleの状態確認・取り消し用refresh tokenはサーバーで暗号化保存し、秘密鍵・暗号鍵はDB/アプリ/Gitと分離する。[認証設計](authentication-design-v0.1.md)・[Database設計](database-design-v0.1.md)参照。

### user_interests
`user_id, category, explicit_score, learned_score, knowledge_score, confidence, updated_at`

### trip_sessions
`id, user_id, purpose, started_at, ended_at, language, manual_transport_mode, selection_mode, memory_summary`

### participants
`id, trip_session_id, display_name, locale, home_region, profile_json`

MVPではアカウントを持たない同行者もホスト端末内のプロフィールとして扱える。

### context_snapshots
`id, trip_session_id, client_event_id, observed_at, position geography(Point,4326), accuracy_m, speed_mps, course_deg, inferred_transport_mode, confidence, context_json`

位置履歴は保持期間を設定し、不要な生ログを永久保存しない。`client_event_id` は端末で採番するUUIDで、`(trip_session_id, client_event_id)` を一意にして再送時の記録点・通知の重複を防ぐ。地図用のサーバー履歴は `context_snapshots` を再利用する。

### knowledge_items
`id, canonical_key, title, category, body_ja, short_ja, body_en, short_en, position geography(Point,4326), radius_m, interestingness, novelty, confidence_level, fact_type, valid_from, valid_until, origin, review_status, area_cell, generated_by, metadata_json`

`origin` は `curated`（事前作成）/ `generated`（実行時生成）。

### knowledge_claims
`id, knowledge_item_id, claim_text_ja, claim_text_en, source_ids, created_at`

実行時生成では主張ごとに出典を持たせ、出典のない主張は保存しない。

### area_coverage / knowledge_generation_jobs
セル（geohash）ごとの生成状況と、非同期生成ジョブのキュー。

`metadata_json`に小話の分類、土地との関係、面白さの理由、現在とのつながり、音声用原稿・版を保持する。詳細は[コンテンツ品質方針](content-quality-policy-v0.1.md)。音声資産は`audio_assets`で本文・読み・声・モデル・利用範囲の版と対応づける。[音声設計](voice-design-v0.1.md)参照。

### knowledge_sources
`id, knowledge_item_id, url, publisher, title, retrieved_at, source_type, reliability_score, license_info`

### knowledge_relations
`from_id, to_id, relation_type, weight`

### notification_history
`id, trip_session_id, knowledge_item_id, guide_decision_id, shown_at, channel, score, rendered_text, selection_mode, opened, spoken, feedback_type, rating`

### guide_decisions
`id, trip_session_id, context_snapshot_id, decided_at, candidates_json, rule_choice_id, llm_choice_id, final_action, reason, selection_mode, llm_model, latency_ms, estimated_cost`

黙った判定も含めて記録し、旅行後の比較・リプレイに使う。

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

地域の小話は`position + radius_m`で適用範囲を定義する。近隣POI検索に加え、利用者がその適用範囲内にいる地域項目も取得して統合・重複排除する。探索半径の外に代表座標があっても適用範囲内なら候補になり、範囲外の一般的な話を量のために混ぜない。[DB設計](database-design-v0.1.md)参照。

## 6. ContextSnapshot

Flutterから送る例:

```json
{
  "session_id": "uuid",
  "client_event_id": "uuid",
  "observed_at": "2026-12-28T15:30:00+09:00",
  "location": {"lat": 34.0, "lon": 132.0, "accuracy_m": 12},
  "motion": {"speed_mps": 1.2, "course_deg": 240, "transport_mode": "walking", "confidence": 0.83},
  "ui": {"detail_mode": "auto", "notification_level": "normal"},
  "active_topics": ["architecture"],
  "temporary_states": []
}
```

## 7. 候補選択パイプライン

1. PostGISで空間候補を取得。近くの施設だけでなく適用範囲内の地域の小話も含める
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
13. 閾値未満なら何も通知しない（LLMを呼ばない）
14. 上位N件（初期値5）をLLMに渡し、話す1件を選ぶか黙るかを決め、状況に合わせた文章を作る
15. サーバーでLLM出力を検証し、不合格・タイムアウト時はルール1位の保存済み本文へフォールバック

初期スコア例:
`score = 0.25*location + 0.20*interest + 0.15*topic + 0.15*interestingness + 0.10*timeliness + 0.10*novelty + 0.05*direction - penalties`

係数はPoC計測用の初期値であり仕様確定値ではない。

通常の自動案内はコンテンツのレビュー結果`auto_eligible=true`を必要とする。沿革だけ・関連の薄い過去ニュース・汎用的な施設概要は、距離が近くてもこの条件を満たさない。明示質問・実用情報は別経路で扱う。趣向外の候補も品質条件を満たすものから選ぶ。候補不足を記録し、地域の小話へ探索を広げても不足する場合は通知しない。詳細は[コンテンツ品質方針](content-quality-policy-v0.1.md)。

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

候補へのbearingとの差分で前方/右/左を分類する。MVPはカメラや画像認識を使わず、建物や山の視認可能性は判定しない。「進行方向右手側、約○mの位置にあります」等、GPSとKnowledgeItemの座標から求めた位置関係として表現する。「見えます」「目の前にあります」等、ユーザーの視界を前提とする案内は行わない。

## 11. Flutter画面

### Login / Account（P0）
- Googleでログイン / Appleでログイン / ID・パスワードでログイン / ID新規登録
- 任意の復旧用メール登録・確認、パスワード再設定
- 設定からログイン方法の連携・解除、ログアウト、アカウント削除
- 認証切れからの復帰、アカウント切替時の位置履歴隔離

### Home
- 「ガイドを開始」
- 現在の旅行/散歩目的
- 言語
- 通知頻度
- 情報量

### Guide
- 最新ガイドカード
- 上部約3分の1のミニ地図（現在地・移動履歴・今の話の地点/地域）。タップでMapを全画面表示
- タイトル/本文/画像(任意)
- 確度
- 出典
- もっと詳しく
- 関連情報を増やす
- この話はもういい
- 次の話（現在の案内のスキップ。topic boost終了とは分ける）
- 音声再生/停止
- 現在有効なtopic/temporary stateチップ

詳細文を展開すると地図を細いプレビューへ縮める。Guide/詳細/Mapの切替は同じ音声再生状態を利用し、画面遷移だけで再生を停止・重複開始しない。新しい案内へスキップした時は現在の再生要求と遅着音声を無効化する。地図の適用範囲はKnowledgeItemの確認済みposition/radius_mを利用し、将来の面geometry未実装時に精密な地域境界として見せない。[Flutter UX](flutter-ux-design-v0.1.md)参照。

### History
- 今日通知した内容を時系列表示
- 再表示/再読み上げ

### Map（P0）
- ガイド中の端末の最新測位による現在地マーカー、精度円、最終更新時刻
- 今の話の地点/地域とコンパクトな音声プレイヤー（案内中のみ）
- セッション内の記録点を時刻順に結んだ移動履歴
- 現在地へ戻る/移動範囲全体を表示
- GuideとHistoryから開く。保存期間内の終了済みセッションも選択可能
- 測位の長い欠損や異常点の前後は線を分断し、道路・線路への補正は行わない

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

### Authentication / Account
- `POST /api/v1/auth/register`, `/auth/login`, `/auth/google`, `/auth/apple`
- Apple認証開始・Webコールバック・一回限りの結果引き渡し
- `POST /api/v1/auth/refresh`, `/auth/logout`, `/auth/reauthenticate`
- `GET/DELETE /api/v1/users/me`
- Google/Apple連携・解除、ID/パスワード追加・変更、復旧用メール確認・パスワード再設定
- 公開する認証・復旧エンドポイント以外はLocalVoice tokenによる本人認証とデータ所有者の検証を必須にする。[API設計](api-design-v0.1.md)参照。

### Session
- `POST /api/v1/trips` 旅行開始
- `PATCH /api/v1/trips/{id}` 設定変更
- `POST /api/v1/trips/{id}/finish` 終了

### Context / Guide
- `POST /api/v1/trips/{id}/context` ContextSnapshot送信。通知候補がなければ `guide=null`
- `GET /api/v1/trips/{id}/history`
- `GET /api/v1/trips/{id}/track` 地図用の時刻順位置履歴。期間指定とカーソルページングに対応

### Feedback
- `POST /api/v1/guides/{history_id}/feedback`
  - `more_detail`
  - `more_related`
  - `enough_topic`
  - `like`
  - `dislike`
  - `interesting` / `knew_it` / `not_interesting` / `wrong_info`（ワンタップ評価）
  - `skip_story`（現在の案内を止め、最新contextから別の適格な小話を要求。topic/長期趣向の変更とは分ける）

### Preferences
- `GET/PATCH /api/v1/users/me/preferences`
- `GET/PATCH /api/v1/users/me/interests`

### Temporary/P1
- `POST /api/v1/trips/{id}/commands` 自然言語またはUIコマンド
- `DELETE /api/v1/trips/{id}/overrides/{override_id}`

## 13. LLM利用方針

MVPの最初から実行時のLLMを使う。詳細・モデル選定・フォールバックは[リアルタイムLLM設計](realtime-llm-design-v0.1.md)を正本とする。

LLMを使う箇所（P0）:
- ルールで絞った上位候補から「今話すもの」または「黙る」を選ぶ（通知可能とルールで判定された時のみ）
- 出典付きの事実から、移動状態・方位・直前の話題・趣向に合わせた短文/読み上げ文を作る
- 事前KnowledgeItemのない場所で、Wikipedia・Wikidata・OSM等の素材から出典付きKnowledgeItemを生成する（非同期）
- TripMemorySummary更新

LLMを使う箇所（P1）:
- 自然言語指示→structured intent

初期値: Anthropic Claude API、モデル `claude-opus-5-5`、選択・語りはeffort `low`、知識生成はeffort `medium`。LLM Adapterで差し替え可能にし、PoCで遅延・原価・品質を測って見直す。

LLMを使わない箇所:
- 距離/方向/速度
- cooldown
- 重複排除
- 基本ランキング
- topic decay
- DB検索

LLMには出典付きの素材・KnowledgeItemだけを与え、素材にない事実を自由生成させない。出力はサーバーで検証し、失敗時はルール結果へフォールバックしてガイドを止めない。

## 14. 日本語/英語

MVP対象地域の主要KnowledgeItemは事前に `ja/en` を生成・レビューしてDB保存する。実行時生成のKnowledgeItemは生成時に `ja/en` を同時に作る。通知文は選択・語りのLLMが利用者の言語で作る。

## 15. TTS

MVPのTTSはGoogle Cloud Text-to-SpeechのChirp 3 HDを採用する（2026-10-06決定）。日本語・英語の具体的な声は同サービス内の試聴で選び、運営の許可リストとして管理する。他サービスは比較メモに将来候補として残す。端末TTSは比較基準と通信断・障害時等の代替とする。

FlaskのVoiceProviderはGoogle公式Pythonクライアントの`synthesize_speech`でテキストからMP3を生成し、完成したファイルを保存・配信する。MVPではストリーミング合成を必須にしない。接続先は`global`を初期値とし、地域変更は利用可否・条件・待ち時間を確認して設定で切り替える。Google Cloud認証はサーバー側のApplication Default Credentials（実行環境のサービスアカウント等）を使い、認証情報をFlutterへ渡さない。

静的な日英小話は原稿と読みをレビューして事前生成する。Flutterは音声ファイルを再生し、Flask側のVoiceProviderが生成・キャッシュ・配信を管理する。個人化した原稿だけ必要時に生成し、個人用音声を共有キャッシュへ混ぜない。キーは本文版・音声用原稿hash・読み辞書版・言語・モデル/声・スタイル/速度・利用範囲を含む。期限切れ本文の音声を再生しない。

生成待ちには期限を設け、キャッシュ→利用者が許可した端末TTS→文字表示の順で劣化動作を選ぶ。停止/スキップ/終了後に遅着した音声を勝手に再生しない。API契約、商用配信・保存条件、事前生成、費用、試聴項目の正本は[音声設計](voice-design-v0.1.md)。

## 16. 情報信頼性

`fact_type`: `verified_fact / likely / tradition / legend / current_dynamic`

`confidence_level`: `high / medium / low`

Highの目安は公的/一次資料を含む複数根拠、Mediumは独立した複数根拠、伝承は事実確度とは別カテゴリとして扱う。機械的スコアだけでHighを決定しない。

## 17. Knowledge作成パイプライン

2系統で作る。

### 17.1 事前作成（curated）
実証対象地域で体験品質の基準を作るため、旅行前に作成・レビューする。

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

レビューで「土地との関係・面白さの理由・具体性・話題の種類」を確認し、自動案内への採用可否と保留理由を保存する。根拠と面白さを別に評価する。採用した日英原稿は読みを確認し、選定音声で事前生成・試聴する。

### 17.2 実行時生成（generated）
事前作成のない場所では、現在地と進行方向の先のセルについて非同期ジョブで生成する。全国を事前に一括生成はしない。

1. セルのカバレッジを確認し、未生成ならジョブを積む
2. Wikipedia（ja/en）・Wikidata・OSMから素材を取得（不足時のみweb検索）
3. LLMで構造化し、主張ごとに出典IDを付与（出典のない主張は破棄）
4. confidence/fact_typeをルールで付与
5. コンテンツ品質方針の採用条件を機械判定し、通ったものだけ `auto_eligible=true`（`reviewer=auto`）にする
6. `origin=generated, review_status=unreviewed` で保存し、全ユーザーで共有
7. `wrong_info` 報告で配信停止・レビュー待ちにする

## 18. バックグラウンド動作

最もリスクが高い部分の一つ。MVPでは「旅行中にガイドモードを明示開始した時だけ」位置追跡を行う。常時追跡はしない。

端末側は距離フィルタ/時間フィルタを使い、サーバー送信頻度を抑える。OSによりバックグラウンド更新が間引かれることを前提とし、秒単位リアルタイム性を要件にしない。

## 19. キャッシュ/オフライン

旅行開始時またはWi-Fi時に、予定地域のKnowledgeItemと利用条件の確認済み音声を端末へ先読み可能な設計にする。MVPではSQLite/FlutterローカルDB等に最近のKnowledgeItem・履歴と音声ファイルをキャッシュする。MVPで通信断時の保存済み音声再生を検証する。通信断時に新しい地域へ移動しても継続する全面的なオフラインガイドは将来目標とする。

### 19.1 地図用位置履歴
- ガイド中の最新の現在地は端末の測位値を利用し、サーバーの最終記録点を現在地として扱わない。ガイド終了後は保存済み履歴を表示し、地図の閲覧だけでは新たな測位を開始しない。
- ContextSnapshot用に間引いた記録点を、送信前に端末へ保存する。移動履歴の記録間隔とサーバー送信頻度を地図のために毎秒へ引き上げない。
- 各点にセッションID、client_event_id、観測時刻、緯度経度、測位精度を保持する。未送信点は通信回復後に既存context APIへ再送する。
- サーバーはcontext_snapshotsからtrack APIで履歴を返す。端末はclient_event_idでローカルの未送信点と統合し、observed_at順に描画する。
- セッションIDと開始/終了時刻を端末に保持し、保存期間内のセッションをMapで選択できるようにする。
- 通信回復後と終了済みセッションを開く時はtrack APIから履歴を再取得する。ページングカーソルは一覧取得用であり、遅れて届いた記録点を検出する増分同期には使わない。
- 連続点の時刻差が5分を超える場合は線を分断する（PoC用初期値、調整可能）。異常座標や明らかな測位飛びは描画から除外し、前後の線もつながない。異常判定の精度・速度閾値は実機PoCで調整する。
- 地図方式の推奨案はMapLibre Flutter + OpenFreeMap（OSM系ベクター地図）。採用確定はAndroid/iOSの実機確認後とし、利用条件・帰属表示・配信の可用性・原価・キャッシュ制約を確認する。[比較検討](map-provider-comparison-v0.1.md)参照。オフライン背景地図はMVPの必須条件にしない。

## 20. プライバシー

Google・Apple・ID／パスワードの3方式をMVPから提供する。Google/Apple ID tokenをサーバーで検証してLocalVoiceのログインセッションを発行する。Appleではnonce/stateと認可コードの検証、メール非公開、連携解除時のApple token取り消しも扱う。旅行セッションとは別に、ログインセッションの期限・refresh・失効を管理する。ログアウト/アカウント切替時は位置取得を停止し、キャッシュ・未送信位置をuser_idごとに隔離する。詳細は[認証設計](authentication-design-v0.1.md)。

- 旅行セッション開始時のみ位置利用
- 位置利用目的を明示
- 生GPS履歴の保存期間を設定し、地図用の端末キャッシュとサーバー記録にも同じ保持方針を適用
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
- ワンタップ評価（interesting / knew_it / not_interesting / wrong_info）の率。curated/generated別、llm/rule別
- LLMが黙ることを選んだ件数、検証失敗・タイムアウトによるフォールバック件数
- `/context` 応答時間（p50/p95）と知識生成ジョブの所要時間
- LLM呼出回数/トークン/原価
- 外部API原価
- 自動案内の保留理由、名所以外の小話数、話題の種類、場所による候補不足
- 声・モデル別の聞き心地/誤読/声への停止反応、生成待ち時間、キャッシュ率、音声秒数と生成原価
- バッテリー開始/終了値（利用者申告または取得可能範囲）

## 22. 年末PoCの成功条件

技術成功だけでなく体験を評価する。

- 3認証方式と連携で同じ本人の履歴を利用でき、他人のtrip/track/feedbackへアクセスできない
- iOS/AndroidのAppleログイン、メール非公開、nonce/state不一致の拒否、解除・削除時の取り消しを確認できる
- token更新、通信断、ログアウト、アカウント切替で履歴が混ざらない
- 8時間利用して致命的な停止がない
- GPS/バックグラウンド制約で体験が破綻しない
- 現在地とセッション内の移動履歴を地図で確認でき、通信断・測位欠損・再送・終了後の再表示でも誤った連続経路や重複点を描かない
- 通知が多すぎる/少なすぎるを調整可能
- 誤情報を事実として断定する重大事故がない
- 日本語/英語で意味が通る
- 「知らなかった。面白い」と感じる通知が一定割合ある
- よく話す設定で土地の小話が豊富に届き、沿革・過去ニュースの羅列や類似話題で埋まらない
- 日英の声・地名の読み・長時間の聞き心地を比較評価し、採用音声と不採用理由を記録できる
- 事前作成のない場所でも出典付きのガイドが届き、curated/generated別に評価を比較できる
- LLMの選択とルール1位の選択を、同じ旅行の決定ログで比較・リプレイできる
- LLMの障害・遅延時もルール結果へフォールバックしてガイドが止まらない
- API原価（特に1人8時間あたりのLLM原価）を測定できる

面白さの合格率はPoC後に数値化する。最初から恣意的な目標値を置かない。

## 23. 推奨実装順

前提として、schemaに認証テーブルを含め、個人データのAPIを端末から利用する前に認証・認可を実装する。ID・パスワード登録/ログイン、Google/Apple ID token検証、token更新/失効、所有者チェックを先行する。Google OAuthクライアント、Apple App ID/Services ID・キー・戻り先の設定は実装時に行う。

1. PostgreSQL + PostGIS schema（guide_decisions・area_coverage・生成ジョブを含む）
2. KnowledgeItem投入用seed/管理スクリプト（少数の実証地域分）
3. Flask `/context` APIとPostGIS周辺検索
4. ranking/cooldown/重複排除
5. LLM Adapterと選択・語り（検証・タイムアウト・フォールバック、決定ログ）
6. Flutter GPS + Guide画面（ワンタップ評価を含む）
7. Flutter→API ContextSnapshot
8. 実行時知識生成ジョブ（Wikipedia/Wikidata/OSM素材→LLM構造化）
9. 履歴/feedback
10. 地図画面と現在地・移動履歴、ローカル記録/track API/再送・重複排除
11. Chirp 3 HD内の声の比較試聴、Google Cloud VoiceProvider/音声再生/キャッシュ/端末TTS代替
12. バックグラウンド位置
13. topic boost/セレンディピティ
14. 英語
15. TripMemorySummary
16. LLM/ルール選択の切り替えと決定ログのリプレイ
17. P1機能

重要: LLMはMVPの最初から接続する。ただしルール側（候補抽出・cooldown・重複排除・フォールバック）を先に用意し、LLMはその上に載せる。全通知判定でルール1位とLLMの選択を両方記録するため、ルールのみの場合との差を同じ旅行のデータで比較できる。
