"""Testes para o cliente Azure DevOps."""

import json

import httpx
import pytest
import respx

from azure_devops_filler.clients.azure_devops import AzureDevOpsClient
from azure_devops_filler.models import TaskConfig, UserStoryConfig

BASE_URL = "https://dev.azure.com"
ORG = "my-org"
PROJECT = "my-project"

# Resposta padrão de criação de work item
TASK_RESPONSE = {
    "id": 1001,
    "_links": {"html": {"href": f"{BASE_URL}/{ORG}/{PROJECT}/_workitems/edit/1001"}},
    "fields": {"System.Title": "Minha Task"},
}

US_RESPONSE = {
    "id": 2001,
    "_links": {"html": {"href": f"{BASE_URL}/{ORG}/{PROJECT}/_workitems/edit/2001"}},
    "fields": {"System.Title": "Atividades Fevereiro 2026"},
}

COMMITS_RESPONSE = {
    "value": [
        {
            "commitId": "abc1234567890abcdef",
            "comment": "fix: corrige bug no modelo",
            "author": {
                "email": "user@example.com",
                "date": "2026-02-19T13:00:00Z",
            },
        },
        {
            "commitId": "def456789012345678",
            "comment": "feat: nova funcionalidade",
            "author": {
                "email": "user@example.com",
                "date": "2026-02-18T10:30:00Z",
            },
        },
    ]
}


@pytest.fixture
def client():
    return AzureDevOpsClient(
        organization=ORG,
        pat="test-pat",
        default_project=PROJECT,
        base_url=BASE_URL,
    )


@pytest.fixture
def basic_task():
    return TaskConfig(
        title="Minha Task",
        project=PROJECT,
        area_path="AI",
        iteration_path="AI\\Iteration 3",
        completed_work=1.0,
    )


@pytest.fixture
def basic_user_story():
    return UserStoryConfig(
        title="Atividades Fevereiro 2026",
        project=PROJECT,
        area_path="AI",
        iteration_path="AI\\Iteration 3",
    )


class TestTestConnection:
    async def test_returns_true_on_200(self, client):
        with respx.mock:
            respx.get(f"{BASE_URL}/{ORG}/_apis/projects").mock(
                return_value=httpx.Response(200, json={"value": []})
            )
            assert await client.test_connection() is True

    async def test_returns_false_on_401(self, client):
        with respx.mock:
            respx.get(f"{BASE_URL}/{ORG}/_apis/projects").mock(
                return_value=httpx.Response(401)
            )
            assert await client.test_connection() is False

    async def test_returns_false_on_403(self, client):
        with respx.mock:
            respx.get(f"{BASE_URL}/{ORG}/_apis/projects").mock(
                return_value=httpx.Response(403)
            )
            assert await client.test_connection() is False

    async def test_returns_false_on_network_error(self, client):
        with respx.mock:
            respx.get(f"{BASE_URL}/{ORG}/_apis/projects").mock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            assert await client.test_connection() is False


