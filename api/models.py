from django.db import models
from django.utils import timezone


class GitHubConnection(models.Model):
    github_user_id = models.PositiveBigIntegerField(unique=True)
    github_login = models.CharField(max_length=255)
    html_url = models.URLField(blank=True)
    access_token = models.TextField()
    token_type = models.CharField(max_length=50, blank=True)
    scope = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)
    connected_at = models.DateTimeField(default=timezone.now)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.github_login


class Repositorio(models.Model):
    nombre = models.CharField(max_length=255)
    github_owner = models.CharField(max_length=255)
    github_repo = models.CharField(max_length=255)
    url = models.URLField()
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.github_owner}/{self.github_repo}"


class PullRequest(models.Model):
    ESTADO_OPEN = "open"
    ESTADO_CLOSED = "closed"
    ESTADO_MERGED = "merged"

    ESTADO_CHOICES = [
        (ESTADO_OPEN, "Open"),
        (ESTADO_CLOSED, "Closed"),
        (ESTADO_MERGED, "Merged"),
    ]

    repositorio = models.ForeignKey(
        Repositorio,
        on_delete=models.CASCADE,
        related_name="pull_requests",
    )
    numero = models.PositiveIntegerField()
    titulo = models.CharField(max_length=255)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES)
    rama_origen = models.CharField(max_length=255, blank=True)
    rama_destino = models.CharField(max_length=255, blank=True)
    autor_github = models.CharField(max_length=255, blank=True)
    url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["repositorio", "numero"],
                name="unique_pr_numero_por_repositorio",
            )
        ]

    def __str__(self):
        return f"PR #{self.numero} - {self.titulo}"


class SummaryTecnico(models.Model):
    ESTADO_PENDING = "pending"
    ESTADO_GENERATED = "generated"
    ESTADO_FAILED = "failed"

    ESTADO_CHOICES = [
        (ESTADO_PENDING, "Pending"),
        (ESTADO_GENERATED, "Generated"),
        (ESTADO_FAILED, "Failed"),
    ]

    pull_request = models.ForeignKey(
        PullRequest,
        on_delete=models.CASCADE,
        related_name="summaries",
    )
    contenido = models.TextField()
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Summary {self.id} for PR #{self.pull_request.numero}"
