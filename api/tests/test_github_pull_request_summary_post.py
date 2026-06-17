from types import SimpleNamespace

import pytest
from django.urls import reverse

from api.models import PullRequest, Repositorio, SummaryTecnico


@pytest.mark.django_db
def test_summary_endpoint_post_publica_en_github_y_guarda_registros_locales(
    authenticated_client,
    mocker,
):
    pull_data = {
        "id": 999,
        "number": 123,
        "title": "Agregar persistencia de summary",
        "state": "open",
        "merged_at": None,
        "additions": 25,
        "deletions": 7,
        "changed_files": 2,
        "html_url": "https://github.com/usuario/repo/pull/123",
        "created_at": "2026-06-10T10:00:00Z",
        "head": {"ref": "feature/summary-post"},
        "base": {
            "ref": "main",
            "repo": {
                "name": "repo",
                "html_url": "https://github.com/usuario/repo",
                "description": "Repositorio usado para probar summary POST",
            },
        },
        "user": {
            "id": 1,
            "login": "valen",
            "html_url": "https://github.com/valen",
        },
    }
    update_data = {
        "id": 999,
        "number": 123,
        "title": "Agregar persistencia de summary",
        "body": "Resumen publicado",
        "html_url": "https://github.com/usuario/repo/pull/123",
        "updated_at": "2026-06-12T10:00:00Z",
    }
    mocker.patch(
        "api.views.github_pull_request_views.get_active_github_token",
        return_value=("fake-token", None),
    )
    mocker.patch(
        "api.views.github_pull_request_views.github_client.get_json",
        return_value=(SimpleNamespace(status_code=200), pull_data),
    )
    mocker.patch(
        "api.views.github_pull_request_views.paginated_or_error",
        side_effect=[
            (
                [
                    {
                        "filename": "api/services/github_persistence.py",
                        "additions": 20,
                        "deletions": 5,
                    },
                    {
                        "filename": "api/tests/test_github_pull_request_summary_post.py",
                        "additions": 5,
                        "deletions": 2,
                    },
                ],
                None,
            ),
            (
                [
                    {
                        "sha": "abc123",
                        "author": {
                            "login": "valen",
                            "html_url": "https://github.com/valen",
                        },
                        "commit": {
                            "author": {
                                "name": "Valentino",
                                "email": "valen@test.com",
                                "date": "2026-06-10T10:00:00Z",
                            },
                        },
                    },
                ],
                None,
            ),
        ],
    )
    mocker.patch(
        "api.views.github_pull_request_views.github_client.get_diff",
        return_value=(SimpleNamespace(status_code=200), "diff --git fake"),
    )
    mocker.patch(
        "api.views.github_pull_request_views._fetch_commit_details",
        return_value=[],
    )
    mocker.patch(
        "api.views.github_pull_request_views.generar_descripcion_ia",
        return_value=("Resumen publicado", None),
    )
    patch_json_mock = mocker.patch(
        "api.views.github_pull_request_views.github_client.patch_json",
        return_value=(SimpleNamespace(status_code=200), update_data),
    )

    url = reverse(
        "github-pull-request-summary",
        kwargs={"owner": "usuario", "repo": "repo", "number": 123},
    )
    response = authenticated_client.post(url)

    assert response.status_code == 200
    assert response.data["summary_tecnico_ia"] == "Resumen publicado"
    assert response.data["pull_request"]["descripcion_actualizada_en_github"] is True
    assert response.data["github_response"]["body"] == "Resumen publicado"

    repository = Repositorio.objects.get(github_owner="usuario", github_repo="repo")
    pull_request = PullRequest.objects.get(repositorio=repository, numero=123)
    summary = SummaryTecnico.objects.get(pull_request=pull_request)

    assert repository.nombre == "repo"
    assert repository.url == "https://github.com/usuario/repo"
    assert pull_request.titulo == "Agregar persistencia de summary"
    assert pull_request.estado == PullRequest.ESTADO_OPEN
    assert pull_request.rama_origen == "feature/summary-post"
    assert pull_request.rama_destino == "main"
    assert pull_request.autor_github == "valen"
    assert pull_request.url == "https://github.com/usuario/repo/pull/123"
    assert summary.contenido == "Resumen publicado"
    assert summary.estado == SummaryTecnico.ESTADO_GENERATED
    assert response.data["repositorio"]["repositorio_api_id"] == repository.id
    assert response.data["pull_request"]["pull_request_api_id"] == pull_request.id
    assert response.data["summary_tecnico_api_id"] == summary.id

    patch_json_mock.assert_called_once()
    access_token, pull_detail_url, payload = patch_json_mock.call_args.args
    assert access_token == "fake-token"
    assert pull_detail_url.endswith("/repos/usuario/repo/pulls/123")
    assert payload == {"body": "Resumen publicado"}
