from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError


ROLE_PERMISSIONS = {
    "Reviewer": {
        "view_repositorio",
        "view_pullrequest",
        "view_summarytecnico",
        "add_summarytecnico",
        "change_summarytecnico",
        "generate_summary",
        "publish_summary_github",
    },
    "Auditor": {
        "view_repositorio",
        "view_pullrequest",
        "view_summarytecnico",
    },
}


class Command(BaseCommand):
    help = "Crea o actualiza los grupos Administrador, Reviewer y Auditor."

    def handle(self, *args, **options):
        api_permissions = Permission.objects.filter(content_type__app_label="api")
        permissions_by_codename = {
            permission.codename: permission for permission in api_permissions
        }

        if not permissions_by_codename:
            raise CommandError(
                "No se encontraron permisos de la app api. Ejecuta primero python manage.py migrate."
            )

        admin_group, _ = Group.objects.get_or_create(name="Administrador")
        admin_group.permissions.set(api_permissions)
        self.stdout.write(self.style.SUCCESS("Grupo Administrador actualizado."))

        for group_name, codenames in ROLE_PERMISSIONS.items():
            missing_permissions = sorted(codenames - set(permissions_by_codename))
            if missing_permissions:
                raise CommandError(
                    f"Faltan permisos para {group_name}: {', '.join(missing_permissions)}"
                )

            group, _ = Group.objects.get_or_create(name=group_name)
            group.permissions.set(
                permissions_by_codename[codename] for codename in sorted(codenames)
            )
            self.stdout.write(self.style.SUCCESS(f"Grupo {group_name} actualizado."))

        self.stdout.write(self.style.SUCCESS("Roles inicializados correctamente."))
