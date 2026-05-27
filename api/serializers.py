from rest_framework import serializers

from .models import GitHubConnection, PullRequest, Repositorio, SummaryTecnico


class GitHubConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GitHubConnection
        fields = "__all__"
        extra_kwargs = {
            "access_token": {"write_only": True},
        }


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
