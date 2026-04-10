create extension if not exists pgcrypto;

create table if not exists sessions (
    id uuid primary key default gen_random_uuid(),
    task_id uuid not null,
    agent_id text not null,
    status text not null check (status in ('queued', 'running', 'completed', 'failed', 'cancelled')),
    execution_mode text not null default 'document',
    current_step text,
    progress integer not null default 0 check (progress >= 0 and progress <= 100),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists batches (
    id uuid primary key default gen_random_uuid(),
    task_type text not null,
    message text not null,
    requested_agent_id text,
    priority integer not null default 0,
    total_tasks integer not null check (total_tasks > 0),
    idempotency_key text,
    input_metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table batches
    add column if not exists idempotency_key text;

create table if not exists tasks (
    id uuid primary key default gen_random_uuid(),
    batch_id uuid references batches(id) on delete set null,
    session_id uuid references sessions(id),
    requested_agent_id text,
    agent_id text,
    file_name text not null,
    task_type text not null,
    status text not null check (status in ('queued', 'running', 'completed', 'failed', 'cancelled')),
    message text not null,
    priority integer not null default 0,
    execution_mode text not null default 'document',
    result text,
    error text,
    input_metadata jsonb not null default '{}'::jsonb,
    output_metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    started_at timestamptz,
    finished_at timestamptz,
    cancelled_at timestamptz
);

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'sessions_task_id_fkey'
    ) then
        alter table sessions
            add constraint sessions_task_id_fkey
            foreign key (task_id)
            references tasks(id)
            deferrable initially deferred;
    end if;
end $$;

create table if not exists task_logs (
    id bigserial primary key,
    task_id uuid not null references tasks(id) on delete cascade,
    session_id uuid references sessions(id) on delete set null,
    event_type text not null,
    status text,
    step text,
    message text,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists task_dispatches (
    task_id uuid primary key references tasks(id) on delete cascade,
    queue_name text not null,
    status text not null check (status in ('pending', 'dispatched', 'failed')),
    payload jsonb not null default '{}'::jsonb,
    attempts integer not null default 0 check (attempts >= 0),
    last_error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    dispatched_at timestamptz
);

create index if not exists idx_tasks_status_created_at on tasks (status, created_at desc);
create index if not exists idx_tasks_batch_id on tasks (batch_id);
create index if not exists idx_tasks_session_id on tasks (session_id);
create index if not exists idx_tasks_agent_id on tasks (agent_id);
create index if not exists idx_tasks_task_type_status_priority_created_at on tasks (task_type, status, priority desc, created_at desc);
create index if not exists idx_batches_created_at on batches (created_at desc);
create index if not exists idx_batches_task_type_created_at on batches (task_type, created_at desc);
create unique index if not exists idx_batches_idempotency_key on batches (idempotency_key) where idempotency_key is not null;
create index if not exists idx_sessions_task_id on sessions (task_id);
create index if not exists idx_sessions_status_created_at on sessions (status, created_at desc);
create index if not exists idx_task_logs_task_id_created_at on task_logs (task_id, created_at);
create index if not exists idx_task_logs_session_id_created_at on task_logs (session_id, created_at);
create index if not exists idx_task_logs_event_type on task_logs (event_type);
create index if not exists idx_task_dispatches_status_created_at on task_dispatches (status, created_at);
