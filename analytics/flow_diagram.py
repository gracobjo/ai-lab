"""
Generación de diagramas de flujo desde CSV (Visio / tramites administrativos).
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE_PATH = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_PATH / "data" / "reports"

TRAMITES_COLUMNS = {
    "from_id": "id_tramite_anterior",
    "from_label": "descripcion_tramite_anterior",
    "order": "num_orden",
    "to_id": "id_tramite_siguiente",
    "to_label": "descripcion_tramite_siguiente",
}


@dataclass
class FlowNode:
    node_id: str
    label: str
    shape: str = "process"
    raw_id: str | None = None


@dataclass
class FlowEdge:
    source: str
    target: str
    label: str = ""


@dataclass
class FlowGraph:
    nodes: dict[str, FlowNode] = field(default_factory=dict)
    edges: list[FlowEdge] = field(default_factory=list)
    source_path: Path | None = None
    mode: str = ""


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).strip().lower())


def _safe_id(raw) -> str:
    sid = re.sub(r"[^a-zA-Z0-9_]", "_", str(raw).strip())
    if not sid or sid[0].isdigit():
        sid = f"n_{sid}"
    return sid


def _shape_from_label(label: str) -> str:
    u = label.upper()
    if "REGISTRO" in u and "SOLICITUD" in u:
        return "start"
    if any(k in u for k in ("BOCYL", "BOLETÍN", "BOLETIN", "BDNS", "PUBLICACIÓN", "PUBLICACION")):
        return "end"
    if u.startswith("NOTIFICACI") or "NOTIFICACI" in u:
        return "document"
    if "PROPUESTA" in u or "RESOLUCI" in u:
        return "decision"
    if "ANULADO" in u or "CADUCIDAD" in u:
        return "end"
    return "process"


def resolve_flow_csv(name: str | None = None) -> Path:
    if name:
        for folder in (BASE_PATH, BASE_PATH / "data"):
            path = folder / name
            if path.is_file():
                return path.resolve()
        raise FileNotFoundError(f"No se encontró '{name}' en la raíz ni en data/.")

    for preferred in ("tramites.csv",):
        for folder in (BASE_PATH, BASE_PATH / "data"):
            path = folder / preferred
            if path.is_file():
                return path.resolve()

    for folder in (BASE_PATH, BASE_PATH / "data"):
        for path in sorted(folder.glob("*.csv")):
            if path.name == "california_housing.csv":
                continue
            return path.resolve()

    raise FileNotFoundError(
        "No hay CSV de flujo. Coloca tramites.csv en la raíz del proyecto."
    )


def _is_tramites_format(columns: list[str]) -> bool:
    n = {_norm(c) for c in columns}
    return all(_norm(v) in n for v in TRAMITES_COLUMNS.values())


def parse_tramites_csv(path: Path) -> FlowGraph:
    df = pd.read_csv(path)
    graph = FlowGraph(source_path=path, mode="tramites")
    c = TRAMITES_COLUMNS

    for _, row in df.iterrows():
        raw_src = row[c["from_id"]]
        raw_tgt = row[c["to_id"]]
        sid = _safe_id(raw_src)
        tid = _safe_id(raw_tgt)
        slabel = str(row[c["from_label"]]).strip()
        tlabel = str(row[c["to_label"]]).strip()
        orden = str(int(row[c["order"]])) if pd.notna(row.get(c["order"])) else ""

        graph.nodes[sid] = FlowNode(sid, slabel, _shape_from_label(slabel), raw_id=str(raw_src))
        graph.nodes[tid] = FlowNode(tid, tlabel, _shape_from_label(tlabel), raw_id=str(raw_tgt))
        graph.edges.append(FlowEdge(sid, tid, orden))

    return graph


def parse_flow_csv(path: Path | None = None) -> FlowGraph:
    path = path or resolve_flow_csv()
    cols = list(pd.read_csv(path, nrows=0).columns)
    if _is_tramites_format(cols):
        return parse_tramites_csv(path)
    raise ValueError(
        f"Formato no soportado en '{path.name}'. "
        f"Columnas: {', '.join(cols)}. "
        "Se requiere el formato tramites (id_tramite_anterior / id_tramite_siguiente)."
    )


def subgraph(
    graph: FlowGraph,
    root_raw_id: int | str,
    max_depth: int = 4,
) -> FlowGraph:
    """Subgrafo BFS desde un trámite (p. ej. 31900 REGISTRO DE SOLICITUD)."""
    root_key = _safe_id(root_raw_id)
    if root_key not in graph.nodes:
        raise ValueError(f"Trámite {root_raw_id} no encontrado en el grafo.")

    adj: dict[str, list[FlowEdge]] = {}
    for edge in graph.edges:
        adj.setdefault(edge.source, []).append(edge)

    visited: set[str] = set()
    edges_out: list[FlowEdge] = []
    queue: deque[tuple[str, int]] = deque([(root_key, 0)])
    visited.add(root_key)

    while queue:
        node, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for edge in adj.get(node, []):
            edges_out.append(edge)
            if edge.target not in visited:
                visited.add(edge.target)
                queue.append((edge.target, depth + 1))

    sub = FlowGraph(source_path=graph.source_path, mode=graph.mode + f"_from_{root_raw_id}_d{max_depth}")
    for nid in visited:
        sub.nodes[nid] = graph.nodes[nid]
    sub.edges = edges_out
    return sub


def _mermaid_shape(node: FlowNode) -> str:
    label = node.label.replace('"', "'")
    shape = node.shape
    if shape == "start":
        return f'{node.node_id}(("{label}"))'
    if shape == "end":
        return f'{node.node_id}(("{label}"))'
    if shape == "decision":
        return f'{node.node_id}{{"{label}"}}'
    if shape == "document":
        return f'{node.node_id}[("{label}")]'
    return f'{node.node_id}["{label}"]'


def graph_to_mermaid(graph: FlowGraph) -> str:
    lines = ["flowchart TD"]
    for node in graph.nodes.values():
        lines.append(f"  {_mermaid_shape(node)}")
    for edge in graph.edges:
        if edge.label:
            lbl = edge.label.replace('"', "'")
            lines.append(f'  {edge.source} -->|"{lbl}"| {edge.target}')
        else:
            lines.append(f"  {edge.source} --> {edge.target}")
    return "\n".join(lines)


def _graph_stats(graph: FlowGraph) -> dict:
    sources = {e.source for e in graph.edges}
    targets = {e.target for e in graph.edges}
    starts = sources - targets
    ends = targets - sources
    branch = {}
    for e in graph.edges:
        branch[e.source] = branch.get(e.source, 0) + 1
    top = sorted(branch.items(), key=lambda x: -x[1])[:5]
    return {
        "starts": starts,
        "ends": ends,
        "top_branch": top,
    }


def analyze_flow_csv(path: Path | None = None) -> str:
    path = path or resolve_flow_csv()
    full = parse_flow_csv(path)
    stats = _graph_stats(full)
    lines = [
        f"# Diagrama de flujo: {path.name}",
        f"- Modo: **{full.mode}** (tabla de transiciones entre trámites)",
        f"- Transiciones: {len(full.edges)} · Trámites únicos: {len(full.nodes)}",
        "",
        "## Columnas",
        "- `id_tramite_anterior` / `descripcion_tramite_anterior` → origen",
        "- `id_tramite_siguiente` / `descripcion_tramite_siguiente` → destino",
        "- `num_orden` → etiqueta de rama (1, 2, 3…)",
        "",
        "## Puntos de entrada (sin predecesores)",
    ]
    for nid in sorted(stats["starts"], key=lambda x: full.nodes.get(x, FlowNode(x, x)).label):
        n = full.nodes[nid]
        lines.append(f"- **{n.raw_id or nid}** — {n.label}")

    lines.append("")
    lines.append("## Pasos con más ramas")
    for nid, count in stats["top_branch"]:
        n = full.nodes.get(nid)
        lines.append(f"- {n.label if n else nid}: **{count}** salidas")

    lines.extend([
        "",
        "## Generación",
        "Pide: *Genera el diagrama de flujo de tramites.csv*",
        "Vista por defecto: desde **31900 REGISTRO DE SOLICITUD** (4 niveles).",
        "También se genera vista completa (`tramites_flow_completo.html`).",
    ])
    return "\n".join(lines)


def _write_flow_html(path: Path, graph: FlowGraph, mermaid: str, title_suffix: str = "") -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = path.stem + title_suffix
    mmd_file = REPORTS_DIR / f"{stem}.mmd"
    html_file = REPORTS_DIR / f"{stem}.html"
    mmd_file.write_text(mermaid, encoding="utf-8")

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title = f"Diagrama de flujo — {path.name}{title_suffix.replace('_', ' ')}"
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ font-family: "Segoe UI", system-ui, sans-serif; background: #0c0e14; color: #e8eaef; margin: 0; padding: 20px; }}
    h1 {{ font-size: 1.25rem; }}
    .meta {{ color: #8b93a7; font-size: 0.85rem; margin-bottom: 16px; }}
    .diagram {{ background: #141820; border: 1px solid #2a3142; border-radius: 12px; padding: 16px; overflow: auto; min-height: 200px; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="meta">ai-lab · {generated} · {len(graph.nodes)} trámites · {len(graph.edges)} transiciones</p>
  <div class="diagram mermaid">
{mermaid}
  </div>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true, theme: "dark", flowchart: {{ useMaxWidth: true, htmlLabels: true, curve: "basis" }} }});
  </script>
</body>
</html>"""
    html_file.write_text(html, encoding="utf-8")
    return html_file


