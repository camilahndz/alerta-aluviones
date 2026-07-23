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
python src/m1_preparar_dem.py     # baja el DEM, lo une y lo pasa a UTM 19S
python src/m1_terreno.py          # rellena, calcula flujo, delinea cuencas
python src/m1_recortar_region.py  # deja solo las cuencas que descargan en Coquimbo
```

Los dos parámetros que vale la pena mover están en el segundo:

| Parámetro | Qué controla |
|---|---|
| `--umbral-km2` | Área drenada mínima para considerar que hay cauce. Bajarlo densifica la red hacia las quebradas chicas. |
| `--area-min-km2` | Bajo qué tamaño se descarta una cuenca. |

**Sobre el margen:** la hidrología se corre sobre un área más grande que la región,
porque hay quebradas cuyas cabeceras nacen fuera del límite administrativo y
cortarlas daría áreas falsas. El tercer script filtra al final, conservando las
cuencas completas cuya desembocadura cae dentro de Coquimbo.

---

## Hoja de ruta (milestones)

- [x] **M0 — Andamiaje**: repo, estructura, README, primer commit.
- [ ] **M1 — Terreno**: DEM descargado; cuencas y red de quebradas delineadas.
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
