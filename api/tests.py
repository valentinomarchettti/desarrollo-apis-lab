from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from .models import PullRequest, Repositorio, SummaryTecnico
from .views import github_pull_request_detail, github_pull_request_summary


class GithubPullRequestDetailTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def _request_detail(self):
        request = self.factory.get(
            "/api/github/repositorios/owner/repo/pull-requests/1/",
            HTTP_AUTHORIZATION="Bearer github-token",
        )
        return github_pull_request_detail(request, "owner", "repo", 1)

    def _request_summary(self, method="get"):
        request_path = "/api/github/repositorios/owner/repo/pull-requests/1/summary/"
        request_method = getattr(self.factory, method)
        request = request_method(
            request_path,
            data={},
            format="json",
            HTTP_AUTHORIZATION="Bearer github-token",
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