class TestCreateTask:
    async def test_creates_task_via_post(self, client, basic_task):
        task_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/$Task"

        with respx.mock:
            create_route = respx.post(task_url).mock(
                return_value=httpx.Response(200, json=TASK_RESPONSE)
            )
            result = await client.create_task(basic_task)

        assert create_route.called
        assert result.id == 1001
        assert result.title == "Minha Task"
        assert result.project == PROJECT
        assert result.url == TASK_RESPONSE["_links"]["html"]["href"]

    async def test_create_request_excludes_state(self, client, basic_task):
        """Na criação, o estado não deve ser enviado no POST inicial."""
        basic_task.state = "Fechado"
        task_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/$Task"
        patch_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/1001"

        with respx.mock:
            create_route = respx.post(task_url).mock(
                return_value=httpx.Response(200, json=TASK_RESPONSE)
            )
            respx.patch(patch_url).mock(return_value=httpx.Response(200, json={}))
            await client.create_task(basic_task)

        create_body = json.loads(create_route.calls[0].request.content)
        paths = [op["path"] for op in create_body]
        assert "/fields/System.State" not in paths

    async def test_patches_state_after_creation(self, client, basic_task):
        basic_task.state = "Fechado"
        task_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/$Task"
        patch_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/1001"

        with respx.mock:
            respx.post(task_url).mock(return_value=httpx.Response(200, json=TASK_RESPONSE))
            patch_route = respx.patch(patch_url).mock(return_value=httpx.Response(200, json={}))
            await client.create_task(basic_task)

        assert patch_route.called
        state_patch = json.loads(patch_route.calls[0].request.content)
        assert state_patch[0]["path"] == "/fields/System.State"
        assert state_patch[0]["value"] == "Fechado"

    async def test_does_not_patch_state_when_not_set(self, client, basic_task):
        task_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/$Task"

        with respx.mock:
            respx.post(task_url).mock(return_value=httpx.Response(200, json=TASK_RESPONSE))
            # Nenhum PATCH deve ser chamado
            await client.create_task(basic_task)

        # Se chegou aqui sem erro, nenhum PATCH foi feito (respx levanta erro em rota não mockada)

    async def test_patches_parent_relation_separately(self, client, basic_task):
        """Relação de pai deve ser enviada em PATCH separado após criação e estado."""
        basic_task.state = "Fechado"
        basic_task.parent_id = 2001

        task_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/$Task"
        patch_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/1001"

        with respx.mock:
            respx.post(task_url).mock(return_value=httpx.Response(200, json=TASK_RESPONSE))
            patch_route = respx.patch(patch_url).mock(return_value=httpx.Response(200, json={}))
            await client.create_task(basic_task)

        # Deve ter 2 PATCHes: estado + parent
        assert patch_route.call_count == 2

        # Segundo PATCH deve ser a relação de pai
        parent_patch = json.loads(patch_route.calls[1].request.content)
        assert parent_patch[0]["path"] == "/relations/-"
        assert "Hierarchy-Reverse" in parent_patch[0]["value"]["rel"]
        assert "2001" in parent_patch[0]["value"]["url"]

    async def test_parent_url_uses_rest_api_format(self, client, basic_task):
        """URL do pai deve ser no formato REST API, não vstfs."""
        basic_task.state = "Fechado"
        basic_task.parent_id = 2001

        task_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/$Task"
        patch_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/1001"

        with respx.mock:
            respx.post(task_url).mock(return_value=httpx.Response(200, json=TASK_RESPONSE))
            patch_route = respx.patch(patch_url).mock(return_value=httpx.Response(200, json={}))
            await client.create_task(basic_task)

        parent_patch = json.loads(patch_route.calls[1].request.content)
        parent_url = parent_patch[0]["value"]["url"]
        assert parent_url.startswith("https://")
        assert "vstfs" not in parent_url
        assert "_apis/wit/workitems/2001" in parent_url

    async def test_raises_on_post_failure(self, client, basic_task):
        task_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/$Task"

        with respx.mock:
            respx.post(task_url).mock(return_value=httpx.Response(401))
            with pytest.raises(httpx.HTTPStatusError):
                await client.create_task(basic_task)

    async def test_uses_default_project_when_task_project_empty(self, client):
        task = TaskConfig(
            title="Minha Task",
            project="",  # vazio — deve usar default_project
            area_path="AI",
            iteration_path="AI\\Iteration 3",
            completed_work=1.0,
        )
        task_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/$Task"

        with respx.mock:
            respx.post(task_url).mock(return_value=httpx.Response(200, json=TASK_RESPONSE))
            result = await client.create_task(task)

        assert result.project == PROJECT

    async def test_raises_value_error_when_no_project(self):
        client_no_project = AzureDevOpsClient(
            organization=ORG, pat="test-pat", base_url=BASE_URL
        )
        task = TaskConfig(
            title="Minha Task",
            project="",
            area_path="AI",
            iteration_path="AI\\Iteration 3",
            completed_work=1.0,
        )
        with pytest.raises(ValueError, match="Projeto"):
            await client_no_project.create_task(task)


