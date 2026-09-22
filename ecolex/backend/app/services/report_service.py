"""Generacion de reportes PDF de cumplimiento normativo a partir de una conversacion del
agente RAG (Fase 3). El resumen ejecutivo se genera via OpenRouter (ver openrouter_client.py)
y el PDF se renderiza con WeasyPrint (HTML -> PDF), siempre en memoria.
"""

import io
from datetime import date
from html import escape

from app.models.conversation import Conversation, Message, MessageRole
from app.services import openrouter_client
from app.services.rag_service import CHAT_MODEL

REPORT_MAX_TOKENS = 4096
TITLE_SUMMARY_MAX_TOKENS = 32

SUMMARY_SYSTEM_PROMPT = (
    "Eres un especialista en cumplimiento ambiental ESG colombiano. Recibirás el historial "
    "completo de una sesión de consulta normativa. Genera un informe ejecutivo de "
    "cumplimiento con estas secciones EXACTAS (usa estos encabezados literalmente):\n\n"
    "1. SÍNTESIS EJECUTIVA\n"
    "Un párrafo resumiendo el alcance de las consultas realizadas.\n\n"
    "2. NORMAS CONSULTADAS\n"
    "Lista de cada norma citada en la sesión con el número de veces que apareció como fuente "
    "relevante.\n\n"
    "3. OBLIGACIONES IDENTIFICADAS\n"
    "Lista de las obligaciones normativas que emergen de las consultas, agrupadas por tema "
    "(aire, agua, ruido, vertimientos, etc.).\n\n"
    "4. BRECHAS POTENCIALES DE CUMPLIMIENTO\n"
    "Áreas donde las consultas sugieren posibles incumplimientos o riesgos regulatorios para "
    "la organización.\n\n"
    "5. RECOMENDACIONES\n"
    "Acciones concretas recomendadas en orden de prioridad.\n\n"
    "Responde SOLO con el informe estructurado, sin comentarios adicionales. Usa lenguaje "
    "formal y preciso."
)

SUMMARY_SECTION_HEADERS = [
    "1. SÍNTESIS EJECUTIVA",
    "2. NORMAS CONSULTADAS",
    "3. OBLIGACIONES IDENTIFICADAS",
    "4. BRECHAS POTENCIALES DE CUMPLIMIENTO",
    "5. RECOMENDACIONES",
]


def _iter_consultation_pairs(messages: list[Message]):
    """Empareja cada mensaje de usuario con la respuesta del asistente que le sigue."""
    pending_user: Message | None = None
    for msg in messages:
        if msg.role == MessageRole.USER:
            pending_user = msg
        elif msg.role == MessageRole.ASSISTANT and pending_user is not None:
            yield pending_user, msg
            pending_user = None


def _format_sources(message: Message) -> str:
    sources = message.source_chunks or []
    fuentes = [
        f"Articulo {s.get('numero_articulo')} (pag. {s.get('pagina_origen')})"
        for s in sources
        if s.get("numero_articulo")
    ]
    return ", ".join(fuentes) if fuentes else "sin fuentes"


def _format_history_for_summary(messages: list[Message]) -> str:
    """Formatea el historial como bloques CONSULTA/RESPUESTA/FUENTES para el prompt del LLM."""
    blocks = [
        f"CONSULTA: {user_msg.content}\nRESPUESTA: {assistant_msg.content}\n"
        f"FUENTES: {_format_sources(assistant_msg)}\n---"
        for user_msg, assistant_msg in _iter_consultation_pairs(messages)
    ]
    return "\n".join(blocks)


