"""Background worker: knowledge generation, Apple token revocation retries, summaries, retention cleanup.

Run with:  flask --app localvoice worker
"""
import logging
import threading
import time
from datetime import timedelta

from flask import current_app
from sqlalchemy import delete, select

from .auth import crypto
from .auth.providers import ProviderTokenInvalid, ProviderUnavailable, apple
from .models import AuthChallenge, ContextSnapshot, LoginAttempt, OAuthRevocationJob, TripSession
from .services import knowledge_gen, memory, next_story
from .util import now

log = logging.getLogger(__name__)


def _db(app):
    return app.extensions["lv_sessionmaker"]()


def process_generation(app, max_jobs=1, stages=None):
    done = 0
    for _ in range(max_jobs):
        db = _db(app)
        try:
            job = knowledge_gen.claim_job(db, stages=stages)
            if job is None:
                break
            knowledge_gen.run_job(db, job)
            done += 1
        finally:
            db.close()
    return done


def process_revocations(app):
    db = _db(app)
    try:
        jobs = db.execute(
            select(OAuthRevocationJob).where(OAuthRevocationJob.next_attempt_at <= now()).limit(20).with_for_update(skip_locked=True)
        ).scalars().all()
        for j in jobs:
            try:
                apple().revoke(j.client_id, crypto.decrypt(j.token_ciphertext))
                db.delete(j)  # revoked: drop the encrypted token
            except ProviderTokenInvalid:
                db.delete(j)  # Apple no longer knows the token
            except (ProviderUnavailable, Exception):  # noqa: BLE001
                j.attempts += 1
                j.next_attempt_at = now() + timedelta(minutes=min(2 ** j.attempts, 24 * 60))
        db.commit()
    finally:
        db.close()


def refresh_summaries(app):
    db = _db(app)
    try:
        # Ended trips are included: finish marks the summary dirty and returns without the LLM.
        trips = db.execute(
            select(TripSession).where(TripSession.state_json["summary_dirty"].as_boolean().is_(True)).limit(10)
        ).scalars().all()
        for trip in trips:
            memory.update_summary(db, trip)
            state = dict(trip.state_json or {})
            state["summary_dirty"] = False
            trip.state_json = state
        db.commit()
    finally:
        db.close()


def cleanup(app):
    cfg = app.config["LV"]
    db = _db(app)
    try:
        t = now()
        db.execute(delete(ContextSnapshot).where(ContextSnapshot.observed_at < t - timedelta(days=cfg.TRACK_RETENTION_DAYS)))
        db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < t - timedelta(days=1)))
        db.execute(delete(AuthChallenge).where(AuthChallenge.expires_at < t - timedelta(days=1)))
        try:
            from .services.voice import cleanup_expired_audio

            cleanup_expired_audio(db)
        except ImportError:
            pass
        db.commit()
    finally:
        db.close()


def process_audio(app):
    try:
        from .services.voice import process_pending_audio
    except ImportError:
        return 0
    db = _db(app)
    try:
        return process_pending_audio(db)
    finally:
        db.close()


def warm_tutorial(app):
    """Voices the tutorial ahead of time in each app language's default voice, so a first wait starts at once."""
    try:
        from .services.voice import VOICE_PROFILES, get_or_create_asset, synthesize_asset
        from .services.waiting import ensure_tutorial
    except ImportError:
        return
    db = _db(app)
    try:
        items = ensure_tutorial(db)
        db.commit()
        for item in items:
            for lang, text in ((item.metadata_json or {}).get("speech") or {}).items():
                vid = f"{lang}-default"
                if vid not in VOICE_PROFILES:
                    continue
                asset, prov = get_or_create_asset(
                    db, text=text, language=lang, voice_profile_id=vid, scope="shared",
                    content_version=item.content_version, knowledge_item_id=item.id,
                )
                db.commit()
                if asset is not None and asset.status in ("pending", "invalidated"):
                    synthesize_asset(db, asset, prov)
    except Exception:  # noqa: BLE001
        log.exception("warming the tutorial audio failed")
        db.rollback()
    finally:
        db.close()


def _fast_generation_loop(app, idle_sleep):
    """Runs only fast jobs (a first round for a place with no stories yet), so they never wait behind deep ones."""
    while True:
        try:
            with app.app_context():
                worked = process_generation(app, stages=("fast",))
        except Exception:  # noqa: BLE001
            log.exception("fast generation loop failed")
            worked = 0
        if not worked:
            time.sleep(idle_sleep)


def run_forever(app, idle_sleep=2.0):
    last_cleanup = 0.0
    log.info("worker started")
    for i in range(max(0, app.config["LV"].GENERATION_FAST_THREADS)):
        threading.Thread(target=_fast_generation_loop, args=(app, idle_sleep), name=f"fast-gen-{i}", daemon=True).start()
    with app.app_context():
        warm_tutorial(app)
    while True:
        with app.app_context():
            worked = process_generation(app)
            worked += process_audio(app) or 0
            process_revocations(app)
            refresh_summaries(app)
            next_story.prepare_upcoming(app)
            if time.time() - last_cleanup > 3600:
                cleanup(app)
                last_cleanup = time.time()
        if not worked:
            time.sleep(idle_sleep)


def register(app):
    @app.cli.command("worker")
    def worker_cmd():
        """Run the background worker loop."""
        run_forever(current_app._get_current_object())
