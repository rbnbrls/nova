-- Nova schema — runs once on first Postgres init.
-- Tasks/todos (Phase 5) + long-term memory (Phase 3).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Household users (Ruben / Méral / household).
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO users (name) VALUES ('Ruben'), ('Meral'), ('household')
    ON CONFLICT (name) DO NOTHING;

-- Shared tasks/todos with per-user attribution and deadlines (drives dashboard, Phase 8).
CREATE TABLE IF NOT EXISTS tasks (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title        TEXT NOT NULL,
    notes        TEXT,
    status       TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active', 'done', 'cancelled')),
    assignee_id  UUID REFERENCES users(id),
    created_by   UUID REFERENCES users(id),
    due_at       TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS tasks_active_due_idx
    ON tasks (due_at) WHERE status = 'active';

-- Long-term memory: household facts & preferences, retrieved by embedding similarity.
-- Dimension 768 matches nomic-embed-text; change if you swap the embedding model.
CREATE TABLE IF NOT EXISTS memories (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID REFERENCES users(id),
    content     TEXT NOT NULL,
    embedding   vector(768),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS memories_embedding_idx
    ON memories USING hnsw (embedding vector_cosine_ops);

-- Short-term conversation history per (user, channel).
CREATE TABLE IF NOT EXISTS messages (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID REFERENCES users(id),
    channel     TEXT NOT NULL,          -- 'whatsapp' | 'voice' | 'api'
    role        TEXT NOT NULL,          -- 'user' | 'assistant' | 'tool'
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS messages_user_channel_idx
    ON messages (user_id, channel, created_at DESC);
