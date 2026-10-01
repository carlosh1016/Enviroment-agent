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
- Parseo de documentos: pdfplumber + clasificador texto/escaneado (PDF), python-docx, texto
  plano. Chunking semantico por articulo (`chunk_semantic`, ver ingestion_service.py).
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

- Cambio de contrasena y recuperacion de contrasena (la contrasena que el admin asigna a un
  usuario nuevo no se puede cambiar).

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
