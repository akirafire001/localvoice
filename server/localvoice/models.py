"""Tables from docs/database-design-v0.1.md."""
import uuid
from datetime import datetime, timezone

from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


def _uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


TS = DateTime(timezone=True)


def _fk(target, ondelete="CASCADE", nullable=False):
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


# ---------------------------------------------------------------- users / auth


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid_pk()
    display_name: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active")
    recovery_email: Mapped[str | None] = mapped_column(Text)
    recovery_email_verified_at: Mapped[datetime | None] = mapped_column(TS)
    locale: Mapped[str] = mapped_column(String(10), default="ja")
    # The operator console. Set only when a verified Google sign-in matches the configured admin address.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # ISO 3166 code (lower case) of the country the user lives in: country-wide manners are told only elsewhere
    home_country: Mapped[str] = mapped_column(String(2), default="jp", server_default="jp")
    notification_level: Mapped[str] = mapped_column(String(20), default="continuous")  # prefs.DEFAULT_NOTIFICATION_LEVEL
    detail_mode: Mapped[str] = mapped_column(String(20), default="auto")
    serendipity_level: Mapped[str] = mapped_column(String(20), default="normal")
    voice_settings_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject"),
        UniqueConstraint("user_id", "provider"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    provider: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class PasswordCredential(Base):
    __tablename__ = "password_credentials"
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    login_id: Mapped[str] = mapped_column(String(100))
    login_id_normalized: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    access_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    access_expires_at: Mapped[datetime] = mapped_column(TS)
    authenticated_via: Mapped[str] = mapped_column(String(32))
    last_reauthenticated_at: Mapped[datetime | None] = mapped_column(TS)
    expires_at: Mapped[datetime] = mapped_column(TS)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class AuthRefreshToken(Base):
    __tablename__ = "auth_refresh_tokens"
    id: Mapped[uuid.UUID] = _uuid_pk()
    auth_session_id: Mapped[uuid.UUID] = _fk("auth_sessions.id")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(TS)
    consumed_at: Mapped[datetime | None] = mapped_column(TS)
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"
    id: Mapped[uuid.UUID] = _uuid_pk()
    purpose: Mapped[str] = mapped_column(String(32))
    user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    client_kind: Mapped[str] = mapped_column(String(16))
    expected_audience: Mapped[str] = mapped_column(String(255))
    nonce_hash: Mapped[str] = mapped_column(String(64))
    state_hash: Mapped[str | None] = mapped_column(String(64))
    app_code_challenge: Mapped[str | None] = mapped_column(String(64))
    result_ciphertext: Mapped[str | None] = mapped_column(Text)
    handoff_code_hash: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(TS)
    consumed_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class AppleCredential(Base):
    __tablename__ = "apple_credentials"
    auth_identity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_identities.id", ondelete="CASCADE"), primary_key=True
    )
    apple_client_id: Mapped[str] = mapped_column(String(255))
    refresh_token_ciphertext: Mapped[str] = mapped_column(Text)
    encryption_key_id: Mapped[str] = mapped_column(String(100))
    last_verified_at: Mapped[datetime | None] = mapped_column(TS)


class OAuthRevocationJob(Base):
    __tablename__ = "oauth_revocation_jobs"
    id: Mapped[uuid.UUID] = _uuid_pk()
    provider: Mapped[str] = mapped_column(String(32))
    client_id: Mapped[str] = mapped_column(String(255))
    token_ciphertext: Mapped[str] = mapped_column(Text)
    encryption_key_id: Mapped[str] = mapped_column(String(100))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class AuthActionToken(Base):
    __tablename__ = "auth_action_tokens"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    purpose: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    target_email: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(TS)
    consumed_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class LoginAttempt(Base):
    """Rate-limit bookkeeping for login (auth-design §3)."""

    __tablename__ = "login_attempts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)


