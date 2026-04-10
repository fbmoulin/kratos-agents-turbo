# Kratos Agents Turbo

Base enterprise para uma plataforma jurídica de execução de agentes.

O repositório evolui o bootstrap original de `API + worker + fila` para uma fundação orientada a eventos, preparada para rastreabilidade, auditoria, catálogo declarativo de agentes e evolução segura do backend.

## Visão

O objetivo do projeto é servir como núcleo de uma agent execution platform jurídica, com foco em:

- processamento jurídico em lote
- sessões de execução
- eventos append-only para rastreabilidade
- catálogo declarativo de agentes
- service layer explícita
- integração futura com observabilidade, validação jurídica avançada e painéis operacionais

## Stack

- FastAPI
- Celery
- Redis
- PostgreSQL via Supabase
- YAML declarativo para catálogo de agentes
- skills locais reutilizáveis

## Arquitetura

O backend está organizado em camadas:

- `src/agent/`
  Agentes, registry e catálogo declarativo.
- `src/core/`
  Settings centralizados, estados, logging e exceptions.
- `src/services/`
  Orquestração, validação, roteamento e lifecycle de sessão.
- `src/session/`
  Gerência de sessões e transições de estado.
- `src/events/`
  Event store append-only apoiado em `task_logs`.
- `src/api/`
  API HTTP para submissão, consulta e cancelamento de tasks.
- `src/worker/`
  Runtime assíncrono com Celery.
- `src/mcp/`
  Servidor HTTP simples para reuso de skills.
- `infra/sql/`
  Schema inicial para `tasks`, `sessions` e `task_logs`.

## Modelo operacional

Direção adotada: `event-first execution`.

Em vez de agentes alterarem estado global diretamente:

1. a API valida a entrada e registra a task como `queued`
2. a task é enfileirada no Celery
3. o worker resolve o agente e cria/carrega a sessão
4. o orchestrator coordena execução e persistência
5. o event store registra eventos estruturados em `task_logs`
6. a task e a sessão transitam entre estados coerentes

Status mínimos suportados:

- `queued`
- `running`
- `completed`
- `failed`
- `cancelled`

## Fluxo de execução

`POST /tasks` recebe um PDF e metadados de execução.

- `validator_service` sanitiza entrada
- `tasks` persiste o pedido inicial
- `task_logs` registra `TASK_CREATED`
- Celery recebe o payload serializado
- `orchestrator_service` resolve o agente, abre sessão e emite eventos
- o agente executa skills locais
- o resultado final é persistido em `tasks.result`

## Papel do Supabase

O Supabase é a camada de persistência operacional deste bootstrap enterprise.

- `tasks`
  estado de execução, input, output e erro
- `sessions`
  ciclo de vida, progresso e contexto operacional
- `task_logs`
  log append-only de eventos estruturados

O schema SQL inicial está em [`infra/sql/schema.sql`](./infra/sql/schema.sql).

## Como rodar

### Pré-requisitos

- Docker e Docker Compose
- projeto Supabase com o schema aplicado

### Configuração

1. Copie `.env.example` para `.env`
2. Preencha `SUPABASE_URL` e `SUPABASE_KEY`
3. Aplique `infra/sql/schema.sql` no banco do Supabase

### Subida local

```bash
docker compose up --build
```

Serviços expostos:

- API: `http://localhost:8000`
- MCP server: `http://localhost:8001`
- Redis: `localhost:6379`

## Endpoints principais

- `GET /health`
- `POST /tasks`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /tasks/{task_id}/cancel`

## Catálogo de agentes

O catálogo declarativo fica em [`src/agent/catalog/agents.yaml`](./src/agent/catalog/agents.yaml).

Hoje existe um agente base:

- `legal-document-agent`

Ele usa as skills:

- `extract_text_from_pdf`
- `classify_document`
- `generate_decision`

## Evolução planejada

Próximas fases recomendadas:

- migrations formais
- autenticação/autorização
- object storage para payloads grandes
- observabilidade distribuída
- validação jurídica mais rica
- retomada real de sessão e checkpoints persistentes
- múltiplos agentes e roteamento declarativo mais sofisticado
