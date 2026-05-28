import requests
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .clients import github as github_client
from .gemini_service import generar_descripcion_ia
from .models import PullRequest
from .permissions import CanUseSummaryEndpoint, CanViewPullRequests
from .services.github_connections import get_active_github_token
from .services.github_persistence import get_local_repository, save_generated_summary
from .services.github_presenters import (
    build_comments,
    build_commits,
    build_files,
    build_review_comments,
    build_reviews,
)
from .services.github_responses import github_error_response, paginated_or_error


@api_view(["GET", "POST"])
@permission_classes([CanUseSummaryEndpoint])
def github_pull_request_summary(request, owner, repo, number):
    access_token, token_error = get_active_github_token()
    if token_error:
        return token_error

    pull_detail_url = github_client.PULL_DETAIL_URL.format(owner=owner, repo=repo, number=number)

    try:
        diff_response, diff_text = github_client.get_diff(access_token, pull_detail_url)
        if diff_response.status_code >= status.HTTP_400_BAD_REQUEST:
            return github_error_response(
                "GitHub no pudo devolver el diff del pull request.",
                diff_response,
                github_client.response_data(diff_response),
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
            pull_response, pull_data = github_client.get_json(access_token, pull_detail_url)
            if pull_response.status_code >= status.HTTP_400_BAD_REQUEST:
                return github_error_response(
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
            update_response, update_data = github_client.patch_json(
                access_token,
                pull_detail_url,
                {"body": summary},
            )
            if update_response.status_code >= status.HTTP_400_BAD_REQUEST:
                return github_error_response(
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
                local_repository, local_pull_request, local_summary = save_generated_summary(
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
@permission_classes([CanViewPullRequests])
def github_pull_request_detail(request, owner, repo, number):
    access_token, token_error = get_active_github_token()
    if token_error:
        return token_error

    pull_detail_url = github_client.PULL_DETAIL_URL.format(owner=owner, repo=repo, number=number)
    pull_files_url = github_client.PULL_FILES_URL.format(owner=owner, repo=repo, number=number)
    pull_commits_url = github_client.PULL_COMMITS_URL.format(owner=owner, repo=repo, number=number)
    pull_reviews_url = github_client.PULL_REVIEWS_URL.format(owner=owner, repo=repo, number=number)
    pull_review_comments_url = github_client.PULL_REVIEW_COMMENTS_URL.format(
        owner=owner,
        repo=repo,
        number=number,
    )
    issue_comments_url = github_client.ISSUE_COMMENTS_URL.format(
        owner=owner,
        repo=repo,
        number=number,
    )

    try:
        pull_response, pull_data = github_client.get_json(access_token, pull_detail_url)
        if pull_response.status_code >= status.HTTP_400_BAD_REQUEST:
            return github_error_response(
                "GitHub no pudo devolver el detalle del pull request.",
                pull_response,
                pull_data,
            )

        files_data, error_response = paginated_or_error(
            access_token,
            pull_files_url,
            "GitHub no pudo devolver los archivos modificados del pull request.",
            "GitHub devolvio una respuesta inesperada al listar archivos del pull request.",
        )
        if error_response:
            return error_response

        commits_data, error_response = paginated_or_error(
            access_token,
            pull_commits_url,
            "GitHub no pudo devolver los commits del pull request.",
            "GitHub devolvio una respuesta inesperada al listar commits del pull request.",
        )
        if error_response:
            return error_response

        issue_comments_data, error_response = paginated_or_error(
            access_token,
            issue_comments_url,
            "GitHub no pudo devolver los comentarios generales del pull request.",
            "GitHub devolvio una respuesta inesperada al listar comentarios generales.",
        )
        if error_response:
            return error_response

        reviews_data, error_response = paginated_or_error(
            access_token,
            pull_reviews_url,
            "GitHub no pudo devolver las reviews del pull request.",
            "GitHub devolvio una respuesta inesperada al listar reviews.",
        )
        if error_response:
            return error_response

        review_comments_data, error_response = paginated_or_error(
            access_token,
            pull_review_comments_url,
            "GitHub no pudo devolver los comentarios de codigo del pull request.",
            "GitHub devolvio una respuesta inesperada al listar comentarios de codigo.",
        )
        if error_response:
            return error_response

        diff_response, diff_text = github_client.get_diff(access_token, pull_detail_url)
        if diff_response.status_code >= status.HTTP_400_BAD_REQUEST:
            return github_error_response(
                "GitHub no pudo devolver el diff del pull request.",
                diff_response,
                github_client.response_data(diff_response),
            )

    except requests.RequestException as exc:
        return Response(
            {
                "error": "No se pudo conectar con GitHub para obtener el detalle del pull request.",
                "detail": str(exc),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    local_repository = get_local_repository(owner, repo)
    local_pull_request = None
    if local_repository:
        local_pull_request = PullRequest.objects.filter(
            repositorio=local_repository,
            numero=number,
        ).first()

    merged_at = pull_data.get("merged_at")
    github_state = pull_data.get("state")
    estado = PullRequest.ESTADO_MERGED if merged_at else github_state

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
            "archivos": build_files(files_data),
            "commits": build_commits(commits_data),
            "comentarios": build_comments(issue_comments_data),
            "reviews": build_reviews(reviews_data),
            "comentarios_codigo": build_review_comments(review_comments_data),
            "diff": diff_text,
        }
    )
