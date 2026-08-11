#!/usr/bin/env python3
import json
import os
from pathlib import Path
from datetime import datetime, timezone

ROLES = {
    "cover", "toc", "section", "bullets", "two-column", "image-hero",
    "image-side", "gallery", "table", "kpi", "quote", "compare",
    "timeline", "closing"
}
THEMES = {
    "business-dark", "business-light", "tech-dark", "editorial",
    "warm-human", "minimal-white"
}


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def now():
    return datetime.now(timezone.utc).isoformat()


def load_state(path):
    p = Path(path)
    if not p.exists():
        return {
            "current_phase": "init",
            "completed_pages": [],
            "qa_round": 0,
            "errors": [],
            "checkpoints": [],
            "updated_at": now(),
        }
    try:
        return read_json(p)
    except Exception:
        backup = p.with_suffix(".corrupt.json")
        p.replace(backup)
        return {
            "current_phase": "recovered",
            "completed_pages": [],
            "qa_round": 0,
            "errors": [{"at": now(), "message": "state corrupted; backed up to " + str(backup)}],
            "checkpoints": [],
            "updated_at": now(),
        }


def save_state(path, state, phase=None, checkpoint=None):
    if phase:
        state["current_phase"] = phase
    if checkpoint:
        state.setdefault("checkpoints", []).append({"at": now(), "name": checkpoint})
    state["updated_at"] = now()
    write_json(path, state)


def rel_to(base_file, maybe_relative):
    p = Path(maybe_relative)
    if p.is_absolute():
        return p
    return Path(base_file).resolve().parent / p


def no_abs_path(text):
    cwd = os.getcwd()
    return cwd not in text
