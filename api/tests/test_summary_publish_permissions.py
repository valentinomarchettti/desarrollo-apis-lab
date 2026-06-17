from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from rest_framework import status


@pytest.fixture
def user_with_permissions(db):
    def _build_user(username, *permission_codenames):
        user = User.objects.create_user(username=username, password="password")
        permissions = Permission.objects.filter(
            content_type__app_label="api",
            codename__in=permission_codenames,
        )
        user.user_permissions.set(permissions)
        return user

    return _build_user


def authenticate(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


def summary_url():
    return reverse(
        "github-pull-request-summary",
        kwargs={"owner": "usuario", "repo": "repo", "number": 123},
    )


@pytest.mark.django_db
def test_summary_post_rechaza_usuario_sin_permiso_de_publicacion(
    api_client,
    user_with_permissions,
):
    user = user_with_permissions("reviewer_solo_genera", "generate_summary")
    client = authenticate(api_client, user)

    response = client.post(summary_url())

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "publicar summaries en GitHub" in str(response.data["detail"])


@pytest.mark.django_db
def test_summary_post_permite_usuario_con_permiso_de_publicacion(
    api_client,
    user_with_permissions,
    mocker,
):
    user = user_with_permissions("reviewer_publica", "publish_summary_github")
    client = authenticate(api_client, user)
    patch_json_mock = mock_summary_post_dependencies(mocker)

    response = client.post(summary_url())

    assert response.status_code == status.HTTP_200_OK
    assert response.data["summary_tecnico_ia"] == "Resumen publicado"
    assert response.data["pull_request"]["descripcion_actualizada_en_github"] is True
    patch_json_mock.assert_called_once()


def mock_summary_post_dependencies(mocker):
    pull_data = {
        "number": 123,
        "title": "PR publicable",
        "state": "open",
        "merged_at": None,
        "additions": 5,
        "deletions": 2,
        "changed_files": 1,
        "html_url": "https://github.com/usuario/repo/pull/123",
        "created_at": "2026-06-10T10:00:00Z",
        "head": {"ref": "feature/publicar-summary"},
        "base": {
            "ref": "main",
            "repo": {
                "name": "repo",
                "html_url": "https://github.com/usuario/repo",
                "description": "Repo usado para probar permisos de publicacion",
            },
        },
        "user": {"login": "valen"},
    }
    update_data = {
        "id": 999,
        "number": 123,
        "title": "PR publicable",
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
            ([{"filename": "api/tests/test_summary_publish_permissions.py"}], None),
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
    return mocker.patch(
        "api.views.github_pull_request_views.github_client.patch_json",
        return_value=(SimpleNamespace(status_code=200), update_data),
    )
