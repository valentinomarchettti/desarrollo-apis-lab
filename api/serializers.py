from datetime import datetime
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import ValidationError as DRFValidationError
from drf_spectacular.utils import extend_schema_serializer

from .models import GitHubConnection, PullRequest, Repositorio, SummaryTecnico


class GitHubConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GitHubConnection
        fields = "__all__"
        extra_kwargs = {
            "github_user_id": {"help_text": "Identificador numerico del usuario autenticado en GitHub."},
            "github_login": {"help_text": "Nombre de usuario de GitHub asociado a la conexión OAuth."},
            "html_url": {"help_text": "URL publica del perfil de GitHub conectado."},
            "access_token": {
                "write_only": True,
                "help_text": "Token OAuth usado por la API para consultar GitHub. Es de solo escritura y nunca se devuelve en las respuestas.",
            },
            "token_type": {"help_text": "Tipo de token devuelto por GitHub, normalmente `bearer`."},
            "scope": {"help_text": "Permisos OAuth concedidos por GitHub para esta conexión."},
            "activo": {"help_text": "Indica si esta conexión es la credencial activa que usarán los endpoints remotos de GitHub."},
            "connected_at": {"help_text": "Fecha y hora en que se vinculo o renovo la cuenta de GitHub."},
            "last_used_at": {"help_text": "Última fecha en que la API usó esta conexión para consultar GitHub."},
        }

    def validate(self, data):
        """Validación advanced de consistencia temporal en credenciales."""
        connected_at = data.get("connected_at")
        last_used_at = data.get("last_used_at")

        # Evitar anomalías temporales si se actualiza el historial
        if last_used_at and connected_at and last_used_at < connected_at:
            raise serializers.ValidationError({
                "last_used_at": "La fecha de último uso no puede ser anterior a la fecha de conexión del token."
            })
        # Ejemplo práctico de datetime: Evitar que connected_at sea una fecha futura incoherente
        if connected_at and connected_at.replace(tzinfo=None) > datetime.now():
            raise serializers.ValidationError({
                "connected_at": "La fecha de conexión no puede ser una fecha futura."
            })
        return data


class RepositorioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Repositorio
        fields = "__all__"
        extra_kwargs = {
            "nombre": {"help_text": "Nombre corto del repositorio dentro de GitHub."},
            "github_owner": {"help_text": "Usuario u organización propietaria del repositorio en GitHub."},
            "github_repo": {"help_text": "Nombre exacto del repositorio en GitHub, usado para construir consultas remotas."},
            "url": {"help_text": "URL publica del repositorio en GitHub."},
            "descripcion": {"help_text": "Descripción local opcional para identificar el repositorio dentro de la API."},
            "activo": {"help_text": "Indica si el repositorio sigue habilitado para seguimiento local de pull requests."},
        }

    def validate_url(self, value):
        """Garantiza que la URL estructurada coincida con el dominio base de GitHub."""
        if not value.lower().startswith("https://github.com/"):
            raise serializers.ValidationError("La URL provista debe ser un enlace válido hacia https://github.com/")
        return value

    def validate(self, data):
        """Verifica la coherencia cruzada entre los strings identificadores y la URL definitiva."""
        owner = data.get("github_owner")
        repo = data.get("github_repo")
        url = data.get("url", "")

        expected_segment = f"github.com/{owner}/{repo}".lower()
        if owner and repo and expected_segment not in url.lower():
            raise serializers.ValidationError({
                "url": f"La URL no coincide con el propietario y repositorio indicados. Debería contener: '{expected_segment}'"
            })
        return data


class PullRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = PullRequest
        fields = "__all__"
        extra_kwargs = {
            "repositorio": {"help_text": "Repositorio local al que pertenece este pull request."},
            "numero": {"help_text": "Número del pull request dentro del repositorio de GitHub."},
            "titulo": {"help_text": "Titulo actual o registrado del pull request."},
            "estado": {"help_text": "Estado local del pull request: `open`, `closed` o `merged`."},
            "rama_origen": {"help_text": "Rama desde la que se propone el cambio."},
            "rama_destino": {"help_text": "Rama base hacia la que apunta el pull request."},
            "autor_github": {"help_text": "Usuario de GitHub que creó el pull request."},
            "url": {"help_text": "URL publica del pull request en GitHub."},
        }

    def validate(self, data):
        """Valida que los datos correspondan coherentemente al Repositorio local asignado."""
        repositorio = data.get("repositorio")
        numero = data.get("numero")
        url = data.get("url", "")

        # Verificación lógica cruzada: la URL del PR debe incluir el owner/repo del modelo relacional
        if repositorio and numero and url:
            expected_url_pattern = f"github.com/{repositorio.github_owner}/{repositorio.github_repo}/pull/{numero}".lower()
            if expected_url_pattern not in url.lower():
                raise serializers.ValidationError({
                    "url": f"La URL del Pull Request no es consistente con el repositorio seleccionado o el número de PR. Se esperaba el patrón: {expected_url_pattern}"
                })
        return data


@extend_schema_serializer(component_name="ResumenTecnico")
class SummaryTecnicoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SummaryTecnico
        fields = "__all__"
        extra_kwargs = {
            "pull_request": {"help_text": "Pull request local para el que se generó el resumen técnico."},
            "contenido": {"help_text": "Texto del resumen técnico generado por la IA a partir del diff del pull request."},
            "estado": {"help_text": "Estado del resumen: `pending`, `generated` o `failed`."},
            "error_message": {"help_text": "Detalle del error cuando la generación del resumen falla."},
        }

    def validate(self, data):
        """
        Garantiza la consistencia lógica de estados y mapea errores nativos del Modelo
        hacia respuestas serializadas legibles en formato JSON (Estrategia de la Cátedra).
        """
        estado = data.get("estado")
        contenido = data.get("contenido")
        error_message = data.get("error_message")

        # Regla 1: Coherencia multi-campo estricta para el proceso asíncrono/IA
        if estado == "failed" and not error_message:
            raise serializers.ValidationError({
                "error_message": "Si el estado se define como 'failed', debe proveerse obligatoriamente un mensaje de error."
            })

        if estado == "generated" and not contenido:
            raise serializers.ValidationError({
                "contenido": "Un resumen en estado 'generated' debe contar obligatoriamente con el texto de análisis técnico."
            })

        if estado == "pending" and (contenido or error_message):
            raise serializers.ValidationError({
                "estado": "Un resumen en estado 'pending' no puede contener texto ni mensajes de error previos."
            })

        # Regla 2: Buenas prácticas de la cátedra - Forzar ejecución de restricciones del modelo limpio
        try:
            # Creamos una instancia en memoria simulada para ejecutar su lógica interna si existiese
            instance = SummaryTecnico(**data)
            instance.clean()
        except DjangoValidationError as e:
            # Transforma el diccionario de errores de Django nativo a una excepción que DRF convierte en JSON (HTTP 400)
            raise DRFValidationError(e.message_dict)

        return data