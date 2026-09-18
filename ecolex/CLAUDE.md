# Ecolex

SaaS multi-tenant con agente conversacional RAG para consulta de normativa
ambiental colombiana. Las empresas hacen preguntas legales ambientales y suben
sus propios documentos para extender la base de conocimiento.

**Este proyecto NO es sobre analisis de contaminacion de suelos.** El scope
es normativa ambiental general (aire, agua, ruido, licenciamiento, vertimientos).

## Stack

- Backend: FastAPI async, PostgreSQL 16 con pgvector, SQLAlchemy 2.x, Alembic
- Auth: JWT access token + refresh token en cookie httpOnly, slowapi rate limiting
- RAG: LangChain + pgvector + Google Gemini (text-embedding-004 / gemini-2.0-flash)
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

- SSL/proxy para la ingesta real: el proxy corporativo intercepta TLS y gRPC (usado por
  google-generativeai) no confia en su certificado. `transport="rest"` NO lo resuelve en
  langchain-google-genai 2.0.7. Hace falta instalar el certificado del proxy en la imagen y
  apuntar `GRPC_DEFAULT_SSL_ROOTS_FILE_PATH` a ese bundle. Mientras tanto, la ingesta y el
  chat RAG terminan en error/503 (con timeouts de 60s/30s).
- Corpus base: los 8 documentos siguen sin cargarse por lo anterior.
- Cambio de contrasena y recuperacion de contrasena (la contrasena que el admin asigna a un
  usuario nuevo no se puede cambiar).

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
