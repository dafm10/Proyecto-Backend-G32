# Proyecto Backend G32 — Barbería

API REST para gestionar una barbería con múltiples sedes: usuarios, servicios, precios por sede, barberos, horarios, bloqueos de agenda y citas. El frontend se mantiene en un proyecto separado y consume esta API mediante HTTP y autenticación JWT.

## Tecnologías y dependencias

La imagen Docker utiliza **Python 3.14** y Compose utiliza **PostgreSQL 18**. Las dependencias de Python se declaran en `requirements.txt`:

| Librería | Versión declarada | Uso |
| --- | --- | --- |
| Django | 6.1.2 | Framework, ORM, migraciones y administrador |
| Django REST Framework | 3.18.3 | Vistas, serializadores y respuestas de la API |
| djangorestframework_simplejwt | 5.5.1 | Autenticación con tokens JWT |
| PyJWT | 2.15.1 | Codificación y validación de JWT |
| django-cors-headers | 4.9.0 | Peticiones desde el origen del frontend |
| psycopg2 | 2.9.13 | Conexión con PostgreSQL |
| python-dotenv | 1.2.4 | Lectura de `barberia/.env` |
| asgiref | 3.13.0 | Utilidades de integración ASGI de Django |
| sqlparse | 0.6.1 | Utilidades de análisis SQL utilizadas por Django |
| Gunicorn | Sin versión fijada | Servidor WSGI dentro del contenedor |
| WhiteNoise | Sin versión fijada | Archivos estáticos en producción |

Gunicorn y WhiteNoise se instalan según la resolución de pip al construir la imagen. Redis y Celery no forman parte de la implementación actual.

## Funcionalidades

- Acceso por correo y contraseña, con perfiles de administrador, barbero y cliente.
- Gestión de sedes y barberos, incluyendo desactivación.
- Catálogo de servicios con descripción y duración.
- Asignación de servicios a sedes con precios y disponibilidad independientes.
- Asignación de servicios a barberos, horarios semanales y bloqueos de agenda.
- Consulta de disponibilidad y creación de citas.
- Confirmación, cancelación, reprogramación, finalización y registro de inasistencia.
- Historial de cambios de las citas y permisos según usuario y operación.

La configuración utiliza el idioma `es-pe` y la zona horaria `America/Lima`.

## Estructura del repositorio

```text
Proyecto_Backend_G32/
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .gitignore
├── requirements.txt
├── README.md
├── MER - Proyecto.png         # Diagrama del modelo de datos
├── docker/
│   └── start.sh               # Arranque de Django y Gunicorn
└── barberia/
    ├── .env.example          # Plantilla sin credenciales reales
    ├── .env                  # Configuración local, excluida de Git y Docker
    ├── manage.py
    ├── barberia/
    │   ├── settings.py
    │   ├── urls.py
    │   ├── wsgi.py
    │   └── asgi.py
    └── gestion/
        ├── models.py
        ├── serializers.py
        ├── views.py
        ├── urls.py
        ├── pagination.py
        ├── admin.py
        ├── tests.py
        └── migrations/
```

Las entidades principales son `Usuario`, `Cliente`, `Barbero`, `Sede`, `Servicio`, `ServicioSede`, `BarberoServicio`, `HorarioBarbero`, `BloqueAgenda`, `Cita` e `HistorialCita`.

## Configuración local

Necesitas Docker con Compose; en macOS puedes utilizar Docker Desktop. Ejecuta los comandos desde la raíz del repositorio, donde están `Dockerfile` y `requirements.txt`.

Si todavía no tienes configuración local:

```bash
cp barberia/.env.example barberia/.env
```

Si el archivo ya existe, conserva sus valores y agrega las variables que falten. Ejemplo de configuración:

```dotenv
SECRET_KEY=reemplazar_por_una_clave_aleatoria
JWT_SECRET=reemplazar_por_otra_clave_aleatoria
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://127.0.0.1:5500
CSRF_TRUSTED_ORIGINS=
DATABASE_NAME=barberia
DATABASE_USER=barberia
DATABASE_PASSWORD=reemplazar_por_una_contraseña_segura
DATABASE_HOST=localhost
DATABASE_PORT=5432
```

