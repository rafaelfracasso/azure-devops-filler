"""CLI principal do Azure DevOps Activity Filler."""

import asyncio
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Literal, Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

from .clients.azure_devops import AzureDevOpsClient
from .clients.llm import LLMEnhancer
from .clients.microsoft_graph import MicrosoftGraphClient
from .config import Settings, get_settings
from .dedup import DedupManager
from .models import Activity, SourceType, TaskConfig, UserStoryConfig
from .sources.base import BaseSource
from .sources.git import GitSource
from .sources.outlook import OutlookSource
from .sources.recurring import RecurringSource

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

app = typer.Typer(
    name="adf",
    help="Azure DevOps Activity Filler - CLI para preencher Tasks automaticamente",
    no_args_is_help=True,
)
console = Console()


def get_sources(settings: Settings, require_pat: bool = True) -> list[BaseSource]:
    """Cria as instâncias dos coletores de fontes.

    Args:
        settings: Configurações da aplicação
        require_pat: Se True, inclui fontes que requerem PAT (Git)

    Returns:
        Lista de coletores habilitados
    """
    sources: list[BaseSource] = []
    config = settings.config

    # Outlook
    if config.sources.outlook and config.sources.outlook.enabled:
        graph_client = None
        if config.sources.outlook.type == "graph_api":
            tenant_id = settings.graph_tenant_id
            client_id = settings.graph_client_id
            client_secret = settings.graph_client_secret

            if tenant_id and client_id and client_secret:
                graph_client = MicrosoftGraphClient(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                )

        sources.append(
            OutlookSource(
                config=config.sources.outlook,
                graph_client=graph_client,
            )
        )

    # Recurring
    if config.sources.recurring and config.sources.recurring.enabled:
        sources.append(RecurringSource(config=config.sources.recurring, non_working_days=config.non_working_days))

    # Git (requer PAT)
    if config.sources.git and config.sources.git.enabled and require_pat:
        try:
            pat = settings.azure_devops_pat
            azure_client = AzureDevOpsClient(
                organization=config.azure_devops.organization,
                pat=pat,
                default_project=config.azure_devops.default_project,
                base_url=config.azure_devops.base_url,
            )
            sources.append(
                GitSource(
                    config=config.sources.git,
                    azure_client=azure_client,
                    author_email=config.azure_devops.author_email,
                )
            )
        except ValueError:
            # PAT não configurado, pula fonte Git
            pass

    return sources


async def process_activities(
    activities: list[Activity],
    settings: Settings,
    dedup: DedupManager,
    dry_run: bool = False,
    enhancer: Optional[LLMEnhancer] = None,
) -> tuple[int, int]:
    """Processa atividades e cria Tasks no Azure DevOps.

    Args:
        activities: Lista de atividades a processar
        settings: Configurações da aplicação
        dedup: Gerenciador de duplicatas
        dry_run: Se True, apenas simula a criação
        enhancer: Instância do LLMEnhancer (opcional)

    Returns:
        Tupla (criadas, ignoradas)
    """
    config = settings.config
    created = 0
    skipped = 0

    async with AzureDevOpsClient(
        organization=config.azure_devops.organization,
        pat=settings.azure_devops_pat,
        default_project=config.azure_devops.default_project,
        base_url=config.azure_devops.base_url,
    ) as client:
        for activity in activities:
            if dedup.is_processed(activity):
                console.print(f"  [yellow]⊘[/yellow] {activity.title} (já processada)")
                skipped += 1
                continue

            description = activity.description
            if enhancer:
                description = await enhancer.enhance_description(
                    activity, system_prompt=config.azure_devops.llm_system_prompt
                )

            task_config = TaskConfig(
                title=activity.title,
                project=config.azure_devops.default_project,
                area_path=activity.area_path or config.azure_devops.default_area,
                iteration_path=activity.iteration_path or config.azure_devops.default_iteration,
                completed_work=activity.hours,
                description=description,
                tags=activity.tags,
                assigned_to=config.azure_devops.assigned_to,
                state=config.azure_devops.default_state,
                activity_datetime=activity.activity_datetime,
            )

            if dry_run:
                console.print(f"  [blue]○[/blue] {activity.title} ({activity.hours}h) - [dim]dry-run[/dim]")
                created += 1
            else:
                try:
                    result = await client.create_task(task_config)
                    dedup.mark_processed(activity, task_id=result.id, task_url=result.url)
                    console.print(f"  [green]✓[/green] {activity.title} ({activity.hours}h) - Task #{result.id}")
                    created += 1
                except httpx.HTTPStatusError as e:
                    detail = e.response.text[:300] if e.response.text else ""
                    console.print(f"  [red]✗[/red] {activity.title} - Erro: {e} | {detail}")
                except Exception as e:
                    console.print(f"  [red]✗[/red] {activity.title} - Erro: {e}")

    return created, skipped


