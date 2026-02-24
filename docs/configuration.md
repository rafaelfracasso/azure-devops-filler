[← Getting Started](getting-started.md) · [Back to README](../README.md) · [Fontes de Dados →](sources.md)

# Configuração

A configuração é dividida em dois arquivos:

| Arquivo | Conteúdo |
|---------|----------|
| `.env` | Segredos (PAT, credenciais OAuth) — **nunca commitar** |
| `config.yaml` | Organização, projeto, áreas, fontes e calendário |

## Variáveis de ambiente (.env)

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `AZURE_DEVOPS_PAT` | Sim | Personal Access Token do Azure DevOps |
| `GRAPH_TENANT_ID` | Não | Tenant ID (apenas para Outlook via Graph API) |
| `GRAPH_CLIENT_ID` | Não | Client ID do App Registration no Azure AD |
| `GRAPH_CLIENT_SECRET` | Não | Client Secret do App Registration |
| `LLM_API_KEY` | Não | API key do LLM (padrão: `ollama`, para instâncias locais sem autenticação) |

```env
# .env
AZURE_DEVOPS_PAT=seu_pat_aqui

# Apenas para Outlook via Microsoft Graph API:
GRAPH_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
GRAPH_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
GRAPH_CLIENT_SECRET=seu_client_secret

# Apenas para aprimoramento de descrições via LLM:
LLM_API_KEY=sua_api_key
```

### Expansão de variáveis de ambiente no config.yaml

Qualquer valor no `config.yaml` pode referenciar variáveis de ambiente usando a sintaxe `${VAR_NAME}` ou `${VAR_NAME:-valor_padrão}`:

```yaml
azure_devops:
  organization: "${AZURE_ORG}"
  default_project: "${AZURE_PROJECT:-MeuProjeto}"
  assigned_to: "${AZURE_ASSIGNED_TO}"
```

## config.yaml — Referência completa

### Seção `azure_devops`

```yaml
azure_devops:
  base_url: "https://dev.azure.com"         # padrão; altere para servidores self-hosted
  organization: "MinhaOrg"                  # nome da organização
  default_project: "MeuProjeto"             # projeto padrão para criar Tasks
  default_area: "MeuProjeto"                # Area Path padrão (ex: "MeuProjeto\\SubÁrea")
  default_iteration: "MeuProjeto\\Iteration 1"  # Sprint/Iteration padrão
  author_email: "usuario@empresa.com"       # e-mail usado para filtrar commits no Git
  assigned_to: "DOMINIO\\matricula"         # (opcional) responsável padrão das Tasks
  default_state: "Fechado"                  # (opcional) estado inicial das Tasks criadas
  create_monthly_user_stories: false        # (opcional) agrupa Tasks sob User Stories mensais
  user_story_name: "Nome Exibido"           # (opcional) sufixo no título das User Stories
  enhance_descriptions: false               # (opcional) aprimora descrições via LLM
  llm_system_prompt: "Você é..."            # (opcional) prompt de sistema para o LLM
```

| Campo | Obrigatório | Padrão | Descrição |
|-------|-------------|--------|-----------|
| `base_url` | Não | `https://dev.azure.com` | URL base do Azure DevOps |
| `organization` | Sim | — | Nome da organização |
| `default_project` | Sim | — | Projeto padrão |
| `default_area` | Sim | — | Area Path padrão |
| `default_iteration` | Sim | `@CurrentIteration` | Sprint padrão |
| `author_email` | Sim | — | E-mail do autor para filtrar commits |
| `assigned_to` | Não | `null` | Responsável das Tasks (formato `DOMINIO\\usuario`) |
| `default_state` | Não | `null` | Estado inicial das Tasks criadas |
| `create_monthly_user_stories` | Não | `false` | Agrupa Tasks sob User Stories mensais |
| `user_story_name` | Não | `null` | Sufixo no título das User Stories (ex: `"João Silva"` → `"Atividades Fevereiro 2026 - João Silva"`) |
| `enhance_descriptions` | Não | `false` | Envia descrições ao LLM para aprimoramento antes de criar a Task |
| `llm_system_prompt` | Não | `null` | Prompt de sistema enviado ao LLM para guiar o aprimoramento |

> **Nota sobre `default_iteration`:** `@CurrentIteration` funciona apenas no Azure DevOps
> cloud. Em servidores self-hosted, use o caminho explícito (ex: `"Projeto\\Iteration 3"`).

> **Nota sobre `default_state`:** O Azure DevOps não permite criar Tasks diretamente em
> estados fechados. O `adf` usa dois passos: cria a Task com estado padrão e então atualiza
> o estado em seguida.

> **Nota sobre `create_monthly_user_stories`:** Quando habilitado, o `adf run` agrupa todas
> as atividades do período por mês e cria uma User Story para cada mês (ex: `"Atividades
> Fevereiro 2026"`), vinculando todas as Tasks como filhas. User Stories já existentes são
> reutilizadas via deduplicação. Veja o exemplo de saída em [Referência CLI](cli.md).

### Seção `llm` (opcional)

