"""/context pipeline: rules → (LLM) selection → validation/fallback → decision log (mvp-technical-design §7-8)."""
import logging
import math
import uuid
from datetime import timedelta, timezone

from flask import current_app
from geoalchemy2.shape import to_shape
from sqlalchemy import func, select

from ..errors import ApiError, bad_request, conflict
from ..models import (
    ApiUsageLog,
    ContextSnapshot,
    GuideDecision,
    IntentOverride,
    KnowledgeItem,
    NotificationHistory,
    Participant,
    TemporaryState,
)
from ..util import now, parse_datetime, parse_uuid
from . import commands, geo
from .languages import narration_languages
from .prefs import CATEGORIES, DEFAULT_NOTIFICATION_LEVEL, NOTIFICATION_LEVELS, trip_settings
from .ranking import (
    active_boosts,
    fetch_candidates,
    heard_before_ids,
    load_interests,
    score_candidates,
    seed_for,
    todays_history,
)
from .rendering import item_speech_text, item_texts, location_payload, guide_payload
from .selector import SelectionInput
from .translation import localized_story, spoken_text

log = logging.getLogger(__name__)


def _cfg():
    return current_app.config["LV"]


def default_voice(user, language):
    vs = user.voice_settings_json or {}
    return (vs.get("voices") or {}).get(language) or f"{language}-default"


# ---------------------------------------------------------------- snapshots


def parse_context(data):
    ev = parse_uuid(data.get("client_event_id"), "client_event_id")
    observed = parse_datetime(data.get("observed_at"), "observed_at")
    loc = data.get("location") or {}
    try:
        lat, lon = float(loc["lat"]), float(loc["lon"])
    except (KeyError, TypeError, ValueError):
        raise bad_request("location.lat and location.lon are required", {"field": "location"})
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or math.isnan(lat) or math.isnan(lon):
        raise bad_request("location out of range", {"field": "location"})
    acc = loc.get("accuracy_m")
    motion = data.get("motion") or {}
    topics = [t for t in (data.get("active_topics") or []) if t in CATEGORIES]
    speaking = data.get("speaking") is True  # the app is still telling the previous story

    def num(v):
        try:
            return None if v is None else float(v)
        except (TypeError, ValueError):
            return None

    offset = num(data.get("utc_offset_min"))  # the phone's time zone, so "morning" is morning where the user is
    if offset is not None and not -14 * 60 <= offset <= 14 * 60:
        offset = None

    return {
        "client_event_id": ev,
        "observed_at": observed,
        "lat": lat,
        "lon": lon,
        "accuracy_m": num(acc),
        "speed_mps": num(motion.get("speed_mps")),
        "course_deg": num(motion.get("course_deg")),
        "transport_mode": motion.get("transport_mode"),
        "confidence": num(motion.get("confidence")),
        "course_confidence": num(motion.get("course_confidence")),
        "active_topics": topics,
        "utc_offset_min": None if offset is None else int(offset),
        "speaking": speaking,
    }


def store_snapshot(db, trip, ctx):
    """Returns (snapshot, is_duplicate). Raises 409 for same id with different content."""
    existing = db.execute(
        select(ContextSnapshot).where(
            ContextSnapshot.trip_session_id == trip.id, ContextSnapshot.client_event_id == ctx["client_event_id"]
        )
    ).scalar_one_or_none()
    if existing is not None:
        plat, plon = point_of(existing.position)
        same = (
            abs(plat - ctx["lat"]) < 1e-7
            and abs(plon - ctx["lon"]) < 1e-7
            and abs((existing.observed_at - ctx["observed_at"]).total_seconds()) < 0.001
        )
        if not same:
            raise conflict("client_event_id reused with different content", "event_conflict")
        return existing, True
    retention = timedelta(days=_cfg().TRACK_RETENTION_DAYS)
    if ctx["observed_at"] < now() - retention:
        raise ApiError(410, "expired", "the point is older than the retention period")
    if ctx["observed_at"] > now() + timedelta(minutes=5):
        raise bad_request("observed_at is in the future", {"field": "observed_at"})
    tclass = geo.transport_class(ctx["transport_mode"], trip.manual_transport_mode, ctx["speed_mps"])
    snap = ContextSnapshot(
        trip_session_id=trip.id,
        client_event_id=ctx["client_event_id"],
        observed_at=ctx["observed_at"],
        position=f"SRID=4326;POINT({ctx['lon']} {ctx['lat']})",
        accuracy_m=ctx["accuracy_m"],
        speed_mps=ctx["speed_mps"],
        course_deg=ctx["course_deg"],
        inferred_transport_mode=tclass,
        confidence=ctx["confidence"],
        context_json={
            "client_transport_mode": ctx["transport_mode"],
            "course_confidence": ctx["course_confidence"],
            "active_topics": ctx["active_topics"],
            **({"utc_offset_min": ctx["utc_offset_min"]} if ctx.get("utc_offset_min") is not None else {}),
            **({"speaking": True} if ctx.get("speaking") else {}),
        },
    )
    db.add(snap)
    db.flush()
    return snap, False


