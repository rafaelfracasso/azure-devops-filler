[← Fontes de Dados](sources.md) · [Back to README](../README.md)

# Referência CLI

Todos os comandos do `adf`. Execute `adf --help` ou `adf <comando> --help` para ajuda inline.

---

## `adf run`

Executa a coleta de atividades e cria Tasks no Azure DevOps.

```bash
adf run [OPÇÕES]
```

| Opção | Atalho | Padrão | Descrição |
|-------|--------|--------|-----------|
| `--date YYYY-MM-DD` | `-d` | hoje | Data específica |
| `--from YYYY-MM-DD` | — | — | Data inicial do período |
| `--to YYYY-MM-DD` | — | — | Data final do período |
| `--source NOME` | `-s` | todas | Fonte específica: `outlook`, `recurring` ou `git` |
| `--dry-run` | — | `false` | Simula sem criar Tasks |
| `--config CAMINHO` | `-c` | `config.yaml` | Caminho alternativo para o config.yaml |

**Exemplos:**

```bash
# Executa para hoje
adf run

# Executa para uma data específica
adf run --date 2026-01-15

# Executa um período completo
adf run --from 2026-01-01 --to 2026-01-31

# Apenas Outlook, com dry-run
adf run --source outlook --dry-run

# Apenas Git para uma data específica
adf run --source git --date 2026-02-10

# Usa config alternativo
adf run --config /path/para/outro-config.yaml
```

**Saída (modo padrão):**

```
📅 2026-02-10

  Outlook
    ✓ Reunião de alinhamento (1.5h) - Task #1055
    ⊘ Stand-up diário (já processada)

  Recorrentes
    ✓ Verificação de carga - Hive (0.5h) - Task #1056

  Azure Git
    ✓ [arrecadacao-ai] fix: corrige cálculo de impostos (0.5h) - Task #1057
    ✗ [outro-repo] feat: nova feature - Erro: 400 Bad Request

Resumo:
  Criadas: 3
  Ignoradas: 1
```

**Saída (modo `create_monthly_user_stories: true`):**

Quando habilitado no `config.yaml`, as Tasks são agrupadas por mês sob uma User Story:

```
📅 Fevereiro 2026

  ✓ [US] Atividades Fevereiro 2026 - João Silva - US #500
    ✓ Reunião de alinhamento (1.5h) - Task #1055
    ⊘ Stand-up diário (já processada)
    ✓ Verificação de carga - Hive (0.5h) - Task #1056
    ✓ [arrecadacao-ai] fix: corrige cálculo (0.5h) - Task #1057

📅 Janeiro 2026

  ⊘ [US] Atividades Janeiro 2026 - João Silva - US #480 (já existe)
    ✓ Reunião de planejamento (1.0h) - Task #1058

Resumo:
  Criadas: 4
  Ignoradas: 1
```

A User Story do mês é criada uma única vez e reutilizada em execuções subsequentes.

Símbolos:
- `✓` Task ou User Story criada com sucesso
- `⊘` Ignorada por deduplicação
- `○` Dry-run (seria criada)
- `✗` Erro ao criar

---

## `adf sources`

Lista as fontes configuradas e seu estado.

```bash
adf sources [--config CAMINHO]
```

**Saída:**

```
        Fontes Configuradas
┏━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Fonte      ┃ Habilitada┃ Tipo/Detalhes                 ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Outlook    │ ✓         │ Tipo: ics | ./data/calendar   │
│ Recorrentes│ ✓         │ 2 template(s) configurado(s)  │
│ Azure Git  │ ✓         │ 1 repo(s): arrecadacao-ai     │
└────────────┴───────────┴──────────────────────────────┘
```

---

## `adf test`

Testa as conexões com Azure DevOps e as fontes configuradas.

```bash
adf test [--config CAMINHO]
```

**Saída:**

```
Testando conexões...

Azure DevOps
  ✓ Conectado a MinhaOrg

Fontes
  ✓ Outlook
  ✓ Recorrentes
  ✓ Azure Git
```

Útil para validar PAT, URL e caminhos de arquivo antes de executar `adf run`.

---

## `adf stats`

Exibe estatísticas das atividades processadas (lê `data/processed.json`).

```bash
adf stats
```

**Saída:**

