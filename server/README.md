# LocalVoice API server (Flask)

MVP implementation of [API設計](../docs/api-design-v0.1.md) / [DB設計](../docs/database-design-v0.1.md) / [リアルタイムLLM設計](../docs/realtime-llm-design-v0.1.md).

## Setup

```bash
# PostgreSQL 16 + PostGIS 3
createdb localvoice && psql -d localvoice -c "create extension postgis"
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/localvoice
flask --app localvoice init-db     # create tables
flask --app localvoice seed        # draft curated stories (宮島・広島・尾道・奈良) — review before the trip
flask --app localvoice run --host 0.0.0.0 --port 8000
flask --app localvoice worker      # separate process: knowledge generation, audio, revocation retries, cleanup
```

## Main settings (environment variables)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL URL (`postgresql+psycopg://…`) |
| `ANTHROPIC_API_KEY` | Enables Claude for selection/narration and runtime knowledge generation. Without an LLM key the rule result is used. |
| `OPENAI_API_KEY` | Enables OpenAI (Responses API) instead, with the same prompts, schemas and validation |
| `LLM_PROVIDER` | `anthropic` / `openai` / `disabled`. Default: whichever key is set (Anthropic first) |
| `LLM_MODEL` | Default `claude-opus-5-5` (Anthropic) / `gpt-6-luna` (OpenAI; fits the 4s selection timeout — `gpt-6.1-sol` took ~8s) |
| `LLM_PRICE_INPUT_PER_MTOK`, `LLM_PRICE_OUTPUT_PER_MTOK` | USD per 1M tokens for the cost cap. Defaults match the default model (4/20 Claude, 0.1/0.5 Luna); set them when changing `LLM_MODEL` |
| `LLM_TIMEOUT_SEC` | Selection timeout (default 4s) before falling back to rules |
| `LLM_SESSION_COST_LIMIT_USD` | Per-trip LLM cost cap (default 5) |
| `GOOGLE_CLIENT_IDS` | Comma-separated Google OAuth client IDs accepted as ID-token audience |
| `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY`, `APPLE_BUNDLE_ID`, `APPLE_SERVICES_ID`, `APPLE_REDIRECT_URI`, `APPLE_ANDROID_APP_RETURN_URI` | Sign in with Apple. Keep the private key out of Git. |
| `TOKEN_ENCRYPTION_KEY` | Key for encrypting Apple refresh tokens (Fernet key or passphrase), stored outside the DB |
| `TTS_PROVIDER` | `none` (clients use device TTS if allowed), `silent` (dev), `google` (+`GOOGLE_TTS_API_KEY`) |
| `MAIL_BACKEND` | `log` (stores mails in `outbox_mails`) or `smtp` (+`SMTP_*`) |
| `SOURCE_FETCH_ENABLED` | Fetch Wikipedia/Wikidata/OSM materials for generation (default on) |

## Tests

```bash
createdb localvoice_test && psql -d localvoice_test -c "create extension postgis"
pytest
```

Tests use a real PostGIS database and fake Google/Apple/LLM/TTS providers; no external network calls.

## Layout

- `localvoice/auth/` — ID/password, Google, Apple, LocalVoice sessions
- `localvoice/api/` — trips/context/history/track, feedback, preferences, voices, commands/overrides/states/participants (P1)
- `localvoice/services/engine.py` — `/context` pipeline (rules → LLM → validation → decision log)
- `localvoice/services/ranking.py` — PostGIS candidates and scoring
- `localvoice/services/llm.py` — Claude adapter and output validation
- `localvoice/services/knowledge_gen.py`, `sources.py` — runtime knowledge generation
- `localvoice/services/voice.py` — VoiceProvider and audio cache
- `localvoice/services/commands.py` — natural-language temporary instructions and temporary states
- `localvoice/worker.py` — background loop