def point_of(geom):
    """(lat, lon) from a geography column value (WKB element or the EWKT string we assigned)."""
    if isinstance(geom, str):
        lon, lat = geom.split("POINT(")[1].rstrip(")").split()
        return float(lat), float(lon)
    p = to_shape(geom)
    return p.y, p.x


def snapshot_point(snap):
    return point_of(snap.position)


def latest_snapshot(db, trip):
    return db.execute(
        select(ContextSnapshot)
        .where(ContextSnapshot.trip_session_id == trip.id)
        .order_by(ContextSnapshot.observed_at.desc(), ContextSnapshot.id.desc())
        .limit(1)
    ).scalar_one_or_none()


# ---------------------------------------------------------------- decision


def _silent(db, trip, snap, reason, mode, next_after=60, candidates=None, rule_choice=None, *, record=True, info=None,
            **extra):
    # info: what the app shows while waiting (e.g. whether new stories are being looked for); not logged
    decision = {"reason": reason, "next_check_after_sec": next_after, **(info or {})}
    if not record:
        # A prepared "nothing to say" is not a decision the traveller has been shown.
        return {"guide": None, "draft": None, "decision": decision}
    d = GuideDecision(
        trip_session_id=trip.id,
        context_snapshot_id=snap.id if snap is not None else None,
        trigger=extra.pop("trigger", "context"),
        candidates_json=[c.summary() for c in (candidates or [])],
        rule_choice_id=rule_choice.item.id if rule_choice else None,
        final_action="silent",
        reason=reason,
        selection_mode=mode,
        **extra,
    )
    db.add(d)
    db.flush()
    decision["decision_id"] = str(d.id)
    return {"guide": None, "decision": decision}


def llm_cost_so_far(db, trip_id):
    from .llm import LLM_PROVIDERS  # local import to avoid cycles

    return float(
        db.execute(
            select(func.coalesce(func.sum(ApiUsageLog.estimated_cost), 0)).where(
                ApiUsageLog.trip_session_id == trip_id, ApiUsageLog.provider.in_(LLM_PROVIDERS)
            )
        ).scalar_one()
    )


def active_intents(db, trip_id, t):
    return list(
        db.execute(
            select(IntentOverride).where(
                IntentOverride.trip_session_id == trip_id,
                IntentOverride.ended_at.is_(None),
                IntentOverride.expires_at > t,
            )
        ).scalars()
    )


def _local_time(snap):
    """observed_at in the phone's time zone when it sent one (older apps send UTC only)."""
    offset = (snap.context_json or {}).get("utc_offset_min")
    if offset is None:
        return snap.observed_at.isoformat()
    return snap.observed_at.astimezone(timezone(timedelta(minutes=offset))).isoformat()


def _course_confident(snap):
    cc = (snap.context_json or {}).get("course_confidence")
    speed = float(snap.speed_mps) if snap.speed_mps is not None else 0
    if snap.course_deg is None:
        return False
    if cc is not None:
        return cc >= 0.6
    return speed >= 1.0


