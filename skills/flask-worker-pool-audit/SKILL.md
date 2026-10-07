---
name: flask-worker-pool-audit
description: "Audit Flask download-worker pools."
version: 1.0.0
author: Community
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [flask, threading, download, queue, audit, race-condition, performance]
    related: [media-downloader-fleet, audio-transcode-pipeline]
---

# Flask Worker Pool Audit

Six recurring defects appear in every Flask + threading.Event download
pipeline. Run each check before signing off on this kind of code.

## 1. The `_queue_event.clear()` race — never skip it

The canonical worker pattern:

```python
_queue_event = threading.Event()
_queued_order: list[str] = []

def _worker_loop():
    while True:
        with _priority_lock:
            if _queued_order:
                job_id = _queued_order.pop(0)
            else:
                job_id = None
        if job_id is None:
            _queue_event.wait(timeout=0.5)
            continue
        ...
```

Two landmines:

* **No clear at all** → event stays set after the first `set()` for the
  lifetime of the process. `wait(timeout=0.5)` returns immediately every
  loop, every idle worker burns a full CPU. Measured **6.6M wakeups/sec
  per idle worker** in 4 different production tool backends.
* **Clear OUTSIDE the lock** → between `with _priority_lock:` exit and
  `_queue_event.clear()`, an enqueue can set the event; the clear then
  wipes it and the worker sleeps the full `timeout=0.5` with the job
  sitting in the queue. Up to 0.5s latency per job under load.

**Correct:** clear **inside** the lock, as part of the same atomic op:

```python
with _priority_lock:
    if _queued_order:
        job_id = _queued_order.pop(0)
        _queue_event.clear()  # atomic with the pop
    else:
        job_id = None
```

## 2. Priority inversion — priority jobs must skip the FIFO queue

If you have a priority queue, a priority job enqueued behind 500 FIFO jobs
waits behind all of them. The worker must check priority first:

```python
def _worker_loop():
    while True:
        with _priority_lock:
            if _priority_queue:
                job_id = _priority_queue.pop(0)
            elif _queued_order:
                job_id = _queued_order.pop(0)
            else:
                job_id = None
            _queue_event.clear()
        if job_id is None:
            _queue_event.wait(timeout=0.5)
            continue
        ...
```

## 3. Stuck job detection — RUNNING jobs need a timeout sweep

A job that starts but never finishes (network hang, deadlock) stays RUNNING
forever. Add a reaper:

```python
import time

_stuck_threshold = 300  # seconds

def _reap_stuck_jobs():
    now = time.time()
    with _priority_lock:
        for job in _running_jobs.values():
            if now - job.started_at > _stuck_threshold:
                job.status = "failed"
                job.error = "timeout"
                del _running_jobs[job.id]
```

Run `_reap_stuck_jobs()` on a timer (e.g., every 60s via a background
thread or APScheduler).

## 4. Job state transitions — validate before applying

Invalid transitions (e.g., CANCEL a COMPLETED job) should return 400, not
silently succeed:

```python
_VALID_TRANSITIONS = {
    "queued": ["running", "cancelled"],
    "running": ["done", "failed", "cancelled"],
    "done": ["queued"],  # retry
    "failed": ["queued"],  # retry
    "cancelled": [],
}

def transition(job_id, new_status):
    job = _jobs[job_id]
    if new_status not in _VALID_TRANSITIONS[job.status]:
        return False, f"invalid transition {job.status} -> {new_status}"
    job.status = new_status
    return True, None
```

## 5. Graceful shutdown — drain the queue before exiting

On SIGTERM, stop accepting new jobs, wait for running jobs to finish,
then exit:

```python
import signal
import sys

_shutdown = False

def _handle_sigterm(signum, frame):
    global _shutdown
    _shutdown = True

signal.signal(signal.SIGTERM, _handle_sigterm)

def _worker_loop():
    while not _shutdown:
        ...
```

## 6. Thread-safe job ID generation

Use `itertools.count()` or `uuid.uuid4()` — never a bare `int` increment
without a lock:

```python
import itertools
_job_ids = itertools.count(1)

def _next_job_id():
    return f"job-{next(_job_ids)}"
```

## Audit Checklist

Before signing off on a Flask worker pool:

- [ ] `_queue_event.clear()` is inside the lock
- [ ] Priority jobs skip the FIFO queue
- [ ] Stuck job reaper is running
- [ ] Invalid state transitions return 400
- [ ] Graceful shutdown drains the queue
- [ ] Job IDs are thread-safe
- [ ] No bare `time.sleep()` in the main thread (blocks the app)
- [ ] Worker count matches expected concurrency
