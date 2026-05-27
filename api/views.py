import secrets
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .gemini_service import generar_descripcion_ia

from .models import GitHubConnection, PullRequest, Repositorio, SummaryTecnico
from .serializers import (
    GitHubConnectionSerializer,
    PullRequestSerializer,
    RepositorioSerializer,
    SummaryTecnicoSerializer,
)


GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_REPOS_URL = "https://api.github.com/user/repos"
GITHUB_PULLS_URL = "https://api.github.com/repos/{owner}/{repo}/pulls"
GITHUB_PULL_DETAIL_URL = "https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
GITHUB_PULL_FILES_URL = "https://api.github.com/repos/{owner}/{repo}/pulls/{number}/files"
GITHUB_PULL_COMMITS_URL = "https://api.github.com/repos/{owner}/{repo}/pulls/{number}/commits"
GITHUB_PULL_REVIEWS_URL = "https://api.github.com/repos/{owner}/{repo}/pulls/{number}/reviews"
GITHUB_PULL_REVIEW_COMMENTS_URL = "https://api.github.com/repos/{owner}/{repo}/pulls/{number}/comments"
GITHUB_ISSUE_COMMENTS_URL = "https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments"
GITHUB_OAUTH_SCOPES = "repo read:user user:email"
GITHUB_STATE_CACHE_PREFIX = "github_oauth_state:"
GITHUB_STATE_TTL_SECONDS = 600
GITHUB_REQUEST_TIMEOUT_SECONDS = 10


def _github_state_cache_key(state):
    return f"{GITHUB_STATE_CACHE_PREFIX}{state}"


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


def _github_api_headers(access_token):
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _active_github_connection():
    return GitHubConnection.objects.filter(activo=True).order_by("-updated_at", "-id").first()


def _missing_github_connection_response():
    return Response(
        {
            "error": "No hay una cuenta de GitHub conectada.",
            "detail": "Conecta GitHub desde /api/github/connect/ antes de usar este endpoint.",
        },
        status=status.HTTP_401_UNAUTHORIZED,
    )


def _get_active_github_token():
    connection = _active_github_connection()
    if not connection:
        return None, _missing_github_connection_response()

    connection.last_used_at = timezone.now()
    connection.save(update_fields=["last_used_at", "updated_at"])
    return connection.access_token, None


def _deactivate_active_github_connection():
    GitHubConnection.objects.filter(activo=True).update(activo=False)


def _github_response_data(response):
    try:
        return response.json()
    except ValueError:
        return {"raw_response": response.text}


def _github_error_status(github_status_code):
    if github_status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
        return github_status_code
    if status.HTTP_400_BAD_REQUEST <= github_status_code < status.HTTP_500_INTERNAL_SERVER_ERROR:
        return status.HTTP_400_BAD_REQUEST
    return status.HTTP_502_BAD_GATEWAY


def _github_get_json(access_token, url, params=None):
    response = requests.get(
        url,
        headers=_github_api_headers(access_token),
        params=params,
        timeout=GITHUB_REQUEST_TIMEOUT_SECONDS,
    )
    return response, _github_response_data(response)


def _github_patch_json(access_token, url, payload):
    response = requests.patch(
        url,
        headers=_github_api_headers(access_token),
        json=payload,
        timeout=GITHUB_REQUEST_TIMEOUT_SECONDS,
    )
    return response, _github_response_data(response)


def _github_get_paginated_json(access_token, url, params=None):
    results = []
    page = 1

    while True:
        page_params = {
            **(params or {}),
            "per_page": 100,
            "page": page,
        }
        response, data = _github_get_json(access_token, url, params=page_params)

        if response.status_code >= status.HTTP_400_BAD_REQUEST:
            return None, response, data

        if not isinstance(data, list):
            return None, response, data

        results.extend(data)

        if "next" not in response.links:
            return results, None, None
        page += 1


