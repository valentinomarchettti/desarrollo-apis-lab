from types import SimpleNamespace

import pytest
from django.urls import reverse
from rest_framework import status


class FakeResponse:
    def __init__(self, status_code, data=None, text=""):
        self.status_code = status_code
        self._data = data
        self.text = text

    def json(self):
        if self._data is None:
            raise ValueError("Invalid JSON")
        return self._data


def summary_url(method_number=123):
    return reverse(
        "github-pull-request-summary",
        kwargs={"owner": "usuario", "repo": "repo", "number": method_number},
    )


def mock_token(mocker):
    return mocker.patch(
        "api.views.github_pull_request_views.get_active_github_token",
        return_value=("fake-token", None),
    )


def pull_data():
    return {
        "number": 123,
        "title": "PR con errores simulados",
        "state": "open",
        "additions": 10,
        "deletions": 3,
        "changed_files": 1,
        "created_at": "2026-06-10T10:00:00Z",
        "head": {"ref": "feature/errors"},
        "base": {"ref": "main"},
        "user": {"login": "valen"},
    }


def mock_files_and_commits(mocker):
    return mocker.patch(
        "api.views.github_pull_request_views.paginated_or_error",
        side_effect=[
            ([{"filename": "api/tests/test_summary_errors.py"}], None),
            (
                [
                    {
                        "sha": "abc123",
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


@pytest.mark.django_db
def test_summary_get_devuelve_error_si_github_no_entrega_detalle(
    authenticated_client,
    mocker,
):
    mock_token(mocker)
    mocker.patch(
        "api.views.github_pull_request_views.github_client.get_json",
        return_value=(
            SimpleNamespace(status_code=status.HTTP_404_NOT_FOUND),
            {"message": "Not Found"},
        ),
    )

    response = authenticated_client.get(summary_url())

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "GitHub no pudo devolver el detalle" in response.data["error"]
    assert response.data["github_response"]["message"] == "Not Found"


@pytest.mark.django_db
def test_summary_get_devuelve_error_si_github_no_entrega_diff(
    authenticated_client,
    mocker,
):
    mock_token(mocker)
    mocker.patch(
        "api.views.github_pull_request_views.github_client.get_json",
        return_value=(SimpleNamespace(status_code=200), pull_data()),
    )
    mock_files_and_commits(mocker)
    mocker.patch(
        "api.views.github_pull_request_views.github_client.get_diff",
        return_value=(
            FakeResponse(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"message": "Diff unavailable"},
            ),
            "",
        ),
    )

    response = authenticated_client.get(summary_url())

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert "GitHub no pudo devolver el diff" in response.data["error"]
    assert response.data["github_response"]["message"] == "Diff unavailable"


@pytest.mark.django_db
def test_summary_get_devuelve_error_si_gemini_no_genera_resumen(
    authenticated_client,
    mocker,
):
    mock_token(mocker)
    mocker.patch(
        "api.views.github_pull_request_views.github_client.get_json",
        return_value=(SimpleNamespace(status_code=200), pull_data()),
    )
    mock_files_and_commits(mocker)
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
        return_value=("", "Gemini no disponible"),
    )

    response = authenticated_client.get(summary_url())

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert "Gemini" in response.data["error"]
    assert response.data["detail"] == "Gemini no disponible"


@pytest.mark.django_db
def test_summary_post_devuelve_error_si_github_no_publica_descripcion(
    authenticated_client,
    mocker,
):
    mock_token(mocker)
    mocker.patch(
        "api.views.github_pull_request_views.github_client.get_json",
        return_value=(SimpleNamespace(status_code=200), pull_data()),
    )
    mock_files_and_commits(mocker)
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
        return_value=("Resumen generado", None),
    )
    mocker.patch(
        "api.views.github_pull_request_views.github_client.patch_json",
        return_value=(
            SimpleNamespace(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR),
            {"message": "Cannot update PR"},
        ),
    )

    response = authenticated_client.post(summary_url())

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert "GitHub no pudo actualizar" in response.data["error"]
    assert response.data["github_response"]["message"] == "Cannot update PR"


@pytest.mark.django_db
def test_summary_post_informa_si_publica_en_github_pero_falla_persistencia_local(
    authenticated_client,
    mocker,
):
    mock_token(mocker)
    mocker.patch(
        "api.views.github_pull_request_views.github_client.get_json",
        return_value=(SimpleNamespace(status_code=200), pull_data()),
    )
    mock_files_and_commits(mocker)
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
        return_value=("Resumen generado", None),
    )
    mocker.patch(
        "api.views.github_pull_request_views.github_client.patch_json",
        return_value=(
            SimpleNamespace(status_code=200),
            {
                "id": 999,
                "number": 123,
                "title": "PR con persistencia fallida",
                "body": "Resumen generado",
                "html_url": "https://github.com/usuario/repo/pull/123",
                "updated_at": "2026-06-12T10:00:00Z",
            },
        ),
    )
    mocker.patch(
        "api.views.github_pull_request_views.save_generated_summary",
        side_effect=Exception("DB no disponible"),
    )

    response = authenticated_client.post(summary_url())

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "no se pudo guardar el resumen" in response.data["error"]
    assert response.data["descripcion_actualizada_en_github"] is True
    assert response.data["github_response"]["body"] == "Resumen generado"
