# Análisis de datos y cuadros de mando (sin Power BI Desktop)

ai-lab puede **analizar CSV** y generar un **cuadro de mando HTML** con KPIs y gráficos usando el LLM y el servidor MCP `analytics` — **sin abrir la interfaz de Power BI**.

Dataset de ejemplo en la raíz: `california_housing.csv` (~20 600 filas, precios de vivienda en California).

## Qué puedes pedir en el chat

| Objetivo | Ejemplo |
|----------|---------|
| Resumen analítico | *Analiza california_housing.csv y resume las métricas clave* |
| Cuadro de mando visual | *Genera un cuadro de mando con gráficos de california_housing.csv* |
| KPIs concretos | *Prepara un dashboard con KPIs: precio, ingreso y zonas oceánicas* |

Usa los **chips** de la tarjeta **Análisis de datos** en http://localhost:8000.

El resultado incluye:

- Archivo HTML en `data/reports/california_housing_dashboard.html` (ábrelo en el navegador).
- Resumen en el chat: estadísticas, correlaciones, distribución por `ocean_proximity`.

## Power BI vs análisis HTML

| Capacidad | MCP Power BI | MCP analytics |
|-----------|--------------|---------------|
| Tablas / columnas del modelo | Sí | — |
| Medidas DAX, consultas KPI | Sí (Desktop abierto) | — |
| Gráficos e informes visuales | **No** | **Sí** (HTML) |
| Requiere Power BI Desktop | Sí | No |
| Lee CSV directamente | No (hay que importar al .pbix) | Sí |

**Flujo recomendado “sin tocar Power BI”:**

1. Arranca `.\run_web.ps1` (no hace falta `run_web_powerbi.ps1`).
2. Pide el dashboard o análisis del CSV.
3. Abre el HTML generado.

**Flujo híbrido** (modelo ya cargado en Desktop):

1. `.\run_web_powerbi.ps1` + Desktop con `mi-modelo.pbix`.
2. *Analiza el modelo california_housing en Power BI con DAX (KPIs)* → métricas vía DAX.
3. *Genera cuadro de mando HTML de california_housing.csv* → gráficos sin usar el diseñador de informes.

## Tools MCP (`analytics__*`)

| Tool | Descripción |
|------|-------------|
| `analyze_dataset` | Estadísticas, correlaciones, recomendaciones |
| `build_dashboard` | Genera HTML con KPIs y gráficos |

Definidas en `mcps/analytics_server.py`; la lógica está en `analytics/dataset_report.py`.

## Añadir otro dataset

1. Copia el `.csv` a la raíz del proyecto o a `data/`.
2. Pide: *Genera un cuadro de mando de mi_archivo.csv*.

## Dependencias

`pandas` y `matplotlib` (en `requirements.txt`):

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Ver también: [mcp-servers.md](mcp-servers.md), [powerbi-mcp.md](powerbi-mcp.md).
