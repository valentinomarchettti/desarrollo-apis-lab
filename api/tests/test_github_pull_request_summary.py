from types import SimpleNamespace

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_summary_endpoint_calcula_metricas_con_respuestas_externas_mockeadas(
    authenticated_client,
    mocker,
):
    mocker.patch(
        "api.views.github_pull_request_views.get_active_github_token",
        return_value=("fake-token", None),
    )
    get_json_mock = mocker.patch(
        "api.views.github_pull_request_views.github_client.get_json",
        return_value=(
            SimpleNamespace(status_code=200),
            {
                "id": 999,
                "number": 123,
                "title": "Agregar tests de summary",
                "additions": 15,
                "deletions": 4,
                "changed_files": 2,
                "created_at": "2026-06-10T10:00:00Z",
                "head": {"ref": "feature/testing"},
                "base": {"ref": "main"},
                "user": {
                    "id": 1,
                    "login": "valen",
                    "html_url": "https://github.com/valen",
                },
            },
        ),
    )
    paginated_mock = mocker.patch(
        "api.views.github_pull_request_views.paginated_or_error",
        side_effect=[
            (
                [
                    {
                        "filename": "api/views/github_pull_request_views.py",
                        "additions": 10,
                        "deletions": 3,
                    },
                    {
                        "filename": "api/tests/test_github_pull_request_summary.py",
                        "additions": 5,
                        "deletions": 1,
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
    get_diff_mock = mocker.patch(
        "api.views.github_pull_request_views.github_client.get_diff",
        return_value=(SimpleNamespace(status_code=200), "diff --git fake"),
    )
    mocker.patch(
        "api.views.github_pull_request_views._fetch_commit_details",
        return_value=[
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
                "files": [
                    {"filename": "api/tests/test_github_pull_request_summary.py"},
                ],
            },
        ],
    )
    generar_descripcion_mock = mocker.patch(
        "api.views.github_pull_request_views.generar_descripcion_ia",
        return_value=("Resumen tecnico generado", None),
    )

    url = reverse(
        "github-pull-request-summary",
        kwargs={"owner": "usuario", "repo": "repo", "number": 123},
    )
    response = authenticated_client.get(url)

    assert response.status_code == 200
    assert response.data["summary_tecnico_ia"] == "Resumen tecnico generado"
    assert response.data["repositorio"] == {
        "owner": "usuario",
        "repo": "repo",
    }
    assert response.data["pull_request"]["numero"] == 123

    metricas = response.data["metricas_pr"]
    assert metricas["ramas"] == {
        "origen": "feature/testing",
        "destino": "main",
    }
    assert metricas["archivos"]["total_modificados"] == 2
    assert metricas["archivos"]["tests_modificados"] == 1
    assert metricas["archivos"]["archivos_test"] == [
        "api/tests/test_github_pull_request_summary.py"
    ]
    assert metricas["lineas"] == {
        "agregadas": 15,
        "eliminadas": 4,
        "balance_neto": 11,
    }
    assert metricas["actividad"]["primer_commit"] == "2026-06-10"
    assert metricas["actividad"]["ultimo_commit"] == "2026-06-10"
    assert metricas["actividad"]["dias_calendario"] == 1
    assert metricas["autoria"]["autor_pr"]["github_login"] == "valen"
    assert metricas["autoria"]["autores_tests"][0]["github_login"] == "valen"

    get_json_mock.assert_called_once()
    assert paginated_mock.call_count == 2
    get_diff_mock.assert_called_once()
    generar_descripcion_mock.assert_called_once_with("diff --git fake", metricas)