async def process_activities_with_user_stories(
    activities: list[Activity],
    settings: Settings,
    dedup: DedupManager,
    dry_run: bool = False,
    enhancer: Optional[LLMEnhancer] = None,
) -> tuple[int, int]:
    """Processa atividades agrupadas por mês sob User Stories mensais.

    Args:
        activities: Lista completa de atividades a processar
        settings: Configurações da aplicação
        dedup: Gerenciador de duplicatas
        dry_run: Se True, apenas simula a criação
        enhancer: Instância do LLMEnhancer (opcional)

    Returns:
        Tupla (criadas, ignoradas)
    """
    config = settings.config
    az_cfg = config.azure_devops
    created = 0
    skipped = 0

    # Agrupa por (ano, mês)
    by_month: dict[tuple[int, int], list[Activity]] = defaultdict(list)
    for activity in activities:
        key = (activity.date.year, activity.date.month)
        by_month[key].append(activity)

    async with AzureDevOpsClient(
        organization=az_cfg.organization,
        pat=settings.azure_devops_pat,
        default_project=az_cfg.default_project,
        base_url=az_cfg.base_url,
    ) as client:
        for (year, month) in sorted(by_month.keys()):
            mes_pt = MESES_PT[month]
            us_name = az_cfg.user_story_name
            us_title = f"Atividades {mes_pt} {year} - {us_name}" if us_name else f"Atividades {mes_pt} {year}"

            console.print(f"\n[bold]📅 {mes_pt} {year}[/bold]")

            # Obtém ou cria a User Story do mês
            user_story_id: Optional[int] = None

            if dedup.is_user_story_processed(year, month):
                user_story_id = dedup.get_user_story_id(year, month)
                console.print(f"  [yellow]⊘[/yellow] [US] {us_title} - US #{user_story_id} (já existe)")
            elif dry_run:
                console.print(f"  [blue]○[/blue] [US] {us_title} - [dim]dry-run[/dim]")
            else:
                us_config = UserStoryConfig(
                    title=us_title,
                    project=az_cfg.default_project,
                    area_path=az_cfg.default_area,
                    iteration_path=az_cfg.default_iteration,
                    assigned_to=az_cfg.assigned_to,
                    state=az_cfg.default_state,
                )
                try:
                    us_result = await client.create_user_story(us_config)
                    dedup.mark_user_story_processed(year, month, us_result.id, us_result.url)
                    user_story_id = us_result.id
                    console.print(f"  [green]✓[/green] [US] {us_title} - US #{us_result.id}")
                except httpx.HTTPStatusError as e:
                    detail = e.response.text[:300] if e.response.text else ""
                    console.print(f"  [red]✗[/red] [US] {us_title} - Erro: {e} | {detail}")
                except Exception as e:
                    console.print(f"  [red]✗[/red] [US] {us_title} - Erro: {e}")

            # Cria as Tasks filhas
            for activity in by_month[(year, month)]:
                if dedup.is_processed(activity):
                    console.print(f"    [yellow]⊘[/yellow] {activity.title} (já processada)")
                    skipped += 1
                    continue

                description = activity.description
                if enhancer:
                    description = await enhancer.enhance_description(
                        activity, system_prompt=az_cfg.llm_system_prompt
                    )

                task_config = TaskConfig(
                    title=activity.title,
                    project=az_cfg.default_project,
                    area_path=activity.area_path or az_cfg.default_area,
                    iteration_path=activity.iteration_path or az_cfg.default_iteration,
                    completed_work=activity.hours,
                    description=description,
                    tags=activity.tags,
                    assigned_to=az_cfg.assigned_to,
                    state=az_cfg.default_state,
                    activity_datetime=activity.activity_datetime,
                    parent_id=user_story_id,
                )

                if dry_run:
                    console.print(f"    [blue]○[/blue] {activity.title} ({activity.hours}h) - [dim]dry-run[/dim]")
                    created += 1
                else:
                    try:
                        result = await client.create_task(task_config)
                        dedup.mark_processed(activity, task_id=result.id, task_url=result.url)
                        console.print(f"    [green]✓[/green] {activity.title} ({activity.hours}h) - Task #{result.id}")
                        created += 1
                    except httpx.HTTPStatusError as e:
                        detail = e.response.text[:300] if e.response.text else ""
                        console.print(f"    [red]✗[/red] {activity.title} - Erro: {e} | {detail}")
                    except Exception as e:
                        console.print(f"    [red]✗[/red] {activity.title} - Erro: {e}")

    return created, skipped


