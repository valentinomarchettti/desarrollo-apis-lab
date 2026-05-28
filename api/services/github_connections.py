from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from api.models import GitHubConnection


def active_github_connection():
    return GitHubConnection.objects.filter(activo=True).order_by("-updated_at", "-id").first()


def missing_github_connection_response():
    return Response(
        {
            "error": "No hay una cuenta de GitHub conectada.",
            "detail": "Conecta GitHub desde /api/github/connect/ antes de usar este endpoint.",
        },
        status=status.HTTP_401_UNAUTHORIZED,
    )


def get_active_github_token():
    connection = active_github_connection()
    if not connection:
        return None, missing_github_connection_response()

    connection.last_used_at = timezone.now()
    connection.save(update_fields=["last_used_at", "updated_at"])
    return connection.access_token, None


def deactivate_active_github_connection():
    GitHubConnection.objects.filter(activo=True).update(activo=False)
