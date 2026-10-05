# LocalVoice Database設計 v0.1

## 方針
PostgreSQL + PostGISをMVPから採用する。位置付き知識、利用者趣向、旅行セッション、短期興味、通知履歴、出典、API原価を分離する。

## 主要テーブル

### users
- id UUID PK
- locale varchar(10)
- notification_level varchar(20)
- detail_mode varchar(20)
- serendipity_level varchar(20)
- created_at timestamptz

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
`context_snapshots` はプライバシー上のリスクが高いため保持期間を設定する。PoCでは分析後に位置を粗粒度化または削除できるようにする。`notification_history` はプロダクト改善に重要なので、位置生ログとは分離する。

地図用の端末キャッシュにも同じ保持方針を適用する。ガイド終了後も保持期間内のセッションは地図で見返せる。PoC開始前に具体的な保存期間を設定し、端末・サーバーの期限切れ記録点を削除する。通信断中の未送信記録点も保持期限後に再送しない。

## 将来拡張
- knowledge_itemの面/線geometry対応
- pgvectorによる意味検索
- route/map matching
- multilingualテーブルへの正規化
- knowledge versioning / review workflow
