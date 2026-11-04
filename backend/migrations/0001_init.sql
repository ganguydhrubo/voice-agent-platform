-- Core schema. Every row that belongs to a customer carries tenant_id, and every query filters on it.

CREATE TABLE tenants (
    id                        TEXT PRIMARY KEY,
    slug                      TEXT NOT NULL UNIQUE,
    name                      TEXT NOT NULL,
    audio_retention           TEXT NOT NULL DEFAULT 'none' CHECK (audio_retention IN ('none')),
    transcript_retention_days INTEGER NOT NULL DEFAULT 30 CHECK (transcript_retention_days >= 0),
    created_at                TEXT NOT NULL
);

CREATE TABLE users (
    id             TEXT PRIMARY KEY,
    tenant_id      TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email          TEXT NOT NULL UNIQUE,
    full_name      TEXT NOT NULL,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'editor', 'viewer')),
    is_active      INTEGER NOT NULL DEFAULT 1,
    failed_logins  INTEGER NOT NULL DEFAULT 0,
    locked_until   TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX idx_users_tenant ON users(tenant_id);

CREATE TABLE auth_sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX idx_auth_sessions_user ON auth_sessions(user_id);

CREATE TABLE password_resets (
    token_hash  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at  TEXT NOT NULL,
    used_at     TEXT
);

CREATE TABLE knowledge_bases (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE (tenant_id, name)
);
CREATE INDEX idx_kb_tenant ON knowledge_bases(tenant_id);

CREATE TABLE agents (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    slug        TEXT NOT NULL,
    name        TEXT NOT NULL,
    industry    TEXT NOT NULL,
    config      TEXT NOT NULL,
    published   INTEGER NOT NULL DEFAULT 0,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE (tenant_id, slug)
);
CREATE INDEX idx_agents_tenant ON agents(tenant_id);

CREATE TABLE documents (
    id           TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    kb_id        TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    source_type  TEXT NOT NULL CHECK (source_type IN ('pdf', 'docx', 'txt', 'csv', 'json', 'url', 'faq')),
    source_ref   TEXT NOT NULL DEFAULT '',
    sha256       TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('processing', 'ready', 'failed')),
    error        TEXT NOT NULL DEFAULT '',
    chunk_count  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    UNIQUE (kb_id, sha256)
);
CREATE INDEX idx_documents_kb ON documents(tenant_id, kb_id);

CREATE TABLE chunks (
    rowid_key    INTEGER PRIMARY KEY AUTOINCREMENT,
    id           TEXT NOT NULL UNIQUE,
    tenant_id    TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    kb_id        TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    document_id  TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal      INTEGER NOT NULL,
    section      TEXT NOT NULL DEFAULT '',
    language     TEXT NOT NULL DEFAULT '',
    text         TEXT NOT NULL,
    search_text  TEXT NOT NULL,
    flagged      INTEGER NOT NULL DEFAULT 0,
    embedding    BLOB NOT NULL
);
CREATE INDEX idx_chunks_scope ON chunks(tenant_id, kb_id);
CREATE INDEX idx_chunks_document ON chunks(document_id);

-- Hindi and Bengali vowel signs are Unicode marks. The default tokeniser splits words on them,
-- so marks (M*) are kept as token characters and diacritics are left alone.
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    search_text,
    content='chunks',
    content_rowid='rowid_key',
    tokenize = "unicode61 remove_diacritics 0 categories 'L* N* Co M*'"
);
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, search_text) VALUES (new.rowid_key, new.search_text);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, search_text) VALUES ('delete', old.rowid_key, old.search_text);
END;

CREATE TABLE conversations (
    id           TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id     TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    language     TEXT NOT NULL,
    voice        TEXT NOT NULL,
    mode         TEXT NOT NULL DEFAULT 'voice' CHECK (mode IN ('voice', 'text')),
    keep_history INTEGER NOT NULL DEFAULT 1,
    token_hash   TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    end_reason   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_conversations_tenant ON conversations(tenant_id, started_at);

CREATE TABLE messages (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    tenant_id        TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    text             TEXT NOT NULL,
    language         TEXT NOT NULL DEFAULT '',
    interrupted      INTEGER NOT NULL DEFAULT 0,
    sources          TEXT NOT NULL DEFAULT '[]',
    confidence       REAL,
    created_at       TEXT NOT NULL
);
CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);

-- Timings only. No text, so it can outlive a deleted transcript for capacity planning.
CREATE TABLE turn_metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   TEXT NOT NULL,
    language    TEXT NOT NULL,
    metrics     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE escalations (
    id               TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id  TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    agent_id         TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    rule             TEXT NOT NULL,
    severity         TEXT NOT NULL CHECK (severity IN ('emergency', 'human')),
    status           TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    created_at       TEXT NOT NULL
);
CREATE INDEX idx_escalations_tenant ON escalations(tenant_id, created_at);

CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   TEXT,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    target      TEXT NOT NULL DEFAULT '',
    detail      TEXT NOT NULL DEFAULT '{}',
    ip          TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX idx_audit_tenant ON audit_log(tenant_id, created_at);
