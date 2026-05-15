from django.contrib import admin

from .models import PullRequest, Repositorio, SummaryTecnico


@admin.register(Repositorio)
class RepositorioAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "github_owner", "github_repo", "activo", "created_at")
    search_fields = ("nombre", "github_owner", "github_repo")


@admin.register(PullRequest)
class PullRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "repositorio", "numero", "titulo", "estado", "created_at")
    list_filter = ("estado", "repositorio")
    search_fields = ("titulo", "autor_github")


@admin.register(SummaryTecnico)
class SummaryTecnicoAdmin(admin.ModelAdmin):
    list_display = ("id", "pull_request", "estado", "created_at")
    list_filter = ("estado",)