Genera una clave para cada secreto con:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(50))'
```

| Variable | Comportamiento |
| --- | --- |
| `SECRET_KEY` | Obligatoria; Django no inicia si está vacía |
| `JWT_SECRET` | Clave de firma de JWT; si está vacía, utiliza `SECRET_KEY` |
| `DEBUG` | `True` para desarrollo y `False` para producción |
| `ALLOWED_HOSTS` | Hosts separados por comas, sin protocolo ni rutas; el nombre va en plural |
| `CORS_ALLOWED_ORIGINS` | Orígenes del frontend con protocolo y puerto, sin rutas como `/index.html` |
| `CSRF_TRUSTED_ORIGINS` | Orígenes confiables para solicitudes protegidas por CSRF; puede quedar vacía en el flujo JWT actual |
| `DATABASE_*` | Host, puerto, nombre, usuario y contraseña de PostgreSQL |
| `PORT` | Puerto de Gunicorn; predeterminado `8000` |
| `WEB_CONCURRENCY` | Cantidad de workers de Gunicorn; predeterminada `2` |
| `RUN_MIGRATIONS` | `true` por defecto; únicamente ese valor ejecuta las migraciones al arrancar |

No subas `.env` ni credenciales al repositorio. `.env.example` sí se versiona, con secretos vacíos.

## Ejecución con Docker

```bash
# Validar la configuración sin imprimir los secretos
docker compose --env-file barberia/.env config --quiet

# Construir la imagen y levantar API + PostgreSQL
docker compose --env-file barberia/.env up --build -d

# Consultar estado y logs
docker compose --env-file barberia/.env ps
docker compose --env-file barberia/.env logs -f api

# Crear el administrador y comprobar Django
docker compose --env-file barberia/.env exec api python manage.py createsuperuser
docker compose --env-file barberia/.env exec api python manage.py check
```

Accesos locales:

- API: `http://127.0.0.1:8000`.
- Servicios: `http://127.0.0.1:8000/servicios`.
- Administrador: `http://127.0.0.1:8000/admin/`.

La raíz `/` devuelve 404 porque no tiene una vista registrada. Las rutas de la API se definen sin barra final; `/admin/` sí la utiliza.

### Cómo funciona el contenedor

El Dockerfile instala `build-essential` y `libpq-dev` para compilar `psycopg2`, instala las dependencias, copia `barberia/` a `/app` y ejecuta la aplicación con el usuario `barberia`, sin permisos de root.

`docker/start.sh` realiza estas operaciones, deteniéndose ante un error:

1. Recopila estáticos con `collectstatic --noinput`.
2. Aplica migraciones si `RUN_MIGRATIONS=true`.
3. Inicia Gunicorn con `barberia.wsgi:application`, escuchando en `0.0.0.0:${PORT:-8000}` y enviando logs a la salida del contenedor.

WhiteNoise sirve los estáticos recopilados en `staticfiles`, incluidos los estilos del administrador.

Compose espera a que PostgreSQL pase la comprobación `pg_isready`. Dentro de la API reemplaza `DATABASE_HOST` por `base_de_datos` y el puerto por `5432`. PostgreSQL no publica un puerto hacia el equipo anfitrión; la API se conecta mediante la red de Compose.

Incluye `--env-file barberia/.env` también al consultar logs, estado o ejecutar comandos: Compose necesita esos valores para resolver `${DATABASE_NAME}`, `${DATABASE_USER}` y `${DATABASE_PASSWORD}`. El `env_file` del servicio proporciona variables al contenedor, pero no sustituye esta interpolación.

### Persistencia y cambios

```bash
# Detener y eliminar contenedores; conservar los datos
docker compose --env-file barberia/.env down

# Recrearlos con la imagen y el volumen existentes
docker compose --env-file barberia/.env up -d
```

Los datos persisten en el volumen `pgdata`, montado en `/var/lib/postgresql` para PostgreSQL 18. **`down -v` elimina también ese volumen y sus datos.** Las credenciales de inicialización se aplican al crear la base por primera vez; editar `.env` no cambia las credenciales de un volumen existente.

El código no se monta como volumen: después de cambiar el backend, ejecuta `up --build -d`. Después de cambiar variables, ejecuta `up -d` para que Compose recree el servicio cuando corresponda. Los cambios del frontend separado no requieren reconstruir el backend.

La base local del equipo, la base de Docker y la base de Render son independientes. Las migraciones crean el esquema; no importan usuarios ni registros de otras bases.

## API y autenticación

`POST /login` recibe `correo` y `password`, y devuelve el token en `token`. Envía ese valor en las peticiones autenticadas:

```http
Authorization: Bearer <token>
```

