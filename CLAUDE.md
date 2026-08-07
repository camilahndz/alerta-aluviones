# CLAUDE.md — contexto permanente de alerta-aluviones

Leer al inicio de cada sesión. Si algo de aquí choca con el README, manda este archivo:
el README documenta lo que ya se hizo, este archivo define hacia dónde va el proyecto.

---

## Qué es

Modelo de riesgo de activación de quebradas (flujos de detritos / aluviones) para la
Región de Coquimbo, Chile. Dado un escenario de lluvia, predice:

1. Qué quebradas se activan.
2. Qué rutas y zonas urbanas quedan expuestas (cortes de camino, población aislada).

Se valida contra el temporal de julio 2026, el peor en ~40 años en la región
(fallecidos, ~99 mil aislados, 40+ cortes de ruta por activación de quebradas).

## Para qué

Proyecto personal de portafolio. Estudiante de Ingeniería Civil Industrial, UCN Coquimbo,
para postular a práctica verano 2027. **No es investigación novedosa**: es un sistema
aplicado, reproducible y validado con un evento real. Prioriza que funcione, sea claro y
se pueda defender en una entrevista, por sobre la sofisticación.

## Alcance

- **Objetivo: Nivel 2** = susceptibilidad + umbral de lluvia + exposición + validación.
- **Fuera de alcance (Nivel 3):** runout físico con reología (RAMMS / FLO-2D), operación
  en tiempo real con alertas. No meterse ahí hasta cerrar lo básico.
- **Ejecución: LOCAL, en el notebook.** No usar servidor remoto para este proyecto.

## Las dos mitades del modelo (no confundirlas)

**SUSCEPTIBILIDAD** — mapa estático de dónde *puede* originarse un flujo. Depende del
terreno, no del clima. Variables: pendiente, acumulación de flujo, índice de poder de
corriente (SPI), curvatura, área de cuenca, geología, cobertura vegetal. Enfoque: primero
heurístico (sumas ponderadas o razón de Melton), luego random forest si hay inventario.

**GATILLO** — umbral de lluvia intensidad-duración (I-D) sobre el cual una quebrada se
activa. Es la parte dinámica. Se calibra contra eventos observados.

> No presentar la susceptibilidad como si fuera un pronóstico. Son cosas distintas.

---

## Pipeline (milestones)

| Hito | Contenido | Estado |
|---|---|---|
| **M0** | Andamiaje: repo, estructura, README, .gitignore, primer commit | Cerrado |
| **M1** | Terreno: DEM, relleno de sumideros, dirección y acumulación de flujo, cuencas y red de quebradas | Cerrado |
| **M2** | Susceptibilidad: variables de terreno + quebradas rankeadas (razón de Melton) | Cerrado |
| **M3** | Exposición: cruce de trayectorias con red vial (OSM) y zonas urbanas | No iniciado |
| **M4** | Gatillo: umbral I-D calibrado con eventos observados (incl. julio 2026) | No iniciado |
| **M5** | Validación: matriz de confusión vs. lo ocurrido; precisión, recall, AUC ROC | No iniciado |
| **M6** | Entrega: mapa/visor final + documentación | No iniciado |

M0–M3 = v0 mostrable. M4–M5 = v1 (calibración y validación).

---

## Fuentes de datos (todas gratis)

- **DEM:** Copernicus GLO-30 (TanDEM-X, 30 m real, bucket público AWS
  `s3://copernicus-dem-30m/`, sin credenciales).
  **NO usar ALOS PALSAR "12,5 m":** fuera de EE.UU. está remuestreado desde SRTM 30 m,
  es resolución falsa. Plan B para hidrología: FABDEM (GLO-30 corregido, quita edificios
  y vegetación; licencia solo no comercial / investigación).
- **Precipitación climatológica:** CR2MET v2.5 (0,05°, diario, 1960–2021, NetCDF,
  Zenodo DOI 10.5281/zenodo.7529682).
- **Precipitación evento jul-2026:** estaciones DGA/DMC (Explorador Climático CR2,
  DataClima) + GPM IMERG (0,1°, 30 min). **IMERG subestima la lluvia orográfica en los
  Andes:** hay que corregir sesgo contra estaciones antes de usarlo.
- **Geología / peligro:** SERNAGEOMIN.
- **Red vial y urbana:** OpenStreetMap (osmnx).
- **Validación satelital:** Sentinel-1 (SAR, ve a través de nubes) y Sentinel-2 (óptico)
  vía Copernicus Data Space o Google Earth Engine.

## Stack

Python: rasterio, geopandas, numpy, scikit-learn, matplotlib, osmnx.
Hidrología: pysheds o richdem (o GRASS GIS si se requiere `r.watershed` / `r.avaflow`).
Visualización: QGIS (local, gráfico). Satelital: Google Earth Engine.

---

## Convenciones del repo

- `data/raw/` = datos originales, intocables, **no** se suben a git.
- `data/processed/` = todo lo derivado; reconstruible corriendo el código.
- Commits pequeños, en español, con mensaje claro (ej.: `M1: acumulacion de flujo`).
- Cada script explica en comentarios **qué** hace y **por qué**, no solo cómo.
- Si borro `data/processed/` y `outputs/`, debo poder regenerarlos desde `data/raw/`.

## Puntos donde este tipo de proyecto suele fallar (vigilar)

- **DEM de baja resolución:** 30 m es el techo sin LiDAR; las quebradas angostas se pierden.
- **Lluvia satelital sin corregir sesgo:** mete error justo en la variable que gatilla.
- **Pocos eventos para calibrar el umbral:** sumar todo el Norte Chico, no solo Coquimbo.
- **Confundir susceptibilidad con predicción.**
- **Sobre-modelar:** saltar a runout físico antes de cerrar susceptibilidad + umbral.

---

## Bitácora externa

Este proyecto se registra también en la carpeta de memoria de Camila:
`D:\Camila\Escritorio\memoria claude\` — ver `06_Base_Conocimiento/Datos_Canonicos.md`
(proyecto 5) y `Pendientes.md`. Cualquier métrica que salga de aquí y vaya al CV o al
portafolio tiene que quedar escrita allá con su nivel de certeza.

Última actualización: 2026-08-07.
