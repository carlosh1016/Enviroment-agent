# Ecolex

SaaS multi-tenant con agente conversacional RAG para consulta de normativa
ambiental colombiana. Las empresas hacen preguntas legales ambientales y suben
sus propios documentos para extender la base de conocimiento.

**Este proyecto NO es sobre analisis de contaminacion de suelos.** El scope
es normativa ambiental general (aire, agua, ruido, licenciamiento, vertimientos).

## Stack

- Backend: FastAPI async, PostgreSQL 16 con pgvector, SQLAlchemy 2.x, Alembic
- Auth: JWT access token + refresh token en cookie httpOnly, slowapi rate limiting
- RAG: pgvector + OpenRouter (`app/services/openrouter_client.py`, httpx puro, sin SDK de
  Google ni LangChain). Modelos: `qwen/qwen3-embedding-8b` (embeddings, recortados a 768 dim
  con `dimensions` para no romper el esquema `Vector(768)`) y `google/gemini-3.5-flash-lite`
  (chat, limpieza de texto de PDFs y transcripcion de paginas escaneadas).
- Parseo de documentos: pdfplumber + clasificador texto/escaneado (PDF), python-docx (DOCX),
  texto plano (TXT/CSV), BeautifulSoup (MHTML/HTML, con deteccion automatica de charset via
  UnicodeDammit -- paginas reales de gobierno suelen declarar el charset solo en un <meta>
  dentro del HTML, no en la cabecera MIME), openpyxl (XLSX). Chunking semantico por articulo
  (`chunk_semantic`, ver ingestion_service.py).
- Reportes PDF de cumplimiento (Fase 3): WeasyPrint (`app/services/report_service.py`).
- Frontend: Next.js 14 (App Router) + TypeScript + TailwindCSS, componentes estilo
  shadcn/ui (Radix), axios, zustand (sesion). Gestor de paquetes: pnpm.
  Diseno exportado de Stitch ("Ecolex Legal Assistant Platform"): tokens en
  `frontend/tailwind.config.ts`, tipografia Plus Jakarta Sans + Inter.
- Infra: Docker Compose (pgvector/pgvector:pg16 + backend)

## Arquitectura multi-tenant y roles

Cada empresa (tenant) tiene sus propios usuarios y documentos. Existe un tenant
especial _base (id: 00000000-0000-0000-0000-000000000001) que aloja el corpus
normativo compartido, consultable via RAG por todos los tenants.

Roles por usuario: `admin`, `analyst`, `viewer`.
- admin: gestiona usuarios, sube y elimina documentos.
- analyst: sube documentos y chatea.
- viewer: solo consulta (lista documentos y chatea).
- No se pueden crear admins por API: el unico admin nace con `POST /auth/register`.

## API (todas responden { success, message, data })

- `/auth`: register (3/min), login (5/min), refresh, logout, me (incluye tenant_name)
- `/api/v1/documents`: upload, listar, detalle, eliminar
- `/api/v1/conversations`: crear, listar, renombrar (PATCH title), borrar, mensajes (GET/POST)
- `/api/v1/users` (solo admin): listar, crear, PATCH rol/is_active, DELETE (desactiva)
- `/api/v1/reports/conversations/{id}`: genera un informe PDF de cumplimiento a partir del
  historial de una conversacion (minimo 2 mensajes, rango de fechas opcional)
- `/api/v1/stats/dashboard`: agregados para las graficas del dashboard (documentos por
  estado/tipo, actividad de los ultimos 14 dias, documentos mas citados en el chat)
- El mensaje del usuario se guarda ANTES de llamar al RAG; si el RAG falla, responde 503
  con envelope y la pregunta no se pierde.

## Fases completadas

- Fase 1: auth, tenants, users
- Fase 2: ingesta de documentos (PDF/DOCX/TXT), pipeline de embeddings, agente RAG,
  conversaciones con historial
