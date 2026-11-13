"""Campaign memory for :class:`~dmbot.runtime.SessionRuntime`: rotated session journals are
ingested into the RAG store in the background (ADR 054), on ``!leave`` and as a ``!join`` catch-up.

A mixin (ADR 065): its methods are methods of the one ``SessionRuntime`` object — ``self`` is
the runtime, all state is created in its ``__init__``.

``_session_ingest_source`` (which RAG source a channel's sessions go to) stays in runtime.py next
to ``is_debug_run``: it checks for the debug sidecar, and the ADR 052 pin allows only runtime.py
to name that file.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from ..rag import ingest_session

log = logging.getLogger(__name__)


class SessionIngestMixin:
    """Session-transcript ingest. Mixed into ``SessionRuntime``; holds no state of its own."""

    def schedule_session_ingest(self, channel_id: int, rotated: Path | None) -> None:
        """Ingest one just-rotated journal in the background (the !leave trigger). Degrades
        silently: any failure only logs; !leave never waits on it."""
        if rotated is None or self._session_ingest_source(channel_id) is None:
            return
        self._spawn_session_ingest([Path(rotated)], channel_id)

    def schedule_session_catchup(self, channel_id: int) -> None:
        """Ingest every rotated journal whose stamp isn't in the store yet, in the background
        (the !join trigger). Self-healing: covers crashes, shutdown-during-ingest — and the
        first !join after the feature lands backfills all existing rotated sessions."""
        if self._session_ingest_source(channel_id) is None:
            return
        session_dir = self._history_path(channel_id).parent
        db_path = self._retriever._db_path
        debug = self.is_debug_run  # captured now — the scan sees only this mode's archives

        def _scan_and_ingest() -> None:
            pending = ingest_session.pending_files(session_dir, db_path=db_path, debug=debug)
            if pending:
                # gate-G10 evidence: the catch-up half of the ingest story is greppable too
                log.info("🗂 session memory: catch-up — %d rotated journal(s) pending",
                         len(pending))
            for path in pending:
                self._ingest_one(path, channel_id)

        self._spawn_session_task(_scan_and_ingest)

    def _ingest_one(self, path: Path, channel_id: int) -> None:
        """One journal into the store (worker thread). Failures log and skip the file — the
        catch-up retries it on the next !join because its stamp was never recorded."""
        try:
            n = ingest_session.ingest_session_file(
                path, channel_id=channel_id,
                db_path=self._retriever._db_path, host=self._ollama_host,
            )
            log.info("🗂 session memory: ingested %s (%d chunks)", path.name, n)
        except Exception:
            log.exception("session ingest failed for %s — skipped", path.name)

    def _spawn_session_ingest(self, paths: list[Path], channel_id: int) -> None:
        def _work() -> None:
            for path in paths:
                self._ingest_one(path, channel_id)

        self._spawn_session_task(_work)

    def _spawn_session_task(self, work) -> None:
        """Run ``work`` (sync, does its own error logging) off the event loop as a fire-and-forget
        background task. Without a running loop (unit tests) it degrades to a no-op."""
        try:
            task = asyncio.get_running_loop().create_task(asyncio.to_thread(work))
        except RuntimeError:
            log.debug("no running event loop — session ingest not scheduled")
            return
        self._session_tasks.add(task)
        task.add_done_callback(self._session_tasks.discard)
