"""
Generación de diagramas de flujo desde CSV (Visio / tramites administrativos).
"""

from __future__ import annotations

import json
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

# Colores por tipo de trámite (vis-network) — fondo claro + texto oscuro (alto contraste)
SHAPE_STYLES: dict[str, dict] = {
    "start": {
        "color": {
            "background": "#bbf7d0",
            "border": "#15803d",
            "highlight": {"background": "#86efac", "border": "#166534"},
        },
        "font": {"color": "#14532d", "size": 13, "face": "Segoe UI", "bold": True},
        "shape": "ellipse",
        "label": "Inicio",
    },
    "end": {
        "color": {
            "background": "#fecaca",
            "border": "#b91c1c",
            "highlight": {"background": "#fca5a5", "border": "#991b1b"},
        },
        "font": {"color": "#7f1d1d", "size": 13, "face": "Segoe UI", "bold": True},
        "shape": "ellipse",
        "label": "Fin / publicación",
    },
    "decision": {
        "color": {
            "background": "#fde68a",
            "border": "#b45309",
            "highlight": {"background": "#fcd34d", "border": "#92400e"},
        },
        "font": {"color": "#78350f", "size": 12, "face": "Segoe UI", "bold": True},
        "shape": "diamond",
        "label": "Propuesta / resolución",
    },
    "document": {
        "color": {
            "background": "#bae6fd",
            "border": "#0369a1",
            "highlight": {"background": "#7dd3fc", "border": "#075985"},
        },
        "font": {"color": "#0c4a6e", "size": 12, "face": "Segoe UI", "bold": True},
        "shape": "box",
        "label": "Notificación",
    },
    "process": {
        "color": {
            "background": "#ddd6fe",
            "border": "#6d28d9",
            "highlight": {"background": "#c4b5fd", "border": "#5b21b6"},
        },
        "font": {"color": "#4c1d95", "size": 12, "face": "Segoe UI", "bold": True},
        "shape": "box",
        "label": "Proceso",
    },
}

DEFAULT_NODE_FONT = {
    "color": "#1e293b",
    "size": 12,
    "face": "Segoe UI",
    "bold": True,
    "strokeWidth": 3,
    "strokeColor": "#f8fafc",
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
        "## Interacción (visor HTML)",
        "- **Colores** por tipo: inicio (verde), notificación (cyan), resolución (ámbar), fin (rojo), proceso (violeta).",
        "- **Arrastrar** cualquier nodo para reorganizar.",
        "- **Clic** en un nodo: resalta trámites anteriores y siguientes + panel lateral.",
        "- **Buscar** por ID o nombre; **Quitar foco** / **Centrar vista**.",
        "",
        "## Generación",
        "Pide: *Genera el diagrama de flujo de tramites.csv*",
        "Vista por defecto: desde **31900 REGISTRO DE SOLICITUD** (4 niveles).",
        "También se genera vista completa (`tramites_flow_completo.html`).",
    ])
    return "\n".join(lines)


def graph_to_vis_payload(graph: FlowGraph) -> dict:
    """Datos para vis-network (nodos + aristas)."""
    nodes = []
    for node in graph.nodes.values():
        style = SHAPE_STYLES.get(node.shape, SHAPE_STYLES["process"])
        short = node.label if len(node.label) <= 36 else node.label[:33] + "…"
        nodes.append({
            "id": node.node_id,
            "label": f"{node.raw_id or ''}\n{short}".strip(),
            "title": f"ID {node.raw_id}\n{node.label}",
            "group": node.shape,
            "shape": style["shape"],
            "color": style["color"],
            "font": {**DEFAULT_NODE_FONT, **style.get("font", {})},
            "borderWidth": 2,
            "raw_id": node.raw_id,
            "full_label": node.label,
        })
    edges = []
    for i, edge in enumerate(graph.edges):
        edges.append({
            "id": f"e{i}",
            "from": edge.source,
            "to": edge.target,
            "label": edge.label,
            "title": f"Rama {edge.label}" if edge.label else "",
            "font": {
                "color": "#1e293b",
                "size": 12,
                "face": "Segoe UI",
                "bold": True,
                "strokeWidth": 4,
                "strokeColor": "#f1f5f9",
                "background": "#e2e8f0",
            },
            "color": {"color": "#64748b", "highlight": "#2563eb", "opacity": 0.9},
            "arrows": "to",
            "smooth": {"type": "cubicBezier", "forceDirection": "vertical", "roundness": 0.35},
        })
    return {"nodes": nodes, "edges": edges}