Necessária apenas quando `enhance_descriptions: true`. Aceita qualquer endpoint compatível
com a API OpenAI (Ollama local, LM Studio, OpenAI, etc.).

```yaml
llm:
  base_url: "http://localhost:11434/v1"  # endpoint OpenAI-compatible
  model: "llama3.1"                      # modelo a usar
```

| Campo | Obrigatório | Padrão | Descrição |
|-------|-------------|--------|-----------|
| `base_url` | Sim | — | URL do servidor LLM compatível com OpenAI |
| `model` | Não | `llama3.1` | Nome do modelo |

A autenticação usa `LLM_API_KEY` do `.env` (padrão: `ollama`, adequado para instâncias locais sem autenticação).

### Seção `sources.outlook`

```yaml
sources:
  outlook:
    enabled: true
    type: "ics"            # "csv", "ics" ou "graph_api"
    ics_path: "./data/calendar.ics"    # para type: ics
    csv_path: "./data/calendar.csv"    # para type: csv
    user_email: "usuario@empresa.com"  # para type: graph_api
    mapping:
      area_path: "MeuProjeto"
      tags:
        - "outlook"
        - "reunião"
```

| Campo | Obrigatório | Descrição |
|-------|-------------|-----------|
| `enabled` | Não (padrão `true`) | Habilita/desabilita a fonte |
| `type` | Sim | Modo de coleta: `csv`, `ics` ou `graph_api` |
| `ics_path` | Para `type: ics` | Caminho do arquivo `.ics` exportado do Outlook |
| `csv_path` | Para `type: csv` | Caminho do arquivo `.csv` exportado do Outlook |
| `user_email` | Para `type: graph_api` | E-mail do usuário para consulta na Graph API |
| `mapping.area_path` | Sim | Area Path para as Tasks do Outlook |
| `mapping.tags` | Não | Tags adicionadas às Tasks criadas |

### Seção `sources.recurring`

```yaml
sources:
  recurring:
    enabled: true
    templates:
      - name: "Verificação de carga - Hive"
        weekdays: [0, 1, 2, 3, 4]   # 0=segunda-feira, 6=domingo
        hours: 0.5
        area_path: "MeuProjeto"
        tags:
          - "recorrente"
          - "monitoramento"
```

| Campo | Obrigatório | Descrição |
|-------|-------------|-----------|
| `enabled` | Não (padrão `true`) | Habilita/desabilita a fonte |
| `templates[].name` | Sim | Título da Task gerada |
| `templates[].weekdays` | Sim | Dias da semana (0=seg, 1=ter, …, 6=dom) |
| `templates[].hours` | Sim | Horas registradas em `CompletedWork` |
| `templates[].area_path` | Sim | Area Path para as Tasks |
| `templates[].tags` | Não | Tags adicionadas às Tasks |

> A fonte de atividades recorrentes cria atividades às **13:00 GMT-4** (horário de Cuiabá) nas datas em que os
> templates se aplicam, respeitando `non_working_days`.

### Seção `sources.git`

```yaml
sources:
  git:
    enabled: true
    repositories:
      - name: "nome-do-repositorio"
        project: "ProjetoDoRepo"       # opcional; usa default_project se omitido
        area_path: "MeuProjeto"
        tags:
          - "git"
          - "desenvolvimento"
```

| Campo | Obrigatório | Descrição |
|-------|-------------|-----------|
| `enabled` | Não (padrão `true`) | Habilita/desabilita a fonte |
| `repositories[].name` | Sim | Nome exato do repositório no Azure DevOps |
| `repositories[].project` | Não | Projeto do repositório (usa `default_project` se omitido) |
| `repositories[].area_path` | Sim | Area Path para as Tasks |
| `repositories[].tags` | Não | Tags adicionadas às Tasks |

### Seção `non_working_days`

Lista de datas (formato `YYYY-MM-DD`) sem expediente. Quando uma data está nessa lista,
A fonte de atividades recorrentes não gera atividades para ela.

```yaml
non_working_days:
  - "2026-01-01"   # Confraternização Universal
  - "2026-02-16"   # Carnaval (segunda)
  - "2026-02-17"   # Carnaval (terça)
  - "2026-02-18"   # Quarta-feira de Cinzas
  - "2026-04-03"   # Sexta-feira Santa
```

> Atualize anualmente com os feriados nacionais, estaduais e recesso forense/institucional.

## Encontrar Area Path e Iteration Path

**Via URL do backlog:**

```
https://{base_url}/{org}/{project}/_backlogs/backlog/{area}
```

O nome da área aparece no caminho da URL.

**Via API REST:**

```bash
# Listar áreas
curl -u ":SEU_PAT" \
  "https://{base_url}/{org}/{project}/_apis/wit/classificationnodes/areas?api-version=7.1&\$depth=5"

# Listar iterations
curl -u ":SEU_PAT" \
  "https://{base_url}/{org}/{project}/_apis/wit/classificationnodes/iterations?api-version=7.1&\$depth=5"
```

## See Also

- [Getting Started](getting-started.md) — instalação e primeiro uso
- [Fontes de Dados](sources.md) — comportamento detalhado de cada fonte
- [Referência CLI](cli.md) — como usar cada comando
