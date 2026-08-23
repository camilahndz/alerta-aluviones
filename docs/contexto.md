# Contexto técnico de alerta-aluviones

Este documento define el alcance y los criterios de diseño del proyecto. El
README documenta lo que ya está implementado y cómo se corre; este archivo
explica hacia dónde va y por qué se tomaron ciertas decisiones. Ante una
discrepancia entre ambos, este documento describe la intención.

---

## Qué es

Modelo de riesgo de activación de quebradas (flujos de detritos / aluviones) para
la Región de Coquimbo, Chile. Dado un escenario de lluvia, predice:

1. Qué quebradas se activan.
2. Qué rutas y zonas urbanas quedan expuestas (cortes de camino, población
   aislada).

Se valida contra el temporal de julio 2026, el peor en ~40 años en la región
(fallecidos, ~99 mil aislados, 40+ cortes de ruta por activación de quebradas).

## Para qué

Proyecto personal de portafolio, en el marco de Ingeniería Civil Industrial en la
UCN Coquimbo. **No es investigación novedosa**: es un sistema aplicado,
reproducible y validado contra un evento real. La prioridad es que funcione, que
sea claro y que se pueda defender, por sobre la sofisticación.

## Alcance

- **Objetivo: Nivel 2** = susceptibilidad + umbral de lluvia + exposición +
  validación.
- **Fuera de alcance (Nivel 3):** runout físico con reología (RAMMS / FLO-2D) y
  operación en tiempo real con alertas. No se aborda hasta cerrar lo básico.
- **Ejecución local.** El pipeline está pensado para correr en un notebook, sin
  depender de infraestructura remota.

## Las dos mitades del modelo

Son cosas distintas y no deben confundirse.

**Susceptibilidad** — mapa estático de dónde *puede* originarse un flujo. Depende
del terreno, no del clima. Variables: pendiente, acumulación de flujo, índice de
poder de corriente (SPI), curvatura, área de cuenca, geología, cobertura
vegetal. Enfoque: primero heurístico (razón de Melton), luego random forest si
llega a haber inventario.

**Gatillo** — umbral de lluvia intensidad-duración (I-D) sobre el cual una
quebrada se activa. Es la parte dinámica, y se calibra contra eventos
observados.

> La susceptibilidad no es un pronóstico y no debe presentarse como tal.

---

## Pipeline (hitos)

| Hito | Contenido | Estado |
|---|---|---|
| **M0** | Andamiaje: repo, estructura, README, .gitignore, primer commit | Cerrado |
| **M1** | Terreno: DEM, relleno de sumideros, dirección y acumulación de flujo, cuencas y red de quebradas | Cerrado y reproducible en local (corrida 2026-08-23) |
| **M2** | Susceptibilidad: variables de terreno + quebradas rankeadas (razón de Melton) | Cerrado y reproducible en local (corrida 2026-08-23) |
| **M3** | Exposición: cruce de trayectorias con red vial (OSM) y zonas urbanas | Cerrado — 422 puntos de corte (corrida 2026-08-23) |
| **M4** | Gatillo: umbral I-D calibrado con eventos observados (incl. julio 2026) | No iniciado |
| **M5** | Validación: matriz de confusión vs. lo ocurrido; precisión, recall, AUC ROC | No iniciado |
| **M6** | Entrega: mapa/visor final + documentación | No iniciado |

M0–M3 = v0 mostrable. M4–M5 = v1 (calibración y validación).

---

## Fuentes de datos (todas gratuitas)

- **DEM:** Copernicus GLO-30 (TanDEM-X, 30 m real, bucket público AWS
  `s3://copernicus-dem-30m/`, sin credenciales).
  **No usar ALOS PALSAR "12,5 m":** fuera de EE.UU. está remuestreado desde SRTM
  30 m, es resolución falsa. Plan B para hidrología: FABDEM (GLO-30 corregido,
  quita edificios y vegetación; licencia solo no comercial / investigación).
- **Precipitación climatológica:** CR2MET v2.5 (0,05°, diario, 1960–2021,
  NetCDF, Zenodo DOI 10.5281/zenodo.7529682).
- **Precipitación evento jul-2026:** estaciones DGA/DMC (Explorador Climático
  CR2, DataClima) + GPM IMERG (0,1°, 30 min). **IMERG subestima la lluvia
  orográfica en los Andes:** hay que corregir sesgo contra estaciones antes de
  usarlo.
- **Geología / peligro:** SERNAGEOMIN.
- **Red vial y urbana:** OpenStreetMap. Se usa el extracto de Chile de
  Geofabrik (`chile-latest-free.gpkg.zip`, se baja del navegador y lo lee
  geopandas), **no la API de Overpass**. Overpass limita a 2 consultas
  simultáneas por IP y M3 necesita ~48, así que la descarga no completa; y
  además responde con el mapa del instante, lo que hace que ninguna corrida sea
  reproducible. El extracto tiene fecha.
- **Validación satelital:** Sentinel-1 (SAR, ve a través de nubes) y Sentinel-2
  (óptico) vía Copernicus Data Space o Google Earth Engine.

## Stack

Python: rasterio, geopandas, numpy, scikit-learn, matplotlib, osmnx.
Hidrología: pysheds o richdem (o GRASS GIS si se requiere `r.watershed` /
`r.avaflow`). Visualización: QGIS. Satelital: Google Earth Engine.

---

## Convenciones del repositorio

- `data/raw/` = datos originales, intocables, **no** se suben a git.
- `data/processed/` = todo lo derivado; reconstruible corriendo el código.
- Commits pequeños, en español, con mensaje claro (ej.: `M1: acumulacion de
  flujo`).
- Cada script explica en comentarios **qué** hace y **por qué**, no solo cómo.
- Si se borran `data/processed/` y `outputs/`, deben poder regenerarse desde
  `data/raw/`.

## Puntos donde este tipo de proyecto suele fallar

- **DEM de baja resolución:** 30 m es el techo sin LiDAR; las quebradas angostas
  se pierden.
- **Lluvia satelital sin corregir sesgo:** mete error justo en la variable que
  gatilla.
- **Pocos eventos para calibrar el umbral:** conviene sumar todo el Norte Chico,
  no solo Coquimbo.
- **Confundir susceptibilidad con predicción.**
- **Sobre-modelar:** saltar a runout físico antes de cerrar susceptibilidad +
  umbral.
- **Correr sobre un DEM parcial sin notarlo:** un recorte de prueba que queda en
  disco produce cifras que se ven plausibles pero cubren una fracción del
  territorio. Además, las cuencas cortadas por el borde del raster quedan con el
  área truncada, y como la razón de Melton es H/√A, eso **infla** el índice y
  fabrica cuencas críticas falsas. Pasó de verdad en agosto de 2026 y está medido:
  sobre el DEM truncado el Melton máximo daba 1,504 contra 1,009 del completo, y
  las cuencas de flujo de detritos salían 38 contra 21. Por eso `src/cobertura.py`
  verifica cobertura al inicio de los cinco scripts que leen un DEM, y aborta bajo
  el 99%.

- **Que la unidad de análisis no coincida con el fenómeno.** M1 corta cuencas solo
  donde el terreno termina, o sea en la costa, así que las quebradas interiores
  quedan absorbidas en las cuencas de río y nunca se evalúan por separado. Cuatro
  cuencas concentran el 83% de la superficie drenada y las cuatro son de clase
  inundación. El índice funciona; lo que falla es a qué objetos se lo aplica.
