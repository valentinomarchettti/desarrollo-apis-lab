import pytest
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from api.models import Repositorio

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def user(db):
    # Creamos un usuario que es superusuario para saltar permisos de DRF
    return User.objects.create_superuser(username="admin", password="password", email="admin@test.com")

@pytest.fixture
def authenticated_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client

@pytest.fixture
def repo_base(db):
    # Creamos un repositorio necesario para relacionar el Pull Request
    return Repositorio.objects.create(
        nombre="Repo Test",
        github_owner="usuario",
        github_repo="repo",
        url="https://github.com/usuario/repo",
    )

@pytest.fixture
def pr_base(db, repo_base):
    from api.models import PullRequest
    return PullRequest.objects.create(
        repositorio=repo_base,
        numero=123,
        titulo="PR Test",
        estado="open",
        url="https://github.com/usuario/repo/pull/123",
    )
