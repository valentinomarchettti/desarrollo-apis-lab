from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PullRequestViewSet, RepositorioViewSet, SummaryTecnicoViewSet

router = DefaultRouter()
router.register("repositorios", RepositorioViewSet, basename="repositorio")
router.register("pull-requests", PullRequestViewSet, basename="pull-request")
router.register("summaries", SummaryTecnicoViewSet, basename="summary-tecnico")

urlpatterns = [
    path("", include(router.urls)),
]
