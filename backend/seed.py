"""First-run set-up: one tenant, the owner account, the 16 agents and their sample knowledge."""
from __future__ import annotations

import logging

from agent_engine.config.loader import load_bundled_agents
from backend.db import new_id, now_iso
from backend.runtime import Runtime
from backend.security import hash_password
from knowledge_engine.ingestion.parsers import IngestionError

log = logging.getLogger("vap.seed")
DEFAULT_TENANT_SLUG = "default"


def ensure_tenant(runtime: Runtime) -> str:
    row = runtime.db.one("SELECT id FROM tenants WHERE slug = ?", (DEFAULT_TENANT_SLUG,))
    if row:
        return row["id"]
    tenant_id = new_id()
    runtime.db.execute(
        "INSERT INTO tenants (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
        (tenant_id, DEFAULT_TENANT_SLUG, "Default Organisation", now_iso()),
    )
    return tenant_id


def ensure_owner(runtime: Runtime, tenant_id: str) -> None:
    settings = runtime.settings
    if not settings.admin_email or not settings.admin_password:
        return
    if runtime.db.one("SELECT id FROM users WHERE email = ?", (settings.admin_email.lower(),)):
        return
    runtime.db.execute(
        "INSERT INTO users (id, tenant_id, email, full_name, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?, 'owner', ?)",
        (new_id(), tenant_id, settings.admin_email.lower(), "Owner", hash_password(settings.admin_password), now_iso()),
    )
    log.info("Created the owner account.")


def ensure_agents(runtime: Runtime, tenant_id: str) -> None:
    for bundled in load_bundled_agents():
        config = bundled.config
        if runtime.db.one("SELECT id FROM agents WHERE tenant_id = ? AND slug = ?", (tenant_id, config.slug)):
            continue
        for name in config.knowledge_bases:
            existing = runtime.db.one(
                "SELECT id FROM knowledge_bases WHERE tenant_id = ? AND name = ?", (tenant_id, name)
            )
            base_id = existing["id"] if existing else runtime.knowledge.create_base(
                tenant_id, name, f"Sample knowledge for {config.industry}"
            )["id"]
            try:
                for path in bundled.sample_files:
                    runtime.knowledge.ingest_file(tenant_id, base_id, path.name, path.read_bytes())
                if bundled.sample_faq:
                    runtime.knowledge.ingest_faq(tenant_id, base_id, f"{config.organisation} FAQs", bundled.sample_faq)
            except IngestionError as error:
                log.warning("Sample knowledge for %s was skipped: %s", config.slug, error)
        now = now_iso()
        runtime.db.execute(
            "INSERT INTO agents (id, tenant_id, slug, name, industry, config, published, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (new_id(), tenant_id, config.slug, config.name, config.industry, config.model_dump_json(), now, now),
        )
        log.info("Added agent %s (%s).", config.name, config.industry)


def seed(runtime: Runtime) -> str:
    tenant_id = ensure_tenant(runtime)
    ensure_owner(runtime, tenant_id)
    ensure_agents(runtime, tenant_id)
    return tenant_id
