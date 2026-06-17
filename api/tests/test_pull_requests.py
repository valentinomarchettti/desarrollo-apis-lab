import pytest
from django.urls import reverse
from api.models import PullRequest


@pytest.mark.django_db
def test_pull_request_crud_crea_lee_actualiza_y_elimina(authenticated_client, repo_base):
    """
    Test completo del ciclo CRUD para el modelo PullRequest.
    - Utiliza 'authenticated_client' para evitar el error 401.
    - Utiliza 'repo_base' (fixture) para cumplir con la relación (FK).
    """

    # 1. CREATE
    url_list = reverse('pull-request-list')
    data = {
        "repositorio": repo_base.id,
        "numero": 123,
        "titulo": "PR Inicial",
        "estado": "open"
    }

    response = authenticated_client.post(url_list, data, format='json')
    assert response.status_code == 201
    pr_id = response.data['id']
    assert response.data['titulo'] == "PR Inicial"

    # 2. READ
    url_detail = reverse('pull-request-detail', kwargs={'pk': pr_id})
    response = authenticated_client.get(url_detail)
    assert response.status_code == 200
    assert response.data['titulo'] == "PR Inicial"

    # 3. UPDATE
    update_data = {
        "repositorio": repo_base.id,
        "numero": 123,
        "titulo": "PR Actualizado",
        "estado": "open"
    }
    response = authenticated_client.put(url_detail, update_data, format='json')
    assert response.status_code == 200
    assert response.data['titulo'] == "PR Actualizado"

    # 4. DELETE
    response = authenticated_client.delete(url_detail)
    assert response.status_code == 204
    assert PullRequest.objects.filter(id=pr_id).count() == 0


@pytest.mark.django_db
def test_create_pull_request_invalid_data(authenticated_client):
    """
    Test de caso negativo: validación ante datos faltantes.
    """
    url_list = reverse('pull-request-list')
    # Enviamos datos vacíos para disparar el error de validación
    response = authenticated_client.post(url_list, {}, format='json')
    assert response.status_code == 400
