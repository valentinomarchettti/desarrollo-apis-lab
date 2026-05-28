# pr_summary_api

API base para un laboratorio de Desarrollo de APIs, enfocada en gestionar repositorios, pull requests y summaries tecnicos.

## Modelos principales

- `Repositorio`
- `PullRequest`
- `SummaryTecnico`

## Relaciones entre modelos

- Un `Repositorio` tiene muchos `PullRequest`.
- Un `PullRequest` pertenece a un `Repositorio`.
- Un `PullRequest` tiene muchos `SummaryTecnico`.
- Un `SummaryTecnico` pertenece a un `PullRequest`.

## Instalacion de dependencias

```bash
python -m pip install -r requirements.txt
```

## Configuracion inicial del proyecto

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_roles
python manage.py runserver
```

El comando `seed_roles` crea o actualiza los grupos `Administrador`, `Reviewer` y `Auditor`.
Como `db.sqlite3` no se versiona, cada persona que clone el proyecto debe ejecutar ese comando despues de las migraciones.

## Roles y permisos

- `Administrador`: puede administrar todos los modelos de la app, conectar GitHub, generar summaries y publicarlos en GitHub.
- `Reviewer`: puede ver repositorios y pull requests, generar summaries y publicar summaries como descripcion del pull request en GitHub. No puede conectar GitHub.
- `Auditor`: puede ver repositorios, pull requests y summaries ya generados. No puede crear, modificar, publicar ni conectar GitHub.

Para asignar roles:

1. Entrar a `http://127.0.0.1:8000/admin/` con el superusuario.
2. Crear usuarios desde `Authentication and Authorization > Users`.
3. En cada usuario, agregar el grupo correspondiente: `Administrador`, `Reviewer` o `Auditor`.

## Autenticacion JWT

Obtener tokens:

```http
POST /api/auth/token/
Content-Type: application/json

{
  "username": "usuario",
  "password": "password"
}
```

La respuesta incluye `access` y `refresh`. El token `access` dura 1 hora. Para usar endpoints protegidos, enviar:

```http
Authorization: Bearer <access_token>
```

Renovar el access token:

```http
POST /api/auth/token/refresh/
Content-Type: application/json

{
  "refresh": "<refresh_token>"
}
```

## Endpoints iniciales

- `GET/POST /api/github-connections/`
- `GET/PUT/PATCH/DELETE /api/github-connections/{id}/`
- `GET/POST /api/repositorios/`
- `GET/PUT/PATCH/DELETE /api/repositorios/{id}/`
- `GET/POST /api/pull-requests/`
- `GET/PUT/PATCH/DELETE /api/pull-requests/{id}/`
- `GET/POST /api/summaries/`
- `GET/PUT/PATCH/DELETE /api/summaries/{id}/`

## Endpoints GitHub

- `GET /api/github/connect/`: redirige a GitHub para autorizar la API. Requiere rol `Administrador`.
- `GET /api/github/oauth/callback/`: callback OAuth de GitHub; guarda o actualiza la `GitHubConnection` activa.
- `GET /api/github/oauth/link/`: devuelve el link OAuth como JSON para pruebas manuales. Requiere rol `Administrador`.
- `GET /api/github/repositorios/`: lista repositorios usando la `GitHubConnection` activa.
- `GET /api/github/repositorios/{owner}/{repo}/pull-requests/`: lista pull requests usando la `GitHubConnection` activa.
- `GET /api/github/repositorios/{owner}/{repo}/pull-requests/{number}/summary/`: genera un summary tecnico del PR sin modificar GitHub. Requiere rol `Reviewer` o `Administrador`.
- `POST /api/github/repositorios/{owner}/{repo}/pull-requests/{number}/summary/`: genera el mismo summary tecnico, lo publica como descripcion del PR en GitHub y guarda el repositorio, pull request y summary en la API local. Requiere rol `Reviewer` o `Administrador`.

Los endpoints GitHub usan automaticamente la conexion activa guardada en `GitHubConnection`, pero igualmente requieren JWT de un usuario autorizado de la API. La excepcion es el callback OAuth, porque GitHub redirige al backend sin header `Authorization`.

En la pantalla principal de la API (`/api/`) tambien aparece `github-login`, que apunta a `/api/github/connect/`.
