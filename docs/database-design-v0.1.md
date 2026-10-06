# LocalVoice Database設計 v0.1

## 方針
PostgreSQL + PostGISをMVPから採用する。位置付き知識、利用者趣向、旅行セッション、短期興味、通知履歴、出典、API原価を分離する。

## 主要テーブル

### users
- id UUID PK
- display_name varchar(100) nullable
- status varchar(20)（active / disabled）
- recovery_email text nullable（任意、Google/Appleメールとは独立）
- recovery_email_verified_at timestamptz nullable
- locale varchar(10)
- notification_level varchar(20)
- detail_mode varchar(20)
- serendipity_level varchar(20)
- voice_settings_json jsonb（言語別voice_profile_id、再生速度、端末TTS代替の許可）
- created_at timestamptz

### auth_identities
- id UUID PK
- user_id UUID FK
- provider varchar(32)（MVP: google / apple）
- subject varchar(255)（検証済みGoogle/Apple sub）
- status varchar(32)（active / revoked / pending_revocation）
- created_at timestamptz

Unique: `(provider, subject)`, `(user_id, provider)`。メールアドレスをGoogle/Apple識別子として使わず、メール一致で自動連携しない。Appleの非公開中継メールも識別子にはしない。

### password_credentials
- user_id UUID PK/FK
- login_id varchar(100)
- login_id_normalized varchar(100) UNIQUE NOT NULL
- password_hash text NOT NULL（Argon2id、ソルトとパラメータを含む）
- updated_at timestamptz

Google/Appleだけの利用者には行を作らない。ログインIDと表示名・復旧用メール・内部UUIDは別の値。IDの文字/長さ/正規化ルールを登録・ログイン・DBで統一する。

### auth_sessions
- id UUID PK
- user_id UUID FK
- access_token_hash varchar(64) UNIQUE
- access_expires_at timestamptz
- authenticated_via varchar(32)
- last_reauthenticated_at timestamptz
- expires_at timestamptz（ログインから30日の絶対期限、初期値）
- revoked_at timestamptz nullable
- created_at timestamptz

旅行セッションとは別のログインセッション。access tokenはランダム値のSHA-256ハッシュで検索し、本人・期限・失効状態を照合する。refresh交換時は新access tokenのハッシュと期限を更新する。

### auth_refresh_tokens
- id UUID PK
- auth_session_id UUID FK
- token_hash varchar(64) UNIQUE NOT NULL
- expires_at timestamptz
- consumed_at timestamptz nullable
- replaced_by UUID FK nullable
- created_at timestamptz

ランダムなrefresh tokenのSHA-256ハッシュのみ保存する。一回使用後も絶対期限まではハッシュを保持して再利用を検出し、再利用時は親auth_sessionsを失効する。交換はトランザクションで処理する。

### auth_challenges（Apple認証用）
- id UUID PK
- purpose varchar(32)（login / link / reauthenticate）
- user_id UUID FK nullable（連携・再認証時は必須）
- client_kind varchar(16)（ios / android）
- expected_audience varchar(255)
- nonce_hash / state_hash varchar(64)
- app_code_challenge varchar(64)（引き渡し用code_verifierのSHA-256）
- result_ciphertext text nullable（Webコールバックの検証済み一時結果）
- handoff_code_hash varchar(64) nullable
- expires_at / consumed_at timestamptz

短期限・一回限り。目的と認証済み本人を変更して再利用できない。nativeではnonce、Webではnonce/stateを照合し、Androidのアプリ復帰ではhandoff codeとcode_verifierも検証する。期限切れの一時結果は削除し、交換済みApple tokenが残る場合は取り消し処理へ渡す。

### apple_credentials
- auth_identity_id UUID PK/FK
- apple_client_id varchar(255)
- refresh_token_ciphertext text NOT NULL
- encryption_key_id varchar(100)
- last_verified_at timestamptz nullable

