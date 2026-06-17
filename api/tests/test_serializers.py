import pytest
from datetime import datetime, timedelta
from api.serializers import (
    RepositorioSerializer,
    PullRequestSerializer,
    SummaryTecnicoSerializer,
    GitHubConnectionSerializer
)

@pytest.mark.django_db
class TestSerializersValidations:

    # --- TESTS DE GITHUB CONNECTION ---
    def test_github_connection_temporal_validation(self):
        """Valida que last_used_at no sea anterior a connected_at."""
        # Se incluyen campos dummy para cumplir con requisitos del modelo
        data = {
            "github_user_id": 12345,
            "github_login": "testuser",
            "access_token": "fake-token",
            "connected_at": datetime.now(),
            "last_used_at": datetime.now() - timedelta(days=1)
        }
        serializer = GitHubConnectionSerializer(data=data)
        assert not serializer.is_valid()
        assert "last_used_at" in serializer.errors

    # --- TESTS DE REPOSITORIO ---
    def test_repositorio_url_validation(self):
        """Valida formato de URL de GitHub."""
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

    # --- TESTS DE PULL REQUEST ---
    def test_pull_request_url_consistency(self, repo_base):
        """Valida consistencia entre Repositorio y URL del PR."""
        data = {
            "repositorio": repo_base.id,
            "numero": 123,
            "titulo": "PR Test",
            "estado": "open",
            "url": "https://github.com/otro/otro-repo/pull/123"
        }
        serializer = PullRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "url" in serializer.errors
        assert "no es consistente" in str(serializer.errors["url"])

    # --- TESTS DE SUMMARY TÉCNICO ---
    def test_summary_tecnico_failed_without_error(self, pr_base):
        """Valida que un Summary en estado 'failed' exija un mensaje de error."""
        data = {
            "pull_request": pr_base.id,
            "estado": "failed",
            "contenido": "Resumen ok"
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
            "contenido": "Texto prohibido"
        }
        serializer = SummaryTecnicoSerializer(data=data)
        assert not serializer.is_valid()
        assert "estado" in serializer.errors

    def test_summary_tecnico_generated_without_content_invalid(self, pr_base):
        """Valida que un Summary en estado 'generated' deba tener contenido."""
        data = {
            "pull_request": pr_base.id,
            "estado": "generated",
            "contenido": ""
        }
        serializer = SummaryTecnicoSerializer(data=data)
        assert not serializer.is_valid()
        assert "contenido" in serializer.errors