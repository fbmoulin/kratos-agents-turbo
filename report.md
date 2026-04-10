# Arquitetura de Fila Robusta com Supabase para Processamento Judicial em Lote

Este documento apresenta uma solução **robusta e definitiva** para o problema de controle de filas de tarefas de IA em um ambiente de vara judicial. O objetivo é permitir que centenas de processos sejam analisados em lote com **controle completo** (cancelamento, rerun, exclusão de fila, auditoria) e **visibilidade em tempo real**. A proposta substitui o uso do Flower como monitor primário e inclui uma camada de persistência em **PostgreSQL (via Supabase)** para rastrear cada tarefa individualmente.

## 1. Por que abandonar Flower como solução única

Embora o Flower seja a ferramenta recomendada pela própria documentação do Celery para monitorar filas e trabalhadores, ele tem limitações relevantes. De acordo com o guia de monitoramento do Celery, o Flower se baseia nos eventos do Celery e oferece funcionalidades de monitoramento em tempo real, inclusive listar tarefas ativas, reservadas ou revogadas e interagir com workers (shutdown, restart, etc.)【462545852730767†L240-L299】. Essas funções são úteis para debug, mas não atendem plenamente a requisitos de produção que exigem:

* Persistência completa do histórico das tarefas (quem criou, quando começou, quanto tempo levou, resultado, erros).
* Auditoria e rastreabilidade exigidas em ambientes jurídicos (quem cancelou, por que foi cancelado, quando e qual processo estava associado).
* Integração nativa com um banco de dados para gerar relatórios e análises (jurimetria, produtividade por vara, etc.).
* Visibilidade de etapas específicas do pipeline jurídico (upload, classificação, geração de despacho, validação).

O Flower também não mantém um banco de dados próprio; ele opera apenas em memória e via eventos do Celery. Mesmo a API HTTP do Flower, embora poderosa, fornece somente o estado atual dos workers e tarefas【462545852730767†L240-L299】.

## 2. Vantagens do Supabase como backend de fila

Supabase disponibiliza o **Supabase Queues**, um sistema de filas durável e nativo do PostgreSQL. As principais características são:

* **Postgres Native** – constrói‑se sobre a extensão `pgmq`, permitindo criar e gerenciar filas usando as ferramentas padrão do Postgres【338621608011010†screenshot】.
* **Granular Authorization** – controla o acesso de produtores e consumidores via políticas de segurança e permissões de API【338621608011010†screenshot】.
* **Guaranteed Message Delivery** – mensagens adicionadas às filas têm garantia de entrega【338621608011010†screenshot】.
* **Exactly Once Message Delivery** – cada mensagem é entregue exatamente uma vez dentro de uma janela configurável【338621608011010†screenshot】.
* **Queue Management and Monitoring** – criação, gerenciamento e monitoramento de filas diretamente no painel do Supabase【338621608011010†screenshot】.
* **Message Durability and Archival** – mensagens são armazenadas no Postgres e podem ser arquivadas para recuperação ou auditoria【338621608011010†screenshot】.

Além das filas, o Supabase também oferece integração entre **Edge Functions**, **cron jobs** e **database queues**. Esse padrão em três camadas (Coleta, Distribuição e Processamento) é sugerido pelo próprio Supabase para dividir grandes trabalhos em pedaços menores e processar em escala【728504228869291†screenshot】. Para nosso caso, a camada de “Processamento” será composta por workers Celery especializados que consultam tarefas no banco.

## 3. Modelo de dados proposto

Para obter controle completo sobre cada tarefa, definimos três tabelas no PostgreSQL (via Supabase). Estas tabelas podem ser criadas manualmente no painel do Supabase ou através de migrations:

### 3.1 Tabela `tasks`

```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY,
    file_name TEXT NOT NULL,
    tipo TEXT NOT NULL,        -- despacho | decisao | sentenca
    status TEXT NOT NULL,      -- queued | running | done | failed | cancelled
    priority INT NOT NULL,
    created_at TIMESTAMP DEFAULT now(),
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    worker TEXT,
    result TEXT,
    error TEXT
);
```

Essa tabela é a fonte de verdade para cada tarefa. Cada job enviado via API recebe um `id` (UUID). Os campos de data permitem calcular o tempo na fila e o tempo de execução. O campo `priority` pode ser utilizado para diferenciar despachos simples (prioridade alta) de decisões complexas (prioridade menor). O campo `worker` armazena qual nó Celery executou a tarefa.

### 3.2 Tabela `task_logs`

```sql
CREATE TABLE task_logs (
    id SERIAL PRIMARY KEY,
    task_id UUID REFERENCES tasks (id) ON DELETE CASCADE,
    step TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT now()
);
```

Esta tabela registra cada etapa do pipeline jurídico (upload, classificar, gerar minuta, validar, etc.). O painel pode usar esses registros para exibir o progresso detalhado de cada processo e permitir depuração de falhas.