class OutboxMail(Base):
    """Mails queued by the app; the 'log' backend only stores them here (dev/test)."""

    __tablename__ = "outbox_mails"
    id: Mapped[uuid.UUID] = _uuid_pk()
    to_address: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ---------------------------------------------------------------- preferences


class UserInterest(Base):
    __tablename__ = "user_interests"
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    category: Mapped[str] = mapped_column(String(64), primary_key=True)
    explicit_score: Mapped[float | None] = mapped_column(Numeric)
    learned_score: Mapped[float] = mapped_column(Numeric, default=0)
    knowledge_score: Mapped[float] = mapped_column(Numeric, default=0)
    confidence: Mapped[float] = mapped_column(Numeric, default=0)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ---------------------------------------------------------------- trips


class TripSession(Base):
    __tablename__ = "trip_sessions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    purpose: Mapped[str] = mapped_column(String(32), default="travel")
    language: Mapped[str] = mapped_column(String(10), default="ja")
    started_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(TS)
    manual_transport_mode: Mapped[str | None] = mapped_column(String(32))
    selection_mode: Mapped[str] = mapped_column(String(8), default="llm")
    memory_summary: Mapped[str | None] = mapped_column(Text)
    settings_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    # runtime state kept per trip (last context, pending skip etc.)
    state_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class Participant(Base):
    __tablename__ = "participants"
    id: Mapped[uuid.UUID] = _uuid_pk()
    trip_session_id: Mapped[uuid.UUID] = _fk("trip_sessions.id")
    display_name: Mapped[str] = mapped_column(String(100))
    locale: Mapped[str | None] = mapped_column(String(10))
    home_region: Mapped[str | None] = mapped_column(String(200))
    profile_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class ContextSnapshot(Base):
    __tablename__ = "context_snapshots"
    __table_args__ = (
        UniqueConstraint("trip_session_id", "client_event_id"),
        Index("ix_ctx_trip_observed", "trip_session_id", "observed_at", "id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trip_session_id: Mapped[uuid.UUID] = _fk("trip_sessions.id")
    client_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    observed_at: Mapped[datetime] = mapped_column(TS)
    position = mapped_column(Geography("POINT", srid=4326, spatial_index=True))
    accuracy_m: Mapped[float | None] = mapped_column(Numeric)
    speed_mps: Mapped[float | None] = mapped_column(Numeric)
    course_deg: Mapped[float | None] = mapped_column(Numeric)
    inferred_transport_mode: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[float | None] = mapped_column(Numeric)
    context_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    received_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ---------------------------------------------------------------- knowledge


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"
    __table_args__ = (
        Index("ix_ki_category", "category"),
        Index("ix_ki_valid_until", "valid_until"),
        Index("ix_ki_area_cell", "area_cell"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    canonical_key: Mapped[str] = mapped_column(String(200), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    title_en: Mapped[str | None] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(64))
    body_ja: Mapped[str | None] = mapped_column(Text)
    short_ja: Mapped[str | None] = mapped_column(Text)
    body_en: Mapped[str | None] = mapped_column(Text)
    short_en: Mapped[str | None] = mapped_column(Text)
    position = mapped_column(Geography("POINT", srid=4326, spatial_index=True), nullable=True)
    radius_m: Mapped[int] = mapped_column(Integer, default=200)
    interestingness: Mapped[float] = mapped_column(Numeric, default=0.5)
    novelty: Mapped[float] = mapped_column(Numeric, default=0.5)
    confidence_level: Mapped[str] = mapped_column(String(16), default="medium")
    fact_type: Mapped[str] = mapped_column(String(32), default="verified_fact")
    valid_from: Mapped[datetime | None] = mapped_column(TS)
    valid_until: Mapped[datetime | None] = mapped_column(TS)
    origin: Mapped[str] = mapped_column(String(16), default="curated")
    review_status: Mapped[str] = mapped_column(String(16), default="reviewed")
    area_cell: Mapped[str | None] = mapped_column(String(12))
    generated_by: Mapped[dict | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    content_version: Mapped[str] = mapped_column(String(32), default="v1")
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)

    sources = relationship("KnowledgeSource", cascade="all, delete-orphan", lazy="selectin")
    claims = relationship("KnowledgeClaim", cascade="all, delete-orphan", lazy="selectin")

    def story_quality(self):
        return (self.metadata_json or {}).get("story_quality", {})

    def auto_eligible(self):
        return bool(self.story_quality().get("auto_eligible"))


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    id: Mapped[uuid.UUID] = _uuid_pk()
    knowledge_item_id: Mapped[uuid.UUID] = _fk("knowledge_items.id")
    url: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime | None] = mapped_column(TS)
    source_type: Mapped[str] = mapped_column(String(32), default="web")
    reliability_score: Mapped[float] = mapped_column(Numeric, default=0.5)
    license_info: Mapped[str | None] = mapped_column(Text)


class KnowledgeClaim(Base):
    __tablename__ = "knowledge_claims"
    __table_args__ = (CheckConstraint("cardinality(source_ids) > 0", name="claims_have_sources"),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    knowledge_item_id: Mapped[uuid.UUID] = _fk("knowledge_items.id")
    claim_text_ja: Mapped[str | None] = mapped_column(Text)
    claim_text_en: Mapped[str | None] = mapped_column(Text)
    source_ids = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class KnowledgeRelation(Base):
    __tablename__ = "knowledge_relations"
    from_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_items.id", ondelete="CASCADE"), primary_key=True
    )
    to_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_items.id", ondelete="CASCADE"), primary_key=True
    )
    relation_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    weight: Mapped[float] = mapped_column(Numeric, default=1.0)


class AreaCoverage(Base):
    __tablename__ = "area_coverage"
    area_cell: Mapped[str] = mapped_column(String(12), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="none")
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime | None] = mapped_column(TS)
    expires_at: Mapped[datetime | None] = mapped_column(TS)


class KnowledgeGenerationJob(Base):
    __tablename__ = "knowledge_generation_jobs"
    __table_args__ = (Index("ix_kgj_status_priority", "status", "priority"),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    area_cell: Mapped[str] = mapped_column(String(12))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(TS)
    finished_at: Mapped[datetime | None] = mapped_column(TS)


class ExternalGenTask(Base):
    """A cell generated by a subscription's agent (services/external_gen.py): the server runs the usual pipeline
    and the agent answers its web searches and story writing one step at a time."""
    __tablename__ = "external_gen_tasks"
    __table_args__ = (Index("ix_egt_status_cell", "status", "area_cell"),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    area_cell: Mapped[str] = mapped_column(String(12))
    agent: Mapped[str] = mapped_column(String(40))  # claude / codex / gemini / cursor ...
    model: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / done / failed / abandoned
    calls_json: Mapped[list] = mapped_column(JSONB, default=list)  # every LLM call so far, answered or pending
    sources_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # towns and materials fetched at the start
    prior_coverage: Mapped[str | None] = mapped_column(String(16))  # area_coverage.status to restore if abandoned
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    lease_until: Mapped[datetime] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ---------------------------------------------------------------- guide / history


class GuideDecision(Base):
    __tablename__ = "guide_decisions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    trip_session_id: Mapped[uuid.UUID] = _fk("trip_sessions.id")
    context_snapshot_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("context_snapshots.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    trigger: Mapped[str] = mapped_column(String(16), default="context")  # context | skip_story
    candidates_json: Mapped[list] = mapped_column(JSONB, default=list)
    rule_choice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    llm_choice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    final_action: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(32))
    llm_reason: Mapped[str | None] = mapped_column(Text)
    selection_mode: Mapped[str] = mapped_column(String(8))
    fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(64))
    llm_model: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    input_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # for replay


class NotificationHistory(Base):
    __tablename__ = "notification_history"
    id: Mapped[uuid.UUID] = _uuid_pk()
    trip_session_id: Mapped[uuid.UUID] = _fk("trip_sessions.id")
    knowledge_item_id: Mapped[uuid.UUID] = _fk("knowledge_items.id")
    guide_decision_id: Mapped[uuid.UUID | None] = _fk(
        "guide_decisions.id", ondelete="SET NULL", nullable=True
    )
    shown_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    channel: Mapped[str] = mapped_column(String(16), default="app")
    score: Mapped[float | None] = mapped_column(Numeric)
    score_components: Mapped[dict] = mapped_column(JSONB, default=dict)
    title: Mapped[str | None] = mapped_column(Text)
    rendered_text: Mapped[str | None] = mapped_column(Text)
    detail_text: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(10), default="ja")
    selection_mode: Mapped[str] = mapped_column(String(8))
    opened: Mapped[bool] = mapped_column(Boolean, default=False)
    spoken: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback_type: Mapped[str | None] = mapped_column(String(32))
    rating: Mapped[str | None] = mapped_column(String(16))
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    speech_snapshot_json: Mapped[dict | None] = mapped_column(JSONB)
    audio_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class TopicBoost(Base):
    __tablename__ = "topic_boosts"
    id: Mapped[uuid.UUID] = _uuid_pk()
    trip_session_id: Mapped[uuid.UUID] = _fk("trip_sessions.id")
    topic_key: Mapped[str] = mapped_column(String(100))
    strength: Mapped[float] = mapped_column(Numeric, default=1.0)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TS)
    decay_rate: Mapped[float] = mapped_column(Numeric, default=0.5)  # per hour
    ended_at: Mapped[datetime | None] = mapped_column(TS)


