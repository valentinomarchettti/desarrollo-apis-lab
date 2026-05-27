from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient, APIRequestFactory

from .models import GitHubConnection, PullRequest, Repositorio, SummaryTecnico
from .views import github_connect, github_oauth_callback, github_pull_request_detail, github_pull_request_summary


class GithubConnectionOAuthTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    @override_settings(
        GITHUB_CLIENT_ID="client-id",
        GITHUB_CLIENT_SECRET="client-secret",
        GITHUB_CALLBACK_URL="http://127.0.0.1:8000/api/github/oauth/callback/",
    )
    def test_connect_redirects_to_github_authorization_url(self):
        request = self.factory.get("/api/github/connect/")

        response = github_connect(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("https://github.com/login/oauth/authorize", response["Location"])
        self.assertIn("client_id=client-id", response["Location"])
        self.assertIn("redirect_uri=http%3A%2F%2F127.0.0.1%3A8000%2Fapi%2Fgithub%2Foauth%2Fcallback%2F", response["Location"])
        self.assertIn("scope=repo+read%3Auser+user%3Aemail", response["Location"])
        self.assertIn("state=", response["Location"])

    def test_api_root_includes_github_login_link(self):
        client = APIClient()

        response = client.get("/api/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("github-login", response.data)
        self.assertTrue(response.data["github-login"].endswith("/api/github/connect/"))

    @override_settings(
        GITHUB_CLIENT_ID="client-id",
        GITHUB_CLIENT_SECRET="client-secret",
        GITHUB_CALLBACK_URL="http://127.0.0.1:8000/api/github/oauth/callback/",
    )
    def test_callback_creates_active_connection_without_exposing_token(self):
        cache.set("github_oauth_state:state-ok", True, timeout=600)
        request = self.factory.get(
            "/api/github/oauth/callback/",
            {"code": "code-ok", "state": "state-ok"},
        )
        token_response = SimpleNamespace(
            json=lambda: {
                "access_token": "new-token",
                "token_type": "bearer",
                "scope": "repo,read:user,user:email",
            }
        )
        user_response = SimpleNamespace(
            json=lambda: {
                "id": 123,
                "login": "octocat",
                "html_url": "https://github.com/octocat",
            },
            raise_for_status=lambda: None,
        )

        with (
            patch("api.views.requests.post", return_value=token_response),
            patch("api.views.requests.get", return_value=user_response),
        ):
            response = github_oauth_callback(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["connected"])
        self.assertNotIn("access_token", response.data)

        connection = GitHubConnection.objects.get()
        self.assertTrue(connection.activo)
        self.assertEqual(connection.github_user_id, 123)
        self.assertEqual(connection.github_login, "octocat")
        self.assertEqual(connection.access_token, "new-token")

    @override_settings(
        GITHUB_CLIENT_ID="client-id",
        GITHUB_CLIENT_SECRET="client-secret",
        GITHUB_CALLBACK_URL="http://127.0.0.1:8000/api/github/oauth/callback/",
    )
    def test_callback_reconnect_deactivates_previous_connection(self):
        previous = GitHubConnection.objects.create(
            github_user_id=99,
            github_login="previous",
            access_token="old-token",
        )
        cache.set("github_oauth_state:state-ok", True, timeout=600)
        request = self.factory.get(
            "/api/github/oauth/callback/",
            {"code": "code-ok", "state": "state-ok"},
        )
        token_response = SimpleNamespace(
            json=lambda: {
                "access_token": "new-token",
                "token_type": "bearer",
                "scope": "repo",
            }
        )
        user_response = SimpleNamespace(
            json=lambda: {
                "id": 123,
                "login": "octocat",
                "html_url": "https://github.com/octocat",
            },
            raise_for_status=lambda: None,
        )

        with (
            patch("api.views.requests.post", return_value=token_response),
            patch("api.views.requests.get", return_value=user_response),
        ):
            response = github_oauth_callback(request)

        self.assertEqual(response.status_code, 200)
        previous.refresh_from_db()
        self.assertFalse(previous.activo)
        self.assertTrue(GitHubConnection.objects.get(github_user_id=123).activo)

    def test_github_connection_viewset_does_not_return_access_token(self):
        GitHubConnection.objects.create(
            github_user_id=123,
            github_login="octocat",
            html_url="https://github.com/octocat",
            access_token="secret-token",
            token_type="bearer",
            scope="repo",
        )
        client = APIClient()

        response = client.get("/api/github-connections/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["github_login"], "octocat")
        self.assertNotIn("access_token", response.data[0])


class GithubPullRequestDetailTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.connection = GitHubConnection.objects.create(
            github_user_id=123,
            github_login="octocat",
            html_url="https://github.com/octocat",
            access_token="github-token",
            token_type="bearer",
            scope="repo read:user user:email",
        )

    def _request_detail(self):
        request = self.factory.get(
            "/api/github/repositorios/owner/repo/pull-requests/1/",
        )
        return github_pull_request_detail(request, "owner", "repo", 1)

    def _request_summary(self, method="get"):
        request_path = "/api/github/repositorios/owner/repo/pull-requests/1/summary/"
        request_method = getattr(self.factory, method)
        request = request_method(
            request_path,
            data={},
            format="json",
        )
        return github_pull_request_summary(request, "owner", "repo", 1)

    def _github_pull_data(self, merged_at=None, state="open"):
        return {
            "id": 123,
            "number": 1,
            "title": "Test PR",
            "body": "PR body",
            "state": state,
            "merged_at": merged_at,
            "draft": False,
            "user": {"login": "octocat"},
            "html_url": "https://github.com/owner/repo/pull/1",
            "head": {"ref": "feature"},
            "base": {
                "ref": "main",
                "repo": {
                    "name": "repo",
                    "html_url": "https://github.com/owner/repo",
                    "description": "Repository description",
                },
            },
            "created_at": "2026-05-01T00:00:00Z",
            "updated_at": "2026-05-01T00:00:00Z",
            "closed_at": None,
            "mergeable": True,
            "merged": bool(merged_at),
            "commits": 1,
            "changed_files": 1,
            "additions": 2,
            "deletions": 1,
            "labels": [],
            "assignees": [],
            "requested_reviewers": [],
        }

    def _mock_github(self, merged_at=None, state="open"):
        ok_response = SimpleNamespace(status_code=200)
        pull_data = self._github_pull_data(merged_at=merged_at, state=state)

        return {
            "json": patch("api.views._github_get_json", return_value=(ok_response, pull_data)),
            "paginated": patch(
                "api.views._github_get_paginated_json",
                side_effect=[
                    ([], None, None),
                    ([], None, None),
                    ([], None, None),
                    ([], None, None),
                    ([], None, None),
                ],
            ),
            "diff": patch("api.views._github_get_diff", return_value=(ok_response, "diff text")),
        }

    def test_detail_without_active_connection_returns_401(self):
        GitHubConnection.objects.all().delete()

        response = self._request_detail()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"], "No hay una cuenta de GitHub conectada.")

    def test_detail_without_local_repository_returns_pr_state(self):
        mocks = self._mock_github(state="closed")

        with mocks["json"], mocks["paginated"], mocks["diff"]:
            response = self._request_detail()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["repositorio"]["linkeado_a_api"])
        self.assertEqual(response.data["pull_request"]["estado"], "closed")
        self.assertFalse(response.data["pull_request"]["guardado_en_api"])
        self.assertIn("No se gener", response.data["summary_tecnico_ia"])
        self.assertEqual(PullRequest.objects.count(), 0)
        self.assertEqual(SummaryTecnico.objects.count(), 0)

    def test_detail_with_local_repository_generates_summary(self):
        Repositorio.objects.create(
            nombre="repo",
            github_owner="owner",
            github_repo="repo",
            url="https://github.com/owner/repo",
        )
        mocks = self._mock_github(merged_at="2026-05-02T00:00:00Z", state="closed")

        with (
            mocks["json"],
            mocks["paginated"],
            mocks["diff"],
            patch("api.views.generar_descripcion_ia", return_value=("Generated summary", None)),
        ):
            response = self._request_detail()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["repositorio"]["linkeado_a_api"])
        self.assertEqual(response.data["pull_request"]["estado"], "merged")
        self.assertEqual(response.data["summary_tecnico_ia"], "Generated summary")
        self.assertEqual(PullRequest.objects.count(), 1)
        self.assertEqual(SummaryTecnico.objects.count(), 1)

    def test_summary_endpoint_generates_summary_without_persisting_data(self):
        ok_response = SimpleNamespace(status_code=200)

        with (
            patch("api.views._github_get_diff", return_value=(ok_response, "diff text")),
            patch("api.views.generar_descripcion_ia", return_value=("Generated summary", None)),
        ):
            response = self._request_summary()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["repositorio"]["owner"], "owner")
        self.assertEqual(response.data["repositorio"]["repo"], "repo")
        self.assertEqual(response.data["pull_request"]["numero"], 1)
        self.assertEqual(response.data["summary_tecnico_ia"], "Generated summary")
        self.assertEqual(Repositorio.objects.count(), 0)
        self.assertEqual(PullRequest.objects.count(), 0)
        self.assertEqual(SummaryTecnico.objects.count(), 0)

    def test_summary_post_updates_github_pull_request_description(self):
        ok_response = SimpleNamespace(status_code=200)
        pull_data = self._github_pull_data()
        updated_pull_request = {
            "id": 123,
            "number": 1,
            "title": "Test PR",
            "body": "Generated summary",
            "html_url": "https://github.com/owner/repo/pull/1",
            "updated_at": "2026-05-01T00:05:00Z",
        }

        with (
            patch("api.views._github_get_diff", return_value=(ok_response, "diff text")),
            patch("api.views._github_get_json", return_value=(ok_response, pull_data)),
            patch("api.views.generar_descripcion_ia", return_value=("Generated summary", None)),
            patch(
                "api.views._github_patch_json",
                return_value=(ok_response, updated_pull_request),
            ) as github_patch,
        ):
            response = self._request_summary(method="post")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary_tecnico_ia"], "Generated summary")
        self.assertTrue(response.data["pull_request"]["descripcion_actualizada_en_github"])
        self.assertEqual(response.data["repositorio"]["repositorio_api_id"], 1)
        self.assertEqual(response.data["pull_request"]["pull_request_api_id"], 1)
        self.assertEqual(response.data["summary_tecnico_api_id"], 1)
        self.assertEqual(response.data["github_response"]["body"], "Generated summary")
        github_patch.assert_called_once_with(
            "github-token",
            "https://api.github.com/repos/owner/repo/pulls/1",
            {"body": "Generated summary"},
        )

        repository = Repositorio.objects.get()
        pull_request = PullRequest.objects.get()
        summary = SummaryTecnico.objects.get()

        self.assertEqual(repository.github_owner, "owner")
        self.assertEqual(repository.github_repo, "repo")
        self.assertEqual(repository.url, "https://github.com/owner/repo")
        self.assertEqual(pull_request.repositorio, repository)
        self.assertEqual(pull_request.numero, 1)
        self.assertEqual(pull_request.titulo, "Test PR")
        self.assertEqual(pull_request.estado, "open")
        self.assertEqual(pull_request.rama_origen, "feature")
        self.assertEqual(pull_request.rama_destino, "main")
        self.assertEqual(summary.pull_request, pull_request)
        self.assertEqual(summary.contenido, "Generated summary")
        self.assertEqual(summary.estado, SummaryTecnico.ESTADO_GENERATED)

    def test_summary_post_reuses_repository_and_pr_creating_summary_history(self):
        ok_response = SimpleNamespace(status_code=200)
        pull_data = self._github_pull_data(merged_at="2026-05-02T00:00:00Z", state="closed")
        updated_pull_request = {
            "id": 123,
            "number": 1,
            "title": "Test PR",
            "body": "Generated summary",
            "html_url": "https://github.com/owner/repo/pull/1",
            "updated_at": "2026-05-01T00:05:00Z",
        }
        repository = Repositorio.objects.create(
            nombre="repo",
            github_owner="owner",
            github_repo="repo",
            url="https://github.com/owner/repo",
        )
        pull_request = PullRequest.objects.create(
            repositorio=repository,
            numero=1,
            titulo="Old title",
            estado=PullRequest.ESTADO_OPEN,
        )
        SummaryTecnico.objects.create(
            pull_request=pull_request,
            contenido="Previous summary",
            estado=SummaryTecnico.ESTADO_GENERATED,
        )

        with (
            patch("api.views._github_get_diff", return_value=(ok_response, "diff text")),
            patch("api.views._github_get_json", return_value=(ok_response, pull_data)),
            patch("api.views.generar_descripcion_ia", return_value=("Generated summary", None)),
            patch("api.views._github_patch_json", return_value=(ok_response, updated_pull_request)),
        ):
            response = self._request_summary(method="post")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Repositorio.objects.count(), 1)
        self.assertEqual(PullRequest.objects.count(), 1)
        self.assertEqual(SummaryTecnico.objects.count(), 2)

        pull_request.refresh_from_db()
        summaries = SummaryTecnico.objects.order_by("id")

        self.assertEqual(pull_request.titulo, "Test PR")
        self.assertEqual(pull_request.estado, PullRequest.ESTADO_MERGED)
        self.assertEqual(summaries[0].contenido, "Previous summary")
        self.assertEqual(summaries[1].contenido, "Generated summary")

    def test_summary_post_returns_github_error_when_description_update_fails(self):
        ok_response = SimpleNamespace(status_code=200)
        error_response = SimpleNamespace(status_code=403)
        pull_data = self._github_pull_data()

        with (
            patch("api.views._github_get_diff", return_value=(ok_response, "diff text")),
            patch("api.views._github_get_json", return_value=(ok_response, pull_data)),
            patch("api.views.generar_descripcion_ia", return_value=("Generated summary", None)),
            patch(
                "api.views._github_patch_json",
                return_value=(error_response, {"message": "Forbidden"}),
            ),
        ):
            response = self._request_summary(method="post")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["error"],
            "GitHub no pudo actualizar la descripcion del pull request.",
        )
        self.assertEqual(response.data["github_response"], {"message": "Forbidden"})
        self.assertEqual(Repositorio.objects.count(), 0)
        self.assertEqual(PullRequest.objects.count(), 0)
        self.assertEqual(SummaryTecnico.objects.count(), 0)

    def test_summary_post_reports_error_when_local_persistence_fails_after_github_update(self):
        ok_response = SimpleNamespace(status_code=200)
        pull_data = self._github_pull_data()
        updated_pull_request = {
            "id": 123,
            "number": 1,
            "title": "Test PR",
            "body": "Generated summary",
            "html_url": "https://github.com/owner/repo/pull/1",
            "updated_at": "2026-05-01T00:05:00Z",
        }

        with (
            patch("api.views._github_get_diff", return_value=(ok_response, "diff text")),
            patch("api.views._github_get_json", return_value=(ok_response, pull_data)),
            patch("api.views.generar_descripcion_ia", return_value=("Generated summary", None)),
            patch("api.views._github_patch_json", return_value=(ok_response, updated_pull_request)),
            patch("api.views._save_generated_summary", side_effect=Exception("db error")),
        ):
            response = self._request_summary(method="post")

        self.assertEqual(response.status_code, 500)
        self.assertTrue(response.data["descripcion_actualizada_en_github"])
        self.assertEqual(
            response.data["error"],
            "GitHub actualizo la descripcion del pull request, pero no se pudo guardar el summary en la API.",
        )
        self.assertEqual(response.data["github_response"]["body"], "Generated summary")
        self.assertEqual(Repositorio.objects.count(), 0)
        self.assertEqual(PullRequest.objects.count(), 0)
        self.assertEqual(SummaryTecnico.objects.count(), 0)
