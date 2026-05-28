from rest_framework import viewsets

from .models import GitHubConnection, PullRequest, Repositorio, SummaryTecnico
from .permissions import ViewDjangoModelPermissions
from .serializers import (
    GitHubConnectionSerializer,
    PullRequestSerializer,
    RepositorioSerializer,
    SummaryTecnicoSerializer,
)


class RepositorioViewSet(viewsets.ModelViewSet):
    queryset = Repositorio.objects.all()
    serializer_class = RepositorioSerializer
    permission_classes = [ViewDjangoModelPermissions]


class GitHubConnectionViewSet(viewsets.ModelViewSet):
    queryset = GitHubConnection.objects.all()
    serializer_class = GitHubConnectionSerializer
    permission_classes = [ViewDjangoModelPermissions]


class PullRequestViewSet(viewsets.ModelViewSet):
    queryset = PullRequest.objects.all()
    serializer_class = PullRequestSerializer
    permission_classes = [ViewDjangoModelPermissions]


class SummaryTecnicoViewSet(viewsets.ModelViewSet):
    queryset = SummaryTecnico.objects.all()
    serializer_class = SummaryTecnicoSerializer
    permission_classes = [ViewDjangoModelPermissions]