def _github_get_diff(access_token, url):
    headers = _github_api_headers(access_token)
    headers["Accept"] = "application/vnd.github.v3.diff"

    response = requests.get(
        url,
        headers=headers,
        timeout=GITHUB_REQUEST_TIMEOUT_SECONDS,
    )
    return response, response.text


def _github_error_response(error, github_response, github_data):
    if github_response.status_code == status.HTTP_401_UNAUTHORIZED:
        _deactivate_active_github_connection()

    return Response(
        {
            "error": error,
            "github_response": github_data,
        },
        status=_github_error_status(github_response.status_code),
    )


def _pull_request_estado_from_github(pull_data):
    if pull_data.get("merged_at"):
        return PullRequest.ESTADO_MERGED
    return pull_data.get("state") or PullRequest.ESTADO_OPEN


def _get_or_create_repository_from_github(owner, repo, pull_data):
    local_repository = (
        Repositorio.objects.filter(github_owner__iexact=owner, github_repo__iexact=repo)
        .order_by("-activo", "id")
        .first()
    )
    if local_repository:
        return local_repository

    github_repository = pull_data.get("base", {}).get("repo") or {}

    return Repositorio.objects.create(
        nombre=github_repository.get("name") or repo,
        github_owner=owner,
        github_repo=repo,
        url=github_repository.get("html_url") or f"https://github.com/{owner}/{repo}",
        descripcion=github_repository.get("description") or "",
    )


def _save_generated_summary(owner, repo, number, pull_data, summary):
    local_repository = _get_or_create_repository_from_github(owner, repo, pull_data)
    estado = _pull_request_estado_from_github(pull_data)

    local_pull_request, _ = PullRequest.objects.update_or_create(
        repositorio=local_repository,
        numero=number,
        defaults={
            "titulo": (pull_data.get("title") or "")[:255],
            "estado": estado,
            "rama_origen": pull_data.get("head", {}).get("ref") or "",
            "rama_destino": pull_data.get("base", {}).get("ref") or "",
            "autor_github": pull_data.get("user", {}).get("login") or "",
            "url": pull_data.get("html_url") or "",
        },
    )
    local_summary = SummaryTecnico.objects.create(
        pull_request=local_pull_request,
        contenido=summary,
        estado=SummaryTecnico.ESTADO_GENERATED,
    )

    return local_repository, local_pull_request, local_summary


def _absolute_api_url(request, view_name, **kwargs):
    return request.build_absolute_uri(reverse(view_name, kwargs=kwargs))


def _build_github_authorization_url():
    # El state protege el flujo OAuth contra respuestas falsificadas o reutilizadas.
    state = secrets.token_urlsafe(32)
    cache.set(_github_state_cache_key(state), True, timeout=GITHUB_STATE_TTL_SECONDS)

    query_params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_CALLBACK_URL,
        "scope": GITHUB_OAUTH_SCOPES,
        "state": state,
    }
    authorization_url = f"{GITHUB_AUTHORIZE_URL}?{urlencode(query_params)}"

    return authorization_url, state


@api_view(["GET"])
def github_oauth_link(request):
    # Devuelve el link de autorizacion para iniciar OAuth con GitHub desde navegador o Postman.
    settings_error = _github_settings_error()
    if settings_error:
        return settings_error

    authorization_url, state = _build_github_authorization_url()

    return Response(
        {
            "authorization_url": authorization_url,
            "state": state,
            "expires_in_seconds": GITHUB_STATE_TTL_SECONDS,
        }
    )


@api_view(["GET"])
def github_connect(request):
    # Redirige directo a GitHub para que el usuario conecte la API en un solo paso.
    settings_error = _github_settings_error(require_secret=True)
    if settings_error:
        return settings_error

    authorization_url, _ = _build_github_authorization_url()
    return redirect(authorization_url)


