"""What a visitor needs: the agent list, starting a conversation, the voice socket and their data."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from agent_engine.config.schema import LANGUAGE_NAMES, AgentConfig
from backend.db import new_id, now_iso
from backend.deps import get_runtime
from backend.runtime import Runtime
from backend.security import SlidingWindowLimiter, client_ip, hash_token, new_token, origin_allowed
from backend.voice.session import ConversationContext, VoiceSession
from voice_engine.tts.voices import default_voice, voice_by_id, voices_for

router = APIRouter(tags=["public"])
log = logging.getLogger("vap.public")
_starts = SlidingWindowLimiter(30, 60)


def _agent_card(row, runtime: Runtime) -> dict:
    config = AgentConfig.model_validate_json(row["config"])
    models = runtime.settings.models_dir
    return {
        "slug": config.slug,
        "industry": config.industry,
        "name": config.name,
        "role": config.role,
        "organisation": config.organisation,
        "languages": [
            {
                "code": language,
                "label": LANGUAGE_NAMES[language],
                "voices": [
                    {"id": voice.id, "label": voice.label, "gender": voice.gender}
                    for voice in voices_for(language, models)
                ],
            }
            for language in config.languages
        ],
    }


def default_tenant(runtime: Runtime) -> str:
    row = runtime.db.one("SELECT id FROM tenants ORDER BY created_at LIMIT 1")
    if not row:
        raise HTTPException(503, "The platform has not been set up yet.")
    return row["id"]


@router.get("/api/public/agents")
def list_agents(runtime: Runtime = Depends(get_runtime)) -> dict:
    tenant = default_tenant(runtime)
    rows = runtime.db.all(
        "SELECT config FROM agents WHERE tenant_id = ? AND published = 1 ORDER BY industry", (tenant,)
    )
    return {"agents": [_agent_card(row, runtime) for row in rows]}


class StartBody(BaseModel):
    agent: str = Field(min_length=2, max_length=40)
    language: str = Field(min_length=2, max_length=2)
    voice: str = Field(default="", max_length=40)
    mode: str = Field(default="voice", pattern="^(voice|text)$")
    keep_history: bool = True


@router.post("/api/public/conversations")
def start_conversation(body: StartBody, request: Request, runtime: Runtime = Depends(get_runtime)) -> dict:
    if not _starts.allow(client_ip(request)):
        raise HTTPException(429, "Too many conversations started. Please wait a minute and try again.")
    tenant = default_tenant(runtime)
    row = runtime.db.one(
        "SELECT * FROM agents WHERE tenant_id = ? AND slug = ? AND published = 1", (tenant, body.agent)
    )
    if not row:
        raise HTTPException(404, "This agent is not available.")
    config = AgentConfig.model_validate_json(row["config"])
    if body.language not in config.languages:
        raise HTTPException(422, "This agent does not offer that language.")
    voice = voice_by_id(body.voice) if body.voice else default_voice(body.language, runtime.settings.models_dir)
    if voice is None or voice.language != body.language:
        voice = default_voice(body.language, runtime.settings.models_dir)
    token = new_token()
    conversation_id = new_id()
    runtime.db.execute(
        "INSERT INTO conversations (id, tenant_id, agent_id, language, voice, mode, keep_history, token_hash, started_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            conversation_id,
            tenant,
            row["id"],
            body.language,
            voice.id if voice else "",
            body.mode,
            1 if body.keep_history else 0,
            hash_token(token),
            now_iso(),
        ),
    )
    return {"id": conversation_id, "token": token, "voice": voice.id if voice else None}


def _guest_conversation(runtime: Runtime, conversation_id: str, authorization: str):
    token = authorization.removeprefix("Bearer ").strip()
    row = runtime.db.one("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
    if not row or not token or row["token_hash"] != hash_token(token):
        raise HTTPException(404, "Conversation not found.")
    return row


@router.get("/api/public/conversations/{conversation_id}/messages")
def conversation_messages(
    conversation_id: str, authorization: str = Header(default=""), runtime: Runtime = Depends(get_runtime)
) -> dict:
    row = _guest_conversation(runtime, conversation_id, authorization)
    rows = runtime.db.all(
        "SELECT role, text, language, interrupted, sources, created_at FROM messages"
        " WHERE conversation_id = ? AND tenant_id = ? ORDER BY created_at",
        (conversation_id, row["tenant_id"]),
    )
    return {
        "messages": [{**dict(item), "sources": json.loads(item["sources"]), "interrupted": bool(item["interrupted"])} for item in rows]
    }


@router.delete("/api/public/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    request: Request,
    authorization: str = Header(default=""),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    row = _guest_conversation(runtime, conversation_id, authorization)
    runtime.db.execute("DELETE FROM conversations WHERE id = ?", (row["id"],))
    runtime.db.audit(row["tenant_id"], "guest", "conversation_deleted", row["id"], {}, client_ip(request))
    return {"message": "Conversation deleted successfully."}


def conversation_context(runtime: Runtime, row, mode: str | None = None) -> ConversationContext:
    agent_row = runtime.db.one("SELECT * FROM agents WHERE id = ? AND tenant_id = ?", (row["agent_id"], row["tenant_id"]))
    config = AgentConfig.model_validate_json(agent_row["config"])
    names = tuple(config.knowledge_bases)
    marks = ",".join("?" * len(names)) or "''"
    kbs = runtime.db.all(
        f"SELECT id FROM knowledge_bases WHERE tenant_id = ? AND name IN ({marks})", (row["tenant_id"], *names)
    )
    return ConversationContext(
        id=row["id"],
        tenant_id=row["tenant_id"],
        agent_id=row["agent_id"],
        agent=config,
        kb_ids=[item["id"] for item in kbs],
        keep_history=bool(row["keep_history"]),
        language=row["language"],
        voice_id=row["voice"],
        mode=mode or row["mode"],
    )


@router.websocket("/ws/voice")
async def voice_socket(websocket: WebSocket) -> None:
    runtime: Runtime = websocket.app.state.runtime
    if not origin_allowed(
        websocket.headers.get("origin"), runtime.settings.public_origin, websocket.headers.get("host")
    ):
        await websocket.close(4403)
        return
    await websocket.accept()
    try:
        # The token comes in the first message, not the URL, so it never reaches an access log.
        first = json.loads(await websocket.receive_text())
    except (WebSocketDisconnect, json.JSONDecodeError, KeyError):
        await websocket.close(4400)
        return
    row = None
    if isinstance(first, dict) and first.get("type") == "start":
        row = runtime.db.one("SELECT * FROM conversations WHERE id = ?", (str(first.get("id", "")),))
    closed = bool(row) and row["end_reason"] not in ("", "disconnected")
    if not row or row["token_hash"] != hash_token(str(first.get("token", ""))) or closed:
        await websocket.send_text(json.dumps({"type": "error", "code": "denied", "message": "This conversation is not available."}))
        await websocket.close(4401)
        return
    admission = runtime.sessions.try_admit()
    if not admission.allowed:
        await websocket.send_text(json.dumps({"type": "error", "code": "busy", "message": admission.message}))
        await websocket.close(4503)
        return
    runtime.db.execute("UPDATE conversations SET ended_at = NULL, end_reason = '' WHERE id = ?", (row["id"],))
    try:
        session = VoiceSession(
            websocket, runtime, conversation_context(runtime, row, first.get("mode")), bool(first.get("resume"))
        )
        await session.run()
    finally:
        runtime.sessions.release()


@router.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/api/ready")
async def ready(runtime: Runtime = Depends(get_runtime)) -> dict:
    llm = await runtime.llm.healthy()
    return {
        "status": "ok" if llm else "degraded",
        "llm": llm,
        "model_error": runtime.model_error,
        **runtime.sessions.snapshot(),
    }
