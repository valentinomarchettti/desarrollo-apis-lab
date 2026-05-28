from collections import OrderedDict

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .github_oauth_views import (
    github_connect,
    github_oauth_callback,
    github_oauth_link,
)
from .github_pull_request_views import (
    github_pull_request_detail,
    github_pull_request_summary,
)
from .github_repository_views import (
    github_repository_pull_requests,
    github_repositories,
)
from .viewsets import (
    GitHubConnectionViewSet,
    PullRequestViewSet,
    RepositorioViewSet,
    SummaryTecnicoViewSet,
)


class ApiRootRouter(DefaultRouter):
    def get_api_root_view(self, api_urls=None):
        api_root_dict = OrderedDict()
        api_root_dict["github-login"] = "github-connect"
        for prefix, viewset, basename in self.registry:
            api_root_dict[prefix] = self.routes[0].name.format(basename=basename)

        return self.APIRootView.as_view(api_root_dict=api_root_dict)


router = ApiRootRouter()
router.register("github-connections", GitHubConnectionViewSet, basename="github-connection")
router.register("repositorios", RepositorioViewSet, basename="repositorio")
router.register("pull-requests", PullRequestViewSet, basename="pull-request")
router.register("summaries", SummaryTecnicoViewSet, basename="summary-tecnico")

urlpatterns = [
    path("github/connect/", github_connect, name="github-connect"),
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
    path(
        "github/repositorios/<str:owner>/<str:repo>/pull-requests/<int:number>/summary/",
        github_pull_request_summary,
        name="github-pull-request-summary",
    ),
    path("", include(router.urls)),
]
