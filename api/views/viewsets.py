from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view
from rest_framework import viewsets

from api.models import GitHubConnection, PullRequest, Repositorio, SummaryTecnico
from api.permissions import ViewDjangoModelPermissions
from api.serializers import (
    GitHubConnectionSerializer,
    PullRequestSerializer,
    RepositorioSerializer,
    SummaryTecnicoSerializer,
)


CONEXIONES_TAG = "Conexiones GitHub locales"
REPOSITORIOS_TAG = "Repositorios locales"
PULL_REQUESTS_TAG = "Pull Requests locales"
RESUMENES_TAG = "Resúmenes técnicos locales"

CONEXIONES_DESCRIPTION = (
    "Representan la credencial OAuth de GitHub guardada por la API. La forma "
    "recomendada de crearlas o renovarlas es mediante el flujo OAuth en "
    "`/api/github/connect/` o `/api/github/oauth/link/`. Estos registros se usan "
    "para que la API consulte GitHub en nombre de la cuenta conectada; el "
    "`access_token` es de solo escritura y no se expone en las respuestas."
)

REPOSITORIOS_DESCRIPTION = (
    "Representan repositorios de GitHub guardados en la base local para seguimiento. "
    "No crean ni modifican repositorios en GitHub: sirven para relacionar pull "
    "requests locales, activar o desactivar seguimiento y conservar contexto propio "
    "de la API."
)

PULL_REQUESTS_DESCRIPTION = (
    "Representan pull requests guardados localmente para un repositorio. No abren, "
    "cierran ni mergean pull requests en GitHub; funcionan como registro interno "
    "para asociar estados, ramas, autor, URL y resúmenes técnicos generados."
)

RESUMENES_DESCRIPTION = (
    "Representan el historial local de resúmenes técnicos generados para pull "
    "requests. La generación real con IA y, si corresponde, la publicación en GitHub "
    "se hace desde el endpoint remoto `/api/github/repositorios/{owner}/{repo}/"
    "pull-requests/{number}/summary/`."
)

REPOSITORIO_ID_PARAMETER = OpenApiParameter(
    name="id",
    type=OpenApiTypes.INT,
    location=OpenApiParameter.PATH,
    description="ID local del repositorio guardado en la API.",
)
CONEXION_ID_PARAMETER = OpenApiParameter(
    name="id",
    type=OpenApiTypes.INT,
    location=OpenApiParameter.PATH,
    description="ID local de la conexión de GitHub guardada en la API.",
)
PULL_REQUEST_ID_PARAMETER = OpenApiParameter(
    name="id",
    type=OpenApiTypes.INT,
    location=OpenApiParameter.PATH,
    description="ID local del pull request guardado en la API.",
)
RESUMEN_ID_PARAMETER = OpenApiParameter(
    name="id",
    type=OpenApiTypes.INT,
    location=OpenApiParameter.PATH,
    description="ID local del resumen técnico guardado en la API.",
)


@extend_schema_view(
    list=extend_schema(
        tags=[REPOSITORIOS_TAG],
        summary="Listar repositorios locales",
        description=REPOSITORIOS_DESCRIPTION,
    ),
    retrieve=extend_schema(
        tags=[REPOSITORIOS_TAG],
        summary="Obtener repositorio local",
        parameters=[REPOSITORIO_ID_PARAMETER],
        description=(
            f"{REPOSITORIOS_DESCRIPTION} Usa este detalle cuando necesites consultar "
            "la configuración local de seguimiento de un repositorio concreto."
        ),
    ),
    create=extend_schema(
        tags=[REPOSITORIOS_TAG],
        summary="Crear repositorio local",
        description=(
            f"{REPOSITORIOS_DESCRIPTION} Esta operacion registra un repositorio ya "
            "existente en GitHub dentro de la API local."
        ),
    ),
    update=extend_schema(
        tags=[REPOSITORIOS_TAG],
        summary="Actualizar repositorio local",
        parameters=[REPOSITORIO_ID_PARAMETER],
        description=(
            "Reemplaza los datos locales del repositorio. No modifica nombre, descripción "
            "ni configuración del repositorio remoto en GitHub."
        ),
    ),
    partial_update=extend_schema(
        tags=[REPOSITORIOS_TAG],
        summary="Actualizar parcialmente repositorio local",
        parameters=[REPOSITORIO_ID_PARAMETER],
        description=(
            "Actualiza solo algunos campos locales, por ejemplo `descripcion` o `activo`, "
            "sin afectar el repositorio remoto en GitHub."
        ),
    ),
    destroy=extend_schema(
        tags=[REPOSITORIOS_TAG],
        summary="Eliminar repositorio local",
        parameters=[REPOSITORIO_ID_PARAMETER],
        description=(
            "Elimina el registro local del repositorio. No elimina el repositorio en GitHub."
        ),
    ),
)


class RepositorioViewSet(viewsets.ModelViewSet):
    queryset = Repositorio.objects.all()
    serializer_class = RepositorioSerializer
    permission_classes = [ViewDjangoModelPermissions]


