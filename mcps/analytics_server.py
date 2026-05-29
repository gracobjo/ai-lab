"""
mcps/analytics_server.py
========================
MCP para analizar CSV y generar cuadros de mando HTML (sin Power BI Desktop).
"""

import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

BASE_PATH = Path(__file__).resolve().parent.parent
if str(BASE_PATH) not in sys.path:
    sys.path.insert(0, str(BASE_PATH))

from analytics.dataset_report import analyze_csv, generate_dashboard, resolve_csv_path
from analytics.flow_diagram import (
    analyze_flow_csv,
    analyze_flow_only,
    generate_flow_diagram,
    resolve_flow_csv,
)

mcp = FastMCP("analytics-server")


@mcp.tool()
def analyze_dataset(csv_path: str = "california_housing.csv") -> str:
    """Analiza un CSV del proyecto: estadísticas, correlaciones y recomendaciones."""
    try:
        path = resolve_csv_path(csv_path)
    except FileNotFoundError as e:
        return str(e)
    return analyze_csv(path)


@mcp.tool()
def build_dashboard(csv_path: str = "california_housing.csv") -> str:
    """Genera un cuadro de mando HTML con KPIs y gráficos para un CSV del proyecto."""
    try:
        path = resolve_csv_path(csv_path)
    except FileNotFoundError as e:
        return str(e)
    out_file, summary = generate_dashboard(path)
    return summary


@mcp.tool()
def analyze_flow(csv_path: str = "tramites.csv") -> str:
    """Analiza un CSV de trámites/proceso (transiciones entre pasos, estilo Visio)."""
    try:
        return analyze_flow_only(resolve_flow_csv(csv_path))
    except (FileNotFoundError, ValueError) as e:
        return str(e)


@mcp.tool()
def build_flow_diagram(
    csv_path: str = "tramites.csv",
    root_tramite_id: int = 31900,
    max_depth: int = 4,
) -> str:
    """Genera diagrama de flujo HTML+Mermaid desde CSV de trámites (sustituto de Visio)."""
    try:
        path = resolve_flow_csv(csv_path)
        return generate_flow_diagram(path, root_id=root_tramite_id, max_depth=max_depth)
    except (FileNotFoundError, ValueError) as e:
        return str(e)


if __name__ == "__main__":
    print("MCP analytics-server starting...", file=sys.stderr)
    mcp.run()
