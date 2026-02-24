[← Configuração](configuration.md) · [Back to README](../README.md) · [Referência CLI →](cli.md)

# Fontes de Dados

O `adf` coleta atividades de três fontes. Cada fonte implementa a interface `BaseSource`
e pode ser habilitada/desabilitada independentemente no `config.yaml`.

## Outlook

Coleta reuniões e eventos do calendário. Suporta três modos:

### ICS (recomendado)

Exporta o calendário do Outlook como arquivo `.ics` (iCalendar):

1. No Outlook Desktop: **Arquivo → Abrir e Exportar → Importar/Exportar**
2. Selecione **Exportar para arquivo → Formato iCalendar (.ics)**
3. Salve em `data/calendar.ics`

```yaml
sources:
  outlook:
    enabled: true
    type: "ics"
    ics_path: "./data/calendar.ics"
    mapping:
      area_path: "MeuProjeto"
      tags: ["outlook", "reunião"]
```

**Comportamento:**
- Cada evento vira uma Task com o assunto como título
- `CompletedWork` = duração real do evento em horas (mínimo 0.25h)
- `StartDate` e `FinishDate` = horário de início do evento
- Eventos all-day (sem horário) são incluídos com duração 0h

### CSV

Exporta o calendário como planilha `.csv`:

1. No Outlook Desktop: **Arquivo → Abrir e Exportar → Importar/Exportar → Exportar para arquivo → Valores Separados por Vírgulas**
2. Salve em `data/calendar.csv`

```yaml
sources:
  outlook:
    enabled: true
    type: "csv"
    csv_path: "./data/calendar.csv"
    mapping:
      area_path: "MeuProjeto"
      tags: ["outlook"]
```

O parser aceita arquivos em português (colunas `Assunto`, `Data de Início`) e inglês
(`Subject`, `Start Date`). Formatos de data suportados: `MM/DD/YYYY`, `DD/MM/YYYY`, `YYYY-MM-DD`.

### Graph API (Microsoft Graph)

Busca eventos diretamente via API, sem exportar arquivo. Requer App Registration no Azure AD.

```yaml
sources:
  outlook:
    enabled: true
    type: "graph_api"
    user_email: "usuario@empresa.com"
    mapping:
      area_path: "MeuProjeto"
      tags: ["outlook"]
```

**Configuração do App Registration:**
1. Acesse [portal.azure.com](https://portal.azure.com) → **Azure Active Directory → App Registrations → New Registration**
2. Adicione permissão de aplicação: **Microsoft Graph → Calendars.Read**
3. Gere um Client Secret em **Certificates & Secrets**
4. Adicione `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID` e `GRAPH_CLIENT_SECRET` ao `.env`

---

## Atividades Recorrentes

Gera Tasks baseadas em templates — atividades recorrentes com horário e carga fixos.
Não requer conexão com nenhuma API; tudo é configurado no `config.yaml`.

```yaml
sources:
  recurring:
    enabled: true
    templates:
      - name: "Verificação de carga - Hive"
        weekdays: [0, 1, 2, 3, 4]   # segunda a sexta
        hours: 0.5
        area_path: "MeuProjeto"
        tags: ["qlik", "monitoramento"]
      - name: "Verificação semanal"
        weekdays: [4]                # apenas sexta-feira
        hours: 1.0
        area_path: "MeuProjeto\\SubÁrea"
        tags: ["revisão"]
```

**Comportamento:**
- Para cada data processada, verifica quais templates se aplicam (`weekday` corresponde)
- Datas listadas em `non_working_days` são completamente ignoradas
- `StartDate` e `FinishDate` = 13:00 GMT-4 (horário de Cuiabá)
- `CompletedWork` = valor de `hours` do template

| Valor | Dia |
|-------|-----|
| `0` | Segunda-feira |
| `1` | Terça-feira |
| `2` | Quarta-feira |
| `3` | Quinta-feira |
| `4` | Sexta-feira |
| `5` | Sábado |
| `6` | Domingo |

---

## Azure Git

Busca commits por autor e período, criando **uma Task por commit**.

```yaml
sources:
  git:
    enabled: true
    repositories:
      - name: "nome-do-repositorio"
        project: "ProjetoDoRepo"      # omitir para usar default_project
        area_path: "MeuProjeto"
        tags: ["git", "desenvolvimento"]
      - name: "outro-repositorio"
        project: "OutroProjeto"
        area_path: "MeuProjeto\\Backend"
        tags: ["git"]
```

**Comportamento:**
- Filtra commits pelo `author_email` configurado em `azure_devops`
- Título da Task: `[nome-do-repo] primeira linha da mensagem do commit`
- Descrição (PT-BR): hash completo + mensagem do commit
- `CompletedWork` = 0.5h por commit
- `StartDate` e `FinishDate` = timestamp exato do commit

> **Importante:** O `author_email` deve corresponder ao e-mail usado nos commits,
> que pode ser diferente do e-mail de login. Verifique em **User Settings → Profile**.
> Em alguns ambientes, o e-mail dos commits usa a matrícula (ex: `12345@empresa.com`).

**Requer PAT** com permissão **Code (Read)**.

---

## Deduplicação

Todas as fontes compartilham o mesmo mecanismo de deduplicação. Antes de criar qualquer
Task, o `adf` gera um hash baseado em:

```
SHA256(fonte + ":" + título_normalizado + ":" + data)
```

A normalização remove acentos, converte para minúsculas e colapsa espaços. O hash é
salvo em `data/processed.json` após a criação.

Rodando `adf run` duas vezes para a mesma data, a segunda execução ignora todas as
atividades já processadas com a mensagem `⊘ título (já processada)`.

## Agrupamento em User Stories mensais

Quando `create_monthly_user_stories: true` está configurado em `azure_devops`, o `adf`
altera o fluxo de criação:

1. Coleta **todas** as atividades do período primeiro
2. Agrupa por mês (ano + mês)
3. Para cada mês, cria uma User Story com o título `"Atividades <Mês> <Ano>"` (ou
   `"Atividades <Mês> <Ano> - <user_story_name>"` se `user_story_name` estiver configurado)
4. Cria cada Task como filha da respectiva User Story via relação `Hierarchy-Reverse`

User Stories já criadas são reutilizadas: o ID fica registrado em `data/processed.json`
e execuções subsequentes vinculam novas Tasks ao mesmo item existente.

```yaml
azure_devops:
  create_monthly_user_stories: true
  user_story_name: "João Silva"  # opcional
```

Veja o exemplo de saída no modo User Story em [Referência CLI](cli.md#adf-run).

## See Also

- [Configuração](configuration.md) — opções completas de cada fonte no config.yaml
- [Getting Started](getting-started.md) — como exportar o calendário do Outlook
- [Referência CLI](cli.md) — filtrar por fonte com `--source`
