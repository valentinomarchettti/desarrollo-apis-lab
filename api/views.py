from rest_framework import viewsets

from .models import PullRequest, Repositorio, SummaryTecnico
from .serializers import (
    PullRequestSerializer,
    RepositorioSerializer,
    SummaryTecnicoSerializer,
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
