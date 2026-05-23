import secrets
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import PullRequest, Repositorio, SummaryTecnico
from .serializers import (
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


def _get_bearer_token(request):
    authorization = request.headers.get("Authorization", "")
    prefix = "Bearer "

    if not authorization.startswith(prefix):
        return None

    return authorization.removeprefix(prefix).strip()


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
    return Response(
        {
            "error": error,
            "github_response": github_data,
        },
        status=_github_error_status(github_response.status_code),
    )


def _absolute_api_url(request, view_name, **kwargs):
    return request.build_absolute_uri(reverse(view_name, kwargs=kwargs))


@api_view(["GET"])
def github_oauth_link(request):
    # Devuelve el link de autorizacion para iniciar OAuth con GitHub desde navegador o Postman.
    settings_error = _github_settings_error()
    if settings_error:
        return settings_error

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

    return Response(
        {
            "authorization_url": authorization_url,
            "state": state,
            "expires_in_seconds": GITHUB_STATE_TTL_SECONDS,
        }
    )


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
        user_warning = None
    except requests.RequestException as exc:
        github_user = None
        user_warning = f"No se pudo consultar el usuario autenticado en GitHub: {exc}"
    except ValueError:
        github_user = None
        user_warning = "GitHub devolvio una respuesta invalida al consultar el usuario autenticado."

    response_data = {
        "message": "Autenticacion con GitHub correcta.",
        "access_token": access_token,
        "token_type": token_data.get("token_type"),
        "scope": token_data.get("scope"),
        "github_user": github_user,
        "warning": "Para laboratorio se devuelve el token. En produccion conviene guardarlo cifrado y no exponerlo.",
    }

    if user_warning:
        response_data["github_user_warning"] = user_warning

    return Response(response_data)


@api_view(["GET"])
def github_repositories(request):
    # Lista repositorios de GitHub con el token OAuth y marca cuales estan linkeados a esta API.
    access_token = _get_bearer_token(request)
    if not access_token:
        return Response(
            {
                "error": "Falta el access_token de GitHub.",
                "detail": "Envia el header Authorization: Bearer <access_token>.",
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

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


@api_view(["GET"])
def github_pull_request_detail(request, owner, repo, number):
    # Detalle completo de un PR: datos generales, diff, archivos, commits, comentarios y reviews.
    access_token = _get_bearer_token(request)
    if not access_token:
        return Response(
            {
                "error": "Falta el access_token de GitHub.",
                "detail": "Envia el header Authorization: Bearer <access_token>.",
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

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
    local_pull_request = None
    if local_repository:
        local_pull_request = PullRequest.objects.filter(
            repositorio=local_repository,
            numero=number,
        ).first()

    merged_at = pull_data.get("merged_at")
    github_state = pull_data.get("state")
    estado = PullRequest.ESTADO_MERGED if merged_at else github_state

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
        }
    )


@api_view(["GET"])
def github_repository_pull_requests(request, owner, repo):
    # Lista pull requests de un repositorio de GitHub usando el token OAuth del usuario.
    access_token = _get_bearer_token(request)
    if not access_token:
        return Response(
            {
                "error": "Falta el access_token de GitHub.",
                "detail": "Envia el header Authorization: Bearer <access_token>.",
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

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


class PullRequestViewSet(viewsets.ModelViewSet):
    queryset = PullRequest.objects.all()
    serializer_class = PullRequestSerializer


class SummaryTecnicoViewSet(viewsets.ModelViewSet):
    queryset = SummaryTecnico.objects.all()
    serializer_class = SummaryTecnicoSerializer