class TestCreateUserStory:
    async def test_creates_user_story_via_post(self, client, basic_user_story):
        us_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/$User%20Story"

        with respx.mock:
            create_route = respx.post(us_url).mock(
                return_value=httpx.Response(200, json=US_RESPONSE)
            )
            result = await client.create_user_story(basic_user_story)

        assert create_route.called
        assert result.id == 2001
        assert result.title == "Atividades Fevereiro 2026"
        assert result.project == PROJECT

    async def test_create_excludes_state_in_post(self, client, basic_user_story):
        basic_user_story.state = "Fechado"
        us_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/$User%20Story"
        patch_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/2001"

        with respx.mock:
            create_route = respx.post(us_url).mock(
                return_value=httpx.Response(200, json=US_RESPONSE)
            )
            respx.patch(patch_url).mock(return_value=httpx.Response(200, json={}))
            await client.create_user_story(basic_user_story)

        create_body = json.loads(create_route.calls[0].request.content)
        paths = [op["path"] for op in create_body]
        assert "/fields/System.State" not in paths

    async def test_patches_state_after_creation(self, client, basic_user_story):
        basic_user_story.state = "Fechado"
        us_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/$User%20Story"
        patch_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/2001"

        with respx.mock:
            respx.post(us_url).mock(return_value=httpx.Response(200, json=US_RESPONSE))
            patch_route = respx.patch(patch_url).mock(return_value=httpx.Response(200, json={}))
            await client.create_user_story(basic_user_story)

        assert patch_route.called
        state_patch = json.loads(patch_route.calls[0].request.content)
        assert state_patch[0]["path"] == "/fields/System.State"
        assert state_patch[0]["value"] == "Fechado"

    async def test_no_state_patch_when_state_not_set(self, client, basic_user_story):
        us_url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/wit/workitems/$User%20Story"

        with respx.mock:
            respx.post(us_url).mock(return_value=httpx.Response(200, json=US_RESPONSE))
            result = await client.create_user_story(basic_user_story)

        assert result.id == 2001


class TestGetCommits:
    async def test_returns_parsed_commits(self, client):
        repo = "arrecadacao-ai"
        url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/git/repositories/{repo}/commits"

        with respx.mock:
            respx.get(url).mock(return_value=httpx.Response(200, json=COMMITS_RESPONSE))
            commits = await client.get_commits(repo)

        assert len(commits) == 2
        assert commits[0].commit_id == "abc1234567890abcdef"
        assert commits[0].message == "fix: corrige bug no modelo"
        assert commits[0].author == "user@example.com"
        assert commits[0].repository == repo

    async def test_returns_empty_list_when_no_commits(self, client):
        repo = "arrecadacao-ai"
        url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/git/repositories/{repo}/commits"

        with respx.mock:
            respx.get(url).mock(return_value=httpx.Response(200, json={"value": []}))
            commits = await client.get_commits(repo)

        assert commits == []

    async def test_commit_date_parsed_correctly(self, client):
        repo = "arrecadacao-ai"
        url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/git/repositories/{repo}/commits"

        with respx.mock:
            respx.get(url).mock(return_value=httpx.Response(200, json=COMMITS_RESPONSE))
            commits = await client.get_commits(repo)

        assert commits[0].date.year == 2026
        assert commits[0].date.month == 2
        assert commits[0].date.day == 19

    async def test_raises_when_no_project(self):
        client_no_project = AzureDevOpsClient(
            organization=ORG, pat="test-pat", base_url=BASE_URL
        )
        with pytest.raises(ValueError, match="Projeto"):
            await client_no_project.get_commits("repo")


class TestGetRepositories:
    async def test_returns_repository_list(self, client):
        url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/git/repositories"
        repos_data = {
            "value": [
                {"id": "abc", "name": "arrecadacao-ai"},
                {"id": "def", "name": "outro-repo"},
            ]
        }

        with respx.mock:
            respx.get(url).mock(return_value=httpx.Response(200, json=repos_data))
            repos = await client.get_repositories()

        assert len(repos) == 2
        assert repos[0]["name"] == "arrecadacao-ai"

    async def test_returns_empty_list_when_no_repos(self, client):
        url = f"{BASE_URL}/{ORG}/{PROJECT}/_apis/git/repositories"

        with respx.mock:
            respx.get(url).mock(return_value=httpx.Response(200, json={"value": []}))
            repos = await client.get_repositories()

        assert repos == []