@app.command()
def run(
    date_str: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Data específica (YYYY-MM-DD)"),
    ] = None,
    from_date_str: Annotated[
        Optional[str],
        typer.Option("--from", help="Data inicial do período (YYYY-MM-DD)"),
    ] = None,
    to_date_str: Annotated[
        Optional[str],
        typer.Option("--to", help="Data final do período (YYYY-MM-DD)"),
    ] = None,
    source_name: Annotated[
        Optional[str],
        typer.Option("--source", "-s", help="Fonte específica (outlook, recurring, git)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Simula sem criar Tasks"),
    ] = False,
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Caminho do arquivo config.yaml"),
    ] = None,
) -> None:
    """Executa a coleta e criação de Tasks."""
    try:
        settings = get_settings(config_path=config_path)
    except FileNotFoundError as e:
        console.print(f"[red]Erro:[/red] {e}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Erro de configuração:[/red] {e}")
        raise typer.Exit(1)

    # Determina o período de datas
    if date_str:
        target_dates = [date.fromisoformat(date_str)]
    elif from_date_str and to_date_str:
        start = date.fromisoformat(from_date_str)
        end = date.fromisoformat(to_date_str)
        target_dates = []
        current = start
        while current <= end:
            target_dates.append(current)
            current += timedelta(days=1)
    else:
        target_dates = [date.today()]

    # Filtra fontes
    sources = get_sources(settings)
    if source_name:
        source_type = SourceType(source_name)
        sources = [s for s in sources if s.source_type == source_type]

    if not sources:
        console.print("[yellow]Nenhuma fonte habilitada ou encontrada.[/yellow]")
        raise typer.Exit(0)

    dedup = DedupManager()

    if dry_run:
        console.print("[blue]Modo dry-run ativado - nenhuma Task será criada[/blue]\n")

    az_cfg = settings.config.azure_devops
    use_user_stories = az_cfg.create_monthly_user_stories

    # Instancia LLM enhancer se configurado
    enhancer: Optional[LLMEnhancer] = None
    if az_cfg.enhance_descriptions and settings.config.llm:
        llm_cfg = settings.config.llm
        enhancer = LLMEnhancer(
            base_url=llm_cfg.base_url,
            model=llm_cfg.model,
            api_key=settings.llm_api_key,
        )

    total_created = 0
    total_skipped = 0

    async def run_async():
        nonlocal total_created, total_skipped

        if use_user_stories:
            # Coleta TODAS as atividades primeiro, depois processa agrupado por mês
            all_activities: list[Activity] = []
            for target_date in target_dates:
                for source in sources:
                    try:
                        activities = await source.collect(target_date)
                        all_activities.extend(activities)
                    except Exception as e:
                        console.print(f"[red]Erro ao coletar {source.name} em {target_date}:[/red] {e}")

            if not all_activities:
                console.print("[yellow]Nenhuma atividade encontrada.[/yellow]")
                return

            cr, sk = await process_activities_with_user_stories(
                activities=all_activities,
                settings=settings,
                dedup=dedup,
                dry_run=dry_run,
                enhancer=enhancer,
            )
            total_created += cr
            total_skipped += sk
        else:
            # Fluxo original: data a data
            for target_date in target_dates:
                console.print(f"\n[bold]📅 {target_date.isoformat()}[/bold]")

                for source in sources:
                    console.print(f"\n[cyan]{source.name}[/cyan]")

                    try:
                        activities = await source.collect(target_date)

                        if not activities:
                            console.print("  [dim]Nenhuma atividade encontrada[/dim]")
                            continue

                        created, skipped = await process_activities(
                            activities=activities,
                            settings=settings,
                            dedup=dedup,
                            dry_run=dry_run,
                            enhancer=enhancer,
                        )
                        total_created += created
                        total_skipped += skipped

                    except Exception as e:
                        console.print(f"  [red]Erro ao coletar:[/red] {e}")

    asyncio.run(run_async())

    # Resumo
    console.print(f"\n[bold]Resumo:[/bold]")
    console.print(f"  Criadas: {total_created}")
    console.print(f"  Ignoradas: {total_skipped}")


