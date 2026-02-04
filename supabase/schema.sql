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

-- Phase 9.5: Durable web adjudication jobs
-- State flow: submitted -> adjudicating -> adjudicated (or error)

create table if not exists review_jobs (
  id uuid primary key,
  status text not null,
  step text not null default 'submitted',
  arxiv_id_or_url text not null,
  normalized_arxiv_id text,
  allow_insecure_tls boolean not null default false,
  persist_to_supabase boolean not null default false,
  num_reviews int not null default 1,
  current_run int not null default 0,
  messages_count int not null default 0,
  last_agent text,
  last_phase text,
  error text,
  artifacts jsonb not null default '[]'::jsonb,
  persisted_reviews jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists review_job_events (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references review_jobs(id),
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- Minimal indexes
create index if not exists idx_reviews_paper_id on reviews(paper_id);
create index if not exists idx_agent_messages_review_id on agent_messages(review_id);
create index if not exists idx_verdict_versions_review_id on verdict_versions(review_id);
create index if not exists idx_human_feedback_review_id on human_feedback(review_id);

create index if not exists idx_review_jobs_created_at on review_jobs(created_at);
create index if not exists idx_review_job_events_job_id on review_job_events(job_id);

-- NOTE:
-- If you plan to use SUPABASE_API_KEY (anon/publishable) for writes, you MUST configure RLS policies.
-- Safer default for local server: use SUPABASE_SERVICE_ROLE_KEY and keep it server-side.
