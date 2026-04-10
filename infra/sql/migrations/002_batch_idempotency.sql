alter table batches
    add column if not exists idempotency_key text;

create unique index if not exists idx_batches_idempotency_key
    on batches (idempotency_key)
    where idempotency_key is not null;
