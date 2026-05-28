from rest_framework import serializers

from api.models import PullRequest


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField(help_text="Mensaje principal del error devuelto por la API.")
    detail = serializers.CharField(
        required=False,
        help_text="Detalle técnico adicional, cuando la API puede incluirlo.",
    )
    missing_settings = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Variables de entorno faltantes para completar la operación.",
    )
    github_response = serializers.JSONField(
        required=False,
        help_text="Respuesta original o resumida devuelta por GitHub cuando el error viene de GitHub.",
    )
    descripcion_actualizada_en_github = serializers.BooleanField(
        required=False,
        help_text="Indica si GitHub llegó a actualizar la descripción antes de que fallara el guardado local.",
    )


class TokenObtainPairRequestSerializer(serializers.Serializer):
    username = serializers.CharField(
        help_text="Nombre de usuario local registrado en Django.",
    )
    password = serializers.CharField(
        write_only=True,
        help_text="Contraseña del usuario local. Se envía solo en el request y nunca se devuelve.",
    )


class TokenObtainPairResponseSerializer(serializers.Serializer):
    refresh = serializers.CharField(
        help_text="Token de renovación. Sirve para pedir un nuevo `access` cuando expire.",
    )
    access = serializers.CharField(
        help_text="Token JWT de acceso. Enviá este valor como `Authorization: Bearer <access_token>`.",
    )


class TokenRefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(
        help_text="Token `refresh` obtenido previamente desde `/api/auth/token/`.",
    )


class TokenRefreshResponseSerializer(serializers.Serializer):
    access = serializers.CharField(
        help_text="Nuevo token JWT de acceso para seguir consumiendo endpoints protegidos.",
    )


class OAuthLinkResponseSerializer(serializers.Serializer):
    authorization_url = serializers.URLField(
        help_text="URL de GitHub donde el usuario debe autorizar la aplicación."
    )
    state = serializers.CharField(
        help_text="Valor temporal usado para validar que el callback pertenece al flujo iniciado."
    )
    expires_in_seconds = serializers.IntegerField(
        help_text="Cantidad de segundos durante los que el `state` sigue siendo válido."
    )


class GitHubUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(help_text="Identificador del usuario en GitHub.")
    login = serializers.CharField(help_text="Nombre de usuario de GitHub.")
    html_url = serializers.URLField(
        allow_blank=True,
        allow_null=True,
        help_text="URL pública del perfil de GitHub.",
    )


class OAuthCallbackResponseSerializer(serializers.Serializer):
    message = serializers.CharField(help_text="Mensaje de confirmación de la conexión.")
    connected = serializers.BooleanField(help_text="Indica si la cuenta quedó conectada correctamente.")
    connection_id = serializers.IntegerField(help_text="ID local de la conexión guardada.")
    token_type = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Tipo de token informado por GitHub.",
    )
    scope = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Scopes concedidos por GitHub para esta conexión.",
    )
    github_user = GitHubUserSerializer()
    warning = serializers.CharField(help_text="Advertencia sobre el almacenamiento seguro del token.")


class GitHubRepositorySerializer(serializers.Serializer):
    github_id = serializers.IntegerField(allow_null=True, help_text="ID remoto del repositorio en GitHub.")
    nombre = serializers.CharField(allow_blank=True, help_text="Nombre corto del repositorio.")
    full_name = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Nombre completo en GitHub con formato `owner/repo`.",
    )
    owner = serializers.CharField(allow_blank=True, help_text="Usuario u organización propietaria.")
    html_url = serializers.URLField(
        allow_blank=True,
        allow_null=True,
        help_text="URL pública del repositorio en GitHub.",
    )
    private = serializers.BooleanField(allow_null=True, help_text="Indica si el repositorio es privado.")
    descripcion = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Descripción remota del repositorio en GitHub.",
    )
    default_branch = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Rama principal configurada en GitHub.",
    )
    linkeado_a_api = serializers.BooleanField(
        help_text="Indica si el repositorio ya existe como registro local en la API."
    )
    seguimiento_pr_activado = serializers.BooleanField(
        help_text="Indica si el repositorio local está activo para seguimiento de pull requests."
    )
    repositorio_api_id = serializers.IntegerField(
        allow_null=True,
        help_text="ID local del repositorio cuando ya está guardado en la API.",
    )
    link_detalle = serializers.URLField(
        help_text="URL de la API para consultar pull requests de este repositorio."
    )


class GitHubRepositoryListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField(help_text="Cantidad de repositorios devueltos.")
    repositorios = GitHubRepositorySerializer(many=True)


class GitHubRepositoryStateSerializer(serializers.Serializer):
    owner = serializers.CharField(help_text="Owner u organización del repositorio.")
    repo = serializers.CharField(help_text="Nombre del repositorio.")
    linkeado_a_api = serializers.BooleanField(help_text="Indica si el repositorio existe localmente.")
    seguimiento_pr_activado = serializers.BooleanField(
        help_text="Indica si el seguimiento local de pull requests está activo."
    )
    repositorio_api_id = serializers.IntegerField(
        allow_null=True,
        help_text="ID local del repositorio cuando existe en la API.",
    )


class GitHubPullRequestListItemSerializer(serializers.Serializer):
    github_id = serializers.IntegerField(allow_null=True, help_text="ID remoto del pull request en GitHub.")
    numero = serializers.IntegerField(allow_null=True, help_text="Número del pull request en GitHub.")
    titulo = serializers.CharField(allow_blank=True, allow_null=True, help_text="Título del pull request.")
    estado = serializers.ChoiceField(
        choices=PullRequest.ESTADO_CHOICES,
        help_text="Estado calculado del pull request: `open`, `closed` o `merged`.",
    )
    draft = serializers.BooleanField(allow_null=True, help_text="Indica si el PR está en modo draft.")
    rama_origen = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Rama de origen del pull request.",
    )
    rama_destino = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Rama base o destino del pull request.",
    )
    autor_github = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Usuario de GitHub que creó el pull request.",
    )
    html_url = serializers.URLField(
        allow_blank=True,
        allow_null=True,
        help_text="URL pública del pull request en GitHub.",
    )
    created_at = serializers.DateTimeField(allow_null=True, help_text="Fecha de creación en GitHub.")
    updated_at = serializers.DateTimeField(allow_null=True, help_text="Última actualización en GitHub.")
    closed_at = serializers.DateTimeField(allow_null=True, help_text="Fecha de cierre, si aplica.")
    merged_at = serializers.DateTimeField(allow_null=True, help_text="Fecha de merge, si aplica.")
    guardado_en_api = serializers.BooleanField(help_text="Indica si el PR ya está guardado localmente.")
    pull_request_api_id = serializers.IntegerField(
        allow_null=True,
        help_text="ID local del pull request cuando ya está guardado en la API.",
    )
    link_detalle = serializers.URLField(help_text="URL de la API para consultar el detalle técnico del PR.")


class GitHubPullRequestListResponseSerializer(serializers.Serializer):
    repositorio = GitHubRepositoryStateSerializer()
    state = serializers.ChoiceField(
        choices=["open", "closed", "all"],
        help_text="Filtro de estado aplicado a la consulta.",
    )
    count = serializers.IntegerField(help_text="Cantidad de pull requests devueltos.")
    pull_requests = GitHubPullRequestListItemSerializer(many=True)


class PullRequestLabelSerializer(serializers.Serializer):
    name = serializers.CharField(allow_blank=True, allow_null=True, help_text="Nombre de la label.")
    color = serializers.CharField(allow_blank=True, allow_null=True, help_text="Color hexadecimal de la label.")


