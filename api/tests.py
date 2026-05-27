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

    def _request_summary(self):
        request = self.factory.get(
            "/api/github/repositorios/owner/repo/pull-requests/1/summary/",
            HTTP_AUTHORIZATION="Bearer github-token",
        )
        return github_pull_request_summary(request, "owner", "repo", 1)

    def _mock_github(self, merged_at=None, state="open"):
        ok_response = SimpleNamespace(status_code=200)
        pull_data = {
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
            "base": {"ref": "main"},
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
