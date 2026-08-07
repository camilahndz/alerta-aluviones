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

Sobre esos valores. La primera pasada usó `--area-min-km2 2.0` y en M2 apareció
una sola cuenca capaz de generar flujos de detritos en toda la región, lo que no
tiene sentido para Coquimbo. El filtro estaba botando justamente las quebradas
chicas y empinadas, que son las que producen aluviones. Con 0,4 km² aparecen 18
cuencas capaces, y la mayor parte del inventario queda dentro del rango de tamaño
donde el índice de Melton está calibrado.

La hidrología se corre sobre un área mayor que la región. Hay quebradas cuyas
cabeceras nacen fuera del límite administrativo, y cortarlas daría áreas falsas.
El tercer script filtra al final y conserva las cuencas completas cuya
desembocadura cae dentro de Coquimbo.

### Resultado de M1

Con los parámetros de arriba se delinean 1.147 cuencas sobre el área con margen,
de las cuales 434 descargan dentro de la región. Suman 39.487 km² y 134.306
tramos de quebrada, y cubren el 96% de la superficie regional. El 4% restante
drena hacia Atacama, Valparaíso o Argentina, así que esas cuencas le pertenecen a
la región vecina.

La pasada anterior, con `--area-min-km2 2.0`, daba 174 cuencas. La superficie
drenada casi no cambia entre una y otra (39.257 contra 39.487 km²) porque las que
entran son pequeñas; lo que cambia es la resolución del inventario, y eso es lo
que M2 necesita.

Como control de que la delineación reproduce la hidrología real, se comparan las
tres cuencas mayores contra las áreas oficiales de la DGA:

| Cuenca | Delineada | Oficial DGA | Desvío |
|---|---|---|---|
| Choapa | 7.620,6 km² | ~7.650 km² | 0,4% |
| Elqui | 9.410,7 km² | ~9.657 km² | 2,5% |
| Limarí | 9.309,0 km² | ~11.800 km² | 21% |

La diferencia del Limarí probablemente sea de definición y no un error. La DGA
agrupa en esa cuenca varias quebradas costeras que hidrológicamente son
independientes; sumando la cuenca contigua (1.878 km²) se llega a 11.187 km²,
cerca del valor oficial. Queda por confirmar cuando estén los nombres a la vista.

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

De las 434 cuencas de la región, por el criterio de Wilford completo, 18 quedan
como flujo de detritos, 138 como crecida de detritos y 278 como inundación. La
razón de Melton máxima es 1,05 y la pendiente media máxima, 24°.

Queda pendiente el desglose de la columna `clase_melton` sobre la región
completa: la última corrida regional es anterior a que el script guardara las dos
clasificaciones.

Las 18 cuencas críticas miden entre 0,4 y 3 km², así que a escala regional son
invisibles. El mapa las marca con un círculo en la desembocadura, que es además
el punto que le importa a M3: por ahí sale el material hacia rutas y poblados.

La diferencia entre las dos columnas importa. Las cuencas más energéticas de toda
la región quedan descartadas por el criterio de largo, algunas por decenas de
metros sobre el umbral. Ese umbral es el parámetro heredado de otra región y es
lo primero que M5 debería recalibrar.

---

## Hoja de ruta

- [x] **M0 — Andamiaje**: repo, estructura, README, primer commit.
- [x] **M1 — Terreno**: DEM descargado; cuencas y red de quebradas delineadas.
- [x] **M2 — Susceptibilidad**: mapa de quebradas rankeadas por peligro (razón de Melton).
- [ ] **M3 — Exposición**: cruce con red vial y zonas urbanas → puntos de corte.
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
| Red vial y urbana | OpenStreetMap | Libre |
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

## Documentación adicional

[`docs/contexto.md`](docs/contexto.md) reúne el alcance del proyecto, las dos
mitades del modelo (susceptibilidad y gatillo), los criterios con que se
eligieron las fuentes de datos, las convenciones del repositorio y los puntos
donde este tipo de modelo suele fallar.
