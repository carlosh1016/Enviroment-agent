# Scripts operacionales

Scripts de una sola vez, fuera de la app (`app/`). No tienen tests: son
operacion manual, no logica de negocio.

## ingest_base_corpus.py

Ingesta el corpus normativo ambiental colombiano (8 documentos PDF) al tenant
compartido `_base` (id `00000000-0000-0000-0000-000000000001`), usando los
endpoints HTTP publicos de la Fase 2 — no toca la base de datos directamente.

### 1. Pre-requisitos

- El stack Docker debe estar corriendo: `docker compose up -d` (o `--build` si
  es la primera vez o cambiaste codigo).
- `GOOGLE_API_KEY` debe ser una API key valida de Google AI Studio en tu `.env`
  — sin esto, cada documento terminara en `status=error` al intentar generar
  los embeddings.
- Los 8 archivos PDF deben existir en `D:\Descargas\` con los nombres exactos
  listados en `DOCUMENTS` dentro de `ingest_base_corpus.py`. Si tus archivos
  estan en otra carpeta o con otros nombres, edita esa lista antes de correr
  el script.

### 2. Setear BASE_ADMIN_PASSWORD antes de levantar el stack

El tenant `_base` existe desde la migracion `0002`, pero **no tiene ningun
usuario** — sin un usuario no hay como loguearse para subir documentos. La
migracion `0003` crea ese usuario admin, y lee la contrasena desde la
variable de entorno `BASE_ADMIN_PASSWORD` **en el momento en que la migracion
se ejecuta** (dentro de `docker compose up --build`, que corre
`alembic upgrade head` antes de arrancar `uvicorn`).

Por eso el orden importa:

1. Edita tu `.env` (copia de `.env.example` si aun no lo tienes) y define:
   ```
   BASE_ADMIN_EMAIL=admin@base.ecolex.internal
   BASE_ADMIN_PASSWORD=un-password-fuerte-aqui
   ```
2. Recien despues levanta o reconstruye el stack:
   ```
   docker compose up --build -d
   ```

Si ya corriste la migracion `0003` antes con la contrasena por defecto
(`changeme_en_produccion`) y quieres cambiarla, la migracion usa
`ON CONFLICT (id) DO NOTHING`, o sea que **no la va a actualizar** en un
`upgrade` posterior. Para reemplazarla:
```
docker compose exec backend alembic downgrade 0002
docker compose exec backend alembic upgrade head
```
(esto solo borra y recrea el usuario admin base, no toca tenants, documentos
ni conversaciones existentes).

### 3. Correr el script desde Windows

```
cd D:\tu-repo\ecolex
set BASE_ADMIN_EMAIL=admin@base.ecolex.internal
set BASE_ADMIN_PASSWORD=tu_password
python scripts/ingest_base_corpus.py
```

El script solo depende de `requests`. Si tu Python de Windows no la tiene:
```
pip install requests
```
(si corres el script con el mismo entorno virtual que usa el backend, o desde
dentro del contenedor, `requests` ya viene instalada de forma transitiva via
`langchain`/`google-generativeai`).

Variables opcionales:
- `BACKEND_BASE_URL` — por defecto `http://localhost:8000`. Cambiala si el
  backend esta publicado en otro host/puerto.

### 4. Que hace el script

Para cada uno de los 8 documentos:
1. Sube el archivo a `POST /api/v1/documents/upload` con `es_base_corpus=true`.
2. Hace polling a `GET /api/v1/documents/{id}` cada 3 segundos hasta que el
   `status` deje de ser `processing` (maximo 120 segundos por documento).
3. Si `status=ready`, registra cuantos chunks se generaron y sigue con el
   siguiente documento.
4. Si `status=error`, registra el `error_message` y sigue con el siguiente
   documento (un documento con error no detiene la ingesta de los demas).
5. Si el token expira (401) en cualquier momento, hace login de nuevo
   automaticamente y reintenta esa operacion una vez.

Al final imprime un resumen: documentos procesados, total de chunks
generados, y la lista de documentos con error (nombre + mensaje).

### 5. Si un documento da error

Causas tipicas:
- **`GOOGLE_API_KEY` invalida o sin cuota**: el `error_message` va a mencionar
  la API de Google directamente (por ejemplo `API_KEY_INVALID`). Corrige la
  key en `.env` y reinicia el backend (`docker compose restart backend`).
- **PDF vacio o ilegible** (por ejemplo un escaneo sin texto, solo imagen):
  el `error_message` sera `Documento vacio o ilegible`. Ese PDF necesita OCR
  antes de poder ingestarse; el script no lo puede resolver solo.
- **Timeout de polling** (120s sin terminar): revisa los logs del backend
  (`docker compose logs -f backend`) para ver si el procesamiento sigue en
  curso o si el contenedor tuvo un problema.

Para reintentar solo los documentos que fallaron, corre el script de nuevo —
es idempotente en el sentido de que simplemente vuelve a subir cada archivo
de `DOCUMENTS` (no hay deduplicacion por nombre, asi que si reintentas TODA
la lista vas a terminar con documentos duplicados para los que ya estaban en
`ready`; si preferis, comenta en la lista los que ya salieron bien antes de
reintentar).

### 6. Verificar que la ingesta fue exitosa

Con el mismo token del admin base (podes loguearte a mano si no lo guardaste):
```
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@base.ecolex.internal","password":"tu_password","tenant_slug":"_base"}'
```

Y despues:
```
curl http://localhost:8000/api/v1/documents/ \
  -H "Authorization: Bearer <access_token>"
```

Deberias ver los 8 documentos listados, todos con `"status": "ready"` y
`"chunk_count"` mayor a 0.