El token de acceso tiene una duración configurada de 3 horas y 30 minutos. No hay una ruta de renovación de tokens registrada. Los permisos efectivos dependen de la vista, el método y el perfil del usuario.

| Recurso | Rutas y métodos |
| --- | --- |
| Registro y acceso | `POST /registro`, `POST /login`, `GET /perfil` |
| Registro de perfiles | `POST /registro-barbero`, `POST /registro-cliente` |
| Sedes | `GET, POST /sedes`; `GET, PATCH, DELETE /sede/<uuid>` |
| Barberos | `GET /barberos`; `GET, PATCH, DELETE /barbero/<uuid>` |
| Servicios | `GET, POST /servicios` |
| Precios y disponibilidad por sede | `GET, POST /servicios-sedes`; `GET, PATCH, DELETE /servicio-sede/<uuid>` |
| Servicios de cada barbero | `GET, POST /barberos-servicios`; `GET, PATCH, DELETE /barbero-servicio/<uuid>` |
| Horarios | `GET, POST /horarios-barberos`; `GET, PATCH, DELETE /horario-barbero/<uuid>` |
| Bloqueos | `GET, POST /bloqueos-agenda`; `GET, PATCH, DELETE /bloqueo-agenda/<uuid>` |
| Disponibilidad | `GET /disponibilidad` |
| Citas | `GET, POST /citas`; `GET /cita/<uuid>` |
| Acciones de citas | `PATCH /cita/<uuid>/confirmar`, `/cancelar`, `/completar`, `/reprogramar`, `/responder-reprogramacion`, `/no-asistio` |
| Historial | `GET /cita/<uuid>/historial` |

En la fila de acciones, cada sufijo se agrega a `/cita/<uuid>`.

Los listados que utilizan `Paginacion` aceptan `pagina` y `cantidad`, con 5 registros por defecto y un máximo de 10 por página. Por ejemplo:

```text
/servicios?pagina=1&cantidad=10
```

Su respuesta incluye `content` y `paginacion` con `total`, `pagina_actual`, `total_paginas`, `siguiente` y `anterior`. No todos los endpoints utilizan paginación.

## Conexión del frontend

El frontend se ejecuta por separado. Para Live Server en `http://127.0.0.1:5500/index.html`:

```dotenv
CORS_ALLOWED_ORIGINS=http://127.0.0.1:5500
```

En su `js/api.js`, usa una URL base sin barra final:

```javascript
// Backend local en Docker
const baseUrl = "http://127.0.0.1:8000";

// Para producción, reemplaza la línea anterior por:
// const baseUrl = "https://proyecto-backend-g32.onrender.com";
```

La API proporciona datos; no publica el HTML del frontend. Cuando publiques el frontend, agrega su origen público a `CORS_ALLOWED_ORIGINS` en Render. Puedes separar varios orígenes con comas.

Para preparar las reservas desde una base vacía, crea un administrador, sedes y servicios; configura precios por sede, registra barberos con sus servicios y define sus horarios. Un servicio sin disponibilidad por sede no estará listo para reservarse.

## Despliegue en Render

1. Sube el backend a GitHub, incluyendo migraciones y archivos Docker, sin `.env` ni el entorno virtual.
2. Crea una base Render Postgres y un Web Service en la misma región.
3. Conecta el repositorio del backend y selecciona **Docker**.
4. Deja Root Directory vacío, Dockerfile Path en `./Dockerfile` y Docker Build Context en `.`. Deja Docker Command vacío para usar el `CMD` de la imagen.
5. Configura las variables siguientes en **Environment del Web Service**:

| Variable | Valor de producción |
| --- | --- |
| `SECRET_KEY` | Una clave nueva, aleatoria y privada |
| `JWT_SECRET` | Otra clave privada, o utiliza el respaldo a `SECRET_KEY` |
| `DEBUG` | `False` |
| `DATABASE_HOST` | Host interno de Render Postgres, sin `@`, protocolo ni puerto |
| `DATABASE_NAME` | Nombre de la base de Render |
| `DATABASE_USER` | Usuario de la base de Render |
| `DATABASE_PASSWORD` | Contraseña de la base de Render |
| `DATABASE_PORT` | `5432` |
| `CORS_ALLOWED_ORIGINS` | Origen público del frontend o `http://127.0.0.1:5500` mientras uses Live Server |
| `CSRF_TRUSTED_ORIGINS` | Orígenes adicionales confiables si el flujo de sesiones/CSRF los requiere |

