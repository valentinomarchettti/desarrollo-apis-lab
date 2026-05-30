# API de Revisión Técnica de Pull Requests

API Django REST para conectar una cuenta de GitHub, consultar repositorios y pull requests, generar summaries tecnicos con Gemini y, cuando corresponde, publicar esos summaries como descripcion del pull request en GitHub.

La API mantiene una base local con repositorios, pull requests y un historial de summaries generados. GitHub sigue siendo la fuente principal para los datos remotos; la base local se usa para seguimiento, permisos e historial.

## Alcance de la API

Esta API permite:

- Autenticar usuarios propios de la API con JWT.
- Administrar roles locales: `Administrador`, `Reviewer` y `Auditor`.
- Conectar una cuenta de GitHub mediante OAuth.
- Usar la conexion activa de GitHub para listar repositorios y pull requests.
- Consultar el detalle tecnico de un pull request, incluyendo archivos, commits, comentarios, reviews, comentarios de codigo y diff.
- Generar summaries tecnicos con Gemini a partir del diff de un pull request y metricas calculadas desde GitHub.
- Publicar un summary generado como descripcion del pull request en GitHub.
- Guardar repositorios, pull requests y summaries en la base local.

Para que el summary no sea solamente una lista de cambios, la API tambien calcula informacion util del PR: ramas involucradas, cantidad de archivos, lineas agregadas y eliminadas, autor del PR, autores de commits, dias con actividad y autores que tocaron archivos de test. Esa informacion se usa como contexto para que Gemini pueda explicar mejor que se hizo y como se trabajo.

Esta API no reemplaza a GitHub ni administra ramas, commits, merges, reviewers o labels. La unica escritura directa sobre GitHub implementada actualmente es la actualizacion de la descripcion del pull request con un summary generado.

## Modelos principales

- `GitHubConnection`
- `Repositorio`
- `PullRequest`
- `SummaryTecnico`

### `GitHubConnection`

Representa la conexion OAuth activa con GitHub. Guarda el usuario conectado, el token de acceso, scopes, estado activo y fechas de conexion/uso.

El token se guarda en backend para poder consultar GitHub, pero no se devuelve en las respuestas del serializer.

### `Repositorio`

Representa un repositorio de GitHub guardado en la API local. Incluye owner, nombre del repositorio, URL, descripcion y si el seguimiento esta activo.

### `PullRequest`

Representa un pull request guardado localmente para un repositorio. Incluye numero, titulo, estado (`open`, `closed` o `merged`), ramas, autor y URL.

Cada pull request es unico por combinacion de repositorio y numero.

### `SummaryTecnico`

Representa un summary generado para un pull request. Guarda el contenido, estado (`pending`, `generated` o `failed`) y mensaje de error cuando falla la generacion.

Un pull request puede tener varios summaries, lo que permite conservar historial.

## Relaciones entre modelos

- `GitHubConnection` no pertenece a un repositorio: funciona como credencial activa para consultar GitHub.
- Un `Repositorio` tiene muchos `PullRequest`.
- Un `PullRequest` pertenece a un `Repositorio`.
- Un `PullRequest` tiene muchos `SummaryTecnico`.
- Un `SummaryTecnico` pertenece a un `PullRequest`.

## Instalacion de dependencias

```bash
python -m pip install -r requirements.txt
```

## Configuracion inicial del proyecto

Copiar `.env.example` como `.env` y completar las variables de entorno:

```env
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_CALLBACK_URL=http://127.0.0.1:8000/api/github/oauth/callback/

GOOGLE_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
```