- Fase 3: script operacional scripts/ingest_base_corpus.py para cargar el corpus base
- Fase 4: frontend Next.js (login/registro, dashboard, documentos, chat, usuarios)
- Fase 3 (post-Fase 4): reportes PDF de cumplimiento normativo via WeasyPrint
- Auditoria: manejo de errores consistente, restricciones de rol en la UI, limpieza del
  modulo `projects` (vestigio del scope anterior de suelos)
- Rediseno del pipeline de ingesta (clasificador texto/escaneado + OpenRouter + chunking
  semantico) y migracion de embeddings y chat de Google a OpenRouter (ver secciones abajo)

## Tests

- 31/32 pasan (`docker compose exec backend python -m pytest -q`). Falla
  `test_auth.py::TestAuth::test_refresh_and_logout_cycle`, fallo **preexistente** (el cliente
  de pruebas no reenvia la cookie `Secure` por HTTP).
- No hay tests de `users`, `/auth/me` ni del frontend.

## Pendiente

- Nada funcional pendiente por ahora (ver seccion de cambio/recuperacion de contrasena abajo,
  resuelto el 2026-10-19). Quedan abiertos: cobertura de tests de `/auth/me`/`users`/frontend,
  CI/CD y despliegue real, y lo necesario para un plan Empresarial (SSO, logs de auditoria, API
  publica, instancia dedicada) si se llega a vender a una empresa grande.

## Historial: de Google (langchain-google-genai) a OpenRouter puro

El proyecto uso originalmente `langchain-google-genai` + Google AI Studio para embeddings y
chat (migrado primero de `google-generativeai` a `google-genai` el 2026-09-18 por
descontinuaciones de modelos). Las dos secciones siguientes (ingesta y embeddings) cubren por
que y como se reemplazo todo eso por OpenRouter. Hoy no queda codigo ni dependencia de Google
en el backend: ni `langchain*`, ni `google-genai`, ni `GOOGLE_API_KEY`.

## Corpus normativo base (tenant _base)

- Decreto 1076 de 2015 — marco institucional ambiental colombiano
- Resolucion 909 de 2008 — emisiones al aire fuentes fijas
- Resolucion 627 de 2006 — ruido ambiental
- Resolucion 1541 de 2013 — calidad recurso hidrico
- Resolucion 2254 de 2017 — calidad del aire (PM2.5, PM10, NO2)
- Resolucion 631 de 2015 — vertimientos
- Resolucion 0316 de 2018 — normativa ambiental complementaria
- Guia Informativa Decreto 1076 de 2015

## Como correrlo

- Backend: `docker compose up --build` (API en :8000, corre `alembic upgrade head` al iniciar;
  el codigo del backend esta montado como volumen pero uvicorn no recarga solo:
  `docker compose restart backend` tras cambios).
- Frontend: `cd frontend && pnpm install && pnpm dev` (usa :3000). CORS solo permite
  `http://localhost:3000`; si Next cae en :3001 porque el 3000 esta ocupado, las peticiones
  al backend se bloquean.
- Tests: `docker compose exec backend python -m pytest -q`

## Convenciones

- Todos los endpoints retornan { success, message, data }, tambien los errores 4xx/5xx/429
- Aislamiento por tenant_id en TODAS las queries — nunca mezclar datos entre tenants
- Tests usan SQLite en memoria con FlexibleVector TypeDecorator para pgvector
- No hardcodear credenciales — todo desde variables de entorno via config.py
- Frontend: errores HTTP se traducen con `lib/errors.ts` (getErrorMessage) y se muestran
  con `ErrorBanner`; nunca `catch` vacio.

## Pipeline de ingesta de PDFs

`ingestion_service.py`: un clasificador (pdfplumber) separa PDFs con capa de texto de PDFs
escaneados. Los primeros van pagina por pagina como texto crudo; los escaneados se renderizan
a imagen (pdf2image/poppler) y se transcriben via un modelo multimodal. Ambos casos pasan por
OpenRouter (`OPENROUTER_MODEL = "google/gemini-3.5-flash-lite"`) para limpiar artefactos de
extraccion antes de `chunk_semantic` (chunking por articulo, regex `ART[IÍ]CULO\s+(\d+)`,
metadata en `DocumentChunk.metadata_`). DOCX/TXT siguen el parseo simple de siempre.

