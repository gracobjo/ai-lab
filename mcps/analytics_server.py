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


if __name__ == "__main__":
    print("MCP analytics-server starting...", file=sys.stderr)
    mcp.run()
