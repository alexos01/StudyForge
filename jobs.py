"""
jobs.py
A minimal in-memory job registry so the frontend can poll the *actual*
current pipeline stage ("Extracting concepts", "Writing the quiz", etc.)
instead of cycling through a fake timed message list.

Fine for a single-process hackathon deployment. If you outgrow this,
swap it for Redis + a real task queue.
"""

import time
import uuid
from threading import Lock

_lock = Lock()
_jobs: dict = {}


def create_job() -> str:
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {
            "stage": "queued",
            "label": "Queued\u2026",
            "done": False,
            "error": None,
            "result": None,
            "created_at": time.time(),
        }
    return job_id


def update_job(job_id: str, **fields) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def get_job(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def cleanup_old_jobs(max_age_seconds: int = 3600) -> None:
    cutoff = time.time() - max_age_seconds
    with _lock:
        stale = [jid for jid, j in _jobs.items() if j["created_at"] < cutoff]
        for jid in stale:
            del _jobs[jid]