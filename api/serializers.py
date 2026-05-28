from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from .models import GitHubConnection, PullRequest, Repositorio, SummaryTecnico


class GitHubConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GitHubConnection
        fields = "__all__"
        extra_kwargs = {
            "github_user_id": {
                "help_text": "Identificador numerico del usuario autenticado en GitHub.",
            },
            "github_login": {
                "help_text": "Nombre de usuario de GitHub asociado a la conexión OAuth.",
            },
            "html_url": {
                "help_text": "URL publica del perfil de GitHub conectado.",
            },
            "access_token": {
                "write_only": True,
                "help_text": (
                    "Token OAuth usado por la API para consultar GitHub. Es de solo escritura "
                    "y nunca se devuelve en las respuestas."
                ),
            },
            "token_type": {
                "help_text": "Tipo de token devuelto por GitHub, normalmente `bearer`.",
            },
            "scope": {
                "help_text": "Permisos OAuth concedidos por GitHub para esta conexión.",
            },
            "activo": {
                "help_text": (
                    "Indica si esta conexión es la credencial activa que usarán los endpoints "
                    "remotos de GitHub."
                ),
            },
            "connected_at": {
                "help_text": "Fecha y hora en que se vinculo o renovo la cuenta de GitHub.",
            },
            "last_used_at": {
                "help_text": "Última fecha en que la API usó esta conexión para consultar GitHub.",
            },
        }


class RepositorioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Repositorio
        fields = "__all__"
        extra_kwargs = {
            "nombre": {
                "help_text": "Nombre corto del repositorio dentro de GitHub.",
            },
            "github_owner": {
                "help_text": "Usuario u organización propietaria del repositorio en GitHub.",
            },
            "github_repo": {
                "help_text": "Nombre exacto del repositorio en GitHub, usado para construir consultas remotas.",
            },
            "url": {
                "help_text": "URL publica del repositorio en GitHub.",
            },
            "descripcion": {
                "help_text": "Descripción local opcional para identificar el repositorio dentro de la API.",
            },
            "activo": {
                "help_text": "Indica si el repositorio sigue habilitado para seguimiento local de pull requests.",
            },
        }


class PullRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = PullRequest
        fields = "__all__"
        extra_kwargs = {
            "repositorio": {
                "help_text": "Repositorio local al que pertenece este pull request.",
            },
            "numero": {
                "help_text": "Número del pull request dentro del repositorio de GitHub.",
            },
            "titulo": {
                "help_text": "Titulo actual o registrado del pull request.",
            },
            "estado": {
                "help_text": "Estado local del pull request: `open`, `closed` o `merged`.",
            },
            "rama_origen": {
                "help_text": "Rama desde la que se propone el cambio.",
            },
            "rama_destino": {
                "help_text": "Rama base hacia la que apunta el pull request.",
            },
            "autor_github": {
                "help_text": "Usuario de GitHub que creó el pull request.",
            },
            "url": {
                "help_text": "URL publica del pull request en GitHub.",
            },
        }


@extend_schema_serializer(component_name="ResumenTecnico")
class SummaryTecnicoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SummaryTecnico
        fields = "__all__"
        extra_kwargs = {
            "pull_request": {
                "help_text": "Pull request local para el que se generó el resumen técnico.",
            },
            "contenido": {
                "help_text": "Texto del resumen técnico generado por la IA a partir del diff del pull request.",
            },
            "estado": {
                "help_text": "Estado del resumen: `pending`, `generated` o `failed`.",
            },
            "error_message": {
                "help_text": "Detalle del error cuando la generación del resumen falla.",
            },
        }