Apple側の認証状態確認・revokeに利用するため、refresh tokenを暗号化保存する。暗号鍵はDB外で管理する。LocalVoiceのrefresh tokenのハッシュ保存とは区別する。

### oauth_revocation_jobs
- id UUID PK
- provider varchar(32)（MVP: apple）
- client_id varchar(255)
- token_ciphertext text
- encryption_key_id varchar(100)
- attempts integer
- next_attempt_at timestamptz
- created_at timestamptz

Apple解除・アカウント削除時のrevoke一時失敗の再試行用。ユーザー削除後も必要最小限の取り消し処理を続けられるよう、user_idの必須FKは持たない。Apple側の取り消しを確認したら暗号化tokenと処理行を削除する。

### auth_action_tokens
- id UUID PK
- user_id UUID FK
- purpose varchar(32)（verify_email / password_reset）
- token_hash varchar(64) UNIQUE NOT NULL
- target_email text nullable（確認対象メール）
- expires_at timestamptz
- consumed_at timestamptz nullable
- created_at timestamptz

メール確認・再設定tokenは用途・user_id・対象メールに紐づけ、短期限・一回限りで検証する。メール変更依頼の再発行時は旧確認tokenを失効する。password_resetは既存password_credentialsがある場合だけ発行する。

### user_interests
- user_id UUID FK
- category varchar(64)
- explicit_score numeric
- learned_score numeric
- knowledge_score numeric
- confidence numeric
- updated_at timestamptz
- PK(user_id, category)

### trip_sessions
- id UUID PK
- user_id UUID FK
- purpose varchar(32)
- language varchar(10)
- started_at/ended_at timestamptz
- manual_transport_mode varchar(32) nullable
- selection_mode varchar(8) default 'llm'
- memory_summary text
- settings_json jsonb

### participants
- id UUID PK
- trip_session_id UUID FK
- display_name varchar(100)
- locale varchar(10)
- home_region varchar(200)
- profile_json jsonb

### context_snapshots
- id bigserial PK
- trip_session_id UUID FK
- client_event_id UUID NOT NULL（端末採番、再送でも同じ値）
- observed_at timestamptz
- position geography(Point,4326)
- accuracy_m numeric
- speed_mps numeric
- course_deg numeric
- inferred_transport_mode varchar(32)
- confidence numeric
- context_json jsonb

Index: `GIST(position)`, `(trip_session_id, observed_at, id)`

Unique: `(trip_session_id, client_event_id)`

MVPの地図用移動履歴はこのテーブルを再利用する。セッションと期間を指定し、`observed_at, id` の昇順で記録点を取得する。緯度経度は `ST_Y(position::geometry)` / `ST_X(position::geometry)` として返す。端末の現在地は最新の端末測位値であり、サーバーの最終記録点とは区別する。

### knowledge_items
- id UUID PK
- canonical_key varchar(200) UNIQUE
- title varchar(300)
- category varchar(64)
- body_ja text / short_ja text
- body_en text / short_en text
- position geography(Point,4326) nullable
- radius_m integer
- interestingness numeric
- novelty numeric
- confidence_level varchar(16)
- fact_type varchar(32)
- valid_from/valid_until timestamptz nullable
- origin varchar(16): `curated`（事前作成）/ `generated`（実行時生成）
- review_status varchar(16): `reviewed` / `unreviewed` / `suspended`（`wrong_info` 報告で配信停止）
- area_cell varchar(12) nullable: 生成元のgeohashセル
- generated_by jsonb nullable: 生成に使ったモデル・プロンプト版・生成日時
- metadata_json jsonb
- created_at/updated_at timestamptz

Index: `GIST(position)`, `(category)`, `(valid_until)`, `(area_cell)`

候補検索では `review_status <> 'suspended'` を条件に加える。

### knowledge_claims
- id UUID PK
- knowledge_item_id UUID FK
- claim_text_ja text / claim_text_en text
- source_ids UUID[]（knowledge_sources.id。空は不可）
- created_at timestamptz

