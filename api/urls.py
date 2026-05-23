from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    PullRequestViewSet,
    RepositorioViewSet,
    SummaryTecnicoViewSet,
    github_pull_request_detail,
    github_oauth_callback,
    github_oauth_link,
    github_repository_pull_requests,
    github_repositories,
)

router = DefaultRouter()
router.register("repositorios", RepositorioViewSet, basename="repositorio")
router.register("pull-requests", PullRequestViewSet, basename="pull-request")
router.register("summaries", SummaryTecnicoViewSet, basename="summary-tecnico")

urlpatterns = [
    path("github/oauth/link/", github_oauth_link, name="github-oauth-link"),
    path("github/oauth/callback/", github_oauth_callback, name="github-oauth-callback"),
    path("github/repositorios/", github_repositories, name="github-repositories"),
    path(
        "github/repositorios/<str:owner>/<str:repo>/pull-requests/",
        github_repository_pull_requests,
        name="github-repository-pull-requests",
    ),
    path(
        "github/repositorios/<str:owner>/<str:repo>/pull-requests/<int:number>/",
        github_pull_request_detail,
        name="github-pull-request-detail",
    ),
    path("", include(router.urls)),
]
