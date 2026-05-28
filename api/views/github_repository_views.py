import requests
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from api.clients import github as github_client
from api.openapi import (
    ErrorResponseSerializer,
    GitHubPullRequestListResponseSerializer,
    GitHubRepositoryListResponseSerializer,
)
from api.permissions import CanViewPullRequests, CanViewRepositorios
from api.services.github_connections import get_active_github_token
from api.services.github_persistence import (
    get_linked_repositories_by_key,
    get_local_pull_requests_by_number,
    get_local_repository,
)
from api.services.github_presenters import build_pull_request_list, build_repository_list
from api.services.github_responses import paginated_or_error


@extend_schema(
    tags=["GitHub Repositorios"],
    summary="Listar repositorios de GitHub",
    description=(
        "Consulta GitHub con la conexión OAuth activa y devuelve los repositorios "
        "visibles para esa cuenta. Cada repositorio incluye datos remotos y una marca "
        "que indica si ya está guardado en la base local de la API, para saber si "
        "tiene seguimiento activado."
    ),
    responses={
        status.HTTP_200_OK: GitHubRepositoryListResponseSerializer,
        status.HTTP_400_BAD_REQUEST: ErrorResponseSerializer,
        status.HTTP_401_UNAUTHORIZED: ErrorResponseSerializer,
        status.HTTP_403_FORBIDDEN: ErrorResponseSerializer,
        status.HTTP_502_BAD_GATEWAY: ErrorResponseSerializer,
    },
)
@api_view(["GET"])
@permission_classes([CanViewRepositorios])
def github_repositories(request):
    access_token, token_error = get_active_github_token()
    if token_error:
        return token_error

    try:
        github_repositories_data, error_response = paginated_or_error(
            access_token,
            github_client.REPOS_URL,
            "GitHub no pudo devolver los repositorios.",
            "GitHub devolvió una respuesta inesperada al listar repositorios.",
            params={
                "affiliation": "owner,collaborator,organization_member",
                "visibility": "all",
                "sort": "full_name",
                "direction": "asc",
            },
        )
    except requests.RequestException as exc:
        return Response(
            {
                "error": "No se pudo conectar con GitHub para listar repositorios.",
                "detail": str(exc),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if error_response:
        return error_response

    repositories = build_repository_list(
        request,
        github_repositories_data,
        get_linked_repositories_by_key(),
    )

    return Response(
        {
            "count": len(repositories),
            "repositorios": repositories,
        }
    )


@extend_schema(
    tags=["GitHub Pull Requests"],
    operation_id="github_repository_pull_requests_list",
    summary="Listar pull requests de un repositorio",
    description=(
        "Consulta los pull requests de un repositorio remoto usando la conexión "
        "activa de GitHub. El filtro `state` permite traer PRs abiertos, cerrados "
        "o todos. La respuesta también indica si cada PR ya existe como registro "
        "local en la API."
    ),
    parameters=[
        OpenApiParameter(
            name="owner",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH,
            description="Owner u organización del repositorio en GitHub.",
        ),
        OpenApiParameter(
            name="repo",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH,
            description="Nombre del repositorio en GitHub.",
        ),
        OpenApiParameter(
            name="state",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            enum=["open", "closed", "all"],
            required=False,
            description="Estado de los pull requests a consultar. Por defecto: `all`.",
        ),
    ],
    responses={
        status.HTTP_200_OK: GitHubPullRequestListResponseSerializer,
        status.HTTP_400_BAD_REQUEST: ErrorResponseSerializer,
        status.HTTP_401_UNAUTHORIZED: ErrorResponseSerializer,
        status.HTTP_403_FORBIDDEN: ErrorResponseSerializer,
        status.HTTP_502_BAD_GATEWAY: ErrorResponseSerializer,
    },
)
@api_view(["GET"])
@permission_classes([CanViewPullRequests])
def github_repository_pull_requests(request, owner, repo):
    access_token, token_error = get_active_github_token()
    if token_error:
        return token_error

    state_filter = request.query_params.get("state", "all")
    allowed_states = {"open", "closed", "all"}
    if state_filter not in allowed_states:
        return Response(
            {
                "error": "El parámetro state es inválido.",
                "detail": "Usá uno de estos valores: open, closed, all.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    github_pulls_url = github_client.PULLS_URL.format(owner=owner, repo=repo)

    try:
        pull_requests_data, error_response = paginated_or_error(
            access_token,
            github_pulls_url,
            "GitHub no pudo devolver los pull requests del repositorio.",
            "GitHub devolvió una respuesta inesperada al listar pull requests.",
            params={
                "state": state_filter,
                "sort": "created",
                "direction": "desc",
            },
        )
    except requests.RequestException as exc:
        return Response(
            {
                "error": "No se pudo conectar con GitHub para listar pull requests.",
                "detail": str(exc),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if error_response:
        return error_response

    local_repository = get_local_repository(owner, repo)
    pull_requests = build_pull_request_list(
        request,
        owner,
        repo,
        pull_requests_data,
        get_local_pull_requests_by_number(local_repository),
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