@api_view(["GET"])
def github_oauth_callback(request):
    # GitHub redirige aca con code y state; el backend intercambia el code por un access_token.
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
        # El client_secret queda en backend porque no debe exponerse en frontend, navegador ni apps publicas.
        "client_secret": settings.GITHUB_CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.GITHUB_CALLBACK_URL,
    }

    try:
        token_response = requests.post(
            GITHUB_ACCESS_TOKEN_URL,
            data=token_payload,
            headers={"Accept": "application/json"},
            timeout=GITHUB_REQUEST_TIMEOUT_SECONDS,
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
            GITHUB_USER_URL,
            headers=_github_api_headers(access_token),
            timeout=GITHUB_REQUEST_TIMEOUT_SECONDS,
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

    response_data = {
        "message": "GitHub conectado correctamente.",
        "connected": True,
        "connection_id": connection.id,
        "token_type": token_data.get("token_type"),
        "scope": token_data.get("scope"),
        "github_user": github_user,
        "warning": "El access_token quedo guardado en la API y no se expone en la respuesta.",
    }

    return Response(response_data)


@api_view(["GET"])
def github_repositories(request):
    # Lista repositorios de GitHub usando la conexion OAuth activa guardada en la API.
    access_token, token_error = _get_active_github_token()
    if token_error:
        return token_error

    github_repositories_data = []
    page = 1

    try:
        while True:
            github_response = requests.get(
                GITHUB_REPOS_URL,
                headers=_github_api_headers(access_token),
                params={
                    "affiliation": "owner,collaborator,organization_member",
                    "visibility": "all",
                    "sort": "full_name",
                    "direction": "asc",
                    "per_page": 100,
                    "page": page,
                },
                timeout=GITHUB_REQUEST_TIMEOUT_SECONDS,
            )
            github_data = _github_response_data(github_response)

            if github_response.status_code >= status.HTTP_400_BAD_REQUEST:
                if github_response.status_code == status.HTTP_401_UNAUTHORIZED:
                    _deactivate_active_github_connection()
                return Response(
                    {
                        "error": "GitHub no pudo devolver los repositorios.",
                        "github_response": github_data,
                    },
                    status=_github_error_status(github_response.status_code),
                )

            if not isinstance(github_data, list):
                return Response(
                    {
                        "error": "GitHub devolvio una respuesta inesperada al listar repositorios.",
                        "github_response": github_data,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            github_repositories_data.extend(github_data)

            if "next" not in github_response.links:
                break
            page += 1

    except requests.RequestException as exc:
        return Response(
            {
                "error": "No se pudo conectar con GitHub para listar repositorios.",
                "detail": str(exc),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    linked_repositories = {}
    for repository in Repositorio.objects.all():
        key = (repository.github_owner.lower(), repository.github_repo.lower())
        if key not in linked_repositories or repository.activo:
            linked_repositories[key] = repository

    repositories = []
    for github_repository in github_repositories_data:
        owner_login = github_repository.get("owner", {}).get("login", "")
        repo_name = github_repository.get("name", "")
        local_repository = linked_repositories.get((owner_login.lower(), repo_name.lower()))

        repositories.append(
            {
                "github_id": github_repository.get("id"),
                "nombre": repo_name,
                "full_name": github_repository.get("full_name"),
                "owner": owner_login,
                "html_url": github_repository.get("html_url"),
                "private": github_repository.get("private"),
                "descripcion": github_repository.get("description"),
                "default_branch": github_repository.get("default_branch"),
                "linkeado_a_api": local_repository is not None,
                "seguimiento_pr_activado": bool(local_repository and local_repository.activo),
                "repositorio_api_id": local_repository.id if local_repository else None,
                "link_detalle": _absolute_api_url(
                    request,
                    "github-repository-pull-requests",
                    owner=owner_login,
                    repo=repo_name,
                ),
            }
        )

    return Response(
        {
            "count": len(repositories),
            "repositorios": repositories,
        }
    )


@api_view(["GET", "POST"])
def github_pull_request_summary(request, owner, repo, number):
    # GET genera un summary; POST ademas lo publica como descripcion del PR en GitHub.
    access_token, token_error = _get_active_github_token()
    if token_error:
        return token_error

    pull_detail_url = GITHUB_PULL_DETAIL_URL.format(owner=owner, repo=repo, number=number)

    try:
        diff_response, diff_text = _github_get_diff(access_token, pull_detail_url)
        if diff_response.status_code >= status.HTTP_400_BAD_REQUEST:
            return _github_error_response(
                "GitHub no pudo devolver el diff del pull request.",
                diff_response,
                _github_response_data(diff_response),
            )
    except requests.RequestException as exc:
        return Response(
            {
                "error": "No se pudo conectar con GitHub para obtener el diff del pull request.",
                "detail": str(exc),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    pull_data = None
    if request.method == "POST":
        try:
            pull_response, pull_data = _github_get_json(access_token, pull_detail_url)
            if pull_response.status_code >= status.HTTP_400_BAD_REQUEST:
                return _github_error_response(
                    "GitHub no pudo devolver el detalle del pull request.",
                    pull_response,
                    pull_data,
                )
        except requests.RequestException as exc:
            return Response(
                {
                    "error": "No se pudo conectar con GitHub para obtener el detalle del pull request.",
                    "detail": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

    summary, error = generar_descripcion_ia(diff_text)
    if error:
        return Response(
            {
                "error": "No se pudo generar el summary tecnico con Gemini.",
                "detail": error,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    response_data = {
        "repositorio": {
            "owner": owner,
            "repo": repo,
        },
        "pull_request": {
            "numero": number,
        },
        "summary_tecnico_ia": summary,
    }

    if request.method == "POST":
        try:
            update_response, update_data = _github_patch_json(
                access_token,
                pull_detail_url,
                {"body": summary},
            )
            if update_response.status_code >= status.HTTP_400_BAD_REQUEST:
                return _github_error_response(
                    "GitHub no pudo actualizar la descripcion del pull request.",
                    update_response,
                    update_data,
                )
        except requests.RequestException as exc:
            return Response(
                {
                    "error": "No se pudo conectar con GitHub para actualizar la descripcion del pull request.",
                    "detail": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            with transaction.atomic():
                local_repository, local_pull_request, local_summary = _save_generated_summary(
                    owner,
                    repo,
                    number,
                    pull_data,
                    summary,
                )
        except Exception as exc:
            return Response(
                {
                    "error": "GitHub actualizo la descripcion del pull request, pero no se pudo guardar el summary en la API.",
                    "detail": str(exc),
                    "descripcion_actualizada_en_github": True,
                    "github_response": {
                        "id": update_data.get("id"),
                        "number": update_data.get("number"),
                        "title": update_data.get("title"),
                        "body": update_data.get("body"),
                        "html_url": update_data.get("html_url"),
                        "updated_at": update_data.get("updated_at"),
                    },
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_data["repositorio"]["repositorio_api_id"] = local_repository.id
        response_data["pull_request"].update(
            {
                "descripcion_actualizada_en_github": True,
                "html_url": update_data.get("html_url"),
                "updated_at": update_data.get("updated_at"),
                "pull_request_api_id": local_pull_request.id,
            }
        )
        response_data["summary_tecnico_api_id"] = local_summary.id
        response_data["github_response"] = {
            "id": update_data.get("id"),
            "number": update_data.get("number"),
            "title": update_data.get("title"),
            "body": update_data.get("body"),
            "html_url": update_data.get("html_url"),
            "updated_at": update_data.get("updated_at"),
        }

    return Response(response_data)


@api_view(["GET"])
def github_pull_request_detail(request, owner, repo, number):
    # Detalle completo de un PR: datos generales, diff, archivos, commits, comentarios y reviews.
    access_token, token_error = _get_active_github_token()
    if token_error:
        return token_error

    pull_detail_url = GITHUB_PULL_DETAIL_URL.format(owner=owner, repo=repo, number=number)
    pull_files_url = GITHUB_PULL_FILES_URL.format(owner=owner, repo=repo, number=number)
    pull_commits_url = GITHUB_PULL_COMMITS_URL.format(owner=owner, repo=repo, number=number)
    pull_reviews_url = GITHUB_PULL_REVIEWS_URL.format(owner=owner, repo=repo, number=number)
    pull_review_comments_url = GITHUB_PULL_REVIEW_COMMENTS_URL.format(
        owner=owner,
        repo=repo,
        number=number,
    )
    issue_comments_url = GITHUB_ISSUE_COMMENTS_URL.format(owner=owner, repo=repo, number=number)

    try:
        pull_response, pull_data = _github_get_json(access_token, pull_detail_url)
        if pull_response.status_code >= status.HTTP_400_BAD_REQUEST:
            return _github_error_response(
                "GitHub no pudo devolver el detalle del pull request.",
                pull_response,
                pull_data,
            )

        files_data, files_error_response, files_error_data = _github_get_paginated_json(
            access_token,
            pull_files_url,
        )
        if files_error_response is not None:
            if files_error_response.status_code >= status.HTTP_400_BAD_REQUEST:
                return _github_error_response(
                    "GitHub no pudo devolver los archivos modificados del pull request.",
                    files_error_response,
                    files_error_data,
                )
            return Response(
                {
                    "error": "GitHub devolvio una respuesta inesperada al listar archivos del pull request.",
                    "github_response": files_error_data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        commits_data, commits_error_response, commits_error_data = _github_get_paginated_json(
            access_token,
            pull_commits_url,
        )
        if commits_error_response is not None:
            if commits_error_response.status_code >= status.HTTP_400_BAD_REQUEST:
                return _github_error_response(
                    "GitHub no pudo devolver los commits del pull request.",
                    commits_error_response,
                    commits_error_data,
                )
            return Response(
                {
                    "error": "GitHub devolvio una respuesta inesperada al listar commits del pull request.",
                    "github_response": commits_error_data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        issue_comments_data, issue_comments_error_response, issue_comments_error_data = (
            _github_get_paginated_json(access_token, issue_comments_url)
        )
        if issue_comments_error_response is not None:
            if issue_comments_error_response.status_code >= status.HTTP_400_BAD_REQUEST:
                return _github_error_response(
                    "GitHub no pudo devolver los comentarios generales del pull request.",
                    issue_comments_error_response,
                    issue_comments_error_data,
                )
            return Response(
                {
                    "error": "GitHub devolvio una respuesta inesperada al listar comentarios generales.",
                    "github_response": issue_comments_error_data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        reviews_data, reviews_error_response, reviews_error_data = _github_get_paginated_json(
            access_token,
            pull_reviews_url,
        )
        if reviews_error_response is not None:
            if reviews_error_response.status_code >= status.HTTP_400_BAD_REQUEST:
                return _github_error_response(
                    "GitHub no pudo devolver las reviews del pull request.",
                    reviews_error_response,
                    reviews_error_data,
                )
            return Response(
                {
                    "error": "GitHub devolvio una respuesta inesperada al listar reviews.",
                    "github_response": reviews_error_data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        review_comments_data, review_comments_error_response, review_comments_error_data = (
            _github_get_paginated_json(access_token, pull_review_comments_url)
        )
        if review_comments_error_response is not None:
            if review_comments_error_response.status_code >= status.HTTP_400_BAD_REQUEST:
                return _github_error_response(
                    "GitHub no pudo devolver los comentarios de codigo del pull request.",
                    review_comments_error_response,
                    review_comments_error_data,
                )
            return Response(
                {
                    "error": "GitHub devolvio una respuesta inesperada al listar comentarios de codigo.",
                    "github_response": review_comments_error_data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        diff_response, diff_text = _github_get_diff(access_token, pull_detail_url)
        if diff_response.status_code >= status.HTTP_400_BAD_REQUEST:
            return _github_error_response(
                "GitHub no pudo devolver el diff del pull request.",
                diff_response,
                _github_response_data(diff_response),
            )

    except requests.RequestException as exc:
        return Response(
            {
                "error": "No se pudo conectar con GitHub para obtener el detalle del pull request.",
                "detail": str(exc),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    local_repository = (
        Repositorio.objects.filter(github_owner__iexact=owner, github_repo__iexact=repo)
        .order_by("-activo", "id")
        .first()
    )

    merged_at = pull_data.get("merged_at")
    github_state = pull_data.get("state")
    estado = PullRequest.ESTADO_MERGED if merged_at else github_state

    local_pull_request = None
    summary_ia_contenido = "No se generó summary (El repositorio no está guardado en la API local)."

    if local_repository:
        local_pull_request, created = PullRequest.objects.get_or_create(
            repositorio=local_repository,
            numero=number,
            defaults={
                "titulo": pull_data.get("title", ""),
                "estado": estado,  # <-- CORREGIDO: ahora usa 'estado'
                "autor_github": pull_data.get("user", {}).get("login", ""),
                "url": pull_data.get("html_url", ""),
            }
        )

        # 2. Lógica para procesar con Gemini e interactuar con el modelo SummaryTecnico
        summary_existente = SummaryTecnico.objects.filter(pull_request=local_pull_request).first()

        if summary_existente:
            if summary_existente.estado == SummaryTecnico.ESTADO_GENERATED:
                summary_ia_contenido = summary_existente.contenido
            else:
                summary_ia_contenido = f"El summary previo falló o quedó pendiente: {summary_existente.error_message}"
        else:
            # Si no existe, creamos un registro inicial en estado 'pending'
            nuevo_summary = SummaryTecnico.objects.create(
                pull_request=local_pull_request,
                contenido="",
                estado=SummaryTecnico.ESTADO_PENDING
            )

            # Mandamos el diff_text que nos bajamos de GitHub directo a Gemini
            resultado_ia, error_ia = generar_descripcion_ia(diff_text)

            if error_ia:
                nuevo_summary.estado = SummaryTecnico.ESTADO_FAILED
                nuevo_summary.error_message = error_ia
                nuevo_summary.save()
                summary_ia_contenido = f"Error al generar con Gemini: {error_ia}"
            else:
                nuevo_summary.contenido = resultado_ia
                nuevo_summary.estado = SummaryTecnico.ESTADO_GENERATED
                nuevo_summary.save()
                summary_ia_contenido = resultado_ia

    files = [
        {
            "sha": file_data.get("sha"),
            "filename": file_data.get("filename"),
            "status": file_data.get("status"),
            "additions": file_data.get("additions"),
            "deletions": file_data.get("deletions"),
            "changes": file_data.get("changes"),
            "blob_url": file_data.get("blob_url"),
            "raw_url": file_data.get("raw_url"),
            "contents_url": file_data.get("contents_url"),
            "patch": file_data.get("patch"),
        }
        for file_data in files_data
    ]

    commits = [
        {
            "sha": commit_data.get("sha"),
            "short_sha": commit_data.get("sha", "")[:7],
            "message": commit_data.get("commit", {}).get("message"),
            "author": commit_data.get("commit", {}).get("author", {}).get("name"),
            "author_email": commit_data.get("commit", {}).get("author", {}).get("email"),
            "author_date": commit_data.get("commit", {}).get("author", {}).get("date"),
            "committer": commit_data.get("commit", {}).get("committer", {}).get("name"),
            "committer_date": commit_data.get("commit", {}).get("committer", {}).get("date"),
            "html_url": commit_data.get("html_url"),
        }
        for commit_data in commits_data
    ]

    comments = [
        {
            "id": comment_data.get("id"),
            "autor_github": comment_data.get("user", {}).get("login"),
            "body": comment_data.get("body"),
            "html_url": comment_data.get("html_url"),
            "created_at": comment_data.get("created_at"),
            "updated_at": comment_data.get("updated_at"),
        }
        for comment_data in issue_comments_data
    ]

    reviews = [
        {
            "id": review_data.get("id"),
            "state": review_data.get("state"),
            "autor_github": review_data.get("user", {}).get("login"),
            "body": review_data.get("body"),
            "commit_id": review_data.get("commit_id"),
            "html_url": review_data.get("html_url"),
            "submitted_at": review_data.get("submitted_at"),
        }
        for review_data in reviews_data
    ]

    review_comments = [
        {
            "id": comment_data.get("id"),
            "autor_github": comment_data.get("user", {}).get("login"),
            "path": comment_data.get("path"),
            "position": comment_data.get("position"),
            "original_position": comment_data.get("original_position"),
            "line": comment_data.get("line"),
            "original_line": comment_data.get("original_line"),
            "side": comment_data.get("side"),
            "diff_hunk": comment_data.get("diff_hunk"),
            "body": comment_data.get("body"),
            "html_url": comment_data.get("html_url"),
            "created_at": comment_data.get("created_at"),
            "updated_at": comment_data.get("updated_at"),
        }
        for comment_data in review_comments_data
    ]

    return Response(
        {
            "repositorio": {
                "owner": owner,
                "repo": repo,
                "linkeado_a_api": local_repository is not None,
                "seguimiento_pr_activado": bool(local_repository and local_repository.activo),
                "repositorio_api_id": local_repository.id if local_repository else None,
            },
            "pull_request": {
                "github_id": pull_data.get("id"),
                "numero": pull_data.get("number"),
                "titulo": pull_data.get("title"),
                "descripcion": pull_data.get("body"),
                "estado": estado,
                "draft": pull_data.get("draft"),
                "autor_github": pull_data.get("user", {}).get("login"),
                "html_url": pull_data.get("html_url"),
                "rama_origen": pull_data.get("head", {}).get("ref"),
                "rama_destino": pull_data.get("base", {}).get("ref"),
                "created_at": pull_data.get("created_at"),
                "updated_at": pull_data.get("updated_at"),
                "closed_at": pull_data.get("closed_at"),
                "merged_at": merged_at,
                "mergeable": pull_data.get("mergeable"),
                "merged": pull_data.get("merged"),
                "commits": pull_data.get("commits"),
                "changed_files": pull_data.get("changed_files"),
                "additions": pull_data.get("additions"),
                "deletions": pull_data.get("deletions"),
                "labels": [
                    {
                        "name": label.get("name"),
                        "color": label.get("color"),
                    }
                    for label in pull_data.get("labels", [])
                ],
                "assignees": [
                    assignee.get("login")
                    for assignee in pull_data.get("assignees", [])
                ],
                "requested_reviewers": [
                    reviewer.get("login")
                    for reviewer in pull_data.get("requested_reviewers", [])
                ],
                "guardado_en_api": local_pull_request is not None,
                "pull_request_api_id": local_pull_request.id if local_pull_request else None,
            },
            "archivos": files,
            "commits": commits,
            "comentarios": comments,
            "reviews": reviews,
            "comentarios_codigo": review_comments,
            "diff": diff_text,
            "summary_tecnico_ia": summary_ia_contenido
        }
    )


@api_view(["GET"])
def github_repository_pull_requests(request, owner, repo):
    # Lista pull requests de un repositorio de GitHub usando la conexion OAuth activa.
    access_token, token_error = _get_active_github_token()
    if token_error:
        return token_error

    state_filter = request.query_params.get("state", "all")
    allowed_states = {"open", "closed", "all"}
    if state_filter not in allowed_states:
        return Response(
            {
                "error": "El parametro state es invalido.",
                "detail": "Usa uno de estos valores: open, closed, all.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    pull_requests_data = []
    page = 1
    github_pulls_url = GITHUB_PULLS_URL.format(owner=owner, repo=repo)

    try:
        while True:
            github_response = requests.get(
                github_pulls_url,
                headers=_github_api_headers(access_token),
                params={
                    "state": state_filter,
                    "sort": "created",
                    "direction": "desc",
                    "per_page": 100,
                    "page": page,
                },
                timeout=GITHUB_REQUEST_TIMEOUT_SECONDS,
            )
            github_data = _github_response_data(github_response)

            if github_response.status_code >= status.HTTP_400_BAD_REQUEST:
                if github_response.status_code == status.HTTP_401_UNAUTHORIZED:
                    _deactivate_active_github_connection()
                return Response(
                    {
                        "error": "GitHub no pudo devolver los pull requests del repositorio.",
                        "github_response": github_data,
                    },
                    status=_github_error_status(github_response.status_code),
                )

            if not isinstance(github_data, list):
                return Response(
                    {
                        "error": "GitHub devolvio una respuesta inesperada al listar pull requests.",
                        "github_response": github_data,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            pull_requests_data.extend(github_data)

            if "next" not in github_response.links:
                break
            page += 1

    except requests.RequestException as exc:
        return Response(
            {
                "error": "No se pudo conectar con GitHub para listar pull requests.",
                "detail": str(exc),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    local_repository = (
        Repositorio.objects.filter(github_owner__iexact=owner, github_repo__iexact=repo)
        .order_by("-activo", "id")
        .first()
    )
    local_pull_requests = {}
    if local_repository:
        local_pull_requests = {
            pull_request.numero: pull_request
            for pull_request in PullRequest.objects.filter(repositorio=local_repository)
        }

    pull_requests = []
    for github_pull_request in pull_requests_data:
        number = github_pull_request.get("number")
        local_pull_request = local_pull_requests.get(number)
        merged_at = github_pull_request.get("merged_at")
        github_state = github_pull_request.get("state")
        estado = PullRequest.ESTADO_MERGED if merged_at else github_state

        pull_requests.append(
            {
                "github_id": github_pull_request.get("id"),
                "numero": number,
                "titulo": github_pull_request.get("title"),
                "estado": estado,
                "draft": github_pull_request.get("draft"),
                "rama_origen": github_pull_request.get("head", {}).get("ref"),
                "rama_destino": github_pull_request.get("base", {}).get("ref"),
                "autor_github": github_pull_request.get("user", {}).get("login"),
                "html_url": github_pull_request.get("html_url"),
                "created_at": github_pull_request.get("created_at"),
                "updated_at": github_pull_request.get("updated_at"),
                "closed_at": github_pull_request.get("closed_at"),
                "merged_at": merged_at,
                "guardado_en_api": local_pull_request is not None,
                "pull_request_api_id": local_pull_request.id if local_pull_request else None,
                "link_detalle": _absolute_api_url(
                    request,
                    "github-pull-request-detail",
                    owner=owner,
                    repo=repo,
                    number=number,
                ),
            }
        )

    return Response(
        {
            "repositorio": {
                "owner": owner,
                "repo": repo,
                "linkeado_a_api": local_repository is not None,
                "seguimiento_pr_activado": bool(local_repository and local_repository.activo),
                "repositorio_api_id": local_repository.id if local_repository else None,
            },
            "state": state_filter,
            "count": len(pull_requests),
            "pull_requests": pull_requests,
        }
    )


class RepositorioViewSet(viewsets.ModelViewSet):
    queryset = Repositorio.objects.all()
    serializer_class = RepositorioSerializer


class GitHubConnectionViewSet(viewsets.ModelViewSet):
    queryset = GitHubConnection.objects.all()
    serializer_class = GitHubConnectionSerializer


class PullRequestViewSet(viewsets.ModelViewSet):
    queryset = PullRequest.objects.all()
    serializer_class = PullRequestSerializer


class SummaryTecnicoViewSet(viewsets.ModelViewSet):
    queryset = SummaryTecnico.objects.all()
    serializer_class = SummaryTecnicoSerializer