実行時生成のKnowledgeItemは主張単位で出典を持つ。LLMの選択・語りは `used_claim_ids` でここを参照し、サーバーが出典のない事実の混入を検証する。

### area_coverage
- area_cell varchar(12) PK
- status varchar(16): `none` / `queued` / `generating` / `done` / `failed`
- item_count integer
- generated_at / expires_at timestamptz nullable

### knowledge_generation_jobs
- id UUID PK
- area_cell varchar(12)
- priority integer（現在地 > 進行方向の先）
- status varchar(16)
- attempts integer
- error text nullable
- created_at / started_at / finished_at timestamptz

MVPのジョブキューはこのテーブルとワーカープロセスで実装する（`FOR UPDATE SKIP LOCKED` で取得）。

`metadata_json.story_quality`に`content_kind, why_here, interest_hook, present_connection, auto_eligible, hold_reason, reviewed_at, reviewer, review_version`を保持する。本文/言語ごとの音声用原稿と読み辞書の版も保持する。通常の自動案内では採用レビュー済みの`auto_eligible=true`だけを使う。[コンテンツ品質方針](content-quality-policy-v0.1.md)参照。

### audio_assets
- id UUID PK
- knowledge_item_id UUID FK nullable
- owner_user_id UUID FK nullable（個人用では必須）
- trip_session_id UUID FK nullable（個人用音声の利用範囲）
- scope varchar(16)（shared / private）
- cache_key varchar(64) UNIQUE（原稿/読み/声/モデル/形式/利用範囲を含むhash）
- content_version text / speech_text_hash varchar(64) / pronunciation_version text
- language varchar(10)
- provider / model / model_version / voice_profile_id / voice_version text
- synthesis_settings_json jsonb（スタイル・合成時の速度等）
- status varchar(16)（pending / ready / failed / invalidated）
- storage_key text nullable（永続の公開URLではない）
- audio_format varchar(32) / duration_ms integer nullable
- attribution_json jsonb / terms_version text（選定声の確認済み条件）
- valid_until timestamptz nullable / retention_until timestamptz nullable
- created_at/updated_at timestamptz

共有は個人情報を含まない静的原稿だけに限定する。privateはowner_user_id必須でuser/trip範囲をcache_keyに含め、所有者を照合して配信する。共有の事前生成費用はapi_usage_logsのtrip_session_id=nullで記録し、利用者ごとの生成費と区別する。Provider内のジョブ・再試行は冪等な同一資産の処理として扱う。

### knowledge_sources
- id UUID PK
- knowledge_item_id UUID FK
- url text
- publisher text
- title text
- retrieved_at timestamptz
- source_type varchar(32)
- reliability_score numeric
- license_info text

### knowledge_relations
- from_id UUID FK
- to_id UUID FK
- relation_type varchar(64)
- weight numeric
- PK(from_id,to_id,relation_type)

### notification_history
- id UUID PK
- trip_session_id UUID FK
- knowledge_item_id UUID FK
- shown_at timestamptz
- channel varchar(16)
- score numeric
- score_components jsonb
- guide_decision_id UUID FK
- rendered_text text（LLMが作った、または保存済みの実際の通知文）
- selection_mode varchar(8): `llm` / `rule`
- opened boolean
- spoken boolean
- feedback_type varchar(32) nullable
- rating varchar(16) nullable: `interesting` / `knew_it` / `not_interesting` / `wrong_info`
- speech_snapshot_json jsonb nullable（案内の確定音声原稿・本文版・言語）
- audio_asset_id UUID FK nullable

案内ごとの確定原稿を音声生成に使い、クライアントから任意の読み上げ本文は受け取らない。音声資産が期限切れ/訂正で無効化された場合は、履歴の旧音声をそのまま再生しない。[音声設計](voice-design-v0.1.md)参照。

