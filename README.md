# alerta-aluviones

Modelo de riesgo de activación de quebradas para la Región de Coquimbo, Chile.
Predice qué quebradas se activan ante una lluvia dada y qué rutas y zonas urbanas
quedan expuestas. Se valida contra el temporal de julio de 2026, el peor en unos
cuarenta años.

---

## Qué hace

1. **Susceptibilidad**: mapea qué quebradas son propensas a generar flujos de
   detritos, usando el modelo de elevación (pendiente, acumulación de flujo,
   geología).
2. **Gatillo**: calibra el umbral de lluvia (intensidad × duración) sobre el cual
   cada quebrada se activa.
3. **Exposición**: cruza las trayectorias de flujo con la red vial y las zonas
   pobladas para identificar cortes de ruta y población en riesgo.
4. **Validación**: compara la predicción contra lo que ocurrió en julio de 2026.

---

## Estructura del repositorio

```
alerta-aluviones/
├── README.md
├── .gitignore
├── requirements.txt
├── data/
│   ├── raw/          # datos originales, NO se modifican ni se suben a git
│   └── processed/    # datos derivados (generados por el código)
├── docs/             # documentación técnica
├── notebooks/        # exploración y pruebas
├── src/              # código ordenado y reutilizable
└── outputs/          # mapas y resultados finales
```

Regla: si se borra todo `data/processed/` y `outputs/`, se debe poder
reconstruirlo corriendo el código sobre `data/raw/`. Los datos pesados no van a
git (ver `.gitignore`).

---

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`rasterio` y `geopandas` dependen de GDAL/PROJ. Si pip falla en Windows, conviene
instalar esas dos con conda o mamba y el resto con pip.

---

## Cómo se corre M1

Tres scripts, en este orden:

```bash
python src/m1_preparar_dem.py                                   # baja el DEM, lo une y lo pasa a UTM 19S
python src/m1_terreno.py --umbral-km2 0.15 --area-min-km2 0.4   # rellena, calcula flujo, delinea cuencas
python src/m1_recortar_region.py                                # deja solo las que descargan en Coquimbo
```

Los dos parámetros que vale la pena mover están en el segundo. `--umbral-km2`
fija el área drenada mínima para considerar que hay cauce: bajarlo densifica la
red hacia las quebradas chicas. `--area-min-km2` fija bajo qué tamaño se descarta
una cuenca.

Sobre esos valores. La primera pasada usó `--area-min-km2 2.0` y en M2 no
apareció ninguna cuenca capaz de generar flujos de detritos en toda la región, lo
que no tiene sentido para Coquimbo. El filtro estaba botando justamente las
quebradas chicas y empinadas, que son las que producen aluviones. Con 0,4 km²
aparecen 21 cuencas capaces, y la mayor parte del inventario queda dentro del
rango de tamaño donde el índice de Melton está calibrado.

La hidrología se corre sobre un área mayor que la región. Hay quebradas cuyas
cabeceras nacen fuera del límite administrativo, y cortarlas daría áreas falsas.
El tercer script filtra al final y conserva las cuencas completas cuya
desembocadura cae dentro de Coquimbo.

### Resultado de M1

Con los parámetros de arriba se delinean 950 cuencas sobre el área con margen, de
las cuales 444 descargan dentro de la región. Suman 39.523 km² y 134.329 tramos
de quebrada, y cubren el 96% de la superficie regional. El 4% restante drena
hacia Atacama, Valparaíso o Argentina, así que esas cuencas le pertenecen a la
región vecina.

La pasada anterior, con `--area-min-km2 2.0`, daba 170 cuencas. La superficie
drenada casi no cambia entre una y otra (39.280 contra 39.523 km², un 0,6%)
porque las que entran son pequeñas; lo que cambia es la resolución del
inventario, y eso es lo que M2 necesita.

Como control de que la delineación reproduce la hidrología real, se comparan las
tres cuencas mayores contra las áreas oficiales de la DGA. Cada una se identifica
por su desembocadura, comparando las coordenadas de salida contra las bocas
conocidas de cada río:

