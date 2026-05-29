"""
Análisis de datasets CSV y generación de cuadros de mando HTML.
Usado por mcps/analytics_server.py y flujos directos en agent_core.
"""

from __future__ import annotations

import base64
import io
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

BASE_PATH = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_PATH / "data" / "reports"

NUMERIC_COLS = [
    "housing_median_age",
    "total_rooms",
    "total_bedrooms",
    "population",
    "households",
    "median_income",
    "median_house_value",
]


def resolve_csv_path(name: str | None = None) -> Path:
    """Resuelve ruta a un CSV en la raíz o en data/."""
    candidates = []
    if name:
        candidates.append(BASE_PATH / name)
        candidates.append(BASE_PATH / "data" / name)
    candidates.extend([
        BASE_PATH / "california_housing.csv",
        BASE_PATH / "data" / "california_housing.csv",
    ])
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        f"No se encontró el dataset CSV"
        + (f" '{name}'" if name else " (california_housing.csv)")
    )


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="#141820")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def analyze_csv(path: Path | None = None) -> str:
    """Resumen textual del dataset (estadísticas, correlaciones, categorías)."""
    path = path or resolve_csv_path()
    df = pd.read_csv(path)

    lines = [
        f"# Análisis: {path.name}",
        f"- Filas: {len(df):,} · Columnas: {len(df.columns)}",
        "",
        "## Columnas",
    ]
    for col in df.columns:
        dtype = str(df[col].dtype)
        nulls = int(df[col].isna().sum())
        lines.append(f"- **{col}** ({dtype}) — nulos: {nulls}")

    lines.extend(["", "## Métricas clave"])
    if "median_house_value" in df.columns:
        s = df["median_house_value"]
        lines.append(
            f"- Precio mediano vivienda: media ${s.mean():,.0f}, "
            f"mediana ${s.median():,.0f}, máx ${s.max():,.0f}"
        )
    if "median_income" in df.columns:
        s = df["median_income"]
        lines.append(f"- Ingreso mediano (escala dataset): media {s.mean():.2f}, mediana {s.median():.2f}")
    if "housing_median_age" in df.columns:
        s = df["housing_median_age"]
        lines.append(f"- Antigüedad media viviendas: {s.mean():.1f} años (mediana {s.median():.0f})")

    if "ocean_proximity" in df.columns:
        lines.extend(["", "## Distribución por proximidad al océano"])
        for cat, n in df["ocean_proximity"].value_counts().items():
            pct = 100 * n / len(df)
            lines.append(f"- {cat}: {n:,} ({pct:.1f}%)")

    numeric = [c for c in NUMERIC_COLS if c in df.columns]
    if len(numeric) >= 2:
        corr = df[numeric].corr(numeric_only=True)
        if "median_house_value" in corr.columns:
            top = (
                corr["median_house_value"]
                .drop("median_house_value")
                .abs()
                .sort_values(ascending=False)
            )
            lines.extend(["", "## Correlación con precio vivienda (|r|)"])
            for col, val in top.head(5).items():
                lines.append(f"- {col}: {corr.loc[col, 'median_house_value']:.3f}")

    lines.extend([
        "",
        "## Recomendaciones para Power BI / dashboard",
        "- KPI: precio medio, ingreso medio, viviendas por zona oceánica.",
        "- Gráficos: barras por ocean_proximity, histograma de precios, ingreso vs precio.",
        "- Segmentar por antigüedad de vivienda (housing_median_age).",
    ])
    return "\n".join(lines)