def _write_flow_html(
    path: Path,
    graph: FlowGraph,
    mermaid: str,
    title_suffix: str = "",
    layout: str = "hierarchical",
    default_focus: str | None = None,
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = path.stem + title_suffix
    mmd_file = REPORTS_DIR / f"{stem}.mmd"
    html_file = REPORTS_DIR / f"{stem}.html"
    mmd_file.write_text(mermaid, encoding="utf-8")

    payload = graph_to_vis_payload(graph)
    data_json = json.dumps(payload, ensure_ascii=False)
    legend_items = "".join(
        f'<span class="legend-item"><i style="background:{s["color"]["background"]}"></i>{s["label"]}</span>'
        for s in SHAPE_STYLES.values()
    )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title = f"Diagrama de flujo — {path.name}{title_suffix.replace('_', ' ')}"
    focus_hint = default_focus or ""

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: "Segoe UI", system-ui, sans-serif; background: #0c0e14; color: #e8eaef; margin: 0; }}
    header {{ padding: 14px 18px; border-bottom: 1px solid #2a3142; background: #141820; }}
    h1 {{ font-size: 1.1rem; margin: 0 0 6px; }}
    .meta {{ color: #8b93a7; font-size: 0.8rem; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 10px; }}
    .toolbar input {{
      flex: 1; min-width: 180px; padding: 8px 12px; border-radius: 8px;
      border: 1px solid #2a3142; background: #0c0e14; color: #e8eaef;
    }}
    .toolbar button {{
      padding: 8px 14px; border-radius: 8px; border: 1px solid #2a3142;
      background: #1c2230; color: #e8eaef; cursor: pointer; font-size: 0.82rem;
    }}
    .toolbar button:hover {{ border-color: #3b82f6; background: #2563eb22; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; font-size: 0.75rem; color: #8b93a7; }}
    .legend-item {{ display: flex; align-items: center; gap: 5px; }}
    .legend-item i {{ width: 12px; height: 12px; border-radius: 3px; display: inline-block; }}
    .layout {{ display: grid; grid-template-columns: 1fr 300px; min-height: calc(100vh - 120px); }}
    @media (max-width: 900px) {{ .layout {{ grid-template-columns: 1fr; }} }}
    #network {{
      width: 100%; height: calc(100vh - 120px); min-height: 480px;
      background: #0a0c10; border-right: 1px solid #2a3142;
    }}
    aside {{
      padding: 16px; background: #141820; overflow-y: auto;
      border-left: 1px solid #2a3142;
    }}
    aside h2 {{ font-size: 0.95rem; margin: 0 0 8px; color: #93c5fd; }}
    aside .hint {{ font-size: 0.78rem; color: #8b93a7; line-height: 1.45; margin-bottom: 14px; }}
    aside section {{ margin-bottom: 16px; }}
    aside h3 {{ font-size: 0.78rem; text-transform: uppercase; letter-spacing: .05em; color: #64748b; margin: 0 0 6px; }}
    .tramite-list {{ list-style: none; padding: 0; margin: 0; }}
    .tramite-list li {{
      padding: 8px 10px; margin-bottom: 4px; border-radius: 8px;
      background: #1c2230; border: 1px solid #2a3142; font-size: 0.78rem; cursor: pointer;
    }}
    .tramite-list li:hover {{ border-color: #3b82f6; }}
    .tramite-list li .tid {{ color: #38bdf8; font-weight: 600; }}
    .tramite-list li .tlabel {{ color: #e2e8f0; line-height: 1.35; }}
    .tramite-list li.focused {{ border-color: #22c55e; background: #14532d33; }}
    .empty {{ color: #64748b; font-size: 0.8rem; font-style: italic; }}
  </style>
</head>
<body>
  <header>
    <h1>{title}</h1>
    <p class="meta">ai-lab · {generated} · {len(graph.nodes)} trámites · {len(graph.edges)} transiciones · Arrastra nodos · Clic para foco</p>
    <div class="toolbar">
      <input type="search" id="search" placeholder="Buscar trámite por ID o nombre…" autocomplete="off">
      <button type="button" id="btn-reset">Quitar foco</button>
      <button type="button" id="btn-fit">Centrar vista</button>
    </div>
    <div class="legend">{legend_items}</div>
  </header>
  <div class="layout">
    <div id="network"></div>
    <aside>
      <h2 id="focus-title">Selecciona un trámite</h2>
      <p class="hint">Haz clic en un nodo para resaltar sus <strong>trámites anteriores</strong> (entrada) y <strong>siguientes</strong> (salida). Arrastra cualquier nodo para reorganizar.</p>
      <section>
        <h3>Trámites anteriores</h3>
        <ul class="tramite-list" id="list-prev"><li class="empty">—</li></ul>
      </section>
      <section>
        <h3>Trámite seleccionado</h3>
        <ul class="tramite-list" id="list-current"><li class="empty">Clic en el diagrama</li></ul>
      </section>
      <section>
        <h3>Trámites siguientes</h3>
        <ul class="tramite-list" id="list-next"><li class="empty">—</li></ul>
      </section>
    </aside>
  </div>
  <script>
    const GRAPH = {data_json};
    const DEFAULT_FOCUS = {json.dumps(focus_hint)};
    const LAYOUT_MODE = {json.dumps(layout)};

    const nodes = new vis.DataSet(GRAPH.nodes);
    const edges = new vis.DataSet(GRAPH.edges);
    const container = document.getElementById("network");

    const options = {{
      nodes: {{ shadow: {{ enabled: true, size: 6, x: 2, y: 2 }} }},
      edges: {{ width: 1.5, font: {{ align: "middle" }} }},
      interaction: {{
        dragNodes: true,
        dragView: true,
        zoomView: true,
        hover: true,
        tooltipDelay: 120,
      }},
      physics: LAYOUT_MODE === "physics" ? {{
        enabled: true,
        barnesHut: {{ gravitationalConstant: -4200, springLength: 140, springConstant: 0.04 }},
        stabilization: {{ iterations: 180 }},
      }} : {{ enabled: false }},
      layout: LAYOUT_MODE === "hierarchical" ? {{
        hierarchical: {{
          enabled: true,
          direction: "UD",
          sortMethod: "directed",
          levelSeparation: 110,
          nodeSpacing: 160,
          treeSpacing: 200,
        }},
      }} : {{}},
    }};

    const network = new vis.Network(container, {{ nodes, edges }}, options);

    const nodeById = Object.fromEntries(GRAPH.nodes.map(n => [n.id, n]));
    const incoming = {{}};
    const outgoing = {{}};
    GRAPH.edges.forEach(e => {{
      (incoming[e.to] ||= []).push(e);
      (outgoing[e.from] ||= []).push(e);
    }});

    let focusedId = null;

    function renderList(el, items, emptyText) {{
      el.innerHTML = "";
      if (!items.length) {{
        el.innerHTML = `<li class="empty">${{emptyText}}</li>`;
        return;
      }}
      items.forEach(item => {{
        const li = document.createElement("li");
        li.innerHTML = `<span class="tid">${{item.raw_id || item.id}}</span><br><span class="tlabel">${{item.full_label || item.label}}</span>`;
        li.addEventListener("click", () => focusNode(item.id));
        el.appendChild(li);
      }});
    }}

    function neighborNodes(edgeList, pickOther) {{
      const seen = new Set();
      const out = [];
      edgeList.forEach(e => {{
        const oid = pickOther(e);
        if (!seen.has(oid) && nodeById[oid]) {{
          seen.add(oid);
          out.push(nodeById[oid]);
        }}
      }});
      return out;
    }}

    function applyFocusVisuals(activeSet) {{
      const nodeUpdates = GRAPH.nodes.map(n => {{
        const on = !focusedId || activeSet.has(n.id);
        return {{ id: n.id, opacity: on ? 1 : 0.2 }};
      }});
      nodes.update(nodeUpdates);
      const edgeUpdates = GRAPH.edges.map(e => {{
        const on = !focusedId || (activeSet.has(e.from) && activeSet.has(e.to));
        return {{
          id: e.id,
          color: {{ color: on ? "#475569" : "#334155", opacity: on ? 1 : 0.15 }},
          width: on ? 2.5 : 0.5,
        }};
      }});
      edges.update(edgeUpdates);
    }}

    function focusNode(id, pan = true) {{
      focusedId = id;
      const prev = neighborNodes(incoming[id] || [], e => e.from);
      const next = neighborNodes(outgoing[id] || [], e => e.to);
      const active = new Set([id, ...prev.map(n => n.id), ...next.map(n => n.id)]);

      const cur = nodeById[id];
      document.getElementById("focus-title").textContent = cur.full_label || cur.label;
      renderList(document.getElementById("list-prev"), prev, "Sin trámites anteriores");
      renderList(document.getElementById("list-current"), [cur], "");
      renderList(document.getElementById("list-next"), next, "Sin trámites siguientes");
      applyFocusVisuals(active);
      if (pan) network.focus(id, {{ scale: 1.05, animation: {{ duration: 450, easingFunction: "easeInOutQuad" }} }});
    }}

    function resetFocus() {{
      focusedId = null;
      nodes.update(GRAPH.nodes);
      edges.update(GRAPH.edges);
      document.getElementById("focus-title").textContent = "Selecciona un trámite";
      renderList(document.getElementById("list-prev"), [], "—");
      renderList(document.getElementById("list-current"), [], "Clic en el diagrama");
      renderList(document.getElementById("list-next"), [], "—");
    }}

    network.on("click", p => {{ if (p.nodes.length) focusNode(p.nodes[0]); }});
    document.getElementById("btn-reset").onclick = resetFocus;
    document.getElementById("btn-fit").onclick = () => network.fit({{ animation: true }});

    document.getElementById("search").addEventListener("input", ev => {{
      const q = ev.target.value.trim().toLowerCase();
      if (!q) return;
      const hit = GRAPH.nodes.find(n =>
        (n.raw_id && String(n.raw_id).includes(q)) ||
        (n.full_label && n.full_label.toLowerCase().includes(q))
      );
      if (hit) focusNode(hit.id);
    }});

    network.once("stabilizationIterationsDone", () => {{
      resetFocus();
      if (DEFAULT_FOCUS && nodeById[DEFAULT_FOCUS]) focusNode(DEFAULT_FOCUS, false);
      else network.fit({{ animation: true }});
    }});
    if (LAYOUT_MODE === "hierarchical") {{
      setTimeout(() => {{
        resetFocus();
        if (DEFAULT_FOCUS && nodeById[DEFAULT_FOCUS]) focusNode(DEFAULT_FOCUS, false);
        network.fit({{ animation: true }});
      }}, 300);
    }}
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
    focus_key = _safe_id(root_id) if root_id is not None else None
    suffix = "_registro" if root_id == 31900 else (f"_from_{root_id}" if root_id else "")
    focus_html = _write_flow_html(
        path,
        focus,
        graph_to_mermaid(focus),
        suffix,
        layout="hierarchical",
        default_focus=focus_key,
    )

    full_html = None
    if include_full and root_id is not None:
        full_html = _write_flow_html(
            path,
            full,
            graph_to_mermaid(full),
            "_completo",
            layout="physics",
            default_focus=None,
        )

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
