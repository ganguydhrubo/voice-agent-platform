"""The admin console's API. Every query is scoped to the signed-in user's tenant."""
from __future__ import annotations

import json
import re

import psutil
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, ValidationError, field_validator

from agent_engine.config.schema import AgentConfig
from agent_engine.orchestration.evaluate import run_agent_tests
from backend.api.auth import check_email, check_password_strength
from backend.db import new_id, now_iso
from backend.deps import CurrentUser, Page, audit, get_runtime, paged, paging, require
from backend.runtime import Runtime
from backend.security import hash_password
from knowledge_engine.ingestion.parsers import IngestionError, fetch_url

router = APIRouter(prefix="/api/admin", tags=["admin"])
NAME = re.compile(r"^[^\W\d_][\w .'-]{1,79}$")


# ---- overview ----------------------------------------------------------------------------


@router.get("/overview")
def overview(user: CurrentUser = Depends(require("viewer")), runtime: Runtime = Depends(get_runtime)) -> dict:
    tenant = user.tenant_id
    count = runtime.db.scalar
    return {
        "agents": count("SELECT COUNT(*) FROM agents WHERE tenant_id = ?", (tenant,)),
        "published_agents": count("SELECT COUNT(*) FROM agents WHERE tenant_id = ? AND published = 1", (tenant,)),
        "knowledge_bases": count("SELECT COUNT(*) FROM knowledge_bases WHERE tenant_id = ?", (tenant,)),
        "documents": count("SELECT COUNT(*) FROM documents WHERE tenant_id = ?", (tenant,)),
        "conversations": count("SELECT COUNT(*) FROM conversations WHERE tenant_id = ?", (tenant,)),
        "open_escalations": count("SELECT COUNT(*) FROM escalations WHERE tenant_id = ? AND status = 'open'", (tenant,)),
        "users": count("SELECT COUNT(*) FROM users WHERE tenant_id = ?", (tenant,)),
        "live": runtime.sessions.snapshot(),
    }


# ---- agents ------------------------------------------------------------------------------


def _agent_row(row) -> dict:
    config = json.loads(row["config"])
    return {
        "id": row["id"],
        "slug": row["slug"],
        "name": row["name"],
        "industry": row["industry"],
        "organisation": config.get("organisation", ""),
        "languages": config.get("languages", []),
        "published": bool(row["published"]),
        "version": row["version"],
        "updated_at": row["updated_at"],
    }


def _get_agent(runtime: Runtime, tenant: str, agent_id: str):
    row = runtime.db.one("SELECT * FROM agents WHERE id = ? AND tenant_id = ?", (agent_id, tenant))
    if not row:
        raise HTTPException(404, "Agent not found.")
    return row


def _validate_agent(body: dict) -> AgentConfig:
    try:
        config = AgentConfig.model_validate(body)
    except ValidationError as error:
        first = error.errors()[0]
        place = ".".join(str(part) for part in first["loc"])
        raise HTTPException(422, f"{place}: {first['msg']}.") from error
    problems = config.missing_translations()
    if problems:
        raise HTTPException(422, problems[0])
    return config


