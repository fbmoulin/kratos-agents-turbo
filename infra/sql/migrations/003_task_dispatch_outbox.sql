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

create index if not exists idx_task_dispatches_status_created_at
    on task_dispatches (status, created_at);
