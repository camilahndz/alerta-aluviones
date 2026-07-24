# alerta-aluviones

Modelo de riesgo de activación de quebradas para la Región de Coquimbo, Chile.
Predice qué quebradas se activan ante una lluvia dada y qué rutas y zonas urbanas
quedan expuestas. Validado contra el temporal de julio 2026 (el peor en ~40 años).

> Proyecto personal · Ingeniería Civil Industrial · UCN Coquimbo

---

## Qué hace

1. **Susceptibilidad** — mapea qué quebradas son propensas a generar flujos de detritos,
   usando el modelo de elevación (pendiente, acumulación de flujo, geología).
2. **Gatillo** — calibra el umbral de lluvia (intensidad × duración) sobre el cual
   cada quebrada se activa.
3. **Exposición** — cruza las trayectorias de flujo con la red vial y las zonas
   pobladas para identificar cortes de ruta y población en riesgo.
4. **Validación** — compara la predicción contra lo que ocurrió en julio 2026.

---

## Estructura del repo

```
alerta-aluviones/
├── README.md
├── .gitignore
├── requirements.txt
├── data/
│   ├── raw/          # datos originales, NO se modifican ni se suben a git
│   └── processed/    # datos derivados (generados por el código)
├── notebooks/        # exploración y pruebas
├── src/              # código ordenado y reutilizable
└── outputs/          # mapas y resultados finales
```

Regla: si borro todo `data/processed/` y `outputs/`, tengo que poder reconstruirlo
corriendo el código sobre `data/raw/`. Los datos pesados no van a git (ver `.gitignore`).

---

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`rasterio` y `geopandas` dependen de GDAL/PROJ. Si pip falla en Windows, instalar
esas dos con conda/mamba y el resto con pip.

---

## Cómo se corre M1

Tres scripts, en este orden:

```bash
python src/m1_preparar_dem.py                                       # baja el DEM, lo une y lo pasa a UTM 19S
python src/m1_terreno.py --umbral-km2 0.15 --area-min-km2 0.4       # rellena, calcula flujo, delinea cuencas
python src/m1_recortar_region.py                                    # deja solo las que descargan en Coquimbo
```

Los dos parámetros que vale la pena mover están en el segundo:

| Parámetro | Qué controla |
|---|---|
| `--umbral-km2` | Área drenada mínima para considerar que hay cauce. Bajarlo densifica la red hacia las quebradas chicas. |
| `--area-min-km2` | Bajo qué tamaño se descarta una cuenca. |

**Por qué esos valores.** La primera pasada usó `--area-min-km2 2.0` y el resultado
en M2 fue absurdo: una sola cuenca capaz de generar flujos de detritos en toda la
región. El filtro estaba descartando justamente las quebradas chicas y empinadas,
que son las que producen aluviones. Bajándolo a 0,4 km² las cuencas capaces pasan
de 1 a 38, y el 85% del total queda dentro del rango donde el índice de Melton
está calibrado.

**Sobre el margen:** la hidrología se corre sobre un área más grande que la región,
porque hay quebradas cuyas cabeceras nacen fuera del límite administrativo y
cortarlas daría áreas falsas. El tercer script filtra al final, conservando las
cuencas completas cuya desembocadura cae dentro de Coquimbo.

### Resultado de M1

Con la primera pasada (`--area-min-km2 2.0`): 174 cuencas · 39.257 km² ·
42.425 tramos de quebrada · 96% de la región cubierta. Con los parámetros finos
de arriba el número de cuencas sube, porque entran las quebradas chicas.

El 4% restante drena hacia Atacama, Valparaíso o Argentina, así que esas cuencas
le pertenecen a la región vecina.

Contraste contra las áreas oficiales de la DGA, como control de que la
delineación reproduce la hidrología real:

| Cuenca | Delineada | Oficial DGA | Desvío |
|---|---|---|---|
| Choapa | 7.620,6 km² | ~7.650 km² | 0,4% |
| Elqui | 9.410,7 km² | ~9.657 km² | 2,5% |
| Limarí | 9.309,0 km² | ~11.800 km² | 21% |

La diferencia del Limarí probablemente sea de definición y no un error: la DGA
agrupa en esa cuenca varias quebradas costeras que hidrológicamente son
independientes. Sumando la cuenca contigua (1.878 km²) se llega a 11.187 km²,
cerca del valor oficial. Queda por confirmar en M2, con los nombres a la vista.