def generate_flow_diagram(
    path: Path | None = None,
    root_id: int | str | None = 31900,
    max_depth: int = 4,
    include_full: bool = True,
) -> str:
    path = path or resolve_flow_csv()
    full = parse_flow_csv(path)

    if not full.nodes:
        raise ValueError(f"No se extrajeron trámites de '{path.name}'.")

    # Vista principal (legible): desde REGISTRO DE SOLICITUD
    focus = subgraph(full, root_id, max_depth) if root_id is not None else full
    focus_html = _write_flow_html(
        path, focus, graph_to_mermaid(focus), "_registro" if root_id == 31900 else f"_from_{root_id}"
    )

    full_html = None
    if include_full and root_id is not None:
        full_html = _write_flow_html(path, full, graph_to_mermaid(full), "_completo")

    lines = [
        f"Diagrama de flujo generado desde `{path.name}`.",
        "",
        f"**Vista principal (desde trámite {root_id}, {max_depth} niveles):**",
        f"http://localhost:8000/reports/{focus_html.name}",
        f"Archivo: `{focus_html.relative_to(BASE_PATH)}`",
        "",
    ]
    if full_html:
        lines.extend([
            f"**Vista completa ({len(full.nodes)} trámites):**",
            f"http://localhost:8000/reports/{full_html.name}",
            f"Archivo: `{full_html.relative_to(BASE_PATH)}`",
            "",
        ])
    lines.append(analyze_flow_csv(path).split("## Generación")[0].strip())
    return "\n".join(lines)


def analyze_flow_only(path: Path | None = None) -> str:
    return analyze_flow_csv(path or resolve_flow_csv())
