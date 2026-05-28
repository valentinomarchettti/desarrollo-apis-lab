from api.models import PullRequest, Repositorio, SummaryTecnico


def pull_request_estado_from_github(pull_data):
    if pull_data.get("merged_at"):
        return PullRequest.ESTADO_MERGED
    return pull_data.get("state") or PullRequest.ESTADO_OPEN


def get_local_repository(owner, repo):
    return (
        Repositorio.objects.filter(github_owner__iexact=owner, github_repo__iexact=repo)
        .order_by("-activo", "id")
        .first()
    )


def get_linked_repositories_by_key():
    linked_repositories = {}
    for repository in Repositorio.objects.all():
        key = (repository.github_owner.lower(), repository.github_repo.lower())
        if key not in linked_repositories or repository.activo:
            linked_repositories[key] = repository
    return linked_repositories


def get_local_pull_requests_by_number(repository):
    if not repository:
        return {}

    return {
        pull_request.numero: pull_request
        for pull_request in PullRequest.objects.filter(repositorio=repository)
    }


def get_or_create_repository_from_github(owner, repo, pull_data):
    local_repository = get_local_repository(owner, repo)
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


def save_generated_summary(owner, repo, number, pull_data, summary):
    local_repository = get_or_create_repository_from_github(owner, repo, pull_data)
    estado = pull_request_estado_from_github(pull_data)

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