---

## Cómo se corre M2

```bash
python src/m2_susceptibilidad.py
```

Clasifica cada cuenca según su capacidad de generar flujos de detritos, usando la
**razón de Melton** — el desnivel dividido por la raíz del área, que mide cuánta
energía potencial tiene la cuenca por unidad de tamaño:

```
R = desnivel (km) / √área (km²)
```

Los umbrales no son inventados: vienen de
[Wilford et al. (2004)](https://link.springer.com/article/10.1007/s10346-003-0002-0),
calibrados contra eventos reales.

| Razón de Melton | Tipo de evento |
|---|---|
| < 0,30 | Inundación de agua |
| 0,30 – 0,60 | Crecida de detritos |
| ≥ 0,60 y cuenca ≤ 2,7 km de largo | **Flujo de detritos** (aluvión) |

El largo entra en la clasificación porque una cuenca empinada pero alargada
disipa energía en el trayecto y deposita el material antes de la salida.

**Se guardan dos clasificaciones, no una.** La razón de Melton es robusta y de uso
universal, pero el umbral de largo sale del estudio original en la Columbia
Británica costera —bosque templado lluvioso— y no hay evidencia de que el mismo
valor sirva en el norte semiárido de Chile. Sobre los datos de Coquimbo ese
umbral resulta decisivo: varias de las cuencas más energéticas de la región
quedan descartadas por diferencias de decenas de metros. Esconder esa
sensibilidad eligiendo un criterio a ciegas sería deshonesto, así que la capa
trae las dos columnas:

| Columna | Criterio |
|---|---|
| `clase` | Wilford completo: Melton **y** largo de la cuenca |
| `clase_melton` | Solo la razón de Melton |

M5, al comparar contra el temporal de julio 2026, va a decir cuál de las dos
reproduce mejor lo que realmente pasó.

**Límite conocido:** Melton se calibró en cuencas de 0,1 a 10 km². Las cuencas
grandes (Elqui, Limarí, Choapa) son cuencas de río, no quebradas de aluvión; el
script las clasifica igual pero las marca con `melton_aplicable = False`.

---

## Hoja de ruta (milestones)

- [x] **M0 — Andamiaje**: repo, estructura, README, primer commit.
- [x] **M1 — Terreno**: DEM descargado; cuencas y red de quebradas delineadas.
- [ ] **M2 — Susceptibilidad**: mapa de quebradas rankeadas por peligro (heurístico).
- [ ] **M3 — Exposición**: cruce con red vial y zonas urbanas → puntos de corte.
- [ ] **M4 — Gatillo de lluvia**: umbral intensidad-duración calibrado.
- [ ] **M5 — Validación**: comparación contra julio 2026 + métricas.
- [ ] **M6 — Entrega**: mapa/visor final y documentación.

M0–M3 = versión mínima mostrable (v0). M4–M5 = calibración y validación (v1).

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

> **Sobre el DEM:** el README original apuntaba a ALOS PALSAR "12,5 m". Ese producto
> se descartó: los RTC de alta resolución se generan desde NED13 (solo EE.UU.) o
> desde SRTM 30 m, y para Chile aplica el segundo caso. La documentación de ASF
> dice que esos productos son *"up sampled from the 30-m version to 12.5 m"*, o sea
> que los píxeles miden 12,5 m pero el detalle real sigue siendo de 30 m.
> Copernicus GLO-30 entrega 30 m reales derivados de TanDEM-X: a igual resolución
> efectiva, es mejor dato y pesa seis veces menos.

---

## Stack

Python (rasterio, geopandas, scikit-learn), GRASS GIS / pysheds para hidrología,
QGIS para visualización, Google Earth Engine para lo satelital.

---

## Prompts de arranque para Claude Code

> M0 — "Crea la estructura de carpetas de este README, un .gitignore de Python que
> excluya data/raw/ y data/processed/, y un requirements.txt con rasterio, geopandas,
> scikit-learn, numpy, matplotlib. Inicializa git y haz el primer commit."

> M1 — "Tengo un DEM en data/raw/dem.tif. Escribe un script en src/ que lo cargue,
> rellene sumideros, calcule dirección y acumulación de flujo, y delinee las cuencas.
> Guarda los resultados en data/processed/. Explícame en comentarios qué hace cada paso."
