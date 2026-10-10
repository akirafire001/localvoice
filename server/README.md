# LocalVoice API server (Flask)

MVP implementation of [API設計](../docs/api-design-v0.1.md) / [DB設計](../docs/database-design-v0.1.md) / [リアルタイムLLM設計](../docs/realtime-llm-design-v0.1.md).

## Setup

```bash
# PostgreSQL 16 + PostGIS 3
createdb localvoice && psql -d localvoice -c "create extension postgis"
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/localvoice
flask --app localvoice init-db     # create tables; on an existing DB it also adds columns added since (db.UPGRADES)
flask --app localvoice seed        # draft curated stories (宮島・広島・尾道・奈良) — review before the trip
flask --app localvoice run --host 0.0.0.0 --port 8000
flask --app localvoice worker      # separate process: knowledge generation, audio, revocation retries, cleanup
flask --app localvoice rewrite-stories [--cell xn764e] [--limit 5] [--dry-run] [--force]  # give stored stories a spoken version (services/storytelling.py)
```

## Landing page

The multilingual LocalVoice landing page is served at `/` by the same Flask app. Open
`http://localhost:8000/` after starting the server above. Restart an already-running
server without auto-reload to register the new route.

- `localvoice/landing.py`: public route, browser-language negotiation and prepared story catalog.
- `localvoice/landing_copy.py`: LP copy in all six of the app's narration languages.
- `localvoice/landing_samples.json`: exported text, sources and audio paths for three selected DB stories.
- `localvoice/templates/landing.html`: product introduction, usage, interactive demo, FAQ, and development status.
- `localvoice/static/landing/`: responsive CSS, prepared audio player, and bundled assets.

The demo does not request location or create accounts. It plays 18 prepared MP3 files
(three stories × Japanese, English, Chinese, Korean, Spanish and French), generated with
the app's Google Chirp 3 HD voice profiles. Page views and playback never call TTS or LLMs,
use OS/browser speech synthesis, or query the database. Audio loads only when played.

`Accept-Language` selects the first supported browser language, including region variants
such as `en-US`, `zh-TW`, `es-MX` and `fr-CA`. Unsupported preferences fall back to English;
requests without a language header default to Japanese. The header language selector uses
`?lang=ja|en|zh|ko|es|fr` to override automatic selection. HTML, metadata, examples and player
messages all use the selected language; responses vary on `Accept-Language`.

To refresh the exported examples/audio, configure `DATABASE_URL`, `TTS_PROVIDER=google`
and `GOOGLE_TTS_API_KEY`, then run from `server/`:

```bash
flask --app localvoice landing prepare-samples
pytest tests/test_landing.py -q
```

The export allowlist in `landing_translations.py` contains the Miyajima torii, Nara Great
Buddha Hall, and Tsutsumine waste-heat stories. JA/EN text comes directly from the DB's spoken
scripts; the other four languages have version-pinned editorial translations. Export reuses
shared TTS cache entries, never private audio or trip histories, and rejects missing,
suspended, expired or changed-version stories. The catalog is published only after all
audio is ready. Refresh explicitly when source content is changed or withdrawn; public
sample copies are independent of the live database. The current source records are drafts,
which is disclosed alongside the source links in the demo's expandable details.

Download links and pricing are intentionally not presented while store release is pending.
For a separate local preview, run `flask --app localvoice run --port 8001`.

Assets reuse the adopted branding and S1 artwork: `docs/branding/apple-touch-icon.png`
(also the compact LP logo), `docs/branding/favicon.ico`, and selected illustrations/icons
from `app/assets/s1/`. Copies are included under the Flask static directory so deploying
`server/` alone includes all LP resources. Refresh those copies if the source artwork changes.

## Main settings (environment variables)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL URL (`postgresql+psycopg://…`) |
| `ANTHROPIC_API_KEY` (or `LOCALVOICE_ANTHROPIC_API_KEY`) | Enables Claude for selection/narration and runtime knowledge generation. Without an LLM key the rule result is used. |
| `OPENAI_API_KEY` (or `LOCALVOICE_OPENAI_API_KEY`) | Enables OpenAI (Responses API) instead, with the same prompts, schemas and validation. The `LOCALVOICE_` names take precedence, so a key for this app does not clash with general-purpose keys on the same machine |
| `LLM_PROVIDER` | `anthropic` / `openai` / `disabled`. Default: whichever key is set (Anthropic first) |
| `LLM_REALTIME_MODEL` | Selection/narration and natural-language commands; must answer within `LLM_TIMEOUT_SEC`. Default `gpt-6-luna` (OpenAI, ~2s) / `claude-opus-5-5` |
| `LLM_BACKGROUND_MODEL` | Knowledge generation, web research and trip summaries in the worker. Default `gpt-6.1-sol` (OpenAI) / `claude-opus-5-5` |
| `LLM_MODEL` | Sets both of the above when they are not set individually |
| `LLM_PRICES` | Extra or overriding prices, `model=in/out,...` (USD per 1M tokens). Built-in: `claude-opus-5-5`, `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6-luna` (`config.MODEL_PRICES`) |
| `LLM_PRICE_INPUT_PER_MTOK`, `LLM_PRICE_OUTPUT_PER_MTOK` | Price for models not in the table (default 4/20) |
| `LLM_TIMEOUT_SEC` | Selection timeout (default 4s) before falling back to rules |
| `LLM_SESSION_COST_LIMIT_USD` | Per-trip LLM cost cap (default 5) |
| `GOOGLE_CLIENT_IDS` | Comma-separated Google OAuth client IDs accepted as ID-token audience |
| `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY`, `APPLE_BUNDLE_ID`, `APPLE_SERVICES_ID`, `APPLE_REDIRECT_URI`, `APPLE_ANDROID_APP_RETURN_URI` | Sign in with Apple. Keep the private key out of Git. |
| `TOKEN_ENCRYPTION_KEY` | Key for encrypting Apple refresh tokens (Fernet key or passphrase), stored outside the DB |
| `TTS_PROVIDER` | `none` (clients use device TTS if allowed), `silent` (dev), `google` (+`GOOGLE_TTS_API_KEY`) |
| `MAIL_BACKEND` | `log` (stores mails in `outbox_mails`) or `smtp` (+`SMTP_*`) |
| `LOCAL_RESEARCH_THEMES_PER_JOB`, `COUNTRY_RESEARCH_THEMES_PER_JOB` | Research themes (`llm.LOCAL_RESEARCH_THEMES`, 42) searched per generation job for the cell's towns (default 4), and country-wide manners (`llm.COUNTRY_RESEARCH_THEMES`, researched once per country, told only to users from other countries) per job (default 2) |
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
