import pytest
from django.urls import reverse
from api.models import PullRequest
from api.filters import filter_github_pull_requests


# --- 1. TEST DE FILTROS DE BASE DE DATOS (Django Filter) ---

@pytest.mark.django_db
def test_pull_request_filter_estado(authenticated_client, repo_base):
    """Verifica que el filtro de estado funcione en el endpoint (paginado)."""
    # Limpiamos PRs previos para asegurar independencia
    PullRequest.objects.all().delete()

    PullRequest.objects.create(repositorio=repo_base, numero=1, titulo="PR Open", estado="open")
    PullRequest.objects.create(repositorio=repo_base, numero=2, titulo="PR Closed", estado="closed")

    url = reverse('pull-request-list') + "?estado=open"
    response = authenticated_client.get(url)

    assert response.status_code == 200
    # Accedemos a 'results' porque el listado está paginado
    assert len(response.data['results']) == 1
    assert response.data['results'][0]['estado'] == 'open'


# --- 2. TEST DE LÓGICA MANUAL (función filter_github_pull_requests) ---

def test_filter_github_pull_requests_manual():
    """Valida la lógica de filtrado manual de PRs externos (sin DB)."""
    prs = [
        {"numero": 1, "estado": "open", "titulo": "Feature A"},
        {"numero": 2, "estado": "closed", "titulo": "Bugfix B"}
    ]

    # Caso positivo: Filtrar por estado
    query_params = {"estado": "open"}
    result, error = filter_github_pull_requests(prs, query_params)
    assert error is None
    assert len(result) == 1
    assert result[0]["numero"] == 1

    # Caso negativo: Estado inválido
    query_params_bad = {"estado": "invalid_status"}
    result, error = filter_github_pull_requests(prs, query_params_bad)
    assert result is None
    assert "error" in error


def test_filter_github_pull_requests_numero_invalido():
    """Valida que el filtro manual maneje números no enteros."""
    prs = [{"numero": 1, "estado": "open"}]
    query_params = {"numero": "abc"}
    result, error = filter_github_pull_requests(prs, query_params)
    assert result is None
    assert "error" in error