El proyecto lee las variables `DATABASE_*`; no interpreta `DATABASE_URL`. Render proporciona `PORT` y `RENDER_EXTERNAL_HOSTNAME`; este último se agrega a `ALLOWED_HOSTS`. Para un dominio propio, configura también `ALLOWED_HOSTS` con el host, sin protocolo. Cuando `RENDER=true`, Django reconoce HTTPS a través del proxy de Render.

6. Despliega y revisa migraciones y Gunicorn en los logs. Prueba `/servicios` y `/admin/`.
7. Crea un administrador o importa los datos anteriores y cambia la URL base del frontend.

Render construye el Dockerfile; Compose se utiliza para el entorno local. No es necesario publicar la imagen en Docker Hub. Para varias instancias, mueve las migraciones a un Pre-Deploy Command si tu plan lo permite y configura `RUN_MIGRATIONS=false`.

La disponibilidad de Shell, pre-deploy y los límites de los planes dependen del servicio contratado. Consulta la [documentación de Docker en Render](https://render.com/docs/docker), la [conexión a PostgreSQL](https://render.com/docs/postgresql-creating-connecting) y los [límites del plan gratuito](https://render.com/docs/free).

### Crear el administrador de producción

Si tienes Shell en el Web Service:

```bash
python manage.py createsuperuser
```

Si no tienes Shell, puedes ejecutar el comando desde la API local conectándola temporalmente a la base de Render. Con los contenedores locales en ejecución, reemplaza los valores de ejemplo:

```bash
docker compose --env-file barberia/.env exec \
  -e DATABASE_HOST='HOST_EXTERNO_COMPLETO_DE_RENDER' \
  -e DATABASE_NAME='BASE_DE_RENDER' \
  -e DATABASE_USER='USUARIO_DE_RENDER' \
  -e DATABASE_PASSWORD='CONTRASEÑA_DE_RENDER' \
  -e DATABASE_PORT='5432' \
  -e PGSSLMODE='require' \
  api python manage.py createsuperuser
```

Este comando **escribe en la base de producción**. Usa el host externo completo de Connections, sin `@` al principio. El host interno se utiliza entre servicios de Render; el externo, desde tu equipo. El acceso externo debe permitir la conexión desde tu IP. Las variables `-e` solo afectan a este proceso; no cambian `.env`.

No compartas comandos con contraseñas reales: pueden quedar en el historial de la terminal. Los usuarios creados en una base local no existen en Render hasta crearlos o importarlos allí.

## Comprobaciones y pruebas

Con la configuración de desarrollo y los servicios locales activos:

```bash
docker compose --env-file barberia/.env exec api python manage.py check
docker compose --env-file barberia/.env exec api python manage.py test gestion
```

Las pruebas utilizan una base de pruebas que Django crea y elimina. Ejecútalas sobre el entorno local; el usuario PostgreSQL necesita permisos para crearla. `gestion/tests.py` contiene pruebas de la API y sus reglas de acceso y reservas. Estos comandos permiten verificar el estado actual; esta documentación no implica que la suite se haya ejecutado en cada versión.

## Problemas frecuentes

| Síntoma | Qué revisar |
| --- | --- |
| Compose indica que falta `DATABASE_NAME` | Incluye `--env-file barberia/.env` y completa las credenciales |
| Error al compilar `psycopg2`, falta `assert.h` | Conserva `build-essential` y `libpq-dev` en el Dockerfile y reconstruye |
| `Configura SECRET_KEY` | Agrega un valor no vacío al entorno correspondiente |
| Error de socket `/var/run/postgresql` | `DATABASE_HOST` está vacío; configura el host de la base |
| No se resuelve un host `dpg-...` desde tu equipo | Utiliza el host externo completo de Render |
| Conexión intenta usar un socket con `@dpg-...` | Quita el `@` inicial de `DATABASE_HOST` |
| 404 en `/` | Es esperado; prueba `/servicios` o `/admin/` |
| 404 desde el frontend | Revisa la URL solicitada; la URL base debe ir sin barra final |
| `content: []` | El listado no tiene registros; comprueba qué base estás utilizando |
| El correo no existe tras desplegar | Crea o importa el usuario en la base de producción |
| Token inválido al cambiar de base | Cierra sesión o elimina `barberia.token` de `sessionStorage` y vuelve a ingresar |
| Error CORS | Comprueba protocolo, host y puerto del frontend en `CORS_ALLOWED_ORIGINS` y recrea o redespliega el servicio |
