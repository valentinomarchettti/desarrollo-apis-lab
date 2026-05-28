import requests
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .clients import github as github_client
from .permissions import CanViewPullRequests, CanViewRepositorios
from .services.github_connections import get_active_github_token
from .services.github_persistence import (
    get_linked_repositories_by_key,
    get_local_pull_requests_by_number,
    get_local_repository,
)
from .services.github_presenters import build_pull_request_list, build_repository_list
from .services.github_responses import paginated_or_error


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
            "GitHub devolvio una respuesta inesperada al listar repositorios.",
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
                "error": "El parametro state es invalido.",
                "detail": "Usa uno de estos valores: open, closed, all.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    github_pulls_url = github_client.PULLS_URL.format(owner=owner, repo=repo)

    try:
        pull_requests_data, error_response = paginated_or_error(
            access_token,
            github_pulls_url,
            "GitHub no pudo devolver los pull requests del repositorio.",
            "GitHub devolvio una respuesta inesperada al listar pull requests.",
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
