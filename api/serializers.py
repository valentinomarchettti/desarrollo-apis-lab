from rest_framework import serializers

from .models import PullRequest, Repositorio, SummaryTecnico


class RepositorioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Repositorio
        fields = "__all__"


class PullRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = PullRequest
        fields = "__all__"


class SummaryTecnicoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SummaryTecnico
        fields = "__all__"
