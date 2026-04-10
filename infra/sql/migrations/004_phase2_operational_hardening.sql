create index if not exists idx_tasks_status_started_at
    on tasks (status, started_at asc)
    where started_at is not null;

create index if not exists idx_tasks_task_type_finished_at
    on tasks (task_type, finished_at desc)
    where finished_at is not null;

create index if not exists idx_task_dispatches_status_updated_at
    on task_dispatches (status, updated_at asc);
