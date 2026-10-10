"""Stories written by the owner's AI subscriptions (services/external_gen.py; docs/external-generation.md).

Only the owner's agents call this, with `Authorization: Bearer <EXTERNAL_GEN_TOKEN>`; without the setting the
endpoints do not exist.
"""
import hmac

from flask import Blueprint, current_app, jsonify, request

from ..db import get_db
from ..errors import ApiError, bad_request, not_found, unauthorized
from ..models import ExternalGenTask
from ..services import external_gen
from ..util import json_body, parse_uuid

bp = Blueprint("external_gen", __name__)


@bp.before_request
def _auth():
    token = current_app.config["LV"].EXTERNAL_GEN_TOKEN
    if not token:
        raise not_found()
    given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(given.encode(), token.encode()):
        raise unauthorized()


def _task(db, task_id):
    task = db.get(ExternalGenTask, parse_uuid(task_id, "task_id"))
    if task is None:
        raise not_found("task not found")
    return task


def _body(db, task, calls):
    out = {"task_id": str(task.id), "cell": task.area_cell, "place": external_gen.place_name(task.area_cell),
           "status": task.status}
    if task.status == "active":
        out["calls"] = calls
    else:
        out["created"] = task.created_count
        out["error"] = task.error
        out["progress"] = external_gen.progress(db)
    return jsonify(out)


@bp.post("/external-gen/tasks")
def claim():
    data = json_body()
    agent = (data.get("agent") or "").strip()[:40]
    if not agent:
        raise bad_request("agent is required", {"field": "agent"})
    db = get_db()
    task, calls = external_gen.claim(db, agent, (data.get("model") or "").strip()[:80] or None)
    if task is None:
        return jsonify({"status": "nothing_to_do", "progress": external_gen.progress(db)})
    return _body(db, task, calls)


@bp.get("/external-gen/tasks/<task_id>")
def show(task_id):
    db = get_db()
    task = _task(db, task_id)
    return _body(db, task, external_gen.pending_requests(task))


@bp.post("/external-gen/tasks/<task_id>/answers")
def answer(task_id):
    db = get_db()
    task = _task(db, task_id)
    if task.status != "active":
        raise ApiError(409, "task_closed", f"this task is {task.status}")
    try:
        calls = external_gen.answer(db, task, json_body().get("answers"))
    except external_gen.AnswerError as e:
        raise bad_request(str(e), code="invalid_answer")
    return _body(db, db.get(ExternalGenTask, task.id), calls)


@bp.post("/external-gen/tasks/<task_id>/abandon")
def abandon(task_id):
    db = get_db()
    task = _task(db, task_id)
    if task.status == "active":
        external_gen.abandon(db, task)
    return _body(db, task, [])
