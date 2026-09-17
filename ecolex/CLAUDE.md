# ecolex

SaaS multi-tenant con agente conversacional RAG para consulta de normativa 
ambiental colombiana. Las empresas pueden hacer preguntas legales ambientales 
y subir sus propios documentos para extender la base de conocimiento.

**Este proyecto NO es sobre analisis de contaminacion de suelos.** El scope 
es normativa ambiental general (aire, agua, ruido, licenciamiento, vertimientos).

## Stack

- Backend: FastAPI async, PostgreSQL 16 con pgvector, SQLAlchemy 2.x, Alembic
- Auth: JWT access token + refresh token en cookie httpOnly, slowapi rate limiting
- RAG: LangChain + pgvector + Google Gemini (text-embedding-004 / gemini-2.0-flash)
- Parseo de documentos: pypdf, python-docx, texto plano
- Infra: Docker Compose (pgvector/pgvector:pg16 + backend + pgadmin)

## Arquitectura multi-tenant

Cada empresa (tenant) tiene sus propios usuarios, proyectos y documentos.
Existe un tenant especial _base (id: 00000000-0000-0000-0000-000000000001) 
que aloja el corpus normativo compartido — 8 resoluciones y decretos ambientales 
colombianos que todos los tenants pueden consultar via RAG.

## Fases completadas

- Fase 1: auth, tenants, users, projects — 9 tests, validado con Postgres real
- Fase 2: ingesta de documentos (PDF/DOCX/TXT), pipeline de embeddings, 
  agente conversacional RAG, conversaciones con historial — 23/23 tests
- Fase 3: script operacional scripts/ingest_base_corpus.py para cargar 
  el corpus base al tenant _base via HTTP

## Fase siguiente

- Fase 4: frontend Next.js 14 + TailwindCSS

## Corpus normativo base (tenant _base)

- Decreto 1076 de 2015 — marco institucional ambiental colombiano
- Resolucion 909 de 2008 — emisiones al aire fuentes fijas
- Resolucion 627 de 2006 — ruido ambiental
- Resolucion 1541 de 2013 — calidad recurso hidrico
- Resolucion 2254 de 2017 — calidad del aire (PM2.5, PM10, NO2)
- Resolucion 631 de 2015 — vertimientos
- Resolucion 0316 de 2018 — normativa ambiental complementaria
- Guia Informativa Decreto 1076 de 2015

## Convenciones

- Todos los endpoints retornan { success, message, data }
- Aislamiento por tenant_id en TODAS las queries — nunca mezclar datos entre tenants
- Tests usan SQLite en memoria con FlexibleVector TypeDecorator para pgvector
- No hardcodear credenciales — todo desde variables de entorno via config.py
