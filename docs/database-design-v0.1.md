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
- metadata_json jsonb
- created_at/updated_at timestamptz

Index: `GIST(position)`, `(category)`, `(valid_until)`

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
- opened boolean
- spoken boolean
- feedback_type varchar(32) nullable

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

## データ保持
パスワード・Google/Apple ID token・LocalVoice tokenの平文をDB/ログに保存しない。ログインID、Google/Apple sub、内部user_idの対応を認証テーブルで管理する。Appleの状態確認・取り消しに必要なrefresh tokenだけは暗号化して保存し、削除時の一時失敗では取り消しキューへ移して、成功後に削除する。認証・所有者チェックは[認証設計](authentication-design-v0.1.md)に従う。アカウント削除時は本人の認証情報・旅行・精密位置履歴を削除し、端末キャッシュへの反映とバックアップの削除方針を公開前に定義する。

`context_snapshots` はプライバシー上のリスクが高いため保持期間を設定する。PoCでは分析後に位置を粗粒度化または削除できるようにする。`notification_history` はプロダクト改善に重要なので、位置生ログとは分離する。

地図用の端末キャッシュにも同じ保持方針を適用する。ガイド終了後も保持期間内のセッションは地図で見返せる。PoC開始前に具体的な保存期間を設定し、端末・サーバーの期限切れ記録点を削除する。通信断中の未送信記録点も保持期限後に再送しない。

## 将来拡張
- knowledge_itemの面/線geometry対応
- pgvectorによる意味検索
- route/map matching
- multilingualテーブルへの正規化
- knowledge versioning / review workflow