def quiet_state(db, trip, t):
    return db.execute(
        select(TemporaryState).where(
            TemporaryState.trip_session_id == trip.id,
            TemporaryState.state_type == "quiet",
            TemporaryState.ended_at.is_(None),
            TemporaryState.expires_at > t,
        )
    ).scalar_one_or_none()


def evaluate(db, trip, user, snap, *, trigger="context", exclude_ids=(), record=True, extra_history=(), seed_extra=0):
    """Decide whether to speak for this snapshot. Always records a GuideDecision."""
    cfg = _cfg()
    t = now()
    settings = trip_settings(trip, user)
    mode = trip.selection_mode
    level = dict(NOTIFICATION_LEVELS.get(settings["notification_level"], NOTIFICATION_LEVELS[DEFAULT_NOTIFICATION_LEVEL]))
    # "continue": continuous mode asking for the next story as one ends. It skips the cooldown like a tap on
    # "next", but quiet mode still holds and it counts as an automatic guide.
    manual = trigger not in ("context", "continue")
    state_topics, cooldown_factor, detail_override = commands.state_effects(commands.active_states(db, trip.id, t))
    if cooldown_factor != 1.0:
        level["cooldown_sec"] = int(level["cooldown_sec"] * cooldown_factor)
        level["hourly_limit"] = max(1, round(level["hourly_limit"] / cooldown_factor))
    if detail_override:
        settings["detail_mode"] = detail_override

    if snap.accuracy_m is not None and float(snap.accuracy_m) > cfg.MAX_ACCURACY_M:
        return _silent(db, trip, snap, "low_accuracy", mode, cfg.LOW_ACCURACY_RECHECK_SEC, trigger=trigger, record=record)

    quiet = quiet_state(db, trip, t)
    if quiet is not None and not manual:
        return _silent(db, trip, snap, "quiet_mode", mode, int((quiet.expires_at - t).total_seconds()), trigger=trigger, record=record)

    history = todays_history(db, trip.id, t) + list(extra_history)
    auto_hist = [h for h in history if h.channel == "auto"]
    if not manual and auto_hist:
        since_last = (t - auto_hist[-1].shown_at).total_seconds()
        if trigger == "context" and since_last < level["cooldown_sec"]:
            return _silent(db, trip, snap, "cooldown", mode, int(level["cooldown_sec"] - since_last) + 1, trigger=trigger, record=record)
        last_hour = [h for h in auto_hist if h.shown_at > t - timedelta(hours=1)]
        if len(last_hour) >= level["hourly_limit"]:
            wait = int((last_hour[0].shown_at + timedelta(hours=1) - t).total_seconds()) + 1
            return _silent(db, trip, snap, "hourly_limit", mode, max(wait, 60), trigger=trigger, record=record,
                           info={"hourly_limit": level["hourly_limit"]})
    if trigger == "context" and (snap.context_json or {}).get("speaking"):
        # never cut into a story that is still being told; check again shortly
        return _silent(db, trip, snap, "speaking", mode, 15, trigger=trigger, record=record)
    if trigger == "context" and record:
        # the next stories were chosen (and voiced) while the last one played; use them when still nearby
        prepared = _take_prepared(db, trip, user, snap)
        if prepared is not None:
            return prepared

    lat, lon = snapshot_point(snap)
    tclass = snap.inferred_transport_mode or "walking"
    confident = _course_confident(snap)
    course = float(snap.course_deg) if snap.course_deg is not None else None
    raw, search_r = fetch_candidates(db, lat, lon, tclass, course, confident, trip.language, t,
                                     home_country=user.home_country)
    intents = active_intents(db, trip.id, t)
    session_topics = set((snap.context_json or {}).get("active_topics") or [])
    session_topics |= set((trip.settings_json or {}).get("focus_categories") or [])
    session_topics |= state_topics
    for (prof,) in db.execute(select(Participant.profile_json).where(Participant.trip_session_id == trip.id)):
        session_topics |= set((prof or {}).get("interests") or [])  # companions' interests (P1)
    for it in intents:
        if it.type == "focus_category" and it.target:
            session_topics.add(it.target)
    boosts = active_boosts(db, trip.id, t)
    for it in intents:
        if it.type == "suppress_category" and it.target:
            boosts[it.target] = boosts.get(it.target, 0) - 1.0
    interests = load_interests(db, user.id)
    ranked, serendipitous = score_candidates(
        raw,
        search_r=search_r,
        interests=interests,
        session_topics=session_topics,
        boosts=boosts,
        history=history,
        serendipity=settings["serendipity"],
        seed=seed_for(snap.client_event_id) + (1 if manual else 0) + seed_extra,
        excluded_ids=exclude_ids,
        heard_ids=heard_before_ids(db, user.id, trip.id, [c.item.id for c in raw]),
        t=t,
    )
    threshold = cfg.SCORE_THRESHOLD * (0.8 if trigger != "context" else 1.0)
    eligible = [c for c in ranked if c.score >= threshold]
    # Stories heard on an earlier trip are offered only when nothing unheard is good enough here.
    unheard = [c for c in eligible if not c.heard_before]
    top = (unheard or eligible)[: cfg.LLM_CANDIDATES]
    # country-wide manners say nothing about this place: they do not count as stories left here
    n_unheard = sum(1 for c in ranked if not c.heard_before and (c.item.metadata_json or {}).get("scope") != "country")
    narr_langs = narration_languages(user)
    _maybe_enqueue_generation(db, lat, lon, course if confident else None, tclass, n_unheard,
                              warm={lang: default_voice(user, lang) for lang in narr_langs})
    if not top:
        reason = "no_candidates" if not ranked else "below_threshold"
        searching = _generation_running(db, lat, lon, course if confident else None, tclass)
        # The tutorial, a story from a little further away, or one for anywhere fills the wait. Chosen live only
        # (never queued ahead by next_story), so the stories of this place take over as soon as they are ready.
        waiting = None if not record else _waiting_guide(db, trip, user, snap, lat, lon, settings, narr_langs, searching=searching,
                                 exclude=set(exclude_ids) | {h.knowledge_item_id for h in history},
                                 trigger=trigger, record=record, seed=seed_for(snap.client_event_id) + seed_extra)
        if waiting is not None:
            return waiting
        # while new stories are being written here, look again sooner so the guide resumes once they are ready
        return _silent(db, trip, snap, reason, mode, cfg.SEARCHING_RECHECK_SEC if searching else 60,
                       candidates=ranked[:10], trigger=trigger, record=record, info={"searching": searching})

    rule_choice = top[0]
    sel_input = SelectionInput(
        candidates=top,
        language=trip.language,
        narration_languages=narr_langs,
        detail_mode=settings["detail_mode"],
        transport_class=tclass,
        course_confident=confident,
        recent_titles=[h.title for h in history[-8:]],
        memory_summary=trip.memory_summary,
        interests=interests,
        boosts=boosts,
        local_time=_local_time(snap),
        trigger=trigger,
        intents=[i.label for i in intents if i.label],
        recent_stories=[_story_trace(h) for h in history[-2:]],
    )
    decision_extra = {
        "input_json": {
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "transport_class": tclass,
            "course_deg": course,
            "course_confident": confident,
            "serendipitous": serendipitous,
            "session_topics": sorted(session_topics),
            "boosts": boosts,
            "recent_titles": sel_input.recent_titles,
        }
    }

    chosen, selection, fallback, fallback_reason = rule_choice, None, False, None
    llm_meta = {}
    if mode == "llm":
        from .llm import get_llm, llm_provider  # local import to avoid cycles

        llm = get_llm()
        if llm is None:
            fallback, fallback_reason = True, "llm_disabled"
        elif llm_cost_so_far(db, trip.id) >= cfg.LLM_SESSION_COST_LIMIT_USD:
            fallback, fallback_reason = True, "cost_limit"
        else:
            result = llm.select(sel_input)
            _log_llm_usage(db, trip.id, result, llm_provider(llm))
            llm_meta = {
                "llm_model": result.model,
                "prompt_version": result.prompt_version,
                "latency_ms": result.latency_ms,
                "estimated_cost": result.cost_usd,
            }
            if result.error:
                fallback, fallback_reason = True, result.error[:64]
            elif result.action == "stay_silent":
                return _silent(
                    db, trip, snap, "llm_silent", mode, 60, candidates=top, rule_choice=rule_choice,
                    trigger=trigger, llm_reason=result.reason, record=record, **llm_meta, **decision_extra,
                )
            else:
                selection = result
                chosen = next(c for c in top if str(c.item.id) == selection.knowledge_id)

    item = chosen.item
    title, text, body = item_texts(item, trip.language, settings["detail_mode"])
    # The story is heard from audio shared by every traveller; the LLM only adds a short intro for this moment,
    # so a personalised guide costs one short private synthesis instead of the whole story.
    speech_text = item_speech_text(item, trip.language, text)
    intros = {}
    if selection is not None:
        title = selection.title or title
        text = selection.text or text
        intros = selection.intros
    intro = intros.get(trip.language, "")
    narrations = _narrations(item, narr_langs, intros, settings["detail_mode"])
    draft = {
        "knowledge_item_id": str(item.id),
        "rule_choice_id": str(rule_choice.item.id),
        "llm_choice_id": str(item.id) if selection is not None else None,
        "title": title,
        "text": text,
        "detail_text": body,
        "language": trip.language,
        "score": float(chosen.score),
        "score_components": {
            **chosen.components,
            "category": item.category,
            "duplicate_group": (item.metadata_json or {}).get("duplicate_group"),
            "used_claim_ids": selection.used_claim_ids if selection else [],
            "story_type": _storytelling(item).get("story_type"),
        },
        "selection_mode": "llm" if selection is not None else "rule",
        "speech": {
            "text": f"{intro} {speech_text}" if intro else speech_text,  # all that is heard (device TTS reads it)
            "intro": intro or None,
            "body": speech_text,
            "language": trip.language,
            "content_version": item.content_version,
            "personalized": bool(intro),
            # every narration language in the order spoken; body None = translated when its audio is first asked for
            "narrations": narrations,
            # recorded so the next stories avoid the same techniques, and for learning which ones work
            "techniques": _item_techniques(item),
        },
        "location": location_payload(chosen),
        "detail_mode": settings["detail_mode"],
        "candidates": [c.summary() for c in top],
        "llm_reason": selection.reason if selection else None,
        "fallback": fallback,
        "fallback_reason": fallback_reason,
        "llm_meta": {
            k: (float(v) if k == "estimated_cost" and v is not None else v) for k, v in llm_meta.items()
        },
        "input_json": decision_extra["input_json"],
        "trigger": trigger,
    }
    if not record:
        return {"guide": None, "draft": draft, "decision": {"reason": "selected", "fallback": fallback, "next_check_after_sec": 60}}
    return materialize(db, trip, user, snap, draft)


