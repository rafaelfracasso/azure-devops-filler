# Azure DevOps Activity Filler

> CLI para preencher Tasks no Azure DevOps automaticamente a partir de múltiplas fontes.

Coleta atividades do calendário Outlook, templates de atividades recorrentes e commits do Azure Git,
e cria Work Items (Tasks) no Azure DevOps via REST API — com deduplicação automática,
dry-run e suporte a períodos de datas.

## Quick Start

```bash
pip install -e .
cp .env.example .env      # adicione seu PAT do Azure DevOps
# edite config.yaml com sua organização, projeto e áreas
adf test                  # verifica as conexões
adf run --dry-run         # pré-visualiza o que seria criado
adf run                   # cria as Tasks
```

## Key Features

- **Outlook** — Importa reuniões do calendário (ICS, CSV ou Microsoft Graph API)
- **Recorrentes** — Templates de atividades recorrentes por dia da semana com horas configuráveis
- **Azure Git** — Uma Task por commit, com hash e timestamp do commit
- **Deduplicação** — Hash por fonte + título + data; nunca cria duplicatas
- **Dry-run** — Pré-visualize tudo antes de criar qualquer Task
- **Export/Import** — Colete atividades sem PAT e importe depois quando disponível
- **Non-working days** — Calendário de feriados e recesso para pular dias sem expediente

## Exemplo

```
$ adf run --from 2026-02-10 --to 2026-02-12

📅 2026-02-10

  Outlook
    ✓ Reunião de planejamento (1.0h) - Task #1042

  Recorrentes
    ✓ Verificação de carga - Hive (0.5h) - Task #1043
    ✓ Verificação de carga - DW (0.5h) - Task #1044

  Azure Git
    ✓ [arrecadacao-ai] feat: adiciona modelo preditivo (0.5h) - Task #1045

📅 2026-02-11

  Recorrentes
    ✓ Verificação de carga - Hive (0.5h) - Task #1046
    ✓ Verificação de carga - DW (0.5h) - Task #1047

Resumo:
  Criadas: 6
  Ignoradas: 0
```

---

## Documentação

| Guia | Descrição |
|------|-----------|
| [Getting Started](docs/getting-started.md) | Instalação, setup e primeiro uso |
| [Configuração](docs/configuration.md) | Referência do config.yaml e variáveis de ambiente |
| [Fontes de Dados](docs/sources.md) | Outlook, Recorrentes e Azure Git — como configurar cada fonte |
| [Referência CLI](docs/cli.md) | Todos os comandos com opções e exemplos |

## Licença

MIT