class PullRequestDetailSerializer(serializers.Serializer):
    github_id = serializers.IntegerField(allow_null=True, help_text="ID remoto del pull request en GitHub.")
    numero = serializers.IntegerField(allow_null=True, help_text="Número del pull request en GitHub.")
    titulo = serializers.CharField(allow_blank=True, allow_null=True, help_text="Título del pull request.")
    descripcion = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Descripción actual del pull request en GitHub.",
    )
    estado = serializers.ChoiceField(
        choices=PullRequest.ESTADO_CHOICES,
        help_text="Estado calculado del pull request: `open`, `closed` o `merged`.",
    )
    draft = serializers.BooleanField(allow_null=True, help_text="Indica si el PR está en modo draft.")
    autor_github = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Usuario de GitHub que creó el pull request.",
    )
    html_url = serializers.URLField(
        allow_blank=True,
        allow_null=True,
        help_text="URL pública del pull request en GitHub.",
    )
    rama_origen = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Rama desde la que se propone el cambio.",
    )
    rama_destino = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Rama base hacia la que apunta el pull request.",
    )
    created_at = serializers.DateTimeField(allow_null=True, help_text="Fecha de creación en GitHub.")
    updated_at = serializers.DateTimeField(allow_null=True, help_text="Última actualización en GitHub.")
    closed_at = serializers.DateTimeField(allow_null=True, help_text="Fecha de cierre, si aplica.")
    merged_at = serializers.DateTimeField(allow_null=True, help_text="Fecha de merge, si aplica.")
    mergeable = serializers.BooleanField(
        allow_null=True,
        help_text="Valor informado por GitHub sobre si el PR puede mergearse.",
    )
    merged = serializers.BooleanField(allow_null=True, help_text="Indica si el PR fue mergeado.")
    commits = serializers.IntegerField(allow_null=True, help_text="Cantidad de commits del PR.")
    changed_files = serializers.IntegerField(allow_null=True, help_text="Cantidad de archivos modificados.")
    additions = serializers.IntegerField(allow_null=True, help_text="Cantidad total de líneas agregadas.")
    deletions = serializers.IntegerField(allow_null=True, help_text="Cantidad total de líneas eliminadas.")
    labels = PullRequestLabelSerializer(many=True)
    assignees = serializers.ListField(
        child=serializers.CharField(),
        help_text="Usuarios asignados al pull request.",
    )
    requested_reviewers = serializers.ListField(
        child=serializers.CharField(),
        help_text="Reviewers solicitados en GitHub.",
    )
    guardado_en_api = serializers.BooleanField(help_text="Indica si el PR ya está guardado localmente.")
    pull_request_api_id = serializers.IntegerField(
        allow_null=True,
        help_text="ID local del pull request cuando ya está guardado en la API.",
    )


class PullRequestFileSerializer(serializers.Serializer):
    sha = serializers.CharField(allow_blank=True, allow_null=True, help_text="SHA del archivo informado por GitHub.")
    filename = serializers.CharField(allow_blank=True, allow_null=True, help_text="Ruta del archivo modificado.")
    status = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Estado del archivo en el PR, por ejemplo `added`, `modified` o `removed`.",
    )
    additions = serializers.IntegerField(allow_null=True, help_text="Líneas agregadas en este archivo.")
    deletions = serializers.IntegerField(allow_null=True, help_text="Líneas eliminadas en este archivo.")
    changes = serializers.IntegerField(allow_null=True, help_text="Cantidad total de cambios en este archivo.")
    blob_url = serializers.URLField(allow_blank=True, allow_null=True, help_text="URL del blob en GitHub.")
    raw_url = serializers.URLField(allow_blank=True, allow_null=True, help_text="URL raw del archivo en GitHub.")
    contents_url = serializers.URLField(
        allow_blank=True,
        allow_null=True,
        help_text="URL de la API de GitHub para el contenido del archivo.",
    )
    patch = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Fragmento de diff correspondiente a este archivo.",
    )


class PullRequestCommitSerializer(serializers.Serializer):
    sha = serializers.CharField(allow_blank=True, allow_null=True, help_text="SHA completo del commit.")
    short_sha = serializers.CharField(allow_blank=True, help_text="SHA corto de 7 caracteres.")
    message = serializers.CharField(allow_blank=True, allow_null=True, help_text="Mensaje del commit.")
    author = serializers.CharField(allow_blank=True, allow_null=True, help_text="Autor declarado en el commit.")
    author_email = serializers.EmailField(
        allow_blank=True,
        allow_null=True,
        help_text="Email del autor declarado en el commit.",
    )
    author_date = serializers.DateTimeField(allow_null=True, help_text="Fecha de autoría del commit.")
    committer = serializers.CharField(allow_blank=True, allow_null=True, help_text="Committer del commit.")
    committer_date = serializers.DateTimeField(allow_null=True, help_text="Fecha en que se commiteó el cambio.")
    html_url = serializers.URLField(allow_blank=True, allow_null=True, help_text="URL del commit en GitHub.")


class PullRequestCommentSerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True, help_text="ID del comentario en GitHub.")
    autor_github = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Usuario que escribió el comentario.",
    )
    body = serializers.CharField(allow_blank=True, allow_null=True, help_text="Contenido del comentario.")
    html_url = serializers.URLField(allow_blank=True, allow_null=True, help_text="URL del comentario en GitHub.")
    created_at = serializers.DateTimeField(allow_null=True, help_text="Fecha de creación del comentario.")
    updated_at = serializers.DateTimeField(allow_null=True, help_text="Última actualización del comentario.")


class PullRequestReviewSerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True, help_text="ID de la review en GitHub.")
    state = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Estado de la review, por ejemplo `APPROVED`, `CHANGES_REQUESTED` o `COMMENTED`.",
    )
    autor_github = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Usuario que realizó la review.",
    )
    body = serializers.CharField(allow_blank=True, allow_null=True, help_text="Texto general de la review.")
    commit_id = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Commit asociado a la review.",
    )
    html_url = serializers.URLField(allow_blank=True, allow_null=True, help_text="URL de la review en GitHub.")
    submitted_at = serializers.DateTimeField(allow_null=True, help_text="Fecha de envío de la review.")


class PullRequestReviewCommentSerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True, help_text="ID del comentario de código en GitHub.")
    autor_github = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Usuario que escribió el comentario de código.",
    )
    path = serializers.CharField(allow_blank=True, allow_null=True, help_text="Archivo comentado.")
    position = serializers.IntegerField(allow_null=True, help_text="Posición del comentario dentro del diff.")
    original_position = serializers.IntegerField(
        allow_null=True,
        help_text="Posición original del comentario dentro del diff.",
    )
    line = serializers.IntegerField(allow_null=True, help_text="Línea actual comentada, si GitHub la informa.")
    original_line = serializers.IntegerField(
        allow_null=True,
        help_text="Línea original comentada, si GitHub la informa.",
    )
    side = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Lado del diff comentado, por ejemplo `LEFT` o `RIGHT`.",
    )
    diff_hunk = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="Fragmento de diff alrededor del comentario.",
    )
    body = serializers.CharField(allow_blank=True, allow_null=True, help_text="Contenido del comentario.")
    html_url = serializers.URLField(allow_blank=True, allow_null=True, help_text="URL del comentario en GitHub.")
    created_at = serializers.DateTimeField(allow_null=True, help_text="Fecha de creación del comentario.")
    updated_at = serializers.DateTimeField(allow_null=True, help_text="Última actualización del comentario.")


class PullRequestDetailResponseSerializer(serializers.Serializer):
    repositorio = GitHubRepositoryStateSerializer()
    pull_request = PullRequestDetailSerializer()
    archivos = PullRequestFileSerializer(many=True)
    commits = PullRequestCommitSerializer(many=True)
    comentarios = PullRequestCommentSerializer(many=True)
    reviews = PullRequestReviewSerializer(many=True)
    comentarios_codigo = PullRequestReviewCommentSerializer(many=True)
    diff = serializers.CharField(help_text="Diff completo del pull request en formato texto.")


class GeneratedSummaryPullRequestSerializer(serializers.Serializer):
    numero = serializers.IntegerField(help_text="Número del pull request en GitHub.")
    descripcion_actualizada_en_github = serializers.BooleanField(
        required=False,
        help_text="Indica si la descripción del pull request fue actualizada en GitHub.",
    )
    html_url = serializers.URLField(required=False, help_text="URL del pull request en GitHub.")
    updated_at = serializers.DateTimeField(
        required=False,
        help_text="Fecha de actualización devuelta por GitHub después de publicar el resumen.",
    )
    pull_request_api_id = serializers.IntegerField(
        required=False,
        help_text="ID local del pull request guardado o actualizado.",
    )


class GeneratedSummaryRepositorySerializer(serializers.Serializer):
    owner = serializers.CharField(help_text="Owner u organización del repositorio en GitHub.")
    repo = serializers.CharField(help_text="Nombre del repositorio en GitHub.")
    repositorio_api_id = serializers.IntegerField(
        required=False,
        help_text="ID local del repositorio guardado o actualizado.",
    )


class GeneratedSummaryResponseSerializer(serializers.Serializer):
    repositorio = GeneratedSummaryRepositorySerializer()
    pull_request = GeneratedSummaryPullRequestSerializer()
    summary_tecnico_ia = serializers.CharField(
        help_text="Resumen técnico generado por Gemini a partir del diff del pull request."
    )
    summary_tecnico_api_id = serializers.IntegerField(
        required=False,
        help_text="ID local del resumen técnico guardado.",
    )
    github_response = serializers.JSONField(
        required=False,
        help_text="Respuesta resumida de GitHub después de actualizar la descripción del PR.",
    )
