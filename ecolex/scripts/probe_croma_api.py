"""Script exploratorio (no productivo): prueba si la API de Croma (api.croma.run) cubre
normativa AMBIENTAL colombiana (Minambiente, ANLA, CARs) a traves del endpoint
co/funcion-publica/norms-search/v1, antes de decidir si vale la pena integrarla al
pipeline de ingesta.

Requiere una API key de Croma (https://usecroma.com) en la variable de entorno
CROMA_API_KEY.

Uso:
    export CROMA_API_KEY="..."
    python scripts/probe_croma_api.py
"""

import os
import sys

import requests

BASE_URL = "https://api.croma.run"
SEARCH_PATH = "/co/funcion-publica/norms-search/v1"
NORM_PATH = "/co/funcion-publica/norm/v1"

# Consultas pensadas para ver si el corpus incluye normativa ambiental especifica,
# no solo administracion publica/empleo publico.
PROBES: list[dict] = [
    {"label": "query=licencia ambiental", "query": "licencia ambiental"},
    {"label": "query=gestion de residuos", "query": "gestion de residuos"},
    {"label": "entity=ministerio-de-ambiente", "entity": "ministerio-de-ambiente"},
    {"label": "entity=minambiente", "entity": "minambiente"},
    {
        "label": "document_type=resolucion + query=ambiental",
        "document_type": "resolucion",
        "query": "ambiental",
    },
    {"label": "query=recursos naturales renovables", "query": "recursos naturales renovables"},
]


def main() -> int:
    api_key = os.environ.get("CROMA_API_KEY")
    if not api_key:
        print("ERROR: falta la variable de entorno CROMA_API_KEY.", file=sys.stderr)
        print("Obtenla en https://usecroma.com y vuelve a correr el script.", file=sys.stderr)
        return 1

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    session = requests.Session()
    session.headers.update(headers)

    for probe in PROBES:
        label = probe["label"]
        payload = {k: v for k, v in probe.items() if k != "label"}
        payload.setdefault("per_page", 5)

        print(f"\n=== {label} ===")
        print(f"payload: {payload}")
        try:
            resp = session.post(BASE_URL + SEARCH_PATH, json=payload, timeout=30)
        except requests.RequestException as exc:
            print(f"ERROR de red: {exc}")
            continue

        print(f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(resp.text[:500])
            continue

        data = resp.json().get("data", {})
        total = data.get("total")
        results = data.get("results", [])
        print(f"total={total} total_is_exact={data.get('total_is_exact')} count={len(results)}")
        for item in results:
            print(
                f"  - [{item.get('document_type')}] {item.get('entity')} "
                f"{item.get('number')}/{item.get('year')} :: {item.get('title')}"
            )

    # Si alguna busqueda devolvio resultados, intenta leer el texto completo del
    # primero para confirmar que el endpoint norm/v1 tambien funciona.
    print("\n=== prueba de lectura de texto completo ===")
    probe_payload = {"query": "licencia ambiental", "per_page": 1}
    resp = session.post(BASE_URL + SEARCH_PATH, json=probe_payload, timeout=30)
    search_data = resp.json().get("data", {}) if resp.status_code == 200 else {}
    if search_data.get("results"):
        norm_id = search_data["results"][0]["id"]
        resp2 = session.post(BASE_URL + NORM_PATH, json={"norm_id": norm_id, "limit": 2000}, timeout=30)
        print(f"norm_id={norm_id} HTTP {resp2.status_code}")
        if resp2.status_code == 200:
            norm_data = resp2.json().get("data", {})
            norm = norm_data.get("norm", {})
            content = (norm.get("content") or {}).get("text", "")
            print(f"primeros 300 caracteres del texto:\n{content[:300]}")
    else:
        print("sin resultados previos para probar lectura de texto")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
