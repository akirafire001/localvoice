import os


def _bool(name, default=False):
    v = os.environ.get(name)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")


def _int(name, default):
    return int(os.environ.get(name, default))


def _float(name, default):
    return float(os.environ.get(name, default))


def _prices(spec):
    """Parse "model=in/out,model2=in/out" into {model: (in, out)}."""
    out = {}
    for part in filter(None, (p.strip() for p in spec.split(","))):
        model, _, price = part.partition("=")
        inp, _, outp = price.partition("/")
        out[model.strip()] = (float(inp), float(outp))
    return out


# USD per million tokens (input, output), as published by the providers (checked 2026-10-07)
MODEL_PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "gpt-6-astra": (10.0, 50.0),
    "gpt-6.1-sol": (2.0, 10.0),
    "gpt-6-luna": (0.1, 0.5),
}


class Config:
    """Runtime settings. Every value can be overridden by an environment variable of the same name."""

    def __init__(self, **overrides):
        self.DATABASE_URL = os.environ.get(
            "DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/localvoice"
        )
        self.TESTING = _bool("TESTING")

        # LocalVoice login sessions (auth-design §5)
        self.ACCESS_TOKEN_TTL_SEC = _int("ACCESS_TOKEN_TTL_SEC", 900)
        self.REFRESH_ABSOLUTE_TTL_SEC = _int("REFRESH_ABSOLUTE_TTL_SEC", 30 * 24 * 3600)
        self.REAUTH_WINDOW_SEC = _int("REAUTH_WINDOW_SEC", 300)
        self.PASSWORD_MIN_LEN = _int("PASSWORD_MIN_LEN", 15)
        self.PASSWORD_MAX_LEN = _int("PASSWORD_MAX_LEN", 128)
        self.LOGIN_RATE_LIMIT = _int("LOGIN_RATE_LIMIT", 10)  # attempts per window
        self.LOGIN_RATE_WINDOW_SEC = _int("LOGIN_RATE_WINDOW_SEC", 300)
        self.ACTION_TOKEN_TTL_SEC = _int("ACTION_TOKEN_TTL_SEC", 3600)
        self.APP_PUBLIC_URL = os.environ.get("APP_PUBLIC_URL", "https://localvoice.example")

        # Google sign-in: comma separated OAuth client IDs accepted as audience.
        # Defaults are the LocalVoice project's public client IDs (web/server and iOS); not secrets.
        self.GOOGLE_CLIENT_IDS = [
            x for x in os.environ.get(
                "GOOGLE_CLIENT_IDS",
                "380406027309-epmgbpd9gk6h1d1vk6j3c7b6d5l0gdlv.apps.googleusercontent.com,"
                "380406027309-ibs30tj1jkoleq1p87s5bv078sa5p5u5.apps.googleusercontent.com",
            ).split(",") if x
        ]
        # Sign in with Apple
        self.APPLE_TEAM_ID = os.environ.get("APPLE_TEAM_ID", "")
        self.APPLE_KEY_ID = os.environ.get("APPLE_KEY_ID", "")
        self.APPLE_PRIVATE_KEY = os.environ.get("APPLE_PRIVATE_KEY", "")  # PEM, never commit
        self.APPLE_BUNDLE_ID = os.environ.get("APPLE_BUNDLE_ID", "")  # iOS audience
        self.APPLE_SERVICES_ID = os.environ.get("APPLE_SERVICES_ID", "")  # Android/Web audience
        self.APPLE_REDIRECT_URI = os.environ.get("APPLE_REDIRECT_URI", "")
        self.APPLE_ANDROID_APP_RETURN_URI = os.environ.get(
            "APPLE_ANDROID_APP_RETURN_URI",
            "intent://callback#Intent;package=com.localvoice.localvoice;scheme=signinwithapple;end"
        )
        self.APPLE_CHALLENGE_TTL_SEC = _int("APPLE_CHALLENGE_TTL_SEC", 600)
        # Fernet-compatible key material for encrypting Apple refresh tokens (kept outside the DB)
        self.TOKEN_ENCRYPTION_KEY = os.environ.get("TOKEN_ENCRYPTION_KEY", "")
        self.TOKEN_ENCRYPTION_KEY_ID = os.environ.get("TOKEN_ENCRYPTION_KEY_ID", "k1")

        # Mail (recovery email). "log" only records that a mail would be sent.
        self.MAIL_BACKEND = os.environ.get("MAIL_BACKEND", "log")
        self.SMTP_HOST = os.environ.get("SMTP_HOST", "")
        self.SMTP_PORT = _int("SMTP_PORT", 587)
        self.SMTP_USER = os.environ.get("SMTP_USER", "")
        self.SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
        self.MAIL_FROM = os.environ.get("MAIL_FROM", "no-reply@localvoice.example")

        # Guide engine (mvp-technical-design §5-8, PoC tuning values)
        self.SCORE_THRESHOLD = _float("SCORE_THRESHOLD", 0.35)
        self.MAX_ACCURACY_M = _float("MAX_ACCURACY_M", 100)
        self.LLM_CANDIDATES = _int("LLM_CANDIDATES", 5)
        self.FRESHNESS_SEC = _int("FRESHNESS_SEC", 180)
        self.TRACK_RETENTION_DAYS = _int("TRACK_RETENTION_DAYS", 90)

        # LLM (realtime-llm-design §5)
        # LOCALVOICE_* names win so a developer's general-purpose keys are not used by accident.
        self.ANTHROPIC_API_KEY = os.environ.get("LOCALVOICE_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
        self.OPENAI_API_KEY = os.environ.get("LOCALVOICE_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        self.LLM_PROVIDER = os.environ.get(
            "LLM_PROVIDER",
            "anthropic" if self.ANTHROPIC_API_KEY else "openai" if self.OPENAI_API_KEY else "disabled",
        )
        openai = self.LLM_PROVIDER == "openai"
        # LLM_MODEL sets both; the realtime model must answer within LLM_TIMEOUT_SEC
        # (selection, commands), the background model does knowledge generation, web research and summaries.
        self.LLM_MODEL = os.environ.get("LLM_MODEL", "")
        self.LLM_REALTIME_MODEL = os.environ.get(
            "LLM_REALTIME_MODEL", self.LLM_MODEL or ("gpt-6-luna" if openai else "claude-opus-5-5")
        )
        self.LLM_BACKGROUND_MODEL = os.environ.get(
            "LLM_BACKGROUND_MODEL", self.LLM_MODEL or ("gpt-6.1-sol" if openai else "claude-opus-5-5")
        )
        # Writing stories from researched materials is the bulk of the background calls but needs no search,
        # so it runs on the cheaper realtime-class model unless overridden.
        self.LLM_GENERATE_MODEL = os.environ.get(
            "LLM_GENERATE_MODEL", self.LLM_MODEL or ("gpt-6-luna" if openai else self.LLM_BACKGROUND_MODEL)
        )
        self.LLM_SELECT_EFFORT = os.environ.get("LLM_SELECT_EFFORT", "low")
        self.LLM_GENERATE_EFFORT = os.environ.get("LLM_GENERATE_EFFORT", "medium")
        self.LLM_TIMEOUT_SEC = _float("LLM_TIMEOUT_SEC", 4.0)
        self.LLM_GENERATE_TIMEOUT_SEC = _float("LLM_GENERATE_TIMEOUT_SEC", 240.0)  # up to 12 items take minutes
        self.LLM_SESSION_COST_LIMIT_USD = _float("LLM_SESSION_COST_LIMIT_USD", 5.0)
        # USD per million tokens (input, output). LLM_PRICES="model=in/out,..." adds or overrides models;
        # LLM_PRICE_*_PER_MTOK is used for models not in the table.
        self.LLM_PRICES = {**MODEL_PRICES, **_prices(os.environ.get("LLM_PRICES", ""))}
        self.LLM_PRICE_INPUT_PER_MTOK = _float("LLM_PRICE_INPUT_PER_MTOK", 4.0)
        self.LLM_PRICE_OUTPUT_PER_MTOK = _float("LLM_PRICE_OUTPUT_PER_MTOK", 20.0)

        # Runtime knowledge generation
        self.KNOWLEDGE_GENERATION_ENABLED = _bool("KNOWLEDGE_GENERATION_ENABLED", True)
        self.GEOHASH_PRECISION = _int("GEOHASH_PRECISION", 6)
        self.COVERAGE_TTL_DAYS = _int("COVERAGE_TTL_DAYS", 90)
        self.SOURCE_FETCH_ENABLED = _bool("SOURCE_FETCH_ENABLED", not self.TESTING)
        self.HTTP_USER_AGENT = os.environ.get(
            "HTTP_USER_AGENT", "LocalVoice/0.1 (https://github.com/akirafire001/localvoice)"
        )
        # Town names (町名) of a cell come from Nominatim reverse geocoding; each town gets one web search
        # for its name origin and local history per COVERAGE_TTL_DAYS (realtime-llm-design §3.2)
        self.NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
        self.LOCAL_HISTORY_RESEARCH_ENABLED = _bool("LOCAL_HISTORY_RESEARCH_ENABLED", True)
        # Fewer untold stories than this around the traveller → also generate the 8 cells around them
        self.NEARBY_GENERATION_MIN_STORIES = _int("NEARBY_GENERATION_MIN_STORIES", 3)
        # Generation repeats ("stories not told yet") until a round adds nothing; at most this many rounds per cell
        self.GENERATION_MAX_ROUNDS = _int("GENERATION_MAX_ROUNDS", 4)
        # Research themes (llm.LOCAL_RESEARCH_THEMES) searched per generation job; the rest wait for later jobs
        self.LOCAL_RESEARCH_THEMES_PER_JOB = _int("LOCAL_RESEARCH_THEMES_PER_JOB", 4)

        # Voice (voice-design §6-7)
        self.TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "none")  # none | silent (dev) | google
        self.GOOGLE_TTS_API_KEY = os.environ.get("GOOGLE_TTS_API_KEY", "")
        self.AUDIO_STORE_DIR = os.environ.get("AUDIO_STORE_DIR", "audio_store")
        self.PRIVATE_AUDIO_RETENTION_DAYS = _int("PRIVATE_AUDIO_RETENTION_DAYS", 7)
        self.PRONUNCIATION_VERSION = os.environ.get("PRONUNCIATION_VERSION", "p1")

        for k, v in overrides.items():
            setattr(self, k, v)

    def llm_price(self, model):
        """(input, output) USD per million tokens for a model."""
        return self.LLM_PRICES.get(model, (self.LLM_PRICE_INPUT_PER_MTOK, self.LLM_PRICE_OUTPUT_PER_MTOK))