@router.get("/agents")
def list_agents(
    page: Page = Depends(paging), user: CurrentUser = Depends(require("viewer")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    where = "tenant_id = ? AND (name LIKE ? ESCAPE '\\' OR industry LIKE ? ESCAPE '\\')"
    args = (user.tenant_id, page.like, page.like)
    total = runtime.db.scalar(f"SELECT COUNT(*) FROM agents WHERE {where}", args)
    rows = runtime.db.all(
        f"SELECT * FROM agents WHERE {where} ORDER BY industry LIMIT ? OFFSET ?", (*args, page.size, page.offset)
    )
    return paged([_agent_row(row) for row in rows], total, page)


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, user: CurrentUser = Depends(require("viewer")), runtime: Runtime = Depends(get_runtime)) -> dict:
    row = _get_agent(runtime, user.tenant_id, agent_id)
    return {**_agent_row(row), "config": json.loads(row["config"])}


@router.post("/agents")
def create_agent(
    body: dict, request: Request, user: CurrentUser = Depends(require("editor")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    config = _validate_agent(body)
    if runtime.db.one("SELECT id FROM agents WHERE tenant_id = ? AND slug = ?", (user.tenant_id, config.slug)):
        raise HTTPException(409, "An agent with this slug already exists.")
    agent_id = new_id()
    now = now_iso()
    runtime.db.execute(
        "INSERT INTO agents (id, tenant_id, slug, name, industry, config, published, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
        (agent_id, user.tenant_id, config.slug, config.name, config.industry, config.model_dump_json(), now, now),
    )
    audit(runtime, request, user, "agent_created", agent_id)
    return {"id": agent_id, "message": "Agent created successfully."}


@router.put("/agents/{agent_id}")
def update_agent(
    agent_id: str,
    body: dict,
    request: Request,
    user: CurrentUser = Depends(require("editor")),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    row = _get_agent(runtime, user.tenant_id, agent_id)
    config = _validate_agent(body)
    if config.slug != row["slug"]:
        raise HTTPException(422, "An agent's slug cannot change once it is created.")
    runtime.db.execute(
        "UPDATE agents SET name = ?, industry = ?, config = ?, version = version + 1, updated_at = ?"
        " WHERE id = ? AND tenant_id = ?",
        (config.name, config.industry, config.model_dump_json(), now_iso(), agent_id, user.tenant_id),
    )
    audit(runtime, request, user, "agent_updated", agent_id)
    return {"message": "Agent updated successfully."}


@router.post("/agents/{agent_id}/publish")
def publish_agent(
    agent_id: str,
    request: Request,
    published: bool = True,
    user: CurrentUser = Depends(require("admin")),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    _get_agent(runtime, user.tenant_id, agent_id)
    runtime.db.execute(
        "UPDATE agents SET published = ? WHERE id = ? AND tenant_id = ?", (1 if published else 0, agent_id, user.tenant_id)
    )
    audit(runtime, request, user, "agent_published" if published else "agent_unpublished", agent_id)
    return {"message": "Agent published successfully." if published else "Agent unpublished successfully."}


@router.delete("/agents/{agent_id}")
def delete_agent(
    agent_id: str, request: Request, user: CurrentUser = Depends(require("admin")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    _get_agent(runtime, user.tenant_id, agent_id)
    runtime.db.execute("DELETE FROM agents WHERE id = ? AND tenant_id = ?", (agent_id, user.tenant_id))
    audit(runtime, request, user, "agent_deleted", agent_id)
    return {"message": "Agent deleted successfully."}


@router.post("/agents/{agent_id}/evaluate")
async def evaluate_agent(
    agent_id: str, user: CurrentUser = Depends(require("editor")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    row = _get_agent(runtime, user.tenant_id, agent_id)
    config = AgentConfig.model_validate_json(row["config"])
    names = tuple(config.knowledge_bases)
    marks = ",".join("?" * len(names)) or "''"
    kbs = runtime.db.all(
        f"SELECT id FROM knowledge_bases WHERE tenant_id = ? AND name IN ({marks})", (user.tenant_id, *names)
    )
    engine = runtime.engine_for(user.tenant_id, [item["id"] for item in kbs])
    return await run_agent_tests(engine, config)


# ---- knowledge ---------------------------------------------------------------------------


class BaseBody(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    description: str = Field(default="", max_length=300)

    @field_validator("name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name is required.")
        return value.strip()


class UrlBody(BaseModel):
    url: str = Field(min_length=8, max_length=500)


class FaqBody(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    pairs: list[dict[str, str]] = Field(min_length=1, max_length=500)


class SearchBody(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    language: str = Field(default="", max_length=2)


def _get_base(runtime: Runtime, tenant: str, kb_id: str):
    row = runtime.db.one("SELECT * FROM knowledge_bases WHERE id = ? AND tenant_id = ?", (kb_id, tenant))
    if not row:
        raise HTTPException(404, "Knowledge base not found.")
    return row


@router.get("/knowledge-bases")
def list_bases(
    page: Page = Depends(paging), user: CurrentUser = Depends(require("viewer")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    where = "k.tenant_id = ? AND k.name LIKE ? ESCAPE '\\'"
    args = (user.tenant_id, page.like)
    total = runtime.db.scalar(f"SELECT COUNT(*) FROM knowledge_bases k WHERE {where}", args)
    rows = runtime.db.all(
        "SELECT k.*, (SELECT COUNT(*) FROM documents d WHERE d.kb_id = k.id) AS documents,"
        " (SELECT COALESCE(SUM(chunk_count), 0) FROM documents d WHERE d.kb_id = k.id) AS chunks"
        f" FROM knowledge_bases k WHERE {where} ORDER BY k.name LIMIT ? OFFSET ?",
        (*args, page.size, page.offset),
    )
    return paged([dict(row) for row in rows], total, page)


@router.post("/knowledge-bases")
def create_base(
    body: BaseBody, request: Request, user: CurrentUser = Depends(require("editor")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    if runtime.db.one("SELECT id FROM knowledge_bases WHERE tenant_id = ? AND name = ?", (user.tenant_id, body.name)):
        raise HTTPException(409, "A knowledge base with this name already exists.")
    base = runtime.knowledge.create_base(user.tenant_id, body.name, body.description)
    audit(runtime, request, user, "knowledge_base_created", base["id"])
    return {**base, "message": "Knowledge base created successfully."}


@router.delete("/knowledge-bases/{kb_id}")
def delete_base(
    kb_id: str, request: Request, user: CurrentUser = Depends(require("admin")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    _get_base(runtime, user.tenant_id, kb_id)
    runtime.knowledge.delete_base(user.tenant_id, kb_id)
    audit(runtime, request, user, "knowledge_base_deleted", kb_id)
    return {"message": "Knowledge base deleted successfully."}


@router.get("/knowledge-bases/{kb_id}/documents")
def list_documents(
    kb_id: str,
    page: Page = Depends(paging),
    user: CurrentUser = Depends(require("viewer")),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    _get_base(runtime, user.tenant_id, kb_id)
    where = "tenant_id = ? AND kb_id = ? AND title LIKE ? ESCAPE '\\'"
    args = (user.tenant_id, kb_id, page.like)
    total = runtime.db.scalar(f"SELECT COUNT(*) FROM documents WHERE {where}", args)
    rows = runtime.db.all(
        "SELECT id, title, source_type, source_ref, status, error, chunk_count, created_at"
        f" FROM documents WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (*args, page.size, page.offset),
    )
    return paged([dict(row) for row in rows], total, page)


@router.post("/knowledge-bases/{kb_id}/documents")
async def upload_document(
    kb_id: str,
    request: Request,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require("editor")),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    _get_base(runtime, user.tenant_id, kb_id)
    limit = runtime.settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"Choose a file under {runtime.settings.max_upload_mb} MB.")
    try:
        document = runtime.knowledge.ingest_file(user.tenant_id, kb_id, file.filename or "document", data)
    except IngestionError as error:
        raise HTTPException(422, str(error)) from error
    audit(runtime, request, user, "document_added", document["id"])
    return {**document, "message": "Document uploaded successfully."}


@router.post("/knowledge-bases/{kb_id}/urls")
async def add_url(
    kb_id: str,
    body: UrlBody,
    request: Request,
    user: CurrentUser = Depends(require("editor")),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    _get_base(runtime, user.tenant_id, kb_id)
    try:
        sections = await fetch_url(body.url, runtime.settings.max_upload_mb * 1024 * 1024)
        document = runtime.knowledge.ingest_sections(user.tenant_id, kb_id, body.url, sections)
    except IngestionError as error:
        raise HTTPException(422, str(error)) from error
    audit(runtime, request, user, "document_added", document["id"], {"url": body.url})
    return {**document, "message": "Web page added successfully."}


@router.post("/knowledge-bases/{kb_id}/faqs")
def add_faq(
    kb_id: str,
    body: FaqBody,
    request: Request,
    user: CurrentUser = Depends(require("editor")),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    _get_base(runtime, user.tenant_id, kb_id)
    try:
        document = runtime.knowledge.ingest_faq(user.tenant_id, kb_id, body.title, body.pairs)
    except IngestionError as error:
        raise HTTPException(422, str(error)) from error
    audit(runtime, request, user, "document_added", document["id"])
    return {**document, "message": "FAQs added successfully."}


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str, request: Request, user: CurrentUser = Depends(require("editor")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    if not runtime.knowledge.delete_document(user.tenant_id, document_id):
        raise HTTPException(404, "Document not found.")
    audit(runtime, request, user, "document_deleted", document_id)
    return {"message": "Document deleted successfully."}


@router.post("/knowledge-bases/{kb_id}/search")
def test_search(
    kb_id: str, body: SearchBody, user: CurrentUser = Depends(require("viewer")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    _get_base(runtime, user.tenant_id, kb_id)
    found = runtime.knowledge.search(user.tenant_id, [kb_id], body.query, body.language)
    return {
        "confidence": found.confidence,
        "hits": [
            {**hit.source(), "text": hit.chunk.text, "language": hit.chunk.language, "cosine": hit.cosine, "coverage": hit.coverage}
            for hit in found.hits
        ],
    }


# ---- conversations and escalations -------------------------------------------------------


@router.get("/conversations")
def list_conversations(
    page: Page = Depends(paging), user: CurrentUser = Depends(require("viewer")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    where = "c.tenant_id = ? AND (a.name LIKE ? ESCAPE '\\' OR a.industry LIKE ? ESCAPE '\\')"
    args = (user.tenant_id, page.like, page.like)
    joined = "FROM conversations c JOIN agents a ON a.id = c.agent_id"
    total = runtime.db.scalar(f"SELECT COUNT(*) {joined} WHERE {where}", args)
    rows = runtime.db.all(
        "SELECT c.id, c.language, c.voice, c.mode, c.keep_history, c.started_at, c.ended_at, a.name AS agent, a.industry,"
        " (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS messages"
        f" {joined} WHERE {where} ORDER BY c.started_at DESC LIMIT ? OFFSET ?",
        (*args, page.size, page.offset),
    )
    return paged([dict(row) for row in rows], total, page)


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str, user: CurrentUser = Depends(require("viewer")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    row = runtime.db.one(
        "SELECT c.*, a.name AS agent, a.industry FROM conversations c JOIN agents a ON a.id = c.agent_id"
        " WHERE c.id = ? AND c.tenant_id = ?",
        (conversation_id, user.tenant_id),
    )
    if not row:
        raise HTTPException(404, "Conversation not found.")
    messages = runtime.db.all(
        "SELECT role, text, language, interrupted, sources, confidence, created_at FROM messages"
        " WHERE conversation_id = ? AND tenant_id = ? ORDER BY created_at",
        (conversation_id, user.tenant_id),
    )
    details = {key: row[key] for key in row.keys() if key != "token_hash"}
    return {
        **details,
        "messages": [{**dict(item), "sources": json.loads(item["sources"]), "interrupted": bool(item["interrupted"])} for item in messages],
    }


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str, request: Request, user: CurrentUser = Depends(require("admin")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    deleted = runtime.db.execute(
        "DELETE FROM conversations WHERE id = ? AND tenant_id = ?", (conversation_id, user.tenant_id)
    )
    if not deleted.rowcount:
        raise HTTPException(404, "Conversation not found.")
    audit(runtime, request, user, "conversation_deleted", conversation_id)
    return {"message": "Conversation deleted successfully."}


@router.get("/escalations")
def list_escalations(
    page: Page = Depends(paging), user: CurrentUser = Depends(require("viewer")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    where = "e.tenant_id = ? AND (a.name LIKE ? ESCAPE '\\' OR e.rule LIKE ? ESCAPE '\\' OR e.severity LIKE ? ESCAPE '\\')"
    args = (user.tenant_id, page.like, page.like, page.like)
    joined = "FROM escalations e JOIN agents a ON a.id = e.agent_id"
    total = runtime.db.scalar(f"SELECT COUNT(*) {joined} WHERE {where}", args)
    rows = runtime.db.all(
        "SELECT e.id, e.conversation_id, e.rule, e.severity, e.status, e.created_at, a.name AS agent, a.industry"
        f" {joined} WHERE {where} ORDER BY e.created_at DESC LIMIT ? OFFSET ?",
        (*args, page.size, page.offset),
    )
    return paged([dict(row) for row in rows], total, page)


@router.post("/escalations/{escalation_id}/close")
def close_escalation(
    escalation_id: str, request: Request, user: CurrentUser = Depends(require("editor")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    done = runtime.db.execute(
        "UPDATE escalations SET status = 'closed' WHERE id = ? AND tenant_id = ?", (escalation_id, user.tenant_id)
    )
    if not done.rowcount:
        raise HTTPException(404, "Escalation not found.")
    audit(runtime, request, user, "escalation_closed", escalation_id)
    return {"message": "Escalation closed successfully."}


@router.get("/audit-log")
def audit_log(
    page: Page = Depends(paging), user: CurrentUser = Depends(require("admin")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    where = "tenant_id = ? AND (actor LIKE ? ESCAPE '\\' OR action LIKE ? ESCAPE '\\')"
    args = (user.tenant_id, page.like, page.like)
    total = runtime.db.scalar(f"SELECT COUNT(*) FROM audit_log WHERE {where}", args)
    rows = runtime.db.all(
        f"SELECT id, actor, action, target, ip, created_at FROM audit_log WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
        (*args, page.size, page.offset),
    )
    return paged([dict(row) for row in rows], total, page)


# ---- users -------------------------------------------------------------------------------


class UserBody(BaseModel):
    full_name: str = Field(min_length=2, max_length=80)
    email: str = Field(max_length=120)
    role: str = Field(pattern="^(admin|editor|viewer)$")
    password: str | None = None
    is_active: bool = True

    _email = field_validator("email")(check_email)

    @field_validator("full_name")
    @classmethod
    def real_name(cls, value: str) -> str:
        value = value.strip()
        if not NAME.match(value):
            raise ValueError("Full Name must contain letters only.")
        return value

    @field_validator("password")
    @classmethod
    def strong(cls, value: str | None) -> str | None:
        return check_password_strength(value) if value else None


def _user_row(row) -> dict:
    return {
        "id": row["id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
    }


@router.get("/users")
def list_users(
    page: Page = Depends(paging), user: CurrentUser = Depends(require("admin")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    where = "tenant_id = ? AND (full_name LIKE ? ESCAPE '\\' OR email LIKE ? ESCAPE '\\')"
    args = (user.tenant_id, page.like, page.like)
    total = runtime.db.scalar(f"SELECT COUNT(*) FROM users WHERE {where}", args)
    rows = runtime.db.all(
        f"SELECT * FROM users WHERE {where} ORDER BY created_at LIMIT ? OFFSET ?", (*args, page.size, page.offset)
    )
    return paged([_user_row(row) for row in rows], total, page)


@router.post("/users")
def create_user(
    body: UserBody, request: Request, user: CurrentUser = Depends(require("admin")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    if not body.password:
        raise HTTPException(422, "Password is required.")
    if runtime.db.one("SELECT id FROM users WHERE email = ?", (body.email,)):
        raise HTTPException(409, "This Email ID is already in use.")
    user_id = new_id()
    runtime.db.execute(
        "INSERT INTO users (id, tenant_id, email, full_name, password_hash, role, is_active, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, user.tenant_id, body.email, body.full_name, hash_password(body.password), body.role, int(body.is_active), now_iso()),
    )
    audit(runtime, request, user, "user_created", user_id)
    return {"id": user_id, "message": "User created successfully."}


def _target_user(runtime: Runtime, actor: CurrentUser, user_id: str):
    row = runtime.db.one("SELECT * FROM users WHERE id = ? AND tenant_id = ?", (user_id, actor.tenant_id))
    if not row:
        raise HTTPException(404, "User not found.")
    if row["role"] == "owner" and actor.role != "owner":
        raise HTTPException(403, "Only the owner can change the owner's account.")
    return row


@router.put("/users/{user_id}")
def update_user(
    user_id: str,
    body: UserBody,
    request: Request,
    user: CurrentUser = Depends(require("admin")),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    row = _target_user(runtime, user, user_id)
    if row["role"] == "owner":
        raise HTTPException(422, "The owner's role cannot be changed here.")
    if runtime.db.one("SELECT id FROM users WHERE email = ? AND id != ?", (body.email, user_id)):
        raise HTTPException(409, "This Email ID is already in use.")
    runtime.db.execute(
        "UPDATE users SET full_name = ?, email = ?, role = ?, is_active = ? WHERE id = ? AND tenant_id = ?",
        (body.full_name, body.email, body.role, int(body.is_active), user_id, user.tenant_id),
    )
    if not body.is_active:
        runtime.db.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
    audit(runtime, request, user, "user_updated", user_id)
    return {"message": "User updated successfully."}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str, request: Request, user: CurrentUser = Depends(require("admin")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    row = _target_user(runtime, user, user_id)
    if row["id"] == user.id:
        raise HTTPException(422, "You cannot delete your own account.")
    if row["role"] == "owner":
        raise HTTPException(422, "The owner's account cannot be deleted.")
    runtime.db.execute("DELETE FROM users WHERE id = ? AND tenant_id = ?", (user_id, user.tenant_id))
    audit(runtime, request, user, "user_deleted", user_id)
    return {"message": "User deleted successfully."}


# ---- settings and system -----------------------------------------------------------------


class RetentionBody(BaseModel):
    transcript_retention_days: int = Field(ge=0, le=3650)


@router.get("/settings")
def get_settings(user: CurrentUser = Depends(require("admin")), runtime: Runtime = Depends(get_runtime)) -> dict:
    row = runtime.db.one("SELECT name, audio_retention, transcript_retention_days FROM tenants WHERE id = ?", (user.tenant_id,))
    return dict(row)


@router.put("/settings")
def update_settings(
    body: RetentionBody, request: Request, user: CurrentUser = Depends(require("admin")), runtime: Runtime = Depends(get_runtime)
) -> dict:
    runtime.db.execute(
        "UPDATE tenants SET transcript_retention_days = ? WHERE id = ?", (body.transcript_retention_days, user.tenant_id)
    )
    audit(runtime, request, user, "retention_changed", "", {"days": body.transcript_retention_days})
    return {"message": "Settings updated successfully."}


@router.get("/system")
async def system(user: CurrentUser = Depends(require("viewer")), runtime: Runtime = Depends(get_runtime)) -> dict:
    memory = psutil.virtual_memory()
    return {
        "hardware": runtime.hardware.to_dict(),
        "plan": runtime.plan.to_dict(),
        "live": runtime.sessions.snapshot(),
        "loaded": runtime.loaded_models(),
        "llm_healthy": await runtime.llm.healthy(),
        "model_error": runtime.model_error,
        "ram_used_percent": memory.percent,
        "cpu_percent": psutil.cpu_percent(interval=None),
    }


@router.get("/latency")
def latency(user: CurrentUser = Depends(require("viewer")), runtime: Runtime = Depends(get_runtime)) -> dict:
    """Percentiles from this tenant's recent real turns. Timings only: no conversation text."""
    rows = runtime.db.all(
        "SELECT metrics FROM turn_metrics WHERE tenant_id = ? ORDER BY id DESC LIMIT 1000", (user.tenant_id,)
    )
    values: dict[str, list[float]] = {}
    for row in rows:
        for key, value in json.loads(row["metrics"]).items():
            if key.endswith("_ms") and isinstance(value, int | float):
                values.setdefault(key, []).append(float(value))

    def percentile(items: list[float], share: float) -> float:
        ordered = sorted(items)
        return round(ordered[min(int(len(ordered) * share), len(ordered) - 1)])

    return {
        "turns": len(rows),
        "stages": {
            key: {"p50": percentile(items, 0.5), "p95": percentile(items, 0.95), "p99": percentile(items, 0.99), "count": len(items)}
            for key, items in sorted(values.items())
        },
    }