## Embeddings y chat via OpenRouter (2026-09-24)

Los embeddings de Gemini (free tier: 100 req/min) devolvian 429 RESOURCE_EXHAUSTED al
ingestar varios PDFs a la vez. Ahora `openrouter_client.create_embeddings` llama a
`POST /embeddings` con `qwen/qwen3-embedding-8b` y `dimensions=768` (MRL: no cambia la columna
`Vector(768)`). `langchain-google-genai`, `google-genai` y `GOOGLE_API_KEY` se eliminaron del
proyecto. `ingestion_service._embed_batch` (semaforo de 5) lo usan tanto la ingesta como
`rag_service._embed_query`. El chat del RAG (`generate_response`, `CHAT_MODEL =
"google/gemini-3.5-flash-lite"`) tambien pasa por `openrouter_client.chat_completion`.
IMPORTANTE: los vectores de modelos distintos no son comparables; al cambiar `EMBEDDING_MODEL`
hay que borrar y re-ingestar todo el corpus. `SCORE_THRESHOLD` se bajo de 0.75 a 0.45: con
qwen3-embedding-8b, preguntas ajenas al corpus puntuan <=0.29 y preguntas relevantes 0.40-0.72
(0.75, calibrado para Gemini, descartaba casi todo con el modelo nuevo).

## Multi-consulta en la recuperacion RAG (2026-10-01)

Preguntas de tipo "que necesito para montar una fabrica de X?" tocan varios permisos a la vez
(vertimientos, emisiones, residuos peligrosos, licenciamiento...), pero una sola busqueda por
similitud textual solo trae lo mas parecido a la pregunta completa, no un chunk de cada tema.
`rag_service._expand_query` pide al LLM descomponer la pregunta en hasta `MAX_SUBQUERIES` (4)
sub-busquedas por tema; `retrieve_relevant_chunks` busca cada una contra pgvector (en paralelo
con `asyncio.gather`, porque los embeddings son llamadas HTTP independientes a OpenRouter y en
serie los reintentos por fallos de red transitorios se acumulaban — se vio un caso real de 92s)
y combina los resultados quedandose con el score mas alto por chunk, hasta `MAX_RELEVANT_CHUNKS`
(10). Si `_expand_query` falla, se degrada a buscar solo con la pregunta original. La ruta
SQLite de los tests (sin pgvector real) no usa expansion: no hay similitud real que aprovechar.

## Tipos de documento soportados en la ingesta (2026-10-19)

Ademas de PDF/DOCX/TXT: **MHTML/HTML** (paginas guardadas por el navegador, ej. resoluciones
publicadas en sitios de gobierno) y **XLSX/CSV** (hojas de calculo). `DocumentFileType`
(migracion 0004, `ALTER TYPE document_file_type ADD VALUE`) y `ALLOWED_EXTENSIONS` en
`routers/documents.py` listan las extensiones. `parse_document` en `ingestion_service.py`
dispacha a `_parse_mhtml`/`_html_to_text`/`_parse_xlsx`/`_parse_csv`; ninguno de estos pasa por
OpenRouter (a diferencia del PDF): su texto ya sale razonablemente limpio de la libreria que lo
extrae. IMPORTANTE: para MHTML, usar `part.get_payload(decode=True)` (bytes crudos) + pasarlos
directo a BeautifulSoup, NUNCA decodificar con `.decode("utf-8")` antes -- la cabecera MIME casi
nunca declara el charset real en archivos reales, y decodificar a ciegas rompe los acentos
(verificado con 3 .mhtml reales de la Secretaria Juridica Distrital de Bogota).

