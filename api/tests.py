from types import SimpleNamespace
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from .models import GitHubConnection, PullRequest, Repositorio, SummaryTecnico
from .views import github_connect, github_oauth_callback, github_pull_request_detail, github_pull_request_summary


def create_user_with_permissions(username, permission_codenames):
    user = User.objects.create_user(username=username, password="pass12345")
    permissions = Permission.objects.filter(
        content_type__app_label="api",
        codename__in=permission_codenames,
    )
    user.user_permissions.set(permissions)
    return user


def create_user_in_group(username, group_name):
    user = User.objects.create_user(username=username, password="pass12345")
    user.groups.add(Group.objects.get(name=group_name))
    return user


class GithubConnectionOAuthTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.github_admin = create_user_with_permissions(
            "github-admin",
            {"connect_github", "view_githubconnection"},
        )

    @override_settings(
        GITHUB_CLIENT_ID="client-id",
        GITHUB_CLIENT_SECRET="client-secret",
        GITHUB_CALLBACK_URL="http://127.0.0.1:8000/api/github/oauth/callback/",
    )
    def test_connect_redirects_to_github_authorization_url(self):
        request = self.factory.get("/api/github/connect/")
        force_authenticate(request, user=self.github_admin)

        response = github_connect(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("https://github.com/login/oauth/authorize", response["Location"])
        self.assertIn("client_id=client-id", response["Location"])
        self.assertIn("redirect_uri=http%3A%2F%2F127.0.0.1%3A8000%2Fapi%2Fgithub%2Foauth%2Fcallback%2F", response["Location"])
        self.assertIn("scope=repo+read%3Auser+user%3Aemail", response["Location"])
        self.assertIn("state=", response["Location"])

    def test_api_root_includes_github_login_link(self):
        client = APIClient()
        client.force_authenticate(user=self.github_admin)

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
        client.force_authenticate(user=self.github_admin)

        response = client.get("/api/github-connections/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["github_login"], "octocat")
        self.assertNotIn("access_token", response.data[0])


class GithubPullRequestDetailTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.github_reviewer = create_user_with_permissions(
            "github-reviewer",
            {
                "view_pullrequest",
                "generate_summary",
                "publish_summary_github",
            },
        )
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
        force_authenticate(request, user=self.github_reviewer)
        return github_pull_request_detail(request, "owner", "repo", 1)

    def _request_summary(self, method="get"):
        request_path = "/api/github/repositorios/owner/repo/pull-requests/1/summary/"
        request_method = getattr(self.factory, method)
        request = request_method(
            request_path,
            data={},
            format="json",
        )
        force_authenticate(request, user=self.github_reviewer)
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


class SeedRolesCommandTests(TestCase):
    def test_seed_roles_creates_expected_groups_and_permissions(self):
        call_command("seed_roles", stdout=StringIO())

        self.assertTrue(Group.objects.filter(name="Administrador").exists())
        self.assertTrue(Group.objects.filter(name="Reviewer").exists())
        self.assertTrue(Group.objects.filter(name="Auditor").exists())

        admin_permissions = set(
            Group.objects.get(name="Administrador").permissions.values_list("codename", flat=True)
        )
        reviewer_permissions = set(
            Group.objects.get(name="Reviewer").permissions.values_list("codename", flat=True)
        )
        auditor_permissions = set(
            Group.objects.get(name="Auditor").permissions.values_list("codename", flat=True)
        )

        self.assertIn("connect_github", admin_permissions)
        self.assertIn("generate_summary", admin_permissions)
        self.assertIn("publish_summary_github", admin_permissions)
        self.assertEqual(
            reviewer_permissions,
            {
                "view_repositorio",
                "view_pullrequest",
                "view_summarytecnico",
                "add_summarytecnico",
                "change_summarytecnico",
                "generate_summary",
                "publish_summary_github",
            },
        )
        self.assertEqual(
            auditor_permissions,
            {
                "view_repositorio",
                "view_pullrequest",
                "view_summarytecnico",
            },
        )

    def test_seed_roles_is_idempotent(self):
        call_command("seed_roles", stdout=StringIO())
        call_command("seed_roles", stdout=StringIO())

        self.assertEqual(Group.objects.filter(name="Administrador").count(), 1)
        self.assertEqual(Group.objects.filter(name="Reviewer").count(), 1)
        self.assertEqual(Group.objects.filter(name="Auditor").count(), 1)


class RolePermissionEndpointTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        self.client = APIClient()

    def test_token_endpoint_returns_jwt_pair(self):
        User.objects.create_user(username="token-user", password="pass12345")

        response = self.client.post(
            "/api/auth/token/",
            {"username": "token-user", "password": "pass12345"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_unauthenticated_user_receives_401(self):
        response = self.client.get("/api/repositorios/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_without_model_permission_gets_descriptive_message(self):
        user = User.objects.create_user(username="without-permissions", password="pass12345")
        self.client.force_authenticate(user=user)

        response = self.client.get("/api/summaries/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            str(response.data["detail"]),
            "No tenes permiso para ver summaries tecnicos. "
            "Necesitas el rol Administrador, Reviewer o Auditor.",
        )
        self.assertNotIn("api.view_summarytecnico", str(response.data["detail"]))

    def test_github_connection_permission_message_uses_roles(self):
        reviewer = create_user_in_group("connection-reviewer", "Reviewer")
        self.client.force_authenticate(user=reviewer)

        response = self.client.get("/api/github-connections/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            str(response.data["detail"]),
            "No tenes permiso para ver las conexiones de GitHub. "
            "Necesitas el rol Administrador.",
        )
        self.assertNotIn("api.view_githubconnection", str(response.data["detail"]))
        self.assertNotIn("git hub connections", str(response.data["detail"]).lower())

    def test_auditor_can_read_summaries_but_cannot_publish(self):
        auditor = create_user_in_group("auditor", "Auditor")
        self.client.force_authenticate(user=auditor)

        read_response = self.client.get("/api/summaries/")
        publish_response = self.client.post(
            "/api/github/repositorios/owner/repo/pull-requests/1/summary/",
            {},
            format="json",
        )

        self.assertEqual(read_response.status_code, status.HTTP_200_OK)
        self.assertEqual(publish_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn(
            "No tenes permiso para publicar summaries en GitHub",
            str(publish_response.data["detail"]),
        )
        self.assertIn("Necesitas el rol Administrador o Reviewer", str(publish_response.data["detail"]))
        self.assertNotIn("api.publish_summary_github", str(publish_response.data["detail"]))

    def test_reviewer_can_publish_summary_but_cannot_connect_github(self):
        reviewer = create_user_in_group("reviewer", "Reviewer")
        self.client.force_authenticate(user=reviewer)
        GitHubConnection.objects.create(
            github_user_id=123,
            github_login="octocat",
            html_url="https://github.com/octocat",
            access_token="github-token",
            token_type="bearer",
            scope="repo read:user user:email",
        )
        ok_response = SimpleNamespace(status_code=200)
        pull_data = {
            "number": 1,
            "title": "Test PR",
            "state": "open",
            "merged_at": None,
            "head": {"ref": "feature"},
            "base": {
                "ref": "main",
                "repo": {
                    "name": "repo",
                    "html_url": "https://github.com/owner/repo",
                    "description": "Repository description",
                },
            },
            "user": {"login": "octocat"},
            "html_url": "https://github.com/owner/repo/pull/1",
        }
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
        ):
            publish_response = self.client.post(
                "/api/github/repositorios/owner/repo/pull-requests/1/summary/",
                {},
                format="json",
            )
        connect_response = self.client.get("/api/github/connect/")

        self.assertEqual(publish_response.status_code, status.HTTP_200_OK)
        self.assertTrue(publish_response.data["pull_request"]["descripcion_actualizada_en_github"])
        self.assertEqual(connect_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn(
            "No tenes permiso para conectar GitHub",
            str(connect_response.data["detail"]),
        )
        self.assertIn("Necesitas el rol Administrador", str(connect_response.data["detail"]))
        self.assertNotIn("api.connect_github", str(connect_response.data["detail"]))

    @override_settings(
        GITHUB_CLIENT_ID="client-id",
        GITHUB_CLIENT_SECRET="client-secret",
        GITHUB_CALLBACK_URL="http://127.0.0.1:8000/api/github/oauth/callback/",
    )
    def test_admin_can_connect_github(self):
        admin = create_user_in_group("admin", "Administrador")
        self.client.force_authenticate(user=admin)

        response = self.client.get("/api/github/connect/")

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("https://github.com/login/oauth/authorize", response["Location"])