| Cuenca | Delineada | Oficial DGA | Desvío |
|---|---|---|---|
| Choapa | 7.620,4 km² | ~7.650 km² | 0,4% |
| Elqui | 9.408,2 km² | ~9.657 km² | 2,6% |
| Limarí | 11.675,1 km² | ~11.800 km² | 1,1% |

Las tres quedan bajo el 3%, que para una delineación automática de 30 m contra
una medición estatal independiente es un resultado fuerte.

Una versión anterior de este README reportaba el Limarí en 9.309,0 km², un 21% de
desvío, y lo atribuía a una diferencia de criterio: que la DGA agrupara ahí
quebradas costeras hidrológicamente independientes. Sobre el DEM completo esa
hipótesis resulta innecesaria, porque el Limarí se delinea entero y cuadra con la
cifra oficial. Tampoco existe la "cuenca contigua de 1.878 km²" que aquel
razonamiento sumaba: después de Los Choros (4.051,7 km²) la cuenca siguiente mide
742,2 km². El 21% era un artefacto de la corrida, no una diferencia de
definición.

---

## Cómo se corre M2

```bash
python src/m2_susceptibilidad.py
```

Clasifica cada cuenca según su capacidad de generar flujos de detritos con la
razón de Melton, que es el desnivel dividido por la raíz del área y mide cuánta
energía potencial tiene la cuenca por unidad de tamaño:

```
R = desnivel (km) / √área (km²)
```

