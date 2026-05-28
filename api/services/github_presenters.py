from django.urls import reverse

from api.models import PullRequest


def absolute_api_url(request, view_name, **kwargs):
    return request.build_absolute_uri(reverse(view_name, kwargs=kwargs))


def build_repository_list(request, github_repositories_data, linked_repositories):
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
                "link_detalle": absolute_api_url(
                    request,
                    "github-repository-pull-requests",
                    owner=owner_login,
                    repo=repo_name,
                ),
            }
        )
    return repositories


def build_pull_request_list(request, owner, repo, pull_requests_data, local_pull_requests):
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
                "link_detalle": absolute_api_url(
                    request,
                    "github-pull-request-detail",
                    owner=owner,
                    repo=repo,
                    number=number,
                ),
            }
        )
    return pull_requests


def build_files(files_data):
    return [
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


def build_commits(commits_data):
    return [
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


def build_comments(issue_comments_data):
    return [
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


def build_reviews(reviews_data):
    return [
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


def build_review_comments(review_comments_data):
    return [
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