### guide_decisions
- id UUID PK
- trip_session_id UUID FK
- context_snapshot_id UUID FK
- decided_at timestamptz
- candidates_json jsonb（候補ID・ルールスコア内訳）
- rule_choice_id UUID nullable（ルール1位）
- llm_choice_id UUID nullable
- final_action varchar(16): `speak` / `silent`
- reason varchar(32)
- selection_mode varchar(8)
- fallback boolean
- llm_model varchar(64) nullable
- prompt_version varchar(32) nullable
- latency_ms integer nullable
- estimated_cost numeric(12,6) nullable

黙った判定も含め、通知判定をしたすべての時点を記録する。旅行後のLLM/ルール比較とリプレイに使う。精密位置は `context_snapshots` 側にあり、保持期間の削除方針に従う。

### topic_boosts
- id UUID PK
- trip_session_id UUID FK
- topic_key varchar(100)
- strength numeric
- created_at/expires_at timestamptz
- decay_rate numeric

### temporary_states
- id UUID PK
- trip_session_id UUID FK
- state_type varchar(64)
- payload_json jsonb
- created_at/expires_at timestamptz
- source varchar(32)

### intent_overrides
- id UUID PK
- trip_session_id UUID FK
- type varchar(64)
- target varchar(200)
- strength numeric
- created_at/expires_at timestamptz
- end_condition_json jsonb

### api_usage_logs
- id bigserial PK
- trip_session_id UUID FK nullable
- provider varchar(64)
- operation varchar(64)
- request_units numeric
- estimated_cost numeric(12,6)
- currency char(3)
- created_at timestamptz

## 空間検索例

```sql
SELECT id, title,
       ST_Distance(position, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography) AS distance_m
FROM knowledge_items
WHERE position IS NOT NULL
  AND ST_DWithin(
      position,
      ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography,
      :radius_m
  )
  AND (valid_from IS NULL OR valid_from <= now())
  AND (valid_until IS NULL OR valid_until > now())
ORDER BY distance_m
LIMIT 100;
```

上記は近隣の点候補の基本例。地域の小話は別に`ST_DWithin(position, current_position, radius_m)`で適用範囲内の項目を取得し、近隣候補と統合・重複排除する。地域の代表座標が近隣探索半径の外にあるだけで、利用者を含む地域知識を落とさない。MVPは事前登録した地域項目に限定し、可変半径検索の性能は実装時に確認する。

## データ保持
パスワード・Google/Apple ID token・LocalVoice tokenの平文をDB/ログに保存しない。ログインID、Google/Apple sub、内部user_idの対応を認証テーブルで管理する。Appleの状態確認・取り消しに必要なrefresh tokenだけは暗号化して保存し、削除時の一時失敗では取り消しキューへ移して、成功後に削除する。認証・所有者チェックは[認証設計](authentication-design-v0.1.md)に従う。アカウント削除時は本人の認証情報・旅行・精密位置履歴を削除し、端末キャッシュへの反映とバックアップの削除方針を公開前に定義する。

`context_snapshots` はプライバシー上のリスクが高いため保持期間を設定する。PoCでは分析後に位置を粗粒度化または削除できるようにする。`notification_history` はプロダクト改善に重要なので、位置生ログとは分離する。

地図用の端末キャッシュにも同じ保持方針を適用する。ガイド終了後も保持期間内のセッションは地図で見返せる。PoC開始前に具体的な保存期間を設定し、端末・サーバーの期限切れ記録点を削除する。通信断中の未送信記録点も保持期限後に再送しない。

個人用音声のDB行・保存ファイル・端末キャッシュをuser/trip単位で期限管理する。DB行を削除する前に保存ファイルのstorage_keyを削除キューへ移し、ファイルも除去する。アカウント切替で別ユーザーへ配信/表示しない。本文の訂正・有効期限・削除を音声資産にも反映し、sharedの音声に個人のプロフィール・会話を混ぜない。

## 将来拡張
- knowledge_itemの面/線geometry対応
- pgvectorによる意味検索
- route/map matching
- multilingualテーブルへの正規化
- knowledge versioning / review workflow（MVPは `review_status` のみ）
