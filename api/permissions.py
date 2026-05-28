from rest_framework.permissions import BasePermission, DjangoModelPermissions


METHOD_ACTIONS = {
    "GET": "ver",
    "OPTIONS": "ver",
    "HEAD": "ver",
    "POST": "crear",
    "PUT": "modificar",
    "PATCH": "modificar",
    "DELETE": "eliminar",
}


MODEL_LABELS = {
    "githubconnection": "las conexiones de GitHub",
    "repositorio": "repositorios",
    "pullrequest": "pull requests",
    "summarytecnico": "summaries tecnicos",
}


MODEL_METHOD_ROLES = {
    "githubconnection": {
        "GET": "Administrador",
        "OPTIONS": "Administrador",
        "HEAD": "Administrador",
        "POST": "Administrador",
        "PUT": "Administrador",
        "PATCH": "Administrador",
        "DELETE": "Administrador",
    },
    "repositorio": {
        "GET": "Administrador, Reviewer o Auditor",
        "OPTIONS": "Administrador, Reviewer o Auditor",
        "HEAD": "Administrador, Reviewer o Auditor",
        "POST": "Administrador",
        "PUT": "Administrador",
        "PATCH": "Administrador",
        "DELETE": "Administrador",
    },
    "pullrequest": {
        "GET": "Administrador, Reviewer o Auditor",
        "OPTIONS": "Administrador, Reviewer o Auditor",
        "HEAD": "Administrador, Reviewer o Auditor",
        "POST": "Administrador",
        "PUT": "Administrador",
        "PATCH": "Administrador",
        "DELETE": "Administrador",
    },
    "summarytecnico": {
        "GET": "Administrador, Reviewer o Auditor",
        "OPTIONS": "Administrador, Reviewer o Auditor",
        "HEAD": "Administrador, Reviewer o Auditor",
        "POST": "Administrador o Reviewer",
        "PUT": "Administrador o Reviewer",
        "PATCH": "Administrador o Reviewer",
        "DELETE": "Administrador",
    },
}


class ViewDjangoModelPermissions(DjangoModelPermissions):
    perms_map = {
        **DjangoModelPermissions.perms_map,
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": ["%(app_label)s.view_%(model_name)s"],
        "HEAD": ["%(app_label)s.view_%(model_name)s"],
    }

    def has_permission(self, request, view):
        allowed = super().has_permission(request, view)
        if allowed or not request.user or not request.user.is_authenticated:
            return allowed

        queryset = self._queryset(view)
        model = queryset.model
        model_name = model._meta.model_name
        resource = MODEL_LABELS.get(model_name, model._meta.verbose_name_plural)
        action = METHOD_ACTIONS.get(request.method, "realizar esta accion sobre")
        roles = MODEL_METHOD_ROLES.get(model_name, {}).get(
            request.method,
            "un rol autorizado",
        )

        self.message = (
            f"No tenes permiso para {action} {resource}. "
            f"Necesitas el rol {roles}."
        )

        return False


class HasApiPermission(BasePermission):
    required_permission = None
    permission_description = "realizar esta accion"
    allowed_roles = "un usuario autorizado"

    def has_permission(self, request, view):
        allowed = bool(
            request.user
            and request.user.is_authenticated
            and self.required_permission
            and request.user.has_perm(self.required_permission)
        )
        if not allowed and request.user and request.user.is_authenticated:
            self.message = (
                f"No tenes permiso para {self.permission_description}. "
                f"Necesitas el rol {self.allowed_roles}."
            )
        return allowed


class CanConnectGitHub(HasApiPermission):
    required_permission = "api.connect_github"
    permission_description = "conectar GitHub"
    allowed_roles = "Administrador"


class CanViewRepositorios(HasApiPermission):
    required_permission = "api.view_repositorio"
    permission_description = "listar repositorios de GitHub"
    allowed_roles = "Administrador, Reviewer o Auditor"


class CanViewPullRequests(HasApiPermission):
    required_permission = "api.view_pullrequest"
    permission_description = "consultar pull requests de GitHub"
    allowed_roles = "Administrador, Reviewer o Auditor"


class CanUseSummaryEndpoint(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.method == "POST":
            allowed = request.user.has_perm("api.publish_summary_github")
            if not allowed:
                self.message = (
                    "No tenes permiso para publicar summaries en GitHub. "
                    "Necesitas el rol Administrador o Reviewer."
                )
            return allowed

        allowed = request.user.has_perm("api.generate_summary")
        if not allowed:
            self.message = (
                "No tenes permiso para generar summaries tecnicos. "
                "Necesitas el rol Administrador o Reviewer."
            )
        return allowed