### 3.3 Tabela `batches`

```sql
CREATE TABLE batches (
    id UUID PRIMARY KEY,
    created_at TIMESTAMP DEFAULT now(),
    total_tasks INT NOT NULL,
    status TEXT NOT NULL     -- queued | processing | completed
);
```

Cada envio em lote cria um `batch` que agrupa várias tarefas. Isso permite ao painel exibir progresso agregado (ex.: 50 despachos enviados, 30 concluídos, 2 falharam).

## 4. Integração com Celery e Supabase

### 4.1 Salvando tarefas no banco

O endpoint FastAPI responsável por receber uploads em lote deve, ao invés de enviar as tarefas diretamente para Celery, inserir um registro em `tasks` para cada arquivo. Em seguida, dispara uma task Celery passando apenas o `task_id` (o resto das informações estão no banco). Por exemplo:

```python
from uuid import uuid4
from fastapi import UploadFile
from supabase import create_client
from src.worker.tasks import process_task

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.post("/webhook/batch")
async def batch(files: list[UploadFile], tipo: str):
    task_ids = []
    for file in files:
        task_id = str(uuid4())
        # salva arquivo em storage (S3/local) e obtém path ou bytes
        file_bytes = await file.read()
        supabase.table("tasks").insert({
            "id": task_id,
            "file_name": file.filename,
            "tipo": tipo,
            "status": "queued",
            "priority": 1 if tipo == "despacho" else 2
        }).execute()
        # cria log
        supabase.table("task_logs").insert({"task_id": task_id, "step": "uploaded"}).execute()
        # dispara worker
        process_task.delay(task_id, file_bytes)
        task_ids.append(task_id)
    return {"tasks": task_ids}
```

### 4.2 Worker Celery com atualização de status

O worker será responsável por ler a tarefa a partir do banco, atualizar seu status e escrever logs. O exemplo abaixo usa a biblioteca oficial do Supabase para Python (ou qualquer wrapper compatível) para interagir com o banco:

```python
from celery import Celery
from supabase import create_client
import os

celery_app = Celery("lex_worker", broker="redis://localhost:6379/0", backend="redis://localhost:6379/1")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

@celery_app.task(bind=True)
def process_task(self, task_id: str, file_bytes: bytes):
    # Recupera task
    task = supabase.table("tasks").select("*").eq("id", task_id).single().execute().data
    if task["status"] == "cancelled":
        return
    # Atualiza para running
    supabase.table("tasks").update({"status": "running", "started_at": "now()"}).eq("id", task_id).execute()
    supabase.table("task_logs").insert({"task_id": task_id, "step": "started"}).execute()
    try:
        # TODO: chamar lógica de IA para gerar despacho/decisão, salvar resultado
        result_text = run_pipeline(file_bytes, task["tipo"], task_id)
        supabase.table("tasks").update({
            "status": "done",
            "finished_at": "now()",
            "result": result_text
        }).eq("id", task_id).execute()
        supabase.table("task_logs").insert({"task_id": task_id, "step": "finished"}).execute()
        return result_text
    except Exception as e:
        supabase.table("tasks").update({"status": "failed", "finished_at": "now()", "error": str(e)}).eq("id", task_id).execute()
        supabase.table("task_logs").insert({"task_id": task_id, "step": "failed"}).execute()
        raise
```

### 4.3 Cancelar ou interromper tarefas

Para cancelar uma tarefa em espera, basta atualizar seu `status` para `cancelled`. O worker consulta o status antes de iniciar; se encontrar `cancelled`, não processará e registrará a revogação. Para interromper uma tarefa em execução, é possível utilizar o comando `revoke` do Celery com `terminate=True`【462545852730767†L154-L176】. Após revogar, atualize o status para `cancelled` no banco.

### 4.4 Purgar filas

Em casos de emergência (por exemplo, envio incorreto de tarefas), pode-se usar o comando `celery -A proj purge` para remover todas as mensagens da fila; entretanto, a documentação alerta que esta operação é irreversível【462545852730767†L132-L153】. O painel deve exigir confirmação dupla antes de executar tal comando.

## 5. API administrativa (FastAPI)

Para que o painel possa controlar as tarefas, implemente as seguintes rotas administrativas:

* **`GET /admin/tasks`** – lista tarefas filtrando por status, tipo, prioridade ou intervalo de datas.
* **`POST /admin/cancel/{task_id}`** – define `status='cancelled'` e revoga a task com `terminate=True` se ela estiver em execução.
* **`POST /admin/retry/{task_id}`** – define `status='queued'` e despacha novamente a task (mantendo o histórico).
* **`POST /admin/clear_queue`** – executa o comando purge no Celery (com proteção de confirmação).
* **`GET /admin/batches/{batch_id}`** – obtém progresso de um lote (quantas tarefas concluídas, em execução, em fila ou falharam).

