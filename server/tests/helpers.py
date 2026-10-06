import uuid
from datetime import datetime, timedelta, timezone

from localvoice.db import session_scope
from localvoice.models import KnowledgeClaim, KnowledgeItem, KnowledgeSource

# Itsukushima Shrine area
MIYAJIMA = (34.2959, 132.3199)


def add_item(app, title, lat, lon, *, category="history", radius_m=200, auto_eligible=True,
             interestingness=0.8, novelty=0.7, en=True, origin="curated", review_status="reviewed", **meta):
    with session_scope(app) as db:
        item = KnowledgeItem(
            canonical_key=f"test:{title}:{uuid.uuid4().hex[:6]}",
            title=title,
            title_en=f"{title} (en)" if en else None,
            category=category,
            short_ja=f"{title}の短い話",
            body_ja=f"{title}の詳しい話",
            short_en=f"Short story about {title}" if en else None,
            body_en=f"Long story about {title}" if en else None,
            position=f"SRID=4326;POINT({lon} {lat})",
            radius_m=radius_m,
            interestingness=interestingness,
            novelty=novelty,
            origin=origin,
            review_status=review_status,
            metadata_json={"story_quality": {"auto_eligible": auto_eligible}, **meta},
        )
        db.add(item)
        db.flush()
        src = KnowledgeSource(knowledge_item_id=item.id, url="https://example.org/src", title="src", publisher="ex")
        db.add(src)
        db.flush()
        db.add(KnowledgeClaim(knowledge_item_id=item.id, claim_text_ja=f"{title}の事実", source_ids=[src.id]))
        return str(item.id)


def iso_now(delta_sec=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_sec)).isoformat()


def ctx(lat, lon, *, acc=10, speed=1.2, course=90, mode="walking", observed_at=None, event_id=None, topics=None):
    return {
        "client_event_id": event_id or str(uuid.uuid4()),
        "observed_at": observed_at or iso_now(),
        "location": {"lat": lat, "lon": lon, "accuracy_m": acc},
        "motion": {"speed_mps": speed, "course_deg": course, "transport_mode": mode, "confidence": 0.8},
        "active_topics": topics or [],
    }