@app.command()
def sources(
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Caminho do arquivo config.yaml"),
    ] = None,
) -> None:
    """Lista as fontes configuradas."""
    try:
        settings = get_settings(config_path=config_path)
    except FileNotFoundError as e:
        console.print(f"[red]Erro:[/red] {e}")
        raise typer.Exit(1)

    config = settings.config

    table = Table(title="Fontes Configuradas")
    table.add_column("Fonte", style="cyan")
    table.add_column("Habilitada", style="green")
    table.add_column("Tipo/Detalhes")

    # Outlook
    if config.sources.outlook:
        outlook = config.sources.outlook
        details = f"Tipo: {outlook.type}"
        if outlook.type == "csv" and outlook.csv_path:
            details += f" | CSV: {outlook.csv_path}"
        elif outlook.type == "graph_api" and outlook.user_email:
            details += f" | Email: {outlook.user_email}"
        table.add_row(
            "Outlook",
            "✓" if outlook.enabled else "✗",
            details,
        )

    # Recurring
    if config.sources.recurring:
        recurring = config.sources.recurring
        templates = len(recurring.templates)
        table.add_row(
            "Recurring",
            "✓" if recurring.enabled else "✗",
            f"{templates} template(s) configurado(s)",
        )

    # Git
    if config.sources.git:
        git = config.sources.git
        repos = len(git.repositories)
        repo_names = ", ".join(r.name for r in git.repositories[:3])
        if repos > 3:
            repo_names += f" (+{repos - 3})"
        table.add_row(
            "Azure Git",
            "✓" if git.enabled else "✗",
            f"{repos} repo(s): {repo_names}",
        )

    console.print(table)


@app.command()
def test(
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Caminho do arquivo config.yaml"),
    ] = None,
) -> None:
    """Testa as conexões com as APIs."""
    try:
        settings = get_settings(config_path=config_path)
    except FileNotFoundError as e:
        console.print(f"[red]Erro:[/red] {e}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Erro de configuração:[/red] {e}")
        raise typer.Exit(1)

    config = settings.config

    async def run_tests():
        console.print("[bold]Testando conexões...[/bold]\n")

        # Azure DevOps
        console.print("[cyan]Azure DevOps[/cyan]")
        try:
            async with AzureDevOpsClient(
                organization=config.azure_devops.organization,
                pat=settings.azure_devops_pat,
                default_project=config.azure_devops.default_project,
                base_url=config.azure_devops.base_url,
            ) as client:
                await client.test_connection()
                console.print(f"  [green]✓[/green] Conectado a {config.azure_devops.organization}")
        except Exception as e:
            console.print(f"  [red]✗[/red] Falha na conexão: {e}")

        # Microsoft Graph
        if config.sources.outlook and config.sources.outlook.type == "graph_api":
            console.print("\n[cyan]Microsoft Graph[/cyan]")
            tenant_id = settings.graph_tenant_id
            client_id = settings.graph_client_id
            client_secret = settings.graph_client_secret

            if not all([tenant_id, client_id, client_secret]):
                console.print("  [yellow]⊘[/yellow] Credenciais não configuradas")
            else:
                try:
                    async with MicrosoftGraphClient(
                        tenant_id=tenant_id,
                        client_id=client_id,
                        client_secret=client_secret,
                    ) as graph_client:
                        if await graph_client.test_connection():
                            console.print("  [green]✓[/green] Autenticação bem sucedida")
                        else:
                            console.print("  [red]✗[/red] Falha na autenticação")
                except Exception as e:
                    console.print(f"  [red]✗[/red] Erro: {e}")

        # Fontes
        console.print("\n[cyan]Fontes[/cyan]")
        sources_list = get_sources(settings)

        for source in sources_list:
            try:
                if await source.test_connection():
                    console.print(f"  [green]✓[/green] {source.name}")
                else:
                    console.print(f"  [red]✗[/red] {source.name}")
            except Exception as e:
                console.print(f"  [red]✗[/red] {source.name}: {e}")

    asyncio.run(run_tests())


