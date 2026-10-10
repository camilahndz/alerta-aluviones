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
| **M1** | Terreno: DEM, flujo, cuencas costeras y subcuencas de confluencia | Cerrado y reproducible en local — 3.757 unidades (corrida 2026-10-10) |
| **M2** | Susceptibilidad: variables de terreno + quebradas rankeadas (razón de Melton) | Cerrado y reproducible en local — 2.589 susceptibles (corrida 2026-10-10) |
| **M3** | Exposición: cruce de trayectorias con red vial (OSM) y zonas urbanas | Cerrado y reproducible en local — 3.669 puntos de corte en 14 comunas (corrida 2026-10-10, extracto OSM del 08-10) |
| **M4** | Gatillo: lluvia sub-diaria de VIPNET + umbrales publicados aplicados | Cerrado y reproducible en local (corrida 2026-10-10). 668 de 2.589 cuencas superan Caine, todas en valles interiores |
| **M5** | Validación contra las activaciones documentadas de julio 2026 | Cerrado (corrida 2026-10-10). Recall 27%; las fallas caen a 0,75 de Caine. **No hay matriz de confusión ni AUC**: el inventario de prensa no tiene negativos observados |
| **M6** | Entrega: visor y documentación | No iniciado |

M4 cambió de contenido respecto de lo que este documento proyectaba. Decía
"umbral I-D **calibrado**" y lo que se pudo hacer fue aplicar umbrales
**publicados**: con tres bloques de activaciones documentadas no hay con qué
calibrar una curva, y ajustarla sobre tres puntos habría sido dibujar, no
medir. Calibrar es M5.

M0–M3 = v0 mostrable. M4–M5 = v1 (calibración y validación).

M5 también cambió de contenido respecto de lo proyectado. Decía "matriz de
confusión, precisión, recall y AUC ROC" y solo el recall resultó estimable: un
inventario armado con prensa registra lo que alguien reportó, así que tiene
positivos observados y no negativos. Calcular precisión contra él equivaldría a
suponer que las 650 cuencas marcadas que no salieron en el diario no se
activaron, y eso no se sabe. La métrica que falta no es un pendiente de código
sino de datos.

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

- **Que una estación desaparezca en vez de fallar.** Un dato que no calza con lo
  que el código espera -una marca de tiempo a los :59 cuando la grilla es de 30
  minutos, una estación horaria en una red de media hora- no produce un error:
  produce cero registros, que el resto del pipeline trata como "no reportó". En
  M4 eso borraba estaciones enteras, entre ellas Glaciar Tapado y Río Cuncumén.
  Es la misma familia del cuadro vacío contra la consulta fallida de M3 y del DEM
  truncado de M1: **el error que no da error**. La defensa es contar cuántas
  unidades entran y cuántas salen de cada paso, y mirar la diferencia.

- **Confundir un artefacto del instrumento con una medición.** El contador de un
  pluviómetro sube por dos motivos: porque llovió o porque el equipo hizo algo.
  Un pluviómetro que vuelve de un corte vuelca de golpe todo lo acumulado, y uno
  sobre la isoterma 0 suelta la nieve derretida de varios días. Los dos producen
  intensidades de 30 minutos enormes y perfectamente falsas. La señal que los
  delata es la forma: la lluvia real sube y baja, un artefacto es un escalón
  entre ceros.

- **Que la unidad de análisis no coincida con el fenómeno.** Es el error más caro
  que tuvo este proyecto y conviene dejarlo escrito completo. M1 cortaba cuencas
  solo donde el terreno termina, o sea en la costa, así que las quebradas
  interiores quedaban absorbidas en las cuencas de río y nunca se evaluaban por
  separado. El índice funcionaba; lo que fallaba era a qué objetos se le aplicaba.

  Costó tres meses detectarlo porque no producía ningún error, solo una
  conclusión plausible: M4 reportaba que ninguna cuenca superaba ningún umbral de
  lluvia durante el peor temporal en cuarenta años. Sonaba a hallazgo —"un umbral
  I-D global no describe este régimen"— y era un artefacto. Las cuencas costeras
  se emparejaban con estaciones costeras, que midieron la mitad de lluvia que las
  del interior, y en el interior no había ninguna cuenca que evaluar.

  Lo que lo delató fue cruzar el modelo contra el inventario de activaciones de
  julio de 2026: ocho de dieciocho ocurrieron en cuatro comunas sin una sola
  unidad de análisis. La corrección está en `src/m1_subcuencas.py`, que delinea
  una unidad en cada confluencia con un valle. Con eso, 668 de 2.589 cuencas
  superan Caine, todas interiores.

  La moraleja es general y vale para cualquier modelo espacial: **antes de creerle
  a un resultado agregado, conviene preguntarse sobre qué objetos se calculó y si
  esos objetos existen donde el fenómeno ocurre.**