@extend_schema_view(
    list=extend_schema(
        tags=[CONEXIONES_TAG],
        summary="Listar conexiones GitHub",
        description=CONEXIONES_DESCRIPTION,
    ),
    retrieve=extend_schema(
        tags=[CONEXIONES_TAG],
        parameters=[CONEXION_ID_PARAMETER],
        summary="Obtener conexión GitHub",
        description=(
            f"{CONEXIONES_DESCRIPTION} Usa este detalle para verificar usuario, scopes, "
            "estado activo y fechas de conexión."
        ),
    ),
    create=extend_schema(
        tags=[CONEXIONES_TAG],
        summary="Crear conexión GitHub local",
        description=(
            "Crea una conexión OAuth manualmente en la base local. En uso normal conviene "
            "usar el flujo OAuth para que GitHub entregue `access_token`, `scope` y datos "
            "del usuario conectado."
        ),
    ),
    update=extend_schema(
        tags=[CONEXIONES_TAG],
        parameters=[CONEXION_ID_PARAMETER],
        summary="Actualizar conexión GitHub local",
        description=(
            "Reemplaza los datos locales de una conexión. Sirve para administración o "
            "corrección manual de la credencial guardada."
        ),
    ),
    partial_update=extend_schema(
        tags=[CONEXIONES_TAG],
        parameters=[CONEXION_ID_PARAMETER],
        summary="Actualizar parcialmente conexión GitHub local",
        description=(
            "Actualiza campos puntuales de la conexión, por ejemplo marcarla como activa "
            "o inactiva."
        ),
    ),
    destroy=extend_schema(
        tags=[CONEXIONES_TAG],
        parameters=[CONEXION_ID_PARAMETER],
        summary="Eliminar conexión GitHub local",
        description=(
            "Elimina la credencial OAuth guardada localmente. Después de eliminarla, los "
            "endpoints que consultan GitHub no podrán operar hasta conectar una cuenta nueva."
        ),
    ),
)
class GitHubConnectionViewSet(viewsets.ModelViewSet):
    queryset = GitHubConnection.objects.all()
    serializer_class = GitHubConnectionSerializer
    permission_classes = [ViewDjangoModelPermissions]


@extend_schema_view(
    list=extend_schema(
        tags=[PULL_REQUESTS_TAG],
        summary="Listar pull requests locales",
        description=PULL_REQUESTS_DESCRIPTION,
    ),
    retrieve=extend_schema(
        tags=[PULL_REQUESTS_TAG],
        summary="Obtener pull request local",
        parameters=[PULL_REQUEST_ID_PARAMETER],
        description=(
            f"{PULL_REQUESTS_DESCRIPTION} Usa este detalle para consultar el registro "
            "local asociado a un PR de GitHub."
        ),
    ),
    create=extend_schema(
        tags=[PULL_REQUESTS_TAG],
        summary="Crear pull request local",
        description=(
            f"{PULL_REQUESTS_DESCRIPTION} Esta operacion guarda un PR ya existente de "
            "GitHub como referencia local."
        ),
    ),
    update=extend_schema(
        tags=[PULL_REQUESTS_TAG],
        summary="Actualizar pull request local",
        parameters=[PULL_REQUEST_ID_PARAMETER],
        description=(
            "Reemplaza los datos locales del pull request. No actualiza el pull request "
            "remoto en GitHub."
        ),
    ),
    partial_update=extend_schema(
        tags=[PULL_REQUESTS_TAG],
        summary="Actualizar parcialmente pull request local",
        parameters=[PULL_REQUEST_ID_PARAMETER],
        description=(
            "Actualiza campos puntuales del registro local, como estado, ramas, autor o URL."
        ),
    ),
    destroy=extend_schema(
        tags=[PULL_REQUESTS_TAG],
        summary="Eliminar pull request local",
        parameters=[PULL_REQUEST_ID_PARAMETER],
        description=(
            "Elimina el registro local del pull request. No borra ni modifica el pull request "
            "en GitHub."
        ),
    ),
)
class PullRequestViewSet(viewsets.ModelViewSet):
    queryset = PullRequest.objects.all()
    serializer_class = PullRequestSerializer
    permission_classes = [ViewDjangoModelPermissions]


@extend_schema_view(
    list=extend_schema(
        tags=[RESUMENES_TAG],
        summary="Listar resúmenes técnicos",
        description=RESUMENES_DESCRIPTION,
    ),
    retrieve=extend_schema(
        tags=[RESUMENES_TAG],
        summary="Obtener resumen técnico",
        parameters=[RESUMEN_ID_PARAMETER],
        description=(
            f"{RESUMENES_DESCRIPTION} Usa este detalle para ver el contenido, estado y "
            "posible error de un resumen generado."
        ),
    ),
    create=extend_schema(
        tags=[RESUMENES_TAG],
        summary="Crear resumen técnico local",
        description=(
            "Crea un resumen técnico manualmente en la base local. Para generar el texto "
            "con IA desde el diff del PR, usa el endpoint remoto de summary."
        ),
    ),
    update=extend_schema(
        tags=[RESUMENES_TAG],
        summary="Actualizar resumen técnico local",
        parameters=[RESUMEN_ID_PARAMETER],
        description=(
            "Reemplaza los datos locales del resumen. No vuelve a ejecutar la IA ni publica "
            "cambios en GitHub."
        ),
    ),
    partial_update=extend_schema(
        tags=[RESUMENES_TAG],
        summary="Actualizar parcialmente resumen técnico local",
        parameters=[RESUMEN_ID_PARAMETER],
        description=(
            "Actualiza campos puntuales del resumen, por ejemplo `estado`, `contenido` o "
            "`error_message`."
        ),
    ),
    destroy=extend_schema(
        tags=[RESUMENES_TAG],
        summary="Eliminar resumen técnico local",
        parameters=[RESUMEN_ID_PARAMETER],
        description=(
            "Elimina el resumen de la base local. No modifica la descripción del pull request "
            "en GitHub si ya fue publicada."
        ),
    ),
)
class SummaryTecnicoViewSet(viewsets.ModelViewSet):
    queryset = SummaryTecnico.objects.all()
    serializer_class = SummaryTecnicoSerializer
    permission_classes = [ViewDjangoModelPermissions]
