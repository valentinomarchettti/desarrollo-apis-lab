from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from rest_framework import status


@pytest.fixture
def plain_user(db):
    return User.objects.create_user(
        username="usuario_sin_permisos",
        password="password",
    )


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


@pytest.mark.django_db
def test_pull_request_list_requiere_autenticacion(api_client):
    response = api_client.get(reverse("pull-request-list"))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_pull_request_list_rechaza_usuario_sin_permiso(api_client, plain_user):
    client = authenticate(api_client, plain_user)

    response = client.get(reverse("pull-request-list"))

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "No tenes permiso" in str(response.data["detail"])


@pytest.mark.django_db
def test_pull_request_list_permite_usuario_con_permiso_de_lectura(
    api_client,
    user_with_permissions,
    pr_base,
):
    user = user_with_permissions("auditor", "view_pullrequest")
    client = authenticate(api_client, user)

    response = client.get(reverse("pull-request-list"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == pr_base.id


@pytest.mark.django_db
def test_pull_request_create_rechaza_usuario_con_solo_permiso_de_lectura(
    api_client,
    user_with_permissions,
    repo_base,
):
    user = user_with_permissions("auditor", "view_pullrequest")
    client = authenticate(api_client, user)
    data = {
        "repositorio": repo_base.id,
        "numero": 456,
        "titulo": "PR sin permiso de creacion",
        "estado": "open",
    }

    response = client.post(reverse("pull-request-list"), data, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "crear pull requests" in str(response.data["detail"])


@pytest.mark.django_db
def test_pull_request_create_permite_usuario_con_permiso_de_creacion(
    api_client,
    user_with_permissions,
    repo_base,
):
    user = user_with_permissions("administrador", "add_pullrequest")
    client = authenticate(api_client, user)
    data = {
        "repositorio": repo_base.id,
        "numero": 456,
        "titulo": "PR con permiso de creacion",
        "estado": "open",
        "url": "https://github.com/usuario/repo/pull/456",
    }

    response = client.post(reverse("pull-request-list"), data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["titulo"] == "PR con permiso de creacion"


@pytest.mark.django_db
def test_summary_endpoint_rechaza_usuario_sin_permiso_de_generacion(
    api_client,
    plain_user,
):
    client = authenticate(api_client, plain_user)
    url = reverse(
        "github-pull-request-summary",
        kwargs={"owner": "usuario", "repo": "repo", "number": 123},
    )

    response = client.get(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "generar summaries tecnicos" in str(response.data["detail"])


@pytest.mark.django_db
def test_summary_endpoint_permite_usuario_con_permiso_de_generacion(
    api_client,
    user_with_permissions,
    mocker,
):
    user = user_with_permissions("reviewer", "generate_summary")
    client = authenticate(api_client, user)
    mocker.patch(
        "api.views.github_pull_request_views.get_active_github_token",
        return_value=("fake-token", None),
    )
    mocker.patch(
        "api.views.github_pull_request_views.github_client.get_json",
        return_value=(
            SimpleNamespace(status_code=200),
            {
                "number": 123,
                "title": "PR autorizado",
                "additions": 3,
                "deletions": 1,
                "changed_files": 1,
                "created_at": "2026-06-10T10:00:00Z",
                "head": {"ref": "feature/testing"},
                "base": {"ref": "main"},
                "user": {"login": "valen"},
            },
        ),
    )
    mocker.patch(
        "api.views.github_pull_request_views.paginated_or_error",
        side_effect=[
            ([{"filename": "api/tests/test_permissions.py"}], None),
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
        return_value=("Resumen autorizado", None),
    )
    url = reverse(
        "github-pull-request-summary",
        kwargs={"owner": "usuario", "repo": "repo", "number": 123},
    )

    response = client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["summary_tecnico_ia"] == "Resumen autorizado"
