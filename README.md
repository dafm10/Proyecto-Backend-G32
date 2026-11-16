# Backend de barbería: Docker y Render

La estructura sigue semana13: Dockerfile para la API y Compose para API + PostgreSQL, con healthcheck y volumen persistente. Se usa Gunicorn para producción y WhiteNoise para los estáticos. Este backend no necesita Redis.

## Preparación local

Ejecuta todos los comandos desde la raíz del repositorio (donde está requirements.txt).

Si ya existe barberia/.env, consérvalo y agrega las variables nuevas tomando como referencia barberia/.env.example. Si no existe:

```bash
cp barberia/.env.example barberia/.env
```

Completa SECRET_KEY y DATABASE_PASSWORD. Puedes generar una clave con:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(50))'
```

JWT_SECRET es opcional: si está vacío, se utiliza SECRET_KEY. Usa claves nuevas para producción. No subas .env a GitHub.

## Levantar los contenedores

Con Docker Desktop iniciado:

```bash
docker compose --env-file barberia/.env up --build -d
docker compose logs -f api
```

El parámetro --env-file también proporciona las variables que Compose usa para configurar PostgreSQL. Dentro de la API, Compose reemplaza DATABASE_HOST por base_de_datos: localhost dentro del contenedor no apunta a tu Mac.

Abre http://localhost:8000/admin/ o las rutas existentes de la API. La raíz puede devolver 404 si no hay una vista registrada.

```bash
docker compose exec api python manage.py createsuperuser
docker compose exec api python manage.py check
docker compose down
```

El volumen pgdata conserva los datos al detener los servicios. La base del contenedor comienza vacía: no copia la base que ya tengas en tu Mac. Sus credenciales de inicialización se aplican al crear el volumen por primera vez.

No hay un montaje del código como en semana13: después de editarlo, vuelve a ejecutar el comando con --build para actualizar la imagen.

## Desplegar en Render

1. Sube este repositorio a GitHub con Dockerfile, docker/, requirements.txt y las migraciones.
2. Crea una base Render Postgres y un Web Service en la misma región.
3. Conecta el repositorio y selecciona Docker. Deja Root Directory vacío, Dockerfile Path en ./Dockerfile y el contexto en la raíz. Deja Docker Command vacío para usar el CMD de la imagen.
4. Configura las variables de entorno del Web Service:

| Variable | Valor |
| --- | --- |
| SECRET_KEY | Una clave nueva y aleatoria |
| JWT_SECRET | Otra clave aleatoria, o deja que use SECRET_KEY |
| DEBUG | False |
| DATABASE_HOST | Host interno de Render Postgres |
| DATABASE_NAME | Nombre de la base de Render |
| DATABASE_USER | Usuario de Render Postgres |
| DATABASE_PASSWORD | Contraseña de Render Postgres |
| DATABASE_PORT | 5432 |
| CORS_ALLOWED_ORIGINS | URL HTTPS del frontend; separa varios orígenes con comas |
| CSRF_TRUSTED_ORIGINS | URL HTTPS del backend y los orígenes confiables que usen sesiones/CSRF |

RENDER_EXTERNAL_HOSTNAME se agrega automáticamente a ALLOWED_HOSTS. Para un dominio propio, agrega ALLOWED_HOSTS con ese dominio, sin https://. Render proporciona PORT y el servidor escucha en 0.0.0.0. No cargues el .env local en Render.

5. Despliega y revisa los logs. El arranque recopila estáticos, aplica migraciones y ejecuta Gunicorn. La base de Render también empieza vacía; migrar el esquema no transfiere tus datos locales.

Compose se utiliza localmente; Render construye el Dockerfile y se conecta a su Postgres administrado. No necesitas publicar la imagen en Docker Hub.

Para varias instancias, ejecuta `python manage.py migrate --noinput` como Pre-Deploy Command si tu plan lo permite, y configura RUN_MIGRATIONS=False. Así las instancias no intentan migrar simultáneamente.

Referencias: https://render.com/docs/docker y https://render.com/docs/deploy-django.

## Verificación pendiente

No se pudo construir ni ejecutar la imagen durante la preparación porque no se autorizó el acceso al motor Docker. La comprobación completa es el comando Compose indicado arriba; si falla la descarga o instalación de una versión de requirements.txt, revisa su disponibilidad antes de cambiar los pins.
