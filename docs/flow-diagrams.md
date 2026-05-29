# Diagramas de flujo desde CSV (sustituto de Visio)

Genera diagramas de proceso **interactivos** a partir de CSV de transiciones entre trámites, sin Microsoft Visio. El visor usa [vis-network](https://visjs.org/) (colores, arrastre, foco por clic).

## Dataset: `tramites.csv`

Formato (tabla de adyacencias — una fila = una transición):

| Columna | Significado |
|---------|-------------|
| `id_tramite_anterior` | ID del paso origen |
| `descripcion_tramite_anterior` | Nombre del trámite origen |
| `num_orden` | Número de rama (1, 2, 3…) |
| `id_tramite_siguiente` | ID del paso destino |
| `descripcion_tramite_siguiente` | Nombre del trámite destino |

Ejemplo:

```
31900 REGISTRO DE SOLICITUD ──(1)──► 31902 DATOS DEL EXPEDIENTE
                            ──(2)──► 31903 INADMISIÓN POR FUERA DE PLAZO
                            ──(3)──► 32305 EXPEDIENTE ANULADO
```

Estadísticas del fichero incluido: **106 transiciones**, **86 trámites** únicos.

---

## Uso en el chat

| Petición | Resultado |
|----------|-----------|
| *Genera el diagrama de flujo de tramites.csv* | HTML interactivo (2 vistas) |
| *Analiza la estructura del proceso en tramites.csv* | Resumen (nodos, entradas, ramas) |
| *Diagrama desde REGISTRO DE SOLICITUD* | Vista desde trámite **31900** (4 niveles) |

Chips en la tarjeta **Análisis de datos** en http://localhost:8000

CLI equivalente:

```powershell
.\venv\Scripts\python.exe -c "from analytics.flow_diagram import generate_flow_diagram; print(generate_flow_diagram())"
```

---

## Archivos generados

Tras generar, los informes quedan en `data/reports/` (HTML servido por la API):

| Archivo | Contenido |
|---------|-----------|
| `tramites_registro.html` | Vista principal — desde **31900**, 4 niveles, layout jerárquico |
| `tramites_completo.html` | Grafo completo (86 trámites), layout con física |
| `tramites_*.mmd` | Export Mermaid (referencia; el visor principal es HTML) |

URLs (con `run_web.ps1` en marcha):

- http://localhost:8000/reports/tramites_registro.html
- http://localhost:8000/reports/tramites_completo.html

Recarga forzada tras regenerar: **Ctrl+F5** en el navegador.

---

## Visor interactivo

### Controles

| Acción | Efecto |
|--------|--------|
| **Clic en nodo** | Resalta trámites anteriores y siguientes; panel lateral |
| **Arrastrar nodo** | Mueve la entidad en el canvas |
| **Buscar** | Ir a trámite por ID (ej. `31902`) o por nombre |
| **Quitar foco** | Restaura colores de todo el grafo |
| **Centrar vista** | Ajusta zoom al diagrama |

### Colores por tipo

Nodos con **fondo claro y texto oscuro** (alto contraste sobre el canvas oscuro):

| Fondo | Texto | Tipo |
|-------|-------|------|
| Verde claro | Verde oscuro | Inicio (Registro) |
| Cyan claro | Azul oscuro | Notificación |
| Ámbar claro | Marrón oscuro | Propuesta / resolución |
| Rojo claro | Rojo oscuro | Fin / publicación |
| Violeta claro | Violeta oscuro | Proceso intermedio |

### Formas

| Heurística en la descripción | Forma |
|------------------------------|-------|
| REGISTRO DE SOLICITUD | Óvalo (inicio) |
| NOTIFICACIÓN | Caja (documento) |
| PROPUESTA / RESOLUCIÓN | Rombo (decisión) |
| PUBLICACIÓN BOCYL / BDNS | Óvalo (fin) |
| Resto | Caja (proceso) |

---

## Tools MCP (`analytics__*`)

| Tool | Descripción |
|------|-------------|
| `analyze_flow` | Estadísticas del grafo (entradas, ramas, columnas detectadas) |
| `build_flow_diagram` | Genera HTML interactivo + export `.mmd` |

Definidas en `mcps/analytics_server.py`. Lógica en `analytics/flow_diagram.py`.

---

## Flujo directo en el agente

Preguntas con *diagrama*, *flujo*, *visio* o *tramites.csv* disparan generación en Python **sin depender del LLM** (`agent_core._flow_diagram_direct`). Detección en `_should_run_flow_diagram()`.

---

## Arquitectura

```
tramites.csv
    ↓
analytics/flow_diagram.py   parse → grafo → vis-network JSON → HTML
    ↓
mcps/analytics_server.py    tools MCP
    ↓
agent_core.py               flujo directo + chips web
    ↓
GET /reports/{filename}     client/app.py sirve HTML
```

---

## Añadir otro CSV de procesos

1. Coloca el `.csv` en la raíz o en `data/`.
2. Usa columnas compatibles con `tramites.csv` o formato Visio (Process Step ID / Next Step ID).
3. Pide: *Genera el diagrama de flujo de mi_archivo.csv*.

---

## Referencias

- [mcp-servers.md](mcp-servers.md) — catálogo MCP y chips
- [analytics-dashboard.md](analytics-dashboard.md) — dashboards numéricos (California Housing)
- [web-server.md](web-server.md) — ruta `/reports`