`GEMINI_MODEL` es opcional. Si no se define, la API intenta usar los modelos configurados en `api/gemini_service.py`.

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_roles
python manage.py runserver
```

El comando `seed_roles` crea o actualiza los grupos `Administrador`, `Reviewer` y `Auditor`.
Como `db.sqlite3` no se versiona, cada persona que clone el proyecto debe ejecutar ese comando despues de las migraciones.

## Documentacion OpenAPI / ReDoc

La API expone documentacion generada con `drf-spectacular`:

- `GET /api/schema/`: schema OpenAPI en formato YAML.
- `GET /api/docs/`: documentacion visual ReDoc.
- `GET /docs/redoc/`: alias de ReDoc para acceso directo desde el navegador.

ReDoc muestra la autenticacion JWT como Bearer Auth. Para probar los endpoints protegidos, primero obtener un token en `/api/auth/token/` y enviar:

```http
Authorization: Bearer <access_token>
```

## Flujo de uso

1. Crear usuarios locales desde el admin de Django.
2. Asignar a cada usuario un grupo: `Administrador`, `Reviewer` o `Auditor`.
3. Obtener un token JWT con `/api/auth/token/`.
4. Con un usuario `Administrador`, conectar GitHub desde `/api/github/connect/` o pedir el link OAuth en `/api/github/oauth/link/`.
5. Usar los endpoints de GitHub para listar repositorios, listar pull requests o consultar el detalle de un pull request.
6. Generar un summary tecnico con `GET /summary/` o generarlo y publicarlo en GitHub con `POST /summary/`. En ambos casos la respuesta incluye `metricas_pr`, con los calculos que la API usa para enriquecer la descripcion generada.

## Roles y permisos

- `Administrador`: puede administrar conexiones de GitHub, repositorios, pull requests y summaries. Tambien puede conectar GitHub, generar summaries y publicarlos en GitHub.
- `Reviewer`: puede ver repositorios, pull requests y summaries, generar summaries y publicar summaries como descripcion del pull request en GitHub. No puede conectar GitHub, administrar conexiones ni crear/modificar repositorios o pull requests locales.
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

## Endpoints CRUD locales

- `GET/POST /api/github-connections/`: administracion local de conexiones OAuth. Requiere rol `Administrador`.
- `GET/PUT/PATCH/DELETE /api/github-connections/{id}/`: administracion local de una conexion OAuth. Requiere rol `Administrador`.
- `GET/POST /api/repositorios/`: listado para todos los roles; creacion solo para `Administrador`.
- `GET/PUT/PATCH/DELETE /api/repositorios/{id}/`: lectura para todos los roles; modificacion y eliminacion solo para `Administrador`.
- `GET/POST /api/pull-requests/`: listado para todos los roles; creacion solo para `Administrador`.
- `GET/PUT/PATCH/DELETE /api/pull-requests/{id}/`: lectura para todos los roles; modificacion y eliminacion solo para `Administrador`.
- `GET/POST /api/summaries/`: listado para todos los roles; creacion para `Administrador` o `Reviewer`.
- `GET/PUT/PATCH/DELETE /api/summaries/{id}/`: lectura para todos los roles; modificacion para `Administrador` o `Reviewer`; eliminacion solo para `Administrador`.

## Endpoints GitHub

- `GET /api/github/connect/`: redirige a GitHub para autorizar la API. Requiere rol `Administrador`.
- `GET /api/github/oauth/callback/`: callback OAuth de GitHub; guarda o actualiza la `GitHubConnection` activa.
- `GET /api/github/oauth/link/`: devuelve el link OAuth como JSON para pruebas manuales. Requiere rol `Administrador`.
- `GET /api/github/repositorios/`: lista repositorios usando la `GitHubConnection` activa.
- `GET /api/github/repositorios/{owner}/{repo}/pull-requests/?state=all`: lista pull requests usando la `GitHubConnection` activa. El parametro `state` puede ser `open`, `closed` o `all`.
- `GET /api/github/repositorios/{owner}/{repo}/pull-requests/{number}/`: devuelve el detalle completo del pull request, incluyendo datos generales, archivos modificados, commits, comentarios, reviews, comentarios de codigo, diff y summary tecnico generado por IA cuando corresponde.
- `GET /api/github/repositorios/{owner}/{repo}/pull-requests/{number}/summary/`: genera un summary tecnico del PR sin modificar GitHub. Ademas del diff, consulta detalle, archivos y commits para devolver `metricas_pr`. Requiere rol `Reviewer` o `Administrador`.
- `POST /api/github/repositorios/{owner}/{repo}/pull-requests/{number}/summary/`: genera el mismo summary tecnico enriquecido con `metricas_pr`, lo publica como descripcion del PR en GitHub y guarda el repositorio, pull request y summary en la API local. Requiere rol `Reviewer` o `Administrador`.

### Metricas calculadas del Pull Request

El campo `metricas_pr` resume calculos propios de la API para que el resumen tecnico tenga mas contexto:

- `ramas`: rama de origen y rama destino del PR.
- `archivos`: total de archivos modificados, archivos de test detectados y cantidad de tests modificados.
- `lineas`: lineas agregadas, eliminadas y balance neto del cambio.
- `actividad`: primer commit, ultimo commit, dias calendario entre ambos y dias concretos con commits.
- `autoria`: autor principal del PR, autores de commits y autores que tocaron archivos de test.

Estas metricas ayudan a explicar no solo que cambio, sino tambien como se trabajo: cuanto volumen tuvo el PR, quienes participaron y en que dias hubo actividad.

Los endpoints GitHub usan automaticamente la conexion activa guardada en `GitHubConnection`, pero igualmente requieren JWT de un usuario autorizado de la API. La excepcion es el callback OAuth, porque GitHub redirige al backend sin header `Authorization`.

El endpoint de detalle de pull request puede consultar GitHub aunque el repositorio no exista en la base local. Si el repositorio ya esta guardado localmente, la API puede asociar el pull request y reutilizar o generar un `SummaryTecnico`.

En la pantalla principal de la API (`/api/`) tambien aparece `github-login`, que apunta a `/api/github/connect/`.
