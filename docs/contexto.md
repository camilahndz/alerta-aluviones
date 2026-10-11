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
| **M1** | Terreno: DEM, flujo, cuencas costeras, subcuencas de confluencia y troncos | Cerrado y reproducible en local — 3.757 unidades más 93 troncos de más de 50 km² (corrida 2026-10-10) |
| **M2** | Susceptibilidad: variables de terreno + quebradas rankeadas (razón de Melton) | Cerrado y reproducible en local — 2.589 susceptibles (corrida 2026-10-10) |
| **M3** | Exposición: cruce de trayectorias con red vial (OSM) y zonas urbanas | Cerrado y reproducible en local — desde el 11-10 suma la clase inundación (sin ríos) y ordena por clase, vía y área drenada en el cruce: 9.424 puntos de corte (extracto OSM del 08-10) |
| **M4** | Gatillo: lluvia sub-diaria de VIPNET + umbrales publicados aplicados | Cerrado y reproducible en local. Desde el 10-10 cubre tres inviernos (2024-2026), 1.188 episodios, con la lluvia de cada cuenca interpolada por random forest (MAE 29,9 mm contra 36,8 de la estación cercana). Desde el 11-10 suma la normal 1991-2020 de CR2MET y un indicador experimental de deshielo con la nieve de VIPNET |
| **M5** | Validación contra las activaciones documentadas de 2026 y calibración con 2024-2025 | Cerrado (corrida 2026-10-10, tres inviernos). Con negativos presuntos, Caine publicado tiene precisión de 4,5% (cota inferior) y AUC 0,47 en 2026; la curva ajustada baja el umbral sin mejorar el AUC. En el temporal de julio el I-D ordena (AUC 0,77); el bloque de agosto, de deshielo, no lo ve ningún umbral de lluvia. Desde el 11-10, también en los términos de una autoridad: por temporal Caine acierta (precisión 0,80), por provincia no (en Elqui no se activa nunca); y la lista de M3 cubre 4 de 11 cortes reales en su 3% de arriba, contra 1,0 al azar. Niveles de alerta por provincia con la lluvia del temporal como fracción de la normal de CR2MET: probados en 2026 sin un error de orden (AUC 1,00) y con AUC 0,95 en validación cruzada, contra 0,88 de Caine |
| **M6** | Entrega: alerta en vivo, visor y documentación | En curso desde el 11-10. La alerta en vivo por provincia (`src/m6_alerta_en_vivo.py`) corre contra VIPNET con el modelo de niveles congelado, y reproduce M5 en 41 de 41 provincias-temporal. Probada contra el temporal real del 6 de octubre de 2026. El visor, Vigía de quebradas (`src/m6_visor.py` y `visor/`), muestra la región en relieve con el nivel de cada provincia y repasa cuatro temporales reales hora a hora |

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
  NetCDF, Zenodo DOI 10.5281/zenodo.7529682). En uso desde octubre de 2026 para la
  normal 1991-2020 (`src/m4_climatologia.py`), leída por rangos dentro del zip
  sin bajar los 2,5 GB.
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

  Con tres inviernos apareció la versión extrema: el 9 y 10 de abril de 2026
  cinco estaciones registran a la vez entre 350 y 739 mm en un solo paso. Y
  apareció algo peor que el artefacto mismo: una regla que decide sobre la
  estación entera la bota por toda su historia. R4 por estación eliminaba a
  Cuncumén del temporal de julio por una falla de abril. **Una regla de calidad
  tiene que aplicarse con la misma granularidad que el daño que vigila**: R3
  pasó de la estación al episodio por eso, y R2 y R4 pasaron al invierno.

- **Contar aciertos sin línea base.** En octubre de 2026 la lista de cortes de
  M3 tenía candidato en 7 de 11 cortes de ruta reales, y parecía un buen
  resultado. Pero poniendo la misma ventana en puntos al azar de las mismas
  rutas se esperaban 5,3: en un valle con una quebrada por kilómetro,
  cualquier lista larga "acierta". Un acierto solo dice algo comparado con lo
  que daría el azar en el mismo lugar (`src/m5_cortes.py`). Con esa prueba se
  vio lo que faltaba: la clase de cuenca que M3 descartaba y un orden dentro de
  cada ruta.

- **Un umbral global sobre un gradiente climático.** Caine se ajustó con
  eventos de todo el mundo, y en Coquimbo la lluvia anual crece varias veces
  de norte a sur y de la costa a la cordillera. Por provincia y temporal
  (`src/m5_alerta_sector.py`), Caine no se activa en Elqui en ningún temporal
  de tres inviernos, incluido el del aluvión de Santa Gracia. Un umbral único
  queda alto justo donde llueve menos, que es donde cabe esperar que las
  quebradas respondan con menos lluvia. La literatura lo resuelve normalizando
  la lluvia por la precipitación media anual de cada lugar.

- **Suponer que todo lo que se activa lo gatilla la lluvia.** El bloque del 13
  al 17 de agosto de 2026 activó 20 zonas con una lluvia mediana de 4,6 mm, y
  el AUC de Caine sobre ese evento es 0,27: se activaron donde menos llovió. La
  prensa lo atribuyó al deshielo sobre suelos saturados. Un umbral I-D no tiene
  ninguna variable que vea eso, y evaluarlo contra esas activaciones mezcla dos
  mecanismos en una sola cifra.

  Desde octubre de 2026 hay un indicador experimental (`src/m4_deshielo.py`):
  nieve de las estaciones de VIPNET sobre 3.000 m e isoterma 0 extrapolada desde
  ellas. Ve el bloque de agosto y no se activa en 2024 ni en 2025, pero con un
  solo evento es una hipótesis con un caso a favor, no un resultado.

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

  **Y volvió a pasar, esta vez de escala.** En octubre de 2026 el satélite
  (`src/m5_satelite_troncos.py`) mostró que las quebradas que la prensa reportó
  activadas cambiaron en su tronco y no en las unidades del modelo que las tocan.
  15 de 23 drenan más de 50 km², el tope de una subcuenca de confluencia:
  Santa Gracia, la del aluvión del Islón, 1.073 km²; Marquesa, 736. El modelo
  las evalúa a través de afluentes chicos que, según el satélite, no hicieron
  nada. La corrección de M1 puso unidades donde faltaban, pero con un tope de
  tamaño que deja fuera justamente las quebradas grandes que se activaron. Ahí
  Melton ya no está calibrado —Wilford trabajó entre 0,1 y 10 km²—, así que la
  solución no es subir el tope sino agregar una segunda clase de unidad, el
  tronco, con su propio criterio.

  Se hizo (`src/m1_troncos.py`, 93 troncos) y el satélite lo confirma: de los 8
  troncos reportados en 2026, ninguno se ve inactivo. Pero arreglar el objeto
  dejó a la vista el límite siguiente. La lluvia que el modelo le asigna a cada
  tronco no separa los que bajaron de los que no (AUC 0,49 contra el satélite).
  Con pluviómetros no se resuelve cuánto llovió en una cuenca contra la vecina.
  **El límite del modelo hoy es la lluvia de entrada, no la unidad ni el
  umbral.**