Los umbrales vienen de
[Wilford et al. (2004)](https://link.springer.com/article/10.1007/s10346-003-0002-0),
calibrados contra eventos reales:

| Razón de Melton | Tipo de evento |
|---|---|
| < 0,30 | Inundación de agua |
| 0,30 a 0,60 | Crecida de detritos |
| ≥ 0,60 y cuenca ≤ 2,7 km de largo | **Flujo de detritos** (aluvión) |

El largo entra en la clasificación porque una cuenca empinada pero alargada
disipa energía en el trayecto y deposita el material antes de la salida.

La capa guarda dos clasificaciones. La razón de Melton se usa igual en todo el
mundo, pero el umbral de largo sale del estudio original en la Columbia Británica
costera, de clima templado lluvioso, y no hay evidencia de que ese valor sirva en
el norte semiárido de Chile. Sobre los datos de Coquimbo el umbral resulta
decisivo: varias de las cuencas más energéticas de la región quedan descartadas
por diferencias de decenas de metros. Elegir un criterio a ciegas escondería esa
sensibilidad, así que la columna `clase` aplica Wilford completo (Melton más
largo) y `clase_melton` aplica solo la razón de Melton. Al comparar contra el
temporal de julio de 2026, M5 va a decir cuál de las dos reproduce mejor lo que
pasó.

Un límite conocido: Melton se calibró en cuencas de 0,1 a 10 km². Las cuencas
grandes (Elqui, Limarí, Choapa) son cuencas de río, no quebradas de aluvión. El
script las clasifica igual, pero las marca con `melton_aplicable = False`.

### Resultado de M2

De las 444 cuencas de la región, las dos columnas dan esto:

| Clase | `clase` (Wilford completo) | `clase_melton` (solo Melton) |
|---|---|---|
| Flujo de detritos | 21 | 33 |
| Crecida de detritos | 146 | 134 |
| Inundación | 277 | 277 |

La razón de Melton máxima es 1,009 y la pendiente media máxima, 24,9°. Ninguna
cuenca quedó marcada como `borde_truncado`.

Las 21 cuencas críticas miden entre 0,43 y 1,07 km², así que a escala regional
son invisibles. El mapa las marca con un círculo en la desembocadura, que es
además el punto que le importa a M3: por ahí sale el material hacia rutas y
poblados.

La diferencia entre las dos columnas importa, y ahora está medida: **12 cuencas
cambian de clase según el criterio de largo**. Las 12 son las más energéticas de
la región y quedan descartadas solo por ser alargadas, algunas por decenas de
metros sobre el umbral: la primera del ranking, con Melton 1,01, mide 2,84 km de
largo contra un umbral de 2,7. Ese umbral es el parámetro heredado de otra región
y es lo primero que M5 debería recalibrar.

### Un límite estructural de M2, que conviene decir antes que lo pregunten

Las 21 cuencas críticas están todas en la franja costera: sus desembocaduras caen
entre las longitudes −71,71 y −71,29, y ninguna se extiende al este de −71,27. La
región llega hasta −69,81.

No es que el interior no tenga quebradas peligrosas. Es que M1 define una
desembocadura como la última celda con terreno antes del vacío, o sea la costa,
así que toda quebrada del interior es afluente del Elqui, del Limarí o del Choapa
y no recibe cuenca propia. Queda absorbida en una cuenca de diez mil kilómetros
cuadrados cuyo Melton es bajo por construcción, porque el área va en el
denominador.

El reparto lo muestra sin ambigüedad: **4 cuencas concentran el 82,9% de la
superficie drenada** y las cuatro son de clase inundación, mientras que las 380
cuencas que caen dentro del rango donde Melton está calibrado (≤ 10 km²) suman el
1,7%.

O sea que hoy el índice solo *ve* las quebradas que descargan al mar. Para el
temporal de julio de 2026, cuyos cortes de ruta ocurrieron en buena parte en
valles interiores, esta es la limitación de fondo del modelo y no un detalle. La
salida es subdividir las cuencas grandes por sus confluencias en vez de cortarlas
solo en el mar, y es trabajo de M5 con el evento a la vista.

---

## Cómo se corre M3

```bash
python src/m3_exposicion.py
```

Cruza el cauce principal de cada cuenca susceptible con la red vial y las zonas
urbanas, y devuelve los puntos donde una ruta cruza el fondo de una quebrada
capaz de generar flujo.

Necesita el extracto de OpenStreetMap de Chile, que se baja una vez del
navegador y se deja descomprimido en `data/raw/osm/chile.gpkg`:

```
https://download.geofabrik.de/south-america/chile.html
```

El archivo es `chile-latest-free.gpkg.zip`, unos 750 MB. Si no está, el script
consulta Overpass, pero eso no es recomendable: Overpass limita a dos consultas
simultáneas por IP y M3 necesita del orden de cuarenta y ocho, así que la
descarga se cae a mitad de camino. Peor aún para un proyecto que quiere ser
reproducible, Overpass responde con el mapa de este instante: dos corridas
separadas por un mes no son comparables. El extracto tiene fecha.

### Resultado de M3

De las 444 cuencas de la región, 167 son susceptibles (21 de flujo de detritos y
146 de crecida) y a las 167 se les trazó el cauce principal, con un largo mediano
de 1,80 km. Contra 46.246 tramos de vía, salen **422 puntos de corte**.

| Jerarquía de la vía | Cortes | Peso |
|---|---|---|
| track (huella rural) | 122 | 0,10 |
| residential | 91 | 0,30 |
| unclassified | 79 | 0,30 |
| **motorway** | **73** | **1,00** |
| service | 24 | 0,15 |
| tertiary | 20 | 0,45 |
| living_street | 8 | 0,20 |
| motorway_link | 5 | 0,15 |

Por comuna: Coquimbo 117, La Higuera 94, La Serena 79, Ovalle 49, Canela 42,
Los Vilos 40 y Salamanca 1. Por clase de la cuenca de origen, 351 vienen de
crecida de detritos y 71 de flujo de detritos.

Los 73 cortes sobre la Ruta 5 Norte son el resultado que le da sentido al hito:
es la vía troncal del país cruzando, una por una, las quebradas costeras que M2
marcó como capaces. Diez de esos cortes tienen prioridad 1,00, el máximo posible,
por combinar una cuenca de flujo de detritos con una vía de peso máximo.

Un límite de la tabla de vías: 265 de los 422 cortes caen en vías sin nombre en
OpenStreetMap, casi todas huellas y caminos sin clasificar. El ranking por nombre
solo describe a los 157 restantes.

**El reporte de localidades alcanzadas está subestimado y no debe citarse.** M3
filtra las zonas urbanas a polígonos, y en la Región de Coquimbo las localidades
—La Serena, Coquimbo, Tongoy, Combarbalá, Monte Patria— están mapeadas como
puntos, 1.113 en total, que ese filtro descarta. Lo que hoy se reporta como
localidad sale del nombre de los polígonos de uso de suelo, que son barrios y
sitios. Decidir si una trayectoria que pasa cerca de un punto poblado cuenta como
alcance urbano es una decisión de modelo y queda para M5.

---

## Hoja de ruta

- [x] **M0 — Andamiaje**: repo, estructura, README, primer commit.
- [x] **M1 — Terreno**: DEM descargado; cuencas y red de quebradas delineadas.
- [x] **M2 — Susceptibilidad**: mapa de quebradas rankeadas por peligro (razón de Melton).
- [x] **M3 — Exposición**: cruce con red vial y zonas urbanas → 422 puntos de corte.
- [ ] **M4 — Gatillo de lluvia**: umbral intensidad-duración calibrado.
- [ ] **M5 — Validación**: comparación contra julio de 2026 y métricas.
- [ ] **M6 — Entrega**: mapa o visor final y documentación.

M0 a M3 forman la versión mínima mostrable (v0). M4 y M5 son calibración y
validación (v1).

---

## Fuentes de datos

| Dato | Fuente | Acceso |
|---|---|---|
| Modelo de elevación (DEM) | Copernicus GLO-30 (TanDEM-X, 30 m) | Libre, sin registro |
| Precipitación climatológica | CR2MET (CR2) | Libre |
| Precipitación evento jul-2026 | Estaciones DGA/DMC + GPM IMERG | Libre |
| Geología / peligro | SERNAGEOMIN | Libre |
| Red vial y urbana | OpenStreetMap, extracto de Chile de Geofabrik | Libre, sin registro |
| Validación satelital | Sentinel-1 / Sentinel-2 (Copernicus) | Libre (registro) |

Sobre el DEM: la primera versión de este README apuntaba a ALOS PALSAR de
"12,5 m". Ese producto se descartó. Los RTC de alta resolución se generan desde
NED13, que solo cubre Estados Unidos, o desde SRTM de 30 m, y para Chile aplica
el segundo caso. La documentación de ASF dice que esos productos vienen
remuestreados hacia arriba desde la versión de 30 m, o sea que los píxeles miden
12,5 m pero el detalle real sigue siendo de 30 m. Copernicus GLO-30 entrega 30 m
reales derivados de TanDEM-X: a igual resolución efectiva es mejor dato y pesa
seis veces menos.

---

## Stack

Python (rasterio, geopandas, scikit-learn), GRASS GIS o pysheds para hidrología,
QGIS para visualización y Google Earth Engine para lo satelital.

---

## Reproducibilidad

Toda cifra de este README sale de una corrida guardada en
[`docs/corridas/`](docs/corridas/), con la salida de consola completa y las
verificaciones derivadas anotadas al final. La corrida de referencia de M1 y M2
es [`2026-08-23_m1_m2.txt`](docs/corridas/2026-08-23_m1_m2.txt), hecha en local
sobre el DEM completo, con la cobertura verificada al 100% de la superficie
regional antes de calcular nada.

Esto existe porque durante un tiempo no fue así. Entre el 7 y el 23 de agosto de
2026 el repositorio reportaba cifras de una corrida remota que no se podían
reproducir en local, sobre un DEM al que le faltaba el tercio sur de la región.
El capítulo 12 del recorrido cuenta el episodio completo. La regla que quedó: si
un número no salió de una corrida guardada en `docs/corridas/`, no entra a este
README.

---

## Documentación adicional

[`docs/contexto.md`](docs/contexto.md) reúne el alcance del proyecto, las dos
mitades del modelo (susceptibilidad y gatillo), los criterios con que se
eligieron las fuentes de datos, las convenciones del repositorio y los puntos
donde este tipo de modelo suele fallar.
