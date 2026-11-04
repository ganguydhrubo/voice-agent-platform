"""Delete transcripts past each tenant's retention period, and expired login sessions."""
from __future__ import annotations

import asyncio
import logging

from backend.db import later_iso, now_iso
from backend.runtime import Runtime

log = logging.getLogger("vap.retention")


def apply_retention(runtime: Runtime) -> int:
    removed = 0
    for tenant in runtime.db.all("SELECT id, transcript_retention_days FROM tenants"):
        cutoff = later_iso(days=-tenant["transcript_retention_days"])
        done = runtime.db.execute(
            "DELETE FROM conversations WHERE tenant_id = ? AND started_at < ?", (tenant["id"], cutoff)
        )
        removed += done.rowcount
    runtime.db.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (now_iso(),))
    runtime.db.execute("DELETE FROM password_resets WHERE expires_at < ?", (now_iso(),))
    return removed


async def retention_loop(runtime: Runtime, every_seconds: int = 3600) -> None:
    while True:
        try:
            removed = await asyncio.to_thread(apply_retention, runtime)
            if removed:
                log.info("Retention removed %s conversations.", removed)
        except Exception:
            log.exception("Retention run failed.")
        await asyncio.sleep(every_seconds)