Tambien se corrigio un bug preexistente: el mensaje de error y la validacion del frontend decian
"10MB" pero `MAX_FILE_SIZE_BYTES` real es 50MB (el frontend bloqueaba de mas, antes de llegar al
backend).

## Reportes y dashboard con graficas (2026-10-19)

El endpoint de reportes (Fase 3) no tenia NINGUN punto de entrada en el frontend -- se podia
probar solo con curl/Postman. Se conecto: boton "Descargar informe" en `chat/[id]/page.tsx`
(`lib/reports.ts`, descarga via blob + `<a download>`). De paso se agrego
`errors.ts:getBlobErrorMessage()` (version async de `getErrorMessage()`): un request con
`responseType: "blob"` tambien recibe el BODY DEL ERROR como Blob, no como el envelope ya
parseado, asi que sin esto se perdia el mensaje especifico del backend (ej. "Se necesitan al
menos 2 mensajes...") detras de un generico de status code.

El "dashboard" (`app/dashboard/page.tsx`) antes solo mostraba 2 numeros (documentos
listos/total, conversaciones) -- no tenia graficas ni estaba conectado al reporte. Se agrego
`GET /api/v1/stats/dashboard` (`routers/stats.py`), siempre acotado al tenant actual, con 4
agregados: documentos por status/tipo (excluye el corpus base, igual que GET /documents),
actividad (conversaciones/mensajes) de los ultimos 14 dias, y documentos mas citados en
`source_chunks` de las respuestas del asistente (SI incluye el corpus base: refleja que normas
consulta mas el equipo). El bucketing por dia se hace en Python, no con funciones de fecha de
Postgres (`date_trunc`), para que la query funcione igual en SQLite (tests).

Frontend: libreria `recharts` (v3, compatible con React 18) + 4 componentes en
`components/dashboard/` (donut de status, barras de tipo, lineas de actividad, barras
horizontales de mas citados), con los colores de marca de Ecolex (`primary`/`secondary`/`sage`
del tema, mismos verdes que `badge.tsx` para status). IMPORTANTE: instalar una dependencia
nueva (`pnpm add`) mientras `next dev` ya estaba corriendo dejo su cache de webpack
desincronizada con el nuevo layout del store de pnpm (`ModuleBuildError: ENOENT .../zustand/esm/index.mjs`
al servir /dashboard) -- hubo que matar el proceso viejo, borrar `.next/` y levantar `pnpm dev`
de nuevo. Si vuelve a pasar tras instalar una dependencia, ese es el primer diagnostico a
probar.

## Cambio y recuperacion de contrasena (2026-10-19)

Ya no es un pendiente. `PATCH /auth/me/password` (autenticado, valida la contrasena actual) y el
flujo de dos pasos `/auth/forgot-password` + `/auth/reset-password`.

Decisiones de seguridad relevantes si se retoma esto:
- El token de reset se guarda en `users.reset_token_hash` con **SHA-256, no bcrypt**: a
  diferencia de una contrasena, el token ya es aleatorio y de alta entropia
  (`secrets.token_urlsafe(32)`), y necesita ser buscable por igualdad en la DB (bcrypt genera un
  hash distinto cada vez para el mismo input, lo cual haria imposible ese lookup).
- `/forgot-password` SIEMPRE responde el mismo mensaje generico, exista o no el email/tenant:
  revelar si una cuenta existe permite enumerar usuarios validos.
- Este proyecto NO tiene un proveedor de email configurado: el token "se envia" solo via
  `logger.info` (ver `auth_service.request_password_reset`). Para produccion real, reemplazar
  ese log por un envio real (Resend, SES, etc.) con un link a `/reset-password?token=...`
  (pagina ya construida en el frontend, falta solo el envio).
- Un unico token activo a la vez por usuario (columna en `users`, no una tabla aparte): generar
  uno nuevo invalida cualquier anterior. Vence a los 30 minutos (`PASSWORD_RESET_EXPIRE_MINUTES`).

## Rol de auditor del admin + cambio forzado de contrasena (2026-10-20)

**Admin como auditor**: un admin ahora VE (nunca escribe en) las conversaciones de cualquier
usuario de su tenant -- `GET /api/v1/conversations/` le trae las de todos (antes, cada quien
solo veia las propias), con `user_email` para saber de quien es cada una; filtrable a un solo
usuario con `?user_id=`. `GET /conversations/{id}/messages` y el nuevo `GET /conversations/{id}`
usan `_get_viewable_conversation_or_404` (dueno O admin). `send_message`/`update_conversation`/
`delete_conversation` siguen con `_get_own_conversation_or_404` (estrictamente el dueno): es
auditoria de solo lectura, el admin no puede escribir en conversaciones ajenas (403). Frontend:
`ConversationList` muestra el email del dueno cuando `showOwner` (admin); `chat/[id]/page.tsx`
calcula `isOwner` comparando `conversation.user_id` contra el usuario actual y, si es false,
oculta borrar/enviar mensaje y muestra un banner de "solo lectura".

**Cambio forzado de contrasena**: `User.must_change_password` (migracion 0006) se marca `True`
cuando un admin crea un usuario (`POST /api/v1/users/`, password asignada por el admin, no
elegida por el usuario) y se limpia a `False` en `auth_service.change_password`/`reset_password`.
`AppShell` redirige a `/change-password` (nueva pagina, PATCH /auth/me/password) si
`must_change_password` es true, para CUALQUIER ruta protegida, con guard de pathname para no
loopear sobre si misma. Se elimino `/settings` (pagina de cambio de contrasena voluntario, sin
link en el sidebar) -- `/change-password` la reemplaza, alcanzable solo via el redirect forzado
(o escribiendo la URL a mano). `app/users/page.tsx` muestra una badge "Debe cambiar contraseña"
mientras el usuario creado no la haya cambiado.

## COOKIE_SECURE en False para desarrollo local + alcance del reporte PDF (2026-10-20)

**COOKIE_SECURE**: estaba en `True` en `.env` mientras todo corria por HTTP en local. Un
navegador descarta cualquier cookie `Secure` que no venga de HTTPS, asi que el refresh token
NUNCA se reenviaba -- no era solo el test conocido fallando, era un bug real: la sesion se
caia silenciosamente al expirar el access token (30 min). Puesto en `False` en `.env` para este
entorno; en produccion (HTTPS real) debe volver a `True`. IMPORTANTE: `docker compose restart`
NO relee el `.env` (solo reinicia el proceso dentro del mismo contenedor) -- hace falta
`docker compose up -d backend` para que recree el contenedor con el env_file actualizado.

**Alcance del reporte PDF**: `POST /reports/conversations/{id}` solo validaba que la
conversacion fuera del mismo tenant, sin revisar dueno -- cualquier usuario del tenant podia
generar el informe de una conversacion ajena, inconsistente con el rol de auditor recien
agregado a `/conversations/*`. Ahora usa el mismo `_get_viewable_conversation_or_404` (dueno o
admin) que los mensajes del chat. Efecto colateral correcto: cruzar de tenant ahora da 404 (no
revela que la conversacion existe), no 403 -- igual que en conversations.py.

## Skill de seguridad instalada (2026-10-20)

`security-audit` (Cloudflare, https://github.com/cloudflare/security-audit-skill) en
`.claude/skills/security-audit/`. IMPORTANTE: instalarla con `npx` fallo (`npx` en este entorno
WSL resuelve al Node.js de *Windows*, que no puede interpretar la ruta UNC de WSL y termina
intentando escribir en `C:\Windows\.claude`, sin permisos). Se instalo con
`pnpm dlx skills add <repo> --skill security-audit --agent claude-code -y`, usando el Node de
Linux que ya trae pnpm. Si hace falta instalar otra skill o paquete npm de un solo uso en este
entorno, usar `pnpm dlx` en vez de `npx`.
