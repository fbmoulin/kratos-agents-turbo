drop index if exists idx_sessions_task_id;

create unique index if not exists idx_sessions_task_id_unique
    on sessions (task_id);

alter table task_dispatches
    drop constraint if exists task_dispatches_status_check;

alter table task_dispatches
    add constraint task_dispatches_status_check
    check (status in ('pending', 'dispatching', 'dispatched', 'failed'));