class TemporaryState(Base):
    __tablename__ = "temporary_states"
    id: Mapped[uuid.UUID] = _uuid_pk()
    trip_session_id: Mapped[uuid.UUID] = _fk("trip_sessions.id")
    state_type: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TS)
    source: Mapped[str] = mapped_column(String(32), default="ui")
    ended_at: Mapped[datetime | None] = mapped_column(TS)


class IntentOverride(Base):
    __tablename__ = "intent_overrides"
    id: Mapped[uuid.UUID] = _uuid_pk()
    trip_session_id: Mapped[uuid.UUID] = _fk("trip_sessions.id")
    type: Mapped[str] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(String(200))
    strength: Mapped[float] = mapped_column(Numeric, default=1.0)
    label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TS)
    end_condition_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    ended_at: Mapped[datetime | None] = mapped_column(TS)


class ApiUsageLog(Base):
    __tablename__ = "api_usage_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trip_session_id: Mapped[uuid.UUID | None] = _fk(
        "trip_sessions.id", ondelete="SET NULL", nullable=True
    )
    provider: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(64))
    request_units: Mapped[float] = mapped_column(Numeric, default=0)
    estimated_cost: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    details_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ---------------------------------------------------------------- voice


class AudioAsset(Base):
    __tablename__ = "audio_assets"
    id: Mapped[uuid.UUID] = _uuid_pk()
    knowledge_item_id: Mapped[uuid.UUID | None] = _fk(
        "knowledge_items.id", ondelete="SET NULL", nullable=True
    )
    owner_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    trip_session_id: Mapped[uuid.UUID | None] = _fk("trip_sessions.id", nullable=True)
    scope: Mapped[str] = mapped_column(String(16))
    cache_key: Mapped[str] = mapped_column(String(64), unique=True)
    content_version: Mapped[str | None] = mapped_column(Text)
    speech_text_hash: Mapped[str] = mapped_column(String(64))
    pronunciation_version: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(10))
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(Text)
    voice_profile_id: Mapped[str] = mapped_column(Text)
    voice_version: Mapped[str | None] = mapped_column(Text)
    synthesis_settings_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    storage_key: Mapped[str | None] = mapped_column(Text)
    audio_format: Mapped[str | None] = mapped_column(String(32))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    attribution_json: Mapped[list] = mapped_column(JSONB, default=list)
    terms_version: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    valid_until: Mapped[datetime | None] = mapped_column(TS)
    retention_until: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)