```
      Estatísticas de Processamento
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Fonte      ┃ Processadas  ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ Outlook    │ 45           │
│ Recorrentes│ 38           │
│ Git        │ 19           │
│ Total      │ 102          │
└────────────┴──────────────┘
```

---

## `adf export`

Coleta atividades e salva em JSON, **sem criar Tasks**. Não requer PAT para Outlook (CSV/ICS)
e Recorrentes. Útil para acumular dados antes de ter acesso ao Azure DevOps.

```bash
adf export --output ARQUIVO [OPÇÕES]
```

| Opção | Atalho | Padrão | Descrição |
|-------|--------|--------|-----------|
| `--output CAMINHO` | `-o` | `data/activities.json` | Arquivo JSON de saída |
| `--date YYYY-MM-DD` | `-d` | hoje | Data específica |
| `--from YYYY-MM-DD` | — | — | Data inicial |
| `--to YYYY-MM-DD` | — | — | Data final |
| `--source NOME` | `-s` | todas | Fonte específica (`outlook` ou `recurring`) |
| `--config CAMINHO` | `-c` | `config.yaml` | Config alternativo |

**Exemplos:**

```bash
# Exporta o mês inteiro
adf export --from 2026-01-01 --to 2026-01-31 -o data/janeiro.json

# Exporta apenas Outlook
adf export --source outlook -o data/reunioes.json

# Exporta um dia específico
adf export --date 2026-02-10 -o data/dia.json
```

> A fonte Git **não está disponível** no export pois requer PAT para buscar commits.

---

## `adf import`

Lê um arquivo JSON gerado pelo `export` e cria as Tasks no Azure DevOps.
Aplica deduplicação: atividades já processadas são ignoradas.

```bash
adf import ARQUIVO [OPÇÕES]
```

| Opção | Padrão | Descrição |
|-------|--------|-----------|
| `--dry-run` | `false` | Simula sem criar Tasks |
| `--config CAMINHO` | `config.yaml` | Config alternativo |

**Exemplos:**

```bash
# Importa com dry-run primeiro
adf import data/janeiro.json --dry-run

# Importa de fato
adf import data/janeiro.json
```

**Saída:**

```
Importando 83 atividades de data/janeiro.json

✓ Reunião de alinhamento (2026-01-05, 1.5h) - Task #1010
✓ Verificação de carga - Hive (2026-01-06, 0.5h) - Task #1011
⊘ Stand-up diário (2026-01-07) - já processada

Resumo:
  Criadas: 82
  Ignoradas: 1
```

---

## `adf delete`

Deleta um ou mais work items do Azure DevOps. Os itens são movidos para a **lixeira** (soft
delete) e podem ser restaurados pela interface web. O registro de deduplicação também é
removido, permitindo recriar a atividade se necessário.

```bash
adf delete ID [ID...] [OPÇÕES]
```

| Opção | Atalho | Padrão | Descrição |
|-------|--------|--------|-----------|
| `--yes` | `-y` | `false` | Pula a confirmação interativa |
| `--config CAMINHO` | `-c` | `config.yaml` | Config alternativo |

**Exemplos:**

```bash
# Deleta uma Task criada por engano
adf delete 1042

# Deleta múltiplas Tasks de uma vez
adf delete 1042 1043 1044

# Deleta sem confirmação interativa (útil em scripts)
adf delete 1042 --yes
```

**Saída:**

```
Work items a deletar: #1042, #1043
Os itens serão movidos para a lixeira e podem ser restaurados pela UI.

Confirmar exclusão? [y/N]: y
  ✓ #1042 deletado (removido do dedup)
  ✓ #1043 deletado (removido do dedup)
```

> **Restaurar:** No Azure DevOps, acesse **Boards → Work Items → Recycle Bin** para
> restaurar itens deletados.

> **Permissão de admin:** Para exclusão permanente (`destroy`), é necessária permissão de
> administrador do projeto. O `adf delete` sempre usa soft delete.

---

## Opção global `--config`

Todos os comandos aceitam `--config` / `-c` para especificar um arquivo de configuração
alternativo ao `config.yaml` padrão:

```bash
adf run --config config-prod.yaml
adf test -c ~/meus-configs/azure.yaml
```

## See Also

- [Getting Started](getting-started.md) — instalação e primeiro uso
- [Configuração](configuration.md) — referência do config.yaml
- [Fontes de Dados](sources.md) — comportamento de cada fonte