def _waiting_guide(db, trip, user, snap, lat, lon, settings, narr_langs, *, searching, exclude, trigger, record, seed):
    """A story to tell while nothing is ready here (waiting.py), as a guide (or a draft when not recording)."""
    from . import waiting  # local import to avoid cycles

    found = waiting.waiting_story(
        db, user, trip, lat, lon, trip.language, searching=searching, filler_radius_m=_cfg().FILLER_RADIUS_M,
        exclude_ids=exclude, seed=seed, tutorial=_cfg().TUTORIAL_ENABLED,
    )
    if found is None:
        return None
    item, kind, distance = found
    if kind == "nearby":
        intros = {lang: waiting.filler_intro(distance, lang) for lang in narr_langs}
    elif kind == "global":
        intros = {lang: waiting.global_intro(lang) for lang in narr_langs}
    else:
        intros = {}
    intros = {k: v for k, v in intros.items() if v}
    title, text, body = item_texts(item, trip.language, settings["detail_mode"])
    speech_text = item_speech_text(item, trip.language, text)
    intro = intros.get(trip.language, "")
    location = None
    if kind == "nearby":
        ilat, ilon = point_of(item.position)
        location = {"lat": ilat, "lon": ilon, "radius_m": item.radius_m,
                    "kind": "area" if (item.metadata_json or {}).get("scope") == "area" or item.radius_m >= 800 else "point",
                    "distance_m": round(distance), "relative_direction": None}
    draft = {
        "knowledge_item_id": str(item.id),
        "rule_choice_id": str(item.id),
        "llm_choice_id": None,
        "title": title,
        "text": text,
        "detail_text": body,
        "language": trip.language,
        "score": 0.0,
        "score_components": {"category": item.category, "waiting": kind,
                             "story_type": _storytelling(item).get("story_type")},
        "selection_mode": "rule",
        "speech": {
            "text": f"{intro} {speech_text}" if intro else speech_text,
            "intro": intro or None,
            "body": speech_text,
            "language": trip.language,
            "content_version": item.content_version,
            "personalized": bool(intro),
            "narrations": _narrations(item, narr_langs, intros, settings["detail_mode"]),
            "techniques": _item_techniques(item),
        },
        "location": location,
        "detail_mode": settings["detail_mode"],
        "candidates": [],
        "llm_reason": None,
        "fallback": False,
        "fallback_reason": None,
        "llm_meta": {},
        "input_json": {"lat": round(lat, 5), "lon": round(lon, 5), "waiting": kind, "searching": searching},
        "trigger": trigger,
    }
    if not record:
        return {"guide": None, "draft": draft, "decision": {"reason": "selected", "fallback": False, "next_check_after_sec": 60}}
    result = materialize(db, trip, user, snap, draft)
    if result is not None:
        result["decision"]["waiting"] = kind
        result["decision"]["searching"] = searching
    return result