def generate_dashboard(path: Path | None = None, out_name: str | None = None) -> tuple[Path, str]:
    """Genera HTML con KPIs y gráficos embebidos. Devuelve (ruta, resumen)."""
    path = path or resolve_csv_path()
    df = pd.read_csv(path)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    stem = path.stem
    out_file = REPORTS_DIR / (out_name or f"{stem}_dashboard.html")

    charts: list[tuple[str, str]] = []

    if "median_house_value" in df.columns:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.hist(df["median_house_value"], bins=40, color="#3b82f6", edgecolor="#1c2230")
        ax.set_title("Distribución precio mediano vivienda", color="white")
        ax.set_xlabel("USD")
        ax.set_ylabel("Frecuencia")
        ax.tick_params(colors="#8b93a7")
        ax.set_facecolor("#141820")
        fig.patch.set_facecolor("#141820")
        charts.append(("Histograma de precios", _fig_to_b64(fig)))

    if "ocean_proximity" in df.columns and "median_house_value" in df.columns:
        by_ocean = df.groupby("ocean_proximity")["median_house_value"].mean().sort_values(ascending=True)
        fig, ax = plt.subplots(figsize=(6, 3.5))
        by_ocean.plot(kind="barh", ax=ax, color="#8b5cf6")
        ax.set_title("Precio medio por proximidad al océano", color="white")
        ax.set_xlabel("USD (media)")
        ax.tick_params(colors="#8b93a7")
        ax.set_facecolor("#141820")
        fig.patch.set_facecolor("#141820")
        charts.append(("Precio por zona oceánica", _fig_to_b64(fig)))

    if "median_income" in df.columns and "median_house_value" in df.columns:
        sample = df.sample(min(2000, len(df)), random_state=42)
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.scatter(sample["median_income"], sample["median_house_value"], alpha=0.35, s=8, c="#22c55e")
        ax.set_title("Ingreso vs precio vivienda", color="white")
        ax.set_xlabel("Ingreso mediano")
        ax.set_ylabel("Precio vivienda USD")
        ax.tick_params(colors="#8b93a7")
        ax.set_facecolor("#141820")
        fig.patch.set_facecolor("#141820")
        charts.append(("Ingreso vs precio", _fig_to_b64(fig)))

    if "housing_median_age" in df.columns:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.hist(df["housing_median_age"], bins=30, color="#f97316", edgecolor="#1c2230")
        ax.set_title("Antigüedad mediana de viviendas", color="white")
        ax.set_xlabel("Años")
        ax.tick_params(colors="#8b93a7")
        ax.set_facecolor("#141820")
        fig.patch.set_facecolor("#141820")
        charts.append(("Antigüedad viviendas", _fig_to_b64(fig)))

    kpis = []
    if "median_house_value" in df.columns:
        kpis.append(("Precio medio", f"${df['median_house_value'].mean():,.0f}"))
        kpis.append(("Precio mediano", f"${df['median_house_value'].median():,.0f}"))
    if "median_income" in df.columns:
        kpis.append(("Ingreso medio", f"{df['median_income'].mean():.2f}"))
    kpis.append(("Registros", f"{len(df):,}"))
    if "ocean_proximity" in df.columns:
        kpis.append(("Zonas oceánicas", str(df["ocean_proximity"].nunique())))

    kpi_html = "".join(
        f'<div class="kpi"><div class="kpi-label">{label}</div><div class="kpi-value">{val}</div></div>'
        for label, val in kpis
    )
    charts_html = "".join(
        f'<figure><h3>{title}</h3><img src="data:image/png;base64,{b64}" alt="{title}"/></figure>'
        for title, b64 in charts
    )

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dashboard — {path.name}</title>
  <style>
    body {{ font-family: "Segoe UI", system-ui, sans-serif; background: #0c0e14; color: #e8eaef; margin: 0; padding: 24px; }}
    h1 {{ font-size: 1.4rem; margin-bottom: 4px; }}
    .meta {{ color: #8b93a7; font-size: 0.85rem; margin-bottom: 24px; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 28px; }}
    .kpi {{ background: #141820; border: 1px solid #2a3142; border-radius: 12px; padding: 16px; }}
    .kpi-label {{ font-size: 0.75rem; color: #8b93a7; text-transform: uppercase; letter-spacing: .04em; }}
    .kpi-value {{ font-size: 1.35rem; font-weight: 600; margin-top: 6px; color: #93c5fd; }}
    .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }}
    figure {{ background: #141820; border: 1px solid #2a3142; border-radius: 14px; padding: 16px; margin: 0; }}
    figure h3 {{ font-size: 0.95rem; margin: 0 0 12px; font-weight: 600; }}
    img {{ max-width: 100%; height: auto; border-radius: 8px; }}
  </style>
</head>
<body>
  <h1>Cuadro de mando — {path.name}</h1>
  <p class="meta">Generado por ai-lab · {generated} · {len(df):,} filas</p>
  <div class="kpis">{kpi_html}</div>
  <div class="charts">{charts_html}</div>
</body>
</html>"""

    out_file.write_text(html, encoding="utf-8")

    rel = out_file.relative_to(BASE_PATH)
    summary = (
        f"Cuadro de mando generado: `{rel}`\n\n"
        f"**Ver en el navegador:** http://localhost:8000/reports/{out_file.name}\n\n"
        f"**KPIs:** {len(kpis)} · **Gráficos:** {len(charts)}\n\n"
        + analyze_csv(path).split("## Recomendaciones")[0].strip()
    )
    return out_file, summary
