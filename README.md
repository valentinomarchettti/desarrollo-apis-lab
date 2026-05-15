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

- `GET/POST /api/repositorios/`
- `GET/PUT/PATCH/DELETE /api/repositorios/{id}/`
- `GET/POST /api/pull-requests/`
- `GET/PUT/PATCH/DELETE /api/pull-requests/{id}/`
- `GET/POST /api/summaries/`
- `GET/PUT/PATCH/DELETE /api/summaries/{id}/`