@app.command()
def stats(
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Caminho do arquivo config.yaml"),
    ] = None,
) -> None:
    """Mostra estatísticas de atividades processadas."""
    dedup = DedupManager()
    stats_data = dedup.get_stats()

    table = Table(title="Estatísticas de Processamento")
    table.add_column("Fonte", style="cyan")
    table.add_column("Processadas", style="green", justify="right")

    for source, count in stats_data["by_source"].items():
        table.add_row(source.capitalize(), str(count))

    table.add_row("[bold]Total[/bold]", f"[bold]{stats_data['total']}[/bold]")

    console.print(table)


@app.command("export")
def export_activities(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Arquivo de saída (JSON)"),
    ] = Path("data/activities.json"),
    date_str: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Data específica (YYYY-MM-DD)"),
    ] = None,
    from_date_str: Annotated[
        Optional[str],
        typer.Option("--from", help="Data inicial do período (YYYY-MM-DD)"),
    ] = None,
    to_date_str: Annotated[
        Optional[str],
        typer.Option("--to", help="Data final do período (YYYY-MM-DD)"),
    ] = None,
    source_name: Annotated[
        Optional[str],
        typer.Option("--source", "-s", help="Fonte específica (outlook, recurring)"),
    ] = None,
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Caminho do arquivo config.yaml"),
    ] = None,
) -> None:
    """Exporta atividades para JSON (não requer PAT para Outlook CSV e Recurring)."""
    try:
        settings = get_settings(config_path=config_path)
    except FileNotFoundError as e:
        console.print(f"[red]Erro:[/red] {e}")
        raise typer.Exit(1)

    # Determina o período de datas
    if date_str:
        target_dates = [date.fromisoformat(date_str)]
    elif from_date_str and to_date_str:
        start = date.fromisoformat(from_date_str)
        end = date.fromisoformat(to_date_str)
        target_dates = []
        current = start
        while current <= end:
            target_dates.append(current)
            current += timedelta(days=1)
    else:
        target_dates = [date.today()]

    # Filtra fontes (sem PAT, apenas Outlook CSV e Recurring funcionam)
    sources = get_sources(settings, require_pat=False)
    if source_name:
        source_type = SourceType(source_name)
        sources = [s for s in sources if s.source_type == source_type]

    if not sources:
        console.print("[yellow]Nenhuma fonte habilitada ou encontrada.[/yellow]")
        console.print("[dim]Nota: Git requer PAT e não está disponível para export sem PAT.[/dim]")
        raise typer.Exit(0)

    all_activities: list[dict] = []

    async def collect_async():
        for target_date in target_dates:
            console.print(f"[bold]📅 {target_date.isoformat()}[/bold]")

            for source in sources:
                console.print(f"  [cyan]{source.name}[/cyan]", end=" ")

                try:
                    activities = await source.collect(target_date)

                    if not activities:
                        console.print("[dim]- nenhuma[/dim]")
                        continue

                    console.print(f"[green]- {len(activities)} atividade(s)[/green]")

                    for activity in activities:
                        all_activities.append(activity.to_dict())

                except Exception as e:
                    console.print(f"[red]- erro: {e}[/red]")

    asyncio.run(collect_async())

    if not all_activities:
        console.print("\n[yellow]Nenhuma atividade encontrada para exportar.[/yellow]")
        raise typer.Exit(0)

    # Garante que o diretório existe
    output.parent.mkdir(parents=True, exist_ok=True)

    # Salva o arquivo
    with open(output, "w", encoding="utf-8") as f:
        json.dump(
            {
                "exported_at": date.today().isoformat(),
                "activities": all_activities,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    console.print(f"\n[green]✓[/green] Exportadas {len(all_activities)} atividades para {output}")


@app.command("import")
def import_activities(
    input_file: Annotated[
        Path,
        typer.Argument(help="Arquivo JSON com atividades exportadas"),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Simula sem criar Tasks"),
    ] = False,
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Caminho do arquivo config.yaml"),
    ] = None,
) -> None:
    """Importa atividades de um arquivo JSON e cria Tasks no Azure DevOps."""
    if not input_file.exists():
        console.print(f"[red]Erro:[/red] Arquivo não encontrado: {input_file}")
        raise typer.Exit(1)

    try:
        settings = get_settings(config_path=config_path)
    except FileNotFoundError as e:
        console.print(f"[red]Erro:[/red] {e}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Erro de configuração:[/red] {e}")
        raise typer.Exit(1)

    # Carrega as atividades
    with open(input_file, encoding="utf-8") as f:
        data = json.load(f)

    activities_data = data.get("activities", [])
    if not activities_data:
        console.print("[yellow]Nenhuma atividade encontrada no arquivo.[/yellow]")
        raise typer.Exit(0)

    # Converte para objetos Activity
    activities = []
    for item in activities_data:
        activities.append(
            Activity(
                title=item["title"],
                source=SourceType(item["source"]),
                date=date.fromisoformat(item["date"]),
                hours=item["hours"],
                description=item.get("description"),
                area_path=item.get("area_path"),
                iteration_path=item.get("iteration_path"),
                tags=item.get("tags", []),
            )
        )

    console.print(f"[bold]Importando {len(activities)} atividades de {input_file}[/bold]\n")

    if dry_run:
        console.print("[blue]Modo dry-run ativado - nenhuma Task será criada[/blue]\n")

    dedup = DedupManager()
    config = settings.config
    total_created = 0
    total_skipped = 0

    async def import_async():
        nonlocal total_created, total_skipped

        async with AzureDevOpsClient(
            organization=config.azure_devops.organization,
            pat=settings.azure_devops_pat,
            default_project=config.azure_devops.default_project,
            base_url=config.azure_devops.base_url,
        ) as client:
            for activity in activities:
                if dedup.is_processed(activity):
                    console.print(f"[yellow]⊘[/yellow] {activity.title} ({activity.date}) - já processada")
                    total_skipped += 1
                    continue

                task_config = TaskConfig(
                    title=activity.title,
                    project=config.azure_devops.default_project,
                    area_path=activity.area_path or config.azure_devops.default_area,
                    iteration_path=activity.iteration_path or config.azure_devops.default_iteration,
                    completed_work=activity.hours,
                    description=activity.description,
                    assigned_to=config.azure_devops.assigned_to,
                    tags=activity.tags,
                )

                if dry_run:
                    console.print(f"[blue]○[/blue] {activity.title} ({activity.date}, {activity.hours}h) - [dim]dry-run[/dim]")
                    total_created += 1
                else:
                    try:
                        result = await client.create_task(task_config)
                        dedup.mark_processed(activity, task_id=result.id, task_url=result.url)
                        console.print(f"[green]✓[/green] {activity.title} ({activity.date}, {activity.hours}h) - Task #{result.id}")
                        total_created += 1
                    except Exception as e:
                        console.print(f"[red]✗[/red] {activity.title} - Erro: {e}")

    asyncio.run(import_async())

    # Resumo
    console.print(f"\n[bold]Resumo:[/bold]")
    console.print(f"  Criadas: {total_created}")
    console.print(f"  Ignoradas: {total_skipped}")


@app.command()
def delete(
    work_item_ids: Annotated[
        list[int],
        typer.Argument(help="ID(s) do(s) work item(s) a deletar"),
    ],
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Pula confirmação interativa"),
    ] = False,
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Caminho do arquivo config.yaml"),
    ] = None,
) -> None:
    """Deleta work items do Azure DevOps (soft delete — vão para a lixeira)."""
    try:
        settings = get_settings(config_path=config_path)
    except FileNotFoundError as e:
        console.print(f"[red]Erro:[/red] {e}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Erro de configuração:[/red] {e}")
        raise typer.Exit(1)

    ids_str = ", ".join(f"#{i}" for i in work_item_ids)
    console.print(f"[yellow]Work items a deletar:[/yellow] {ids_str}")
    console.print("[dim]Os itens serão movidos para a lixeira e podem ser restaurados pela UI.[/dim]\n")

    if not yes:
        confirmed = typer.confirm("Confirmar exclusão?")
        if not confirmed:
            console.print("[dim]Operação cancelada.[/dim]")
            raise typer.Exit(0)

    config = settings.config
    dedup = DedupManager()

    async def delete_async():
        async with AzureDevOpsClient(
            organization=config.azure_devops.organization,
            pat=settings.azure_devops_pat,
            default_project=config.azure_devops.default_project,
            base_url=config.azure_devops.base_url,
        ) as client:
            for work_item_id in work_item_ids:
                try:
                    await client.delete_work_item(work_item_id)
                    removed_from_dedup = dedup.remove_by_task_id(work_item_id)
                    dedup_note = " [dim](removido do dedup)[/dim]" if removed_from_dedup else ""
                    console.print(f"  [green]✓[/green] #{work_item_id} deletado{dedup_note}")
                except Exception as e:
                    console.print(f"  [red]✗[/red] #{work_item_id} - Erro: {e}")

    asyncio.run(delete_async())


if __name__ == "__main__":
    app()