### Exemplo de cancelamento via API

```python
@app.post("/admin/cancel/{task_id}")
async def cancel_task(task_id: str):
    # Atualiza status no banco
    supabase.table("tasks").update({"status": "cancelled"}).eq("id", task_id).execute()
    # Revoga no Celery
    revoke(task_id, terminate=True)
    supabase.table("task_logs").insert({"task_id": task_id, "step": "cancelled"}).execute()
    return {"status": "cancelled"}
```

## 6. Painel de controle (Streamlit ou outro front‑end)

### 6.1 Visão geral

O painel deve chamar os endpoints acima para obter a lista de tarefas e agrupá-las em quatro estados: **na fila**, **executando**, **concluídas** e **falhas/canceladas**. Os totens exibem contadores (similar a um kanban) e permitem filtrar por tipo de decisão (despacho/decisão/sentença), por prioridade ou por lote.

### 6.2 Controles por tarefa

Para cada tarefa, o painel oferece botões para **cancelar**, **interromper** (se já estiver rodando) ou **reprocessar**. Um modal exibe os logs (`task_logs`) mostrando cada etapa e o timestamp. Isso atende ao requisito de “ter a exata noção do processamento em tempo real”.

### 6.3 Upload e criação de lote

Na aba de envio, o usuário seleciona vários arquivos, escolhe o tipo de decisão (despacho/decisão/sentença) e clica em **Enviar**. O front faz uma requisição `POST /webhook/batch`, que cria um `batch` no banco, gera vários `tasks` e dispara os workers. O painel acompanha o progresso e exibe alertas quando todas as tarefas terminam.

### 6.4 Central de administração

Uma página “Administração” apresenta:

* **Workers** – lista workers ativos, pool size, memória, etc. Pode ser obtido via `celery inspect stats`【462545852730767†L154-L176】.
* **Purgar fila** – botão com confirmação dupla que chama `/admin/clear_queue`.
* **Dashboard de Lotes** – lista dos últimos lotes, com progresso e tempo médio.

## 7. Considerações de implantação

1. **Ambiente** – Uma máquina virtual (AWS EC2 ou VPS da Locaweb) com 4 vCPU e 8–16 GB de RAM suporta facilmente 8 workers para despachos rápidos e 2–3 workers para decisões mais pesadas.
2. **Redis** continua sendo o broker rápido. O Celery usa Redis para enfileirar, mas o estado de cada task não depende do broker; ele vive no Postgres.
3. **Supabase** – A instância gratuita do Supabase suporta Postgres e permite criar as tabelas acima. Para alta disponibilidade, considere Supabase Pro ou rodar o próprio PostgreSQL.
4. **Segurança** – Use políticas de **Row Level Security (RLS)** em Supabase para garantir que apenas o backend possa alterar o status das tarefas【338621608011010†screenshot】.
5. **Backups** – Como o banco armazena a verdade das tarefas, configure backups regulares no Supabase.

## 8. Próximos passos

* **Integração com IA** – Substituir a função `run_pipeline()` por chamadas aos seus agentes Claude, incluindo o uso de modelos distintos para despachos (modelo Haiku) e decisões (modelo Sonnet) e o validador judicial.
* **Anonymização** – Adicionar um passo no pipeline para anonimizar dados sensíveis antes de armazenar ou exibir resultados, conforme a Resolução CNJ 615.
* **Jurimetria** – Com os dados estruturados no Postgres, você poderá gerar relatórios sobre tempos de processamento, tipos de ações, taxas de aprovação pelo validador, etc.
* **Escala horizontal** – A arquitetura suporta adicionar mais workers em outras máquinas; o Celery escala facilmente distribuindo tasks a todos os workers conectados ao mesmo broker.

## 9. Referências

* O artigo da Supabase descreve o lançamento do **Supabase Queues** com características como ser baseado em Postgres (`pgmq`), garantir entrega de mensagens, fornecer gerenciamento de filas e possibilitar arquivamento para auditoria【338621608011010†screenshot】.
* A documentação oficial do Celery apresenta os comandos de inspeção e controle (inspect active, reserved, revoked, etc.) e alerta que a operação `purge` remove mensagens de forma irreversível【462545852730767†L132-L153】. Ela também descreve as capacidades do Flower, incluindo monitoramento em tempo real, visualização de tarefas em execução, listas de filas e a possibilidade de revogar ou terminar tarefas via API HTTP【462545852730767†L240-L299】.
* Outro artigo da Supabase sugere combinar **Edge Functions**, **cron jobs** e **database queues** para dividir grandes trabalhos em etapas menores; esse padrão de três camadas (Coleta, Distribuição e Processamento) é relevante para escalabilidade【728504228869291†screenshot】.