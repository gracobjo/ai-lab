# Diagramas de flujo desde CSV (sustituto de Visio)

Genera diagramas de proceso **HTML + Mermaid** a partir de CSV de transiciones entre trámites, sin Microsoft Visio.

## Dataset: `tramites.csv`

Formato (tabla de adyacencias):

| Columna | Significado |
|---------|-------------|
| `id_tramite_anterior` | ID del paso origen |
| `descripcion_tramite_anterior` | Nombre del trámite origen |
| `num_orden` | Número de rama (1, 2, 3…) |
| `id_tramite_siguiente` | ID del paso destino |
| `descripcion_tramite_siguiente` | Nombre del trámite destino |

## Uso en el chat

| Petición | Resultado |
|----------|-----------|
| *Genera el diagrama de flujo de tramites.csv* | HTML interactivo |
| *Analiza la estructura del proceso en tramites.csv* | Resumen (nodos, entradas, ramas) |
| *Diagrama desde REGISTRO DE SOLICITUD* | Vista desde trámite **31900** (4 niveles) |

Chips en la tarjeta **Análisis de datos** en http://localhost:8000

## Archivos generados

| Archivo | Contenido |
|---------|-----------|
| `data/reports/tramites_registro.html` | Vista principal (desde 31900, legible) |
| `data/reports/tramites_completo.html` | Grafo completo (86 trámites) |
| `data/reports/tramites_*.mmd` | Fuente Mermaid (editable) |

Abrir en el navegador (visor **interactivo** con colores, arrastre y foco por clic):

- http://localhost:8000/reports/tramites_registro.html
- http://localhost:8000/reports/tramites_completo.html

### Controles del visor

| Acción | Efecto |
|--------|--------|
| **Clic en nodo** | Resalta trámites anteriores y siguientes; panel lateral |
| **Arrastrar nodo** | Mueve la entidad en el canvas |
| **Buscar** | Ir a trámite por ID o nombre |
| **Quitar foco** | Muestra todo el grafo a color de nuevo |
| **Centrar vista** | Ajusta zoom al diagrama |

### Colores

| Color | Tipo |
|-------|------|
| Verde | Inicio (Registro) |
| Cyan | Notificación |
| Ámbar | Propuesta / resolución |
| Rojo | Fin / publicación BOCYL |
| Violeta | Proceso intermedio |

## Tools MCP (`analytics__*`)

| Tool | Descripción |
|------|-------------|
| `analyze_flow` | Estadísticas del grafo de trámites |
| `build_flow_diagram` | Genera HTML + Mermaid |

## Formas automáticas

| Tipo de trámite | Forma en el diagrama |
|-----------------|----------------------|
| REGISTRO DE SOLICITUD | Inicio (óvalo) |
| NOTIFICACIÓN | Documento |
| PROPUESTA / RESOLUCIÓN | Decisión (rombo) |
| PUBLICACIÓN BOCYL / BDNS | Fin |

Ver también: [mcp-servers.md](mcp-servers.md), [analytics-dashboard.md](analytics-dashboard.md).