def _take_prepared(db, trip, user, snap):
    from . import next_story  # local import to avoid cycles

    latest = db.execute(
        select(NotificationHistory.id)
        .where(NotificationHistory.trip_session_id == trip.id)
        .order_by(NotificationHistory.shown_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        return None
    taken = next_story.take(db, trip, user, snap, latest, trigger="context")
    if not taken or not taken["result"]:
        return None
    # the caller keeps the rest of the queue ("_keep" is removed before the response is sent)
    return {**taken["result"], "_keep": taken["remaining"]}


def materialize(db, trip, user, snap, draft):
    """Turn a prepared story into the guide the traveller is actually shown."""
    item = db.get(KnowledgeItem, uuid.UUID(draft["knowledge_item_id"]))
    if item is None or item.review_status == "suspended":
        return None
    if item.valid_until is not None and item.valid_until <= now():
        return None
    trigger = draft.get("trigger") or "context"
    meta = draft.get("llm_meta") or {}
    decision = GuideDecision(
        trip_session_id=trip.id,
        context_snapshot_id=snap.id if snap is not None else None,
        trigger=trigger,
        candidates_json=draft.get("candidates") or [],
        rule_choice_id=uuid.UUID(draft["rule_choice_id"]) if draft.get("rule_choice_id") else None,
        llm_choice_id=uuid.UUID(draft["llm_choice_id"]) if draft.get("llm_choice_id") else None,
        final_action="speak",
        reason="selected",
        llm_reason=draft.get("llm_reason"),
        selection_mode=draft.get("selection_mode") or "rule",
        fallback=bool(draft.get("fallback")),
        fallback_reason=draft.get("fallback_reason"),
        llm_model=meta.get("llm_model"),
        prompt_version=meta.get("prompt_version"),
        latency_ms=meta.get("latency_ms"),
        estimated_cost=meta.get("estimated_cost"),
        input_json=draft.get("input_json") or {},
    )
    db.add(decision)
    db.flush()
    hist = NotificationHistory(
        trip_session_id=trip.id,
        knowledge_item_id=item.id,
        guide_decision_id=decision.id,
        channel="auto" if trigger in ("context", "continue") else "manual",
        score=draft["score"],
        score_components=draft.get("score_components") or {},
        title=draft["title"],
        rendered_text=draft["text"],
        detail_text=draft["detail_text"],
        language=draft["language"],
        selection_mode=draft["selection_mode"],
        speech_snapshot_json=draft["speech"],
    )
    db.add(hist)
    db.flush()
    guide = guide_payload(
        hist, item, draft.get("location"),
        voice_for=lambda lang: default_voice(user, lang), selection_mode=hist.selection_mode,
    )
    return {
        "guide": guide,
        "decision": {
            "score": round(float(draft["score"]), 4),
            "reason": "selected",
            "decision_id": str(decision.id),
            "fallback": bool(draft.get("fallback")),
            # the next automatic story cannot come before the cooldown ends, so the app need not ask sooner
            "next_check_after_sec": max(60, cooldown_sec(trip, user)) if hist.channel == "auto" else 60,
        },
    }


def _log_llm_usage(db, trip_id, sel, provider):
    if sel.model is None:
        return
    db.add(
        ApiUsageLog(
            trip_session_id=trip_id,
            provider=provider,
            operation="select_narrate",
            request_units=1,
            estimated_cost=sel.cost_usd or 0,
            details_json={"model": sel.model, "latency_ms": sel.latency_ms, "error": sel.error},
        )
    )


def cooldown_sec(trip, user):
    level = trip_settings(trip, user)["notification_level"]
    return NOTIFICATION_LEVELS.get(level, NOTIFICATION_LEVELS[DEFAULT_NOTIFICATION_LEVEL])["cooldown_sec"]


def describe_pacing(result, trip, user):
    """Adds what the app needs to explain the wait before the next story (level and its cooldown in seconds)."""
    decision = result.setdefault("decision", {})
    level = trip_settings(trip, user)["notification_level"]
    if level not in NOTIFICATION_LEVELS:
        level = DEFAULT_NOTIFICATION_LEVEL
    decision["notification_level"] = level
    decision["cooldown_sec"] = NOTIFICATION_LEVELS[level]["cooldown_sec"]
    return result


def _generation_running(db, lat, lon, course, tclass):
    """True while stories for this spot (or right around it) are queued or being written."""
    if not _cfg().KNOWLEDGE_GENERATION_ENABLED:
        return False
    try:
        from .knowledge_gen import generation_running
    except ImportError:
        return False
    return generation_running(db, lat, lon, course, tclass)


def _maybe_enqueue_generation(db, lat, lon, course, tclass, n_left, warm=None):
    """n_left: stories still untold here. When few are left (typically while staying in one place),
    the cells around the current one are queued too, so "next story" has something new to offer.
    warm: the traveller's voices, so the first stories written for a new place are voiced at once."""
    cfg = _cfg()
    if not cfg.KNOWLEDGE_GENERATION_ENABLED:
        return
    try:
        from .knowledge_gen import enqueue_for_position

        enqueue_for_position(db, lat, lon, course, tclass, nearby=n_left < cfg.NEARBY_GENERATION_MIN_STORIES, warm=warm)
    except ImportError:
        pass


def item_location(db, item):
    if item.position is None:
        return None
    lat, lon = point_of(item.position)
    return {
        "lat": lat,
        "lon": lon,
        "radius_m": item.radius_m,
        "kind": "area" if (item.metadata_json or {}).get("scope") == "area" or item.radius_m >= 800 else "point",
    }


def history_payload(db, hist, user):
    item = db.get(KnowledgeItem, hist.knowledge_item_id)
    return guide_payload(
        hist, item, item_location(db, item),
        voice_for=lambda lang: default_voice(user, lang), selection_mode=hist.selection_mode,
    )


def _narrations(item, langs, intros, detail_mode):
    out = []
    for lang in langs:
        story = localized_story(item, lang)
        out.append({"language": lang, "intro": intros.get(lang) or None,
                    "body": spoken_text(story, detail_mode) if story else None})
    return out


def _storytelling(item):
    return (item.metadata_json or {}).get("storytelling") or {}


def _item_techniques(item):
    st = _storytelling(item)
    if not st:
        return None
    return {k: st.get(k) for k in ("opening", "structure", "style", "devices", "tone")}


def _story_trace(h):
    """What the next story should not repeat: type, tone, length and techniques of a story already told."""
    speech = h.speech_snapshot_json or {}
    techniques = speech.get("techniques") or {}
    return {
        "story_type": (h.score_components or {}).get("story_type"),
        "tone": techniques.get("tone"),
        "length": len(speech.get("text") or ""),
        "techniques": {k: techniques.get(k) for k in ("opening", "structure", "style") if techniques.get(k)},
    }