async def generate_compliance_summary(messages: list[Message], tenant_name: str) -> str:
    """Genera el resumen ejecutivo de cumplimiento normativo via OpenRouter, a partir del
    historial de mensajes de la sesion (o el rango de fechas seleccionado)."""
    history_text = _format_history_for_summary(messages)
    user_content = f"Organizacion: {tenant_name}\n\n{history_text}"

    payload = [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    return await openrouter_client.chat_completion(payload, model=CHAT_MODEL, max_tokens=REPORT_MAX_TOKENS)


def _short_document_name(name: str, max_length: int = 40) -> str:
    """Trunca un nombre de archivo largo para que quepa en un chip de fuente."""
    if len(name) <= max_length:
        return name
    return name[: max_length - 1].rstrip() + "…"


def _render_summary_html(summary: str) -> str:
    """Convierte el texto plano del summary en HTML, distinguiendo los 5 encabezados
    exactos (bold, color #1a5276) del resto del contenido (parrafos normales)."""
    known_headers = {h.upper() for h in SUMMARY_SECTION_HEADERS}
    parts: list[str] = []
    paragraph_lines: list[str] = []

    def flush_paragraph():
        if paragraph_lines:
            text = " ".join(paragraph_lines).strip()
            if text:
                parts.append(f'<p class="summary-body">{escape(text)}</p>')
            paragraph_lines.clear()

    for raw_line in summary.strip().splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if line.upper() in known_headers:
            flush_paragraph()
            parts.append(f'<h3 class="summary-header">{escape(line)}</h3>')
        else:
            paragraph_lines.append(line)
    flush_paragraph()

    return "\n".join(parts)


def _render_consultation_cards_html(messages: list[Message]) -> str:
    """Renderiza cada par user/assistant como una tarjeta con fondo alternado, fuentes como
    chips y borde izquierdo de color."""
    cards: list[str] = []
    for index, (user_msg, assistant_msg) in enumerate(_iter_consultation_pairs(messages), start=1):
        background = "#ffffff" if index % 2 == 1 else "#f8f9fa"
        timestamp = assistant_msg.created_at.strftime("%Y-%m-%d %H:%M")

        chips = "".join(
            '<span class="source-chip">Art. {numero} — {documento}</span>'.format(
                numero=escape(str(source.get("numero_articulo") or "N/A")),
                documento=escape(_short_document_name(source.get("document_name") or "Documento")),
            )
            for source in (assistant_msg.source_chunks or [])
        )
        chips_html = f'<div class="source-chips">{chips}</div>' if chips else ""

        cards.append(
            f"""
            <div class="consult-card" style="background-color: {background};">
                <div class="consult-header">Consulta #{index} &middot; {escape(timestamp)}</div>
                <p><strong>Pregunta:</strong> {escape(user_msg.content)}</p>
                <p><strong>Respuesta:</strong> {escape(assistant_msg.content)}</p>
                {chips_html}
            </div>
            """
        )
    return "\n".join(cards)


def _aggregate_referenced_sources(messages: list[Message]) -> list[dict]:
    """Agrupa todos los source_chunks de todos los mensajes por documento: frecuencia y
    articulos unicos citados, ordenado por frecuencia descendente."""
    aggregated: dict[str, dict] = {}

    for msg in messages:
        for source in msg.source_chunks or []:
            document_id = str(source.get("document_id"))
            entry = aggregated.setdefault(
                document_id,
                {"document_name": source.get("document_name") or "Documento", "articulos": set(), "frequency": 0},
            )
            entry["frequency"] += 1
            if source.get("numero_articulo"):
                entry["articulos"].add(str(source["numero_articulo"]))

    return sorted(aggregated.values(), key=lambda entry: entry["frequency"], reverse=True)


def _render_sources_table_html(messages: list[Message]) -> str:
    aggregated = _aggregate_referenced_sources(messages)
    if not aggregated:
        return '<p class="summary-body">No se citaron fuentes normativas especificas en esta sesion.</p>'

    rows = []
    for index, entry in enumerate(aggregated):
        background = "#ffffff" if index % 2 == 0 else "#f2f3f4"
        articulos = ", ".join(sorted(entry["articulos"], key=lambda a: (len(a), a))) or "N/A"
        rows.append(
            f"""
            <tr style="background-color: {background};">
                <td>{escape(entry["document_name"])}</td>
                <td>{escape(articulos)}</td>
                <td>{entry["frequency"]}</td>
            </tr>
            """
        )

    return f"""
    <table class="sources-table">
        <thead>
            <tr><th>Documento</th><th>Articulos citados</th><th>Frecuencia</th></tr>
        </thead>
        <tbody>
            {"".join(rows)}
        </tbody>
    </table>
    """


def _render_html(
    conversation: Conversation,
    messages: list[Message],
    summary: str,
    tenant_name: str,
    date_from: date,
    date_to: date,
) -> str:
    generated_at = date.today().isoformat()
    conversation_title = conversation.title or "Conversacion sin titulo"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: A4;
        margin: 2.5cm;
        @bottom-left {{ content: element(footer-left); }}
        @bottom-right {{ content: element(footer-right); }}
    }}
    @page cover {{
        @bottom-left {{ content: none; }}
        @bottom-right {{ content: none; }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
        font-family: 'Helvetica Neue', Arial, sans-serif;
        color: #1c2833;
        margin: 0;
    }}
    .footer-left {{
        position: running(footer-left);
        font-size: 9px;
        color: #566573;
    }}
    .footer-right {{
        position: running(footer-right);
        font-size: 9px;
        color: #566573;
    }}
    .footer-right::after {{ content: "Pagina " counter(page); }}

    .cover {{ page: cover; text-align: center; padding-top: 4cm; }}
    .cover .logo-placeholder {{
        width: 120px; height: 60px; background: #d5d8dc; color: #566573;
        display: flex; align-items: center; justify-content: center;
        margin: 0 auto 2cm auto; font-size: 12px; font-weight: bold;
    }}
    .cover .tenant-name {{ font-size: 22px; font-weight: bold; margin-bottom: 1cm; }}
    .cover .report-title {{ font-size: 18px; color: #1a5276; font-weight: bold; margin-bottom: 0.5cm; }}
    .cover .report-subtitle {{ font-size: 13px; color: #2e86c1; margin-bottom: 1cm; }}
    .cover .conversation-title {{ font-size: 13px; margin-bottom: 0.3cm; }}
    .cover .generated-at {{ font-size: 11px; color: #566573; margin-bottom: 1cm; }}
    .cover hr {{ border: none; border-top: 1px solid #d5d8dc; width: 60%; margin: 1cm auto; }}
    .cover .cover-footer {{ font-size: 10px; color: #808b96; margin-top: 2cm; }}

    .toc {{ page-break-before: always; padding-top: 1cm; }}
    .toc h2 {{ color: #1a5276; }}
    .toc-entry {{
        display: flex; justify-content: space-between; font-size: 12px;
        border-bottom: 1px dotted #aeb6bf; padding: 6px 0;
    }}

    .section {{ page-break-before: always; }}
    .section h2 {{ color: #1a5276; font-size: 16px; }}

    .summary-header {{
        font-weight: bold; color: #1a5276; font-size: 13px; padding-top: 16px;
    }}
    .summary-body {{ font-size: 11px; line-height: 1.6; }}

    .consult-card {{
        border-left: 3px solid #1a5276; padding: 10px 14px; margin-bottom: 10px;
    }}
    .consult-header {{ font-size: 10px; color: #808b96; margin-bottom: 6px; }}
    .consult-card p {{ font-size: 11px; line-height: 1.5; margin: 4px 0; }}
    .source-chips {{ margin-top: 6px; }}
    .source-chip {{
        display: inline-block; background: #d6eaf8; color: #1a5276;
        font-size: 9px; padding: 3px 8px; border-radius: 10px; margin: 2px 4px 2px 0;
    }}

    .sources-table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
    .sources-table th {{
        background-color: #1a5276; color: #ffffff; text-align: left; padding: 8px;
    }}
    .sources-table td {{ padding: 8px; border-bottom: 1px solid #eaecee; }}
</style>
</head>
<body>

<div class="footer-left">ESG AI Agent | {escape(tenant_name)} | Confidencial</div>
<div class="footer-right"></div>

<div class="cover">
    <div class="logo-placeholder">LOGO</div>
    <div class="tenant-name">{escape(tenant_name)}</div>
    <div class="report-title">Informe de Cumplimiento Normativo Ambiental ESG</div>
    <div class="report-subtitle">Consultas del {date_from.isoformat()} al {date_to.isoformat()}</div>
    <div class="conversation-title">{escape(conversation_title)}</div>
    <div class="generated-at">Fecha de generacion: {generated_at}</div>
    <hr>
    <div class="cover-footer">Generado por ESG AI Agent — Confidencial</div>
</div>

<div class="toc">
    <h2>Tabla de contenido</h2>
    <div class="toc-entry"><span>1. Resumen Ejecutivo de Cumplimiento</span><span>pag. 3</span></div>
    <div class="toc-entry"><span>2. Historial de Consultas</span><span>pag. 4</span></div>
    <div class="toc-entry"><span>3. Fuentes Normativas Referenciadas</span><span>ultima pag.</span></div>
</div>

<div class="section">
    <h2>1. Resumen Ejecutivo de Cumplimiento</h2>
    {_render_summary_html(summary)}
</div>

<div class="section">
    <h2>2. Historial de Consultas</h2>
    {_render_consultation_cards_html(messages)}
</div>

<div class="section">
    <h2>3. Fuentes Normativas Referenciadas</h2>
    {_render_sources_table_html(messages)}
</div>

</body>
</html>"""


async def build_pdf(
    conversation: Conversation,
    messages: list[Message],
    summary: str,
    tenant_name: str,
    date_from: date,
    date_to: date,
) -> bytes:
    """Renderiza el informe de cumplimiento a PDF con WeasyPrint, en memoria (nunca a disco)."""
    from weasyprint import HTML

    html = _render_html(conversation, messages, summary, tenant_name, date_from, date_to)

    buffer = io.BytesIO()
    HTML(string=html).write_pdf(buffer)
    return buffer.getvalue()
