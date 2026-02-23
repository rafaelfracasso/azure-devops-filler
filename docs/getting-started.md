[Back to README](../README.md) · [Configuração →](configuration.md)

# Getting Started

## Pré-requisitos

| Requisito | Versão mínima |
|-----------|---------------|
| Python | 3.10+ |
| pip | qualquer |
| Azure DevOps PAT | com permissões Work Items (Read & Write) e Code (Read) |

## Instalação

```bash
# Clone ou baixe o projeto
cd azure-devops-filler

# Instale em modo editável (recomendado)
pip install -e .

# Verifique a instalação
adf --help
```

## Setup

### 1. Configurar o PAT

Copie o arquivo de exemplo e adicione seu Personal Access Token:

```bash
cp .env.example .env
```

Edite `.env`:

```env
AZURE_DEVOPS_PAT=seu_pat_aqui
```

Para gerar um PAT no Azure DevOps: **User Settings → Personal Access Tokens → New Token**.
Permissões necessárias: **Work Items** (Read & Write) e **Code** (Read).

> Para servidores self-hosted (ex: `https://azure-devops.empresa.com`), o PAT é gerado
> na mesma interface: clique no ícone de usuário no canto superior direito.

### 2. Editar config.yaml

O arquivo `config.yaml` controla a organização, projeto, área e fontes de dados:

```yaml
azure_devops:
  base_url: "https://azure-devops.empresa.com"   # omitir para usar dev.azure.com
  organization: "MinhaOrg"
  default_project: "MeuProjeto"
  default_area: "MeuProjeto"
  default_iteration: "MeuProjeto\\Iteration 1"
  author_email: "meu.email@empresa.com"
  assigned_to: "DOMINIO\\matricula"              # opcional
  default_state: "Fechado"                       # opcional

sources:
  outlook:
    enabled: true
    type: "ics"
    ics_path: "./data/calendar.ics"
    mapping:
      area_path: "MeuProjeto"
      tags: ["outlook", "reunião"]

  recurring:
    enabled: true
    templates:
      - name: "Verificação diária"
        weekdays: [0, 1, 2, 3, 4]   # 0=segunda … 6=domingo
        hours: 0.5
        area_path: "MeuProjeto"
        tags: ["recorrente"]

  git:
    enabled: true
    repositories:
      - name: "meu-repositorio"
        project: "MeuProjeto"
        area_path: "MeuProjeto"
        tags: ["git", "desenvolvimento"]
```

### 3. Exportar o calendário (fonte Outlook)

No Outlook (desktop):
1. **Arquivo → Abrir e Exportar → Importar/Exportar**
2. **Exportar para um arquivo → Formato iCalendar (.ics)**
3. Selecione o calendário e salve em `data/calendar.ics`

## Primeiro uso

```bash
# Testa conexões com Azure DevOps e fontes configuradas
adf test

# Pré-visualiza o que seria criado hoje (sem criar nada)
adf run --dry-run

# Pré-visualiza um período específico
adf run --from 2026-01-01 --to 2026-01-31 --dry-run

# Cria as Tasks de fato
adf run
```

## Verificar resultado

```bash
# Mostra quantas Tasks foram criadas por fonte
adf stats
```

Saída esperada:

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

## Fluxo sem PAT (Export/Import)

Se você ainda não tem o PAT, é possível coletar Outlook e Recorrentes sem ele:

```bash
# 1. Coleta e exporta para JSON (sem PAT)
adf export --from 2026-01-01 --to 2026-01-31 -o data/janeiro.json

# 2. Quando tiver o PAT, importa
adf import data/janeiro.json
```

> A fonte Git **sempre requer PAT** (busca commits via API).

## See Also

- [Configuração](configuration.md) — referência completa do config.yaml e .env
- [Fontes de Dados](sources.md) — detalhes de cada fonte (Outlook, Recorrentes, Git)
- [Referência CLI](cli.md) — todos os comandos disponíveis
