-- Phase 9.4: Supabase-backed persistence schema (append-only judgments)
--
-- Run this in Supabase SQL editor.
-- Recommended: use a service role key for server-side writes.

create extension if not exists pgcrypto;

create table if not exists papers (
  id uuid primary key default gen_random_uuid(),
  arxiv_id text unique not null,
  title text not null,
  authors jsonb not null,
  abstract text not null,
  created_at timestamptz not null default now()
);

create table if not exists reviews (
  id uuid primary key,
  paper_id uuid not null references papers(id),
  agent_model_configs jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists agent_messages (
  id uuid primary key,
  review_id uuid not null references reviews(id),
  agent text not null,
  phase text not null,
  timestamp timestamptz not null,
  content text not null,
  model_provider text,
  model_name text,
  temperature numeric,
  max_tokens int,
  references_json jsonb not null default '[]'::jsonb,
  flags_violation boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists verdict_versions (
  id uuid primary key,
  review_id uuid not null references reviews(id),
  version int not null,
  verdict jsonb not null,
  synthesis text not null,
  created_at timestamptz not null default now(),
  unique (review_id, version)
);

create table if not exists human_feedback (
  id uuid primary key,
  review_id uuid not null references reviews(id),
  critique_text text not null,
  classification jsonb not null,
  forward_change_note text not null,
  created_at timestamptz not null default now()
);

-- Minimal indexes
create index if not exists idx_reviews_paper_id on reviews(paper_id);
create index if not exists idx_agent_messages_review_id on agent_messages(review_id);
create index if not exists idx_verdict_versions_review_id on verdict_versions(review_id);
create index if not exists idx_human_feedback_review_id on human_feedback(review_id);

-- NOTE:
-- If you plan to use SUPABASE_API_KEY (anon/publishable) for writes, you MUST configure RLS policies.
-- Safer default for local server: use SUPABASE_SERVICE_ROLE_KEY and keep it server-side.
