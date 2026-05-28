import secrets
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .clients import github as github_client
from .models import GitHubConnection
from .permissions import CanConnectGitHub


def _github_state_cache_key(state):
    return f"{github_client.STATE_CACHE_PREFIX}{state}"


def _github_settings_error(require_secret=False):
    missing_settings = []

    if not settings.GITHUB_CLIENT_ID:
        missing_settings.append("GITHUB_CLIENT_ID")
    if require_secret and not settings.GITHUB_CLIENT_SECRET:
        missing_settings.append("GITHUB_CLIENT_SECRET")
    if not settings.GITHUB_CALLBACK_URL:
        missing_settings.append("GITHUB_CALLBACK_URL")

    if not missing_settings:
        return None

    return Response(
        {
            "error": "Faltan variables de entorno para OAuth con GitHub.",
            "missing_settings": missing_settings,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _build_github_authorization_url():
    # El state protege el flujo OAuth contra respuestas falsificadas o reutilizadas.
    state = secrets.token_urlsafe(32)
    cache.set(
        _github_state_cache_key(state),
        True,
        timeout=github_client.STATE_TTL_SECONDS,
    )

    query_params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_CALLBACK_URL,
        "scope": github_client.OAUTH_SCOPES,
        "state": state,
    }
    authorization_url = f"{github_client.AUTHORIZE_URL}?{urlencode(query_params)}"

    return authorization_url, state


@api_view(["GET"])
@permission_classes([CanConnectGitHub])
def github_oauth_link(request):
    settings_error = _github_settings_error()
    if settings_error:
        return settings_error

    authorization_url, state = _build_github_authorization_url()

    return Response(
        {
            "authorization_url": authorization_url,
            "state": state,
            "expires_in_seconds": github_client.STATE_TTL_SECONDS,
        }
    )


@api_view(["GET"])
@permission_classes([CanConnectGitHub])
def github_connect(request):
    settings_error = _github_settings_error(require_secret=True)
    if settings_error:
        return settings_error

    authorization_url, _ = _build_github_authorization_url()
    return redirect(authorization_url)


@api_view(["GET"])
@permission_classes([AllowAny])
def github_oauth_callback(request):
    settings_error = _github_settings_error(require_secret=True)
    if settings_error:
        return settings_error

    code = request.query_params.get("code")
    state_value = request.query_params.get("state")

    if not code:
        return Response(
            {"error": "Falta el parametro code enviado por GitHub."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not state_value:
        return Response(
            {"error": "Falta el parametro state enviado por GitHub."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    state_cache_key = _github_state_cache_key(state_value)
    if not cache.get(state_cache_key):
        return Response(
            {"error": "El state es invalido o expiro. Inicia nuevamente el flujo OAuth."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    cache.delete(state_cache_key)

    token_payload = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "client_secret": settings.GITHUB_CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.GITHUB_CALLBACK_URL,
    }

    try:
        token_response = requests.post(
            github_client.ACCESS_TOKEN_URL,
            data=token_payload,
            headers={"Accept": "application/json"},
            timeout=github_client.REQUEST_TIMEOUT_SECONDS,
        )
        token_data = token_response.json()
    except requests.RequestException as exc:
        return Response(
            {
                "error": "No se pudo conectar con GitHub para obtener el access_token.",
                "detail": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    except ValueError:
        return Response(
            {"error": "GitHub devolvio una respuesta invalida al solicitar el access_token."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    access_token = token_data.get("access_token")
    if not access_token:
        return Response(
            {
                "error": "GitHub no devolvio access_token.",
                "github_response": token_data,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user_response = requests.get(
            github_client.USER_URL,
            headers=github_client.api_headers(access_token),
            timeout=github_client.REQUEST_TIMEOUT_SECONDS,
        )
        user_data = user_response.json()
        user_response.raise_for_status()
        github_user = {
            "id": user_data.get("id"),
            "login": user_data.get("login"),
            "html_url": user_data.get("html_url"),
        }
    except requests.RequestException as exc:
        return Response(
            {
                "error": "No se pudo consultar el usuario autenticado en GitHub.",
                "detail": str(exc),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except ValueError:
        return Response(
            {"error": "GitHub devolvio una respuesta invalida al consultar el usuario autenticado."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if not github_user["id"] or not github_user["login"]:
        return Response(
            {
                "error": "GitHub devolvio datos de usuario incompletos.",
                "github_response": user_data,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    with transaction.atomic():
        GitHubConnection.objects.exclude(github_user_id=github_user["id"]).update(activo=False)
        connection, _ = GitHubConnection.objects.update_or_create(
            github_user_id=github_user["id"],
            defaults={
                "github_login": github_user["login"],
                "html_url": github_user["html_url"] or "",
                "access_token": access_token,
                "token_type": token_data.get("token_type") or "",
                "scope": token_data.get("scope") or "",
                "activo": True,
                "connected_at": timezone.now(),
            },
        )

    return Response(
        {
            "message": "GitHub conectado correctamente.",
            "connected": True,
            "connection_id": connection.id,
            "token_type": token_data.get("token_type"),
            "scope": token_data.get("scope"),
            "github_user": github_user,
            "warning": "El access_token quedo guardado en la API y no se expone en la respuesta.",
        }
    )
