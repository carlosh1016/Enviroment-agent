# Ecolex

SaaS multi-tenant con agente conversacional RAG para consulta de normativa
ambiental colombiana. Las empresas hacen preguntas legales ambientales y suben
sus propios documentos para extender la base de conocimiento.

**Este proyecto NO es sobre analisis de contaminacion de suelos.** El scope
es normativa ambiental general (aire, agua, ruido, licenciamiento, vertimientos).

## Stack

- Backend: FastAPI async, PostgreSQL 16 con pgvector, SQLAlchemy 2.x, Alembic
- Auth: JWT access token + refresh token en cookie httpOnly, slowapi rate limiting
- RAG: LangChain 1.x + pgvector + Google Gemini via el SDK `google-genai`
  (`langchain-google-genai` 4.x). Modelos: `gemini-embedding-001` (embeddings,
  truncados a 768 dim con `output_dimensionality` para no romper el esquema
  `Vector(768)`) y `gemini-3.8-flash` (chat).
- Parseo de documentos: pypdf, python-docx, texto plano
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
- El mensaje del usuario se guarda ANTES de llamar al RAG; si el RAG falla, responde 503
  con envelope y la pregunta no se pierde.

## Fases completadas

- Fase 1: auth, tenants, users
- Fase 2: ingesta de documentos (PDF/DOCX/TXT), pipeline de embeddings, agente RAG,
  conversaciones con historial
- Fase 3: script operacional scripts/ingest_base_corpus.py para cargar el corpus base
- Fase 4: frontend Next.js (login/registro, dashboard, documentos, chat, usuarios)
- Auditoria: manejo de errores consistente, restricciones de rol en la UI, limpieza del
  modulo `projects` (vestigio del scope anterior de suelos)

## Tests

- 20/21 pasan. Falla `test_auth.py::TestAuth::test_refresh_and_logout_cycle`, fallo
  **preexistente** (el cliente de pruebas no reenvia la cookie `Secure` por HTTP).
- Antes eran 22/23: se retiraron 2 tests de `/projects/` junto con el modulo.
- No hay tests de `users`, `/auth/me` ni del frontend.

## Pendiente

- Cambio de contrasena y recuperacion de contrasena (la contrasena que el admin asigna a un
  usuario nuevo no se puede cambiar).
- Correr `scripts/ingest_base_corpus.py` para cargar el corpus base ahora que el pipeline de
  embeddings funciona (ver nota de migracion abajo).

## Migracion google-generativeai -> google-genai (2026-09-18)

`text-embedding-004` fue descontinuado por Google (2026-01-14) y `gemini-2.0-flash` fue
apagado el 2026-06-01; ambos devolvian 404. Ademas `google-generativeai` (SDK viejo, usado
por `langchain-google-genai` 2.0.7) esta deprecado. Cambios:
- `requirements.txt`: `langchain-google-genai` 2.0.7 -> 4.4.0 (usa el SDK `google-genai`
  en vez de `google-generativeai`), + `google-genai`, `langchain` 0.3.7 -> 1.4.2 (arrastra
  `langchain-core` 1.x), `langchain-text-splitters` explicito, `httpx` 0.27.2 -> 0.28.1 y
  `pydantic` 2.9.2 -> 2.13.4 (requeridos por las nuevas versiones).
- `ingestion_service.py` / `rag_service.py`: modelo de embeddings ahora
  `models/gemini-embedding-001` con `output_dimensionality=768` (el default del modelo es
  3072, pero el esquema `document_chunks.embedding` sigue siendo `Vector(768)`); modelo de
  chat ahora `gemini-3.8-flash`. Se quito `transport="rest"` (parametro que ya no existe en
  el SDK nuevo).
- Import `from langchain.text_splitter import ...` -> `from langchain_text_splitters import ...`
  (se movio de paquete en langchain 1.x).
- `generate_response` ahora devuelve `str(response.text)` en vez de `response.content`:
  en langchain-core 1.x el contenido de `AIMessage` puede venir como lista de bloques
  (texto + firma de thinking) en vez de string plano, y `Message.content` en la BD es
  `str`. `.text` concatena solo los bloques de tipo texto.
- El proxy corporativo interceptaba TLS en las llamadas gRPC de `google-generativeai`; el
  SDK `google-genai` usa REST/httpx por defecto para la Developer API, lo cual evito el
  problema en las pruebas dentro del contenedor (ya no hizo falta tocar certificados ni
  `GRPC_DEFAULT_SSL_ROOTS_FILE_PATH`). Si reaparece un timeout/SSL error, revisar ahi primero.

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
