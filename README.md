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

## Migraciones

```bash
python manage.py makemigrations
python manage.py migrate
```

## Levantar servidor de desarrollo

```bash
python manage.py runserver
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

- `GET /api/github/connect/`: redirige directamente a GitHub para autorizar la API.
- `GET /api/github/oauth/callback/`: callback OAuth; guarda o actualiza la `GitHubConnection` activa.
- `GET /api/github/oauth/link/`: devuelve el link OAuth como JSON para pruebas manuales.
- `GET /api/github/repositorios/`: lista repositorios usando la `GitHubConnection` activa.
- `GET /api/github/repositorios/{owner}/{repo}/pull-requests/`: lista pull requests usando la `GitHubConnection` activa.
- `GET /api/github/repositorios/{owner}/{repo}/pull-requests/{number}/summary/`: genera un summary tecnico del PR sin modificar GitHub.
- `POST /api/github/repositorios/{owner}/{repo}/pull-requests/{number}/summary/`: genera el mismo summary tecnico, lo publica como descripcion del PR en GitHub y guarda el repositorio, pull request y summary en la API local.

Los endpoints GitHub usan automaticamente la conexion activa guardada en `GitHubConnection`; no requieren enviar `Authorization: Bearer`.

En la pantalla principal de la API (`/api/`) tambien aparece `github-login`, que apunta a `/api/github/connect/`.

## Migraciones locales para este flujo

Si ya tenias el proyecto levantado antes de agregar `GitHubConnection`, ejecutar:

```bash
python manage.py makemigrations api
python manage.py migrate
```
