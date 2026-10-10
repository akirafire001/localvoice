#!/usr/bin/env python3
"""Hand LocalVoice's story generation to an AI subscription's agent (Codex, Claude Code, Antigravity, Cursor...).

The server picks the cell and runs the usual pipeline; this script fetches the steps the agent has to do (web
searches and story writing), writes them to files, and sends the agent's answers back. Standard library only.

    python tools/subgen/subgen.py plan   --agent codex              # how many cells to do in this run
    python tools/subgen/subgen.py next   --agent codex --model gpt-x  # start or resume a cell, write the steps
    python tools/subgen/subgen.py submit --agent codex              # send the answers, write the next steps
    python tools/subgen/subgen.py abandon --agent codex             # give the current cell back

Settings: LOCALVOICE_SERVER (default https://localvoice.ideaworks.tech) and LOCALVOICE_EXTERNAL_GEN_TOKEN
(environment variables, or the files .subgen/server and .subgen/token). See docs/external-generation.md.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".subgen"
SCHEDULE = Path(__file__).resolve().with_name("schedule.json")
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# exit codes, so a scheduled prompt can tell what happened
MORE_STEPS, CELL_DONE, NOTHING_TO_DO, ERROR = 0, 3, 4, 1


def setting(name, env, default=None):
    if os.environ.get(env):
        return os.environ[env].strip()
    f = WORK / name
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    return default


def api(method, path, body=None):
    server = setting("server", "LOCALVOICE_SERVER", "https://localvoice.ideaworks.tech").rstrip("/")
    token = setting("token", "LOCALVOICE_EXTERNAL_GEN_TOKEN")
    if not token:
        sys.exit("LOCALVOICE_EXTERNAL_GEN_TOKEN is not set (or write it to .subgen/token)")
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(f"{server}/api/v1/external-gen{path}", data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise SystemExit(f"server answered {e.code}: {detail}") from None


def agent_dir(agent):
    d = WORK / agent
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_state(agent):
    f = agent_dir(agent) / "state.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def save_state(agent, state):
    (agent_dir(agent) / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def clear_steps(d):
    for f in d.glob("call-*"):
        f.unlink()
    for f in d.glob("answer-*.json"):
        f.unlink()


def write_steps(agent, body):
    """One file per pending call, plus TODO.md saying what to do and where to write each answer."""
    d = agent_dir(agent)
    clear_steps(d)
    calls = body["calls"]
    save_state(agent, {"task_id": body["task_id"], "cell": body["cell"], "place": body.get("place"),
                       "pending": [c["index"] for c in calls]})
    place = body.get("place") or body["cell"]
    lines = [f"# LocalVoice: {place} (cell {body['cell']})", "",
             f"Answer every step below, then run: python tools/subgen/subgen.py submit --agent {agent}", ""]
    for c in calls:
        i = c["index"]
        answer = d / f"answer-{i}.json"
        if c["kind"] == "web_research":
            f = d / f"call-{i}.md"
            f.write_text(f"## Web research (step {i})\n\n{c['instructions']}\n\n"
                         f"Answer file: {answer}\nFormat: a JSON list, e.g. "
                         '[{"fact": "...", "url": "https://...", "title": "..."}] or [] when nothing is found.\n\n'
                         f"### Prompt\n\n{c['prompt']}\n", encoding="utf-8")
            lines.append(f"- step {i}: web research. Read {f} and write the JSON list to {answer}")
        else:
            sysf, inf, scf = d / f"call-{i}-system.md", d / f"call-{i}-input.json", d / f"call-{i}-schema.json"
            sysf.write_text(c["system"], encoding="utf-8")
            inf.write_text(json.dumps(c["input"], ensure_ascii=False, indent=1), encoding="utf-8")
            scf.write_text(json.dumps(c["schema"], ensure_ascii=False, indent=1), encoding="utf-8")
            lines.append(f"- step {i}: writing. {c['instructions']} Instructions: {sysf}. Input: {inf}. "
                         f"Schema: {scf}. Write the JSON object to {answer}")
    (d / "TODO.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def report_done(agent, body):
    d = agent_dir(agent)
    clear_steps(d)
    save_state(agent, {})
    (d / "TODO.md").unlink(missing_ok=True)
    place = body.get("place") or body.get("cell")
    if body["status"] == "done":
        print(f"DONE: {place}: {body.get('created', 0)} stories saved.")
    else:
        print(f"CLOSED: {place}: {body['status']} {body.get('error') or ''}")
    if body.get("progress"):
        print("progress:", json.dumps(body["progress"], ensure_ascii=False))
    print(f"Next cell: python tools/subgen/subgen.py next --agent {agent}")
    return CELL_DONE


def cmd_next(a):
    state = load_state(a.agent)
    if state.get("task_id"):
        body = api("GET", f"/tasks/{state['task_id']}")
        if body["status"] == "active":
            write_steps(a.agent, body)
            return MORE_STEPS
    body = api("POST", "/tasks", {"agent": a.agent, "model": a.model})
    if body["status"] == "nothing_to_do":
        save_state(a.agent, {})
        print("NOTHING_TO_DO: every target cell has enough stories.", json.dumps(body.get("progress"), ensure_ascii=False))
        return NOTHING_TO_DO
    if body["status"] != "active":
        return report_done(a.agent, body)
    write_steps(a.agent, body)
    return MORE_STEPS


def cmd_submit(a):
    state = load_state(a.agent)
    if not state.get("task_id"):
        sys.exit(f"no cell in progress: run `next --agent {a.agent}` first")
    d = agent_dir(a.agent)
    answers, missing = [], []
    for i in state["pending"]:
        f = d / f"answer-{i}.json"
        if not f.exists():
            missing.append(str(f))
            continue
        try:
            answers.append({"index": i, "result": json.loads(f.read_text(encoding="utf-8"))})
        except ValueError as e:
            sys.exit(f"{f} is not valid JSON: {e}")
    if missing:
        sys.exit("answers missing: " + ", ".join(missing))
    body = api("POST", f"/tasks/{state['task_id']}/answers", {"answers": answers})
    if body["status"] != "active":
        return report_done(a.agent, body)
    write_steps(a.agent, body)
    return MORE_STEPS


def cmd_abandon(a):
    state = load_state(a.agent)
    if state.get("task_id"):
        api("POST", f"/tasks/{state['task_id']}/abandon")
    clear_steps(agent_dir(a.agent))
    save_state(a.agent, {})
    print("abandoned")
    return CELL_DONE


def hours_to_reset(reset, t):
    """Hours from t until the next weekly reset given as "mon 09:00" (local time)."""
    day, _, hm = reset.strip().lower().partition(" ")
    h, _, m = hm.partition(":")
    target = t.replace(hour=int(h), minute=int(m or 0), second=0, microsecond=0)
    target += timedelta(days=(DAYS.index(day[:3]) - t.weekday()) % 7)
    if target <= t:
        target += timedelta(days=7)
    return (target - t).total_seconds() / 3600


def hours_to_monthly_reset(day, t):
    """Hours from t until the quota resets on `day` of the month (00:00 local time)."""
    target = t.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for _ in range(3):
        try:
            cand = target.replace(day=day)
        except ValueError:  # the month is shorter: its last day
            cand = (target.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        if cand > t:
            return (cand - t).total_seconds() / 3600
        target = (target.replace(day=28) + timedelta(days=4)).replace(day=1)
    return 24 * 31


def cmd_plan(a):
    cfg = json.loads(SCHEDULE.read_text(encoding="utf-8"))
    local = WORK / "schedule.json"
    if local.exists():  # the owner's own reset times and amounts, outside Git
        for k, v in json.loads(local.read_text(encoding="utf-8")).get("agents", {}).items():
            cfg["agents"][k] = {**cfg["agents"].get(k, {}), **v}
    ag = cfg["agents"].get(a.agent) or cfg["agents"]["default"]
    t = datetime.now()
    if ag.get("monthly_reset"):
        left, span = hours_to_monthly_reset(int(ag["monthly_reset"]), t), "monthly"
    else:
        left, span = hours_to_reset(ag["weekly_reset"], t), "weekly"
    final = left <= ag.get("final_hours", 24)
    n = ag["final_cells"] if final else ag["cells"]
    why = f"{span} quota resets in {left:.0f} h" + (": use what is left" if final else "")
    print(f"CELLS={n}  ({a.agent}: {why})")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "next", "submit", "abandon"):
        s = sub.add_parser(name)
        s.add_argument("--agent", required=True, help="codex / claude / gemini / cursor ...")
        if name == "next":
            s.add_argument("--model", default=None, help="model the agent runs on, recorded with each story")
    a = p.parse_args()
    return {"plan": cmd_plan, "next": cmd_next, "submit": cmd_submit, "abandon": cmd_abandon}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
