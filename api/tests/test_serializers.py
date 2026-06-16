import pytest
from api.serializers import (
    RepositorioSerializer,
    PullRequestSerializer,
    SummaryTecnicoSerializer
)

@pytest.mark.django_db
class TestSerializersValidations:

    def test_repositorio_url_validation(self):
        """Valida que la URL de Repositorio deba ser de GitHub."""
        data = {
            "nombre": "RepoTest",
            "github_owner": "user",
            "github_repo": "repo",
            "url": "https://gitlab.com/invalid"
        }
        serializer = RepositorioSerializer(data=data)
        assert not serializer.is_valid()
        assert "url" in serializer.errors
        assert "https://github.com/" in str(serializer.errors["url"])

    def test_pull_request_url_consistency(self, repo_base):
        """Valida la consistencia cruzada entre repositorio y URL del PR."""
        data = {
            "repositorio": repo_base.id,
            "numero": 123,
            "titulo": "PR Test",
            "estado": "open",
            "url": "https://github.com/otro/otro-repo/pull/123" # URL inconsistente
        }
        serializer = PullRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "url" in serializer.errors
        assert "no es consistente" in str(serializer.errors["url"])

    def test_summary_tecnico_failed_without_error(self, pr_base):
        """Valida que un Summary en estado 'failed' exija un mensaje de error."""
        data = {
            "pull_request": pr_base.id,
            "estado": "failed",
            "contenido": "Resumen ok",
            # Falta 'error_message'
        }
        serializer = SummaryTecnicoSerializer(data=data)
        assert not serializer.is_valid()
        assert "error_message" in serializer.errors

    def test_summary_tecnico_pending_with_content_invalid(self, pr_base):
        """Valida que un Summary en estado 'pending' no deba tener contenido."""
        data = {
            "pull_request": pr_base.id,
            "estado": "pending",
            "contenido": "Resumen que no deberia estar aqui"
        }
        serializer = SummaryTecnicoSerializer(data=data)
        assert not serializer.is_valid()
        assert "estado" in serializer.errors