"""
M6 - Los datos del visor.

El visor (visor/index.html) es lo que ve alguien que no va a leer este
repositorio: un mapa de la region en relieve, las provincias pintadas con su
nivel de alerta, y temporales reales que se pueden repasar hora a hora. Este
script le prepara todo lo que necesita en visor/datos/, a partir de lo que ya
produjeron M1 a M6.

POR QUE EL MAPA BASE SE HACE ACA

    El visor se publica como una pagina que no puede pedir nada a servidores
    ajenos: ni teselas de OpenStreetMap ni de ningun otro mapa base. El relieve
    se arma entonces con el DEM del proyecto, Copernicus GLO-30, que ademas es
    el mismo terreno sobre el que se calcularon las cuencas. Salen tres
    imagenes de la misma grilla en grados:

        elevacion.png   la altura codificada en RGB (el formato terrain-RGB:
                        h = -10000 + (R*65536 + G*256 + B) * 0,1), que deck.gl
                        convierte en una malla 3D
        relieve.png     sombreado con colores de altitud, la textura de la malla
        provincias.png  el numero de provincia de cada pixel, para que el visor
                        pinte cada una con el color de su nivel

LOS REPASOS

    Cada temporal se recorre en pasos de 3 horas con m6_alerta_en_vivo.evaluar,
    la misma funcion que emite el boletin en vivo, sobre el cache de M4. Lo que
    el visor muestra en cada hora es lo que la alerta habria dicho a esa hora,
    no lo que se supo despues.

    Y con un modelo que no conocia ese invierno. La primera version repasaba
    todo con el modelo final, que se ajusto con estos mismos temporales: el
    repaso de julio de 2026 mostraba un acierto que el sistema no habria tenido
    en julio de 2026. Ahora cada repaso usa el modelo que m5_niveles.py ajusta
    dejando fuera su invierno, con sus propios cortes.

    El primer escenario es el boletin del momento en que se corre este script,
    pedido a VIPNET. Es una foto: el visor no se actualiza solo, y lo dice.

    Los cuatro temporales se eligieron para contar lo que el modelo hace y lo
    que no: julio de 2026 (el peor en 40 anios), el bloque de deshielo de
    agosto de 2026, el de fines de julio de 2025 (otro acierto, en otro
    invierno) y junio de 2025, donde fallo dos veces seguidas: una falsa alarma
    el 11 y una falla el 16.

Uso:

    python src/m6_visor.py                    # todo, ~25 minutos
    python src/m6_visor.py --solo-capas       # el mapa, sin repasar temporales
    python src/m6_visor.py --sin-vivo         # sin pedir el boletin de ahora

Los repasos usan unos 600 MB de RAM.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m5_alerta_sector as alerta  # noqa: E402
import m5_calibracion as cal  # noqa: E402
import m5_cortes as mc  # noqa: E402
import m5_validacion as m5  # noqa: E402
import m6_alerta_en_vivo as vivo  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "visor" / "datos"

CAJA = (-71.85, -32.40, -69.70, -28.95)      # oeste, sur, este, norte
RES_TEXTURA = 0.002                          # ~200 m
RES_ELEVACION = 0.004                        # ~400 m; la malla no necesita mas
SIMPLIFICAR_GRADOS = 0.0005                  # ~50 m, menos que un pixel de textura
PROVINCIAS = list(alerta.PROVINCIAS)
NIVELES = ["ninguna"] + [n for n, _ in vivo.niv.NIVELES]

ESCENARIOS = [
    {"id": "julio-2026", "titulo": "Julio de 2026", "desde": "2026-07-15 06:00",
     "hasta": "2026-07-23 00:00",
     "resumen": "El peor temporal en cuarenta anios en la region."},
    {"id": "agosto-2026", "titulo": "Agosto de 2026", "desde": "2026-08-11 06:00",
     "hasta": "2026-08-18 12:00",
     "resumen": "Lluvia sobre la nieve que dejo julio: el bloque de deshielo."},
    {"id": "julio-2025", "titulo": "Fines de julio de 2025", "desde": "2025-07-31 00:00",
     "hasta": "2025-08-08 06:00",
     "resumen": "Otro invierno, otro temporal con activaciones en las tres provincias."},
    {"id": "junio-2025", "titulo": "Junio de 2025", "desde": "2025-06-10 12:00",
     "hasta": "2025-06-17 12:00",
     "resumen": "Donde el modelo fallo: una falsa alarma el 11 y una falla el 16."},
]
PASO_H = 3

def guardar(nombre: str, datos):
    ruta = SALIDA / nombre
    ruta.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    print(f"  {nombre:<22} {ruta.stat().st_size / 1e6:>6.2f} MB")


def _r(v, d=4):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), d)


# =============================================================================
# El relieve
# =============================================================================

def leer_dem(res: float) -> np.ndarray:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds

    oeste, sur, este, norte = CAJA
    ancho, alto = round((este - oeste) / res), round((norte - sur) / res)
    with rasterio.open(RAIZ / "data" / "processed" / "dem_mosaico_wgs84.tif") as src:
        v = from_bounds(oeste, sur, este, norte, src.transform)
        a = src.read(1, window=v, out_shape=(alto, ancho), resampling=Resampling.average,
                     masked=True)
    return np.where(np.ma.getmaskarray(a), np.nan, np.ma.getdata(a)).astype("float32")


def rasters(provincias_geo):
    from matplotlib.colors import LightSource, LinearSegmentedColormap
    from PIL import Image
    from rasterio import features
    from rasterio.transform import from_bounds as transformada

    print("\nRelieve...")
    # --- elevacion en terrain-RGB ---
    h = np.nan_to_num(leer_dem(RES_ELEVACION), nan=0.0)
    v = np.clip(np.round((h + 10000.0) / 0.1), 0, 2 ** 24 - 1).astype(np.uint32)
    rgb = np.stack([(v >> 16) & 255, (v >> 8) & 255, v & 255], axis=-1).astype(np.uint8)
    Image.fromarray(rgb, "RGB").save(SALIDA / "elevacion.png", optimize=True)

    # --- sombreado con colores de altitud ---
    t = leer_dem(RES_TEXTURA)
    mar = ~np.isfinite(t) | (t <= 0)
    t0 = np.nan_to_num(t, nan=0.0)
    lat_media = np.radians((CAJA[1] + CAJA[3]) / 2)
    dx = RES_TEXTURA * 111_320 * np.cos(lat_media)
    dy = RES_TEXTURA * 110_574
    # Tonos de tierra apagados: el visor es oscuro y el color fuerte se reserva
    # para las alertas que se pintan encima.
    tonos = LinearSegmentedColormap.from_list("coquimbo", [
        (0.00, "#1f2725"), (0.08, "#2c302a"), (0.25, "#3f3a2f"),
        (0.50, "#58503f"), (0.75, "#776e62"), (1.00, "#b4afa7")])
    luz = LightSource(azdeg=315, altdeg=38)
    sombreado = luz.shade(t0, cmap=tonos, vmin=0, vmax=6000, blend_mode="soft",
                          vert_exag=2.0, dx=dx, dy=dy)
    img = (sombreado[..., :3] * 255).astype(np.uint8)
    img[mar] = (11, 20, 24)
    Image.fromarray(img, "RGB").save(SALIDA / "relieve.png", optimize=True)

    # --- provincias ---
    alto, ancho = t.shape
    afin = transformada(*CAJA, ancho, alto)
    indice = features.rasterize(
        [(g, i + 1) for i, g in enumerate(provincias_geo)], out_shape=(alto, ancho),
        transform=afin, fill=0, dtype="uint8")
    indice[mar] = 0
    Image.fromarray(indice * 60, "L").save(SALIDA / "provincias.png", optimize=True)
    print(f"  elevacion {h.shape[1]} x {h.shape[0]}, textura {ancho} x {alto} pixeles")


# =============================================================================
# Las capas
# =============================================================================

def lineas(gdf, columnas) -> dict:
    """Lineas como listas planas de coordenadas, con sus atributos al lado."""
    g = gdf.to_crs(4326)
    g["geometry"] = g.geometry.simplify(SIMPLIFICAR_GRADOS)
    salida = {c: [] for c in columnas}
    salida["c"] = []
    for _, f in g.iterrows():
        partes = list(getattr(f.geometry, "geoms", [f.geometry]))
        for p in partes:
            if p.is_empty or p.length == 0:
                continue
            salida["c"].append([round(x, 4) for xy in p.coords for x in xy[:2]])
            for c in columnas:
                v = f[c]
                v = v.item() if hasattr(v, "item") else v       # numpy -> python
                salida[c].append(_r(v, 1) if isinstance(v, float) else
                                 (None if pd.isna(v) else v))
    return salida


def capas(fijo):
    import geopandas as gpd

    print("\nCapas...")
    procesados = RAIZ / "data" / "processed"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        comunas = m5.cargar_comunas()

    # --- provincias ---
    comunas["provincia"] = comunas["clave"].map(alerta.PROVINCIA_DE)
    prov = comunas[comunas["provincia"].notna()].dissolve("provincia").to_crs(4326)
    prov = prov.loc[PROVINCIAS]
    bordes = {"provincia": [], "c": []}
    for nombre, f in prov.iterrows():
        g = f.geometry.simplify(0.003)
        for poli in getattr(g, "geoms", [g]):
            bordes["provincia"].append(nombre)
            bordes["c"].append([round(x, 4) for xy in poli.exterior.coords for x in xy])
    guardar("provincias.json", bordes)
    rasters(list(prov.geometry))

    # --- quebradas ---
    tray = gpd.read_file(procesados / "trayectorias.gpkg")
    troncos = gpd.read_file(procesados / "troncos_coquimbo.gpkg", ignore_geometry=True)
    tray = tray.merge(troncos[["id_cuenca", "nombre_osm"]], on="id_cuenca", how="left")
    guardar("quebradas.json", lineas(tray, ["id_cuenca", "clase", "area_km2", "nombre_osm"]))

    # --- rutas principales ---
    vias = gpd.read_file(RAIZ / "data" / "raw" / "osm" / "vias.gpkg")
    vias = vias[vias["highway"].isin(["motorway", "trunk", "primary", "secondary"])]
    guardar("rutas.json", lineas(vias, ["highway", "name"]))

    # --- cruces de ruta ---
    pc = gpd.read_file(procesados / "puntos_corte.gpkg", ignore_geometry=True)
    pc = pc.sort_values("rank")
    pc["provincia"] = pc["comuna"].map(lambda c: alerta.PROVINCIA_DE.get(m5.sin_tildes(c)))
    guardar("cruces.json", {
        "lon": pc["lon"].round(5).tolist(), "lat": pc["lat"].round(5).tolist(),
        "rank": pc["rank"].astype(int).tolist(),
        "via": [v if isinstance(v, str) and v else None for v in pc["via_nombre"]],
        "tipo": pc["via_tipo"].tolist(), "comuna": pc["comuna"].fillna("").tolist(),
        "provincia": pc["provincia"].fillna("").tolist(), "clase": pc["clase"].tolist(),
        "area": pc["area_cruce_km2"].round(1).tolist(), "id_cuenca": pc["id_cuenca"].astype(int).tolist(),
        "total": int(len(pc))})

    # --- estaciones ---
    est = fijo["catalogos"]["lluvia"]
    guardar("estaciones.json", {
        "codigo": est["codigo"].tolist(), "nombre": est["nombre"].tolist(),
        "lon": est["lon"].round(5).tolist(), "lat": est["lat"].round(5).tolist(),
        "altitud": [None if pd.isna(a) else int(a) for a in est["altitud_m"]],
        "normal": [None if pd.isna(n) else round(float(n)) for n in est["normal_mm"]],
        "provincia": est["provincia"].fillna("").tolist()})

    # --- localidades ---
    lugares = gpd.read_file(m5.OSM, layer="gis_osm_places_free", bbox=CAJA,
                            columns=["name", "fclass", "population"], engine="pyogrio")
    lugares = lugares[lugares["fclass"].isin(["city", "town"]) & lugares["name"].notna()]
    guardar("localidades.json", {
        "nombre": lugares["name"].tolist(), "tipo": lugares["fclass"].tolist(),
        "lon": lugares.geometry.x.round(4).tolist(), "lat": lugares.geometry.y.round(4).tolist()})

    activaciones(comunas)


def activaciones(comunas):
    """Las activaciones de los inventarios, ubicadas lo mejor que se pueda."""
    from shapely.ops import nearest_points

    inv = cal.cargar_inventario()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        osm = m5.cargar_osm()
    vias = mc.leer_vias()

    # Como se dibuja cada una depende de cuanto se sabe de donde fue:
    #   punto   un corte de ruta (m5_cortes) o un caserio con el nombre: el
    #           lugar se conoce con un error de poco mas de un kilometro;
    #   cauce   se ubico por el nombre de la quebrada en OSM: se dibuja el
    #           cauce entero, porque un punto en cualquier parte de un cauce de
    #           60 km dice mas de lo que se sabe;
    #   lista   solo se sabe la comuna, o ni eso: va a la lista del panel y no
    #           al mapa. La primera version las ponia en el centro de la comuna,
    #           o en el primer homonimo de la region si no traian comuna, y
    #           eso en un mapa es inventar un lugar.
    import geopandas as gpd

    filas, como_va = [], {"punto": 0, "cauce": 0, "lista": 0}
    for _, e in inv.iterrows():
        dibujo, punto, lineas, precision = "lista", None, None, None
        tiene_comuna = bool(m5._texto(e["comuna"]))
        if e["id"] in mc.CORTES:
            ref, capa, clave, _ = mc.CORTES[e["id"]]
            ruta = vias.loc[vias["ref"] == ref].geometry.union_all()
            geo = mc.localizar(capa, clave, e["comuna"], osm, comunas)
            punto, dibujo, precision = nearest_points(ruta, geo)[0], "punto", "corte de ruta"
        elif tiene_comuna and (m5._texto(e["quebrada"]) or m5._texto(e["sector"])):
            geo, como = m5.ubicar(e.to_dict(), osm, comunas)
            if geo is not None and "FUERA DE COMUNA" not in como:
                if como.startswith("lugar"):
                    punto, dibujo, precision = geo.representative_point(), "punto", "caserio"
                else:
                    lineas, dibujo, precision = geo, "cauce", "cauce"
        if dibujo == "lista":
            precision = "comuna" if tiene_comuna else "ninguna"
        como_va[dibujo] += 1
        fila = {"id": e["id"], "fecha": e["fecha"],
                "quebrada": m5._texto(e["quebrada"]) or None,
                "comuna": m5._texto(e["comuna"]) or None,
                "evidencia": e["evidencia"], "via": m5._texto(e["via_afectada"]) or None,
                "fuente": m5._texto(e["fuente"]) or None,
                "url": m5._texto(e["fuente_url"]) or None,
                "dibujo": dibujo, "precision": precision}
        if punto is not None:
            lon, lat = gpd_a_lonlat(punto)
            fila.update(lon=round(lon, 5), lat=round(lat, 5))
        if lineas is not None:
            g = gpd.GeoSeries([lineas], crs=m5.CRS_METRICO).to_crs(4326).iloc[0]
            g = g.simplify(SIMPLIFICAR_GRADOS)
            partes = [q for q in getattr(g, "geoms", [g]) if not q.is_empty]
            fila["lineas"] = [[round(x, 4) for xy in q.coords for x in xy[:2]] for q in partes]
            x0, y0, x1, y1 = g.bounds
            fila.update(lon=round((x0 + x1) / 2, 5), lat=round((y0 + y1) / 2, 5))
        filas.append(fila)
    print(f"  activaciones: {len(filas)}; en el mapa como punto {como_va['punto']}, como cauce "
          f"{como_va['cauce']}; solo en la lista {como_va['lista']}")
    guardar("activaciones.json", filas)


def gpd_a_lonlat(punto):
    import geopandas as gpd
    p = gpd.GeoSeries([punto], crs=m5.CRS_METRICO).to_crs(4326).iloc[0]
    return p.x, p.y


# =============================================================================
# Los repasos
# =============================================================================

def paso(r: dict, indice_est: dict) -> dict:
    prov = {}
    for p, v in r["provincias"].items():
        s = v["siguiente_nivel"] or {}
        # [nivel, prob, fraccion (segunda), mm (segunda), segunda estacion,
        #  siguiente nivel, mm que faltan, en que estacion, transmitiendo,
        #  datos insuficientes, la mas mojada, sus mm]
        prov[p] = [NIVELES.index(v["nivel"]), v["probabilidad"], v["fraccion_normal"],
                   v["lluvia_temporal_mm"], v["estacion_que_fija"],
                   s.get("nivel"), s.get("falta_mm"), s.get("estacion"),
                   v["estaciones_transmitiendo"], int(v["datos_insuficientes"]),
                   v["estacion_mas_mojada"], v["lluvia_mas_mojada_mm"]]
    est = [[indice_est[e["codigo"]], e["lluvia_mm"], e["fraccion_normal"]]
           for e in r.get("lluvia_por_estacion", []) if e["codigo"] in indice_est]
    t = r["temporal"]
    return {"t": r["momento"][:16], "temporal": None if t is None else t["inicio"][:16],
            "prov": prov, "desh": int(r["deshielo"]["activo"]), "est": est}


def escenarios(fijo, con_vivo: bool):
    print("\nRepasos (pasos de 3 horas, con la alerta en vivo sobre el cache de M4)...")
    indice_est = {c: i for i, c in enumerate(fijo["catalogos"]["lluvia"]["codigo"])}
    cache = vivo.CacheM4()
    # Cada repaso usa el modelo ajustado SIN su invierno (m5_niveles.py los
    # guarda). Con el modelo final, que se ajusto con estos mismos temporales,
    # el repaso mostraria un acierto que el sistema no habria tenido.
    modelos = json.loads((RAIZ / "outputs" / "m5_niveles_modelo.json").read_text())["sin_invierno"]
    salida = []
    for esc in ESCENARIOS:
        t0 = time.time()
        momento, hasta = vivo.momento_de(esc["desde"]), vivo.momento_de(esc["hasta"])
        desde = pd.Timestamp(esc["desde"])
        invierno = int(desde.year - (desde.month < 4))
        modelo = tuple(modelos[str(invierno)])
        umbrales = {n: round(vivo.fraccion_para(u, modelo), 3) for n, u in vivo.niv.NIVELES}
        pasos = []
        while momento <= hasta:
            pasos.append(paso(vivo.evaluar(momento, cache, fijo, modelo), indice_est))
            momento += pd.Timedelta(hours=PASO_H)
        salida.append({**esc, "invierno_excluido": invierno, "umbrales": umbrales, "pasos": pasos})
        cortes = ", ".join(f"{n} {v:.0%}" for n, v in umbrales.items())
        print(f"  {esc['titulo']:<24} {len(pasos):>3} pasos, modelo sin {invierno} "
              f"({cortes})  ({time.time() - t0:.0f} s)")
    if con_vivo:
        r = vivo.evaluar(vivo.momento_de(None), vivo.AlmacenVivo(), fijo)
        m = pd.Timestamp(r["momento"])
        umbrales = {n: round(vivo.fraccion_para(u), 3) for n, u in vivo.niv.NIVELES}
        salida.insert(0, {"id": "boletin", "titulo": "Boletin", "desde": r["momento"][:16],
                          "hasta": r["momento"][:16], "vivo": True, "umbrales": umbrales,
                          "resumen": f"El boletin del {m:%d-%m-%Y a las %H:%M}, con los datos de VIPNET.",
                          "pasos": [paso(r, indice_est)]})
        print(f"  Hoy: boletin de las {m:%H:%M}")
    guardar("escenarios.json", salida)


def resumen(fijo):
    """Las cifras que el visor cita, sacadas de las salidas y no escritas a mano."""
    niv = pd.read_csv(RAIZ / "outputs" / "m5_niveles.csv")
    prueba = niv[niv["prueba"]].copy()
    prueba["nivel_h"] = vivo.niv.nivel(prueba["p_holdout"])
    altas = prueba[prueba["nivel_h"].isin(["naranja", "roja"])]
    sin = prueba[prueba["nivel_h"] == "ninguna"]
    umbrales = {n: round(vivo.fraccion_para(p), 3) for n, p in vivo.niv.NIVELES}
    import geopandas as gpd
    guardar("resumen.json", {
        "umbrales": umbrales,
        "cuencas": int(len(gpd.read_file(RAIZ / "data" / "processed" / "susceptibilidad.gpkg",
                                         ignore_geometry=True))),
        "estaciones": int(len(fijo["catalogos"]["lluvia"])),
        "prueba_2026": {"naranja_o_roja": int(len(altas)), "con_activaciones": int(altas["y"].sum()),
                        "sin_nivel": int(len(sin)), "sin_nivel_con_activaciones": int(sin["y"].sum())},
        "positivos_calibracion": int(niv["y"].sum()), "casos_calibracion": int(len(niv)),
        "calibracion": vivo.CALIBRACION,
        "caja": CAJA,
    })


def main():
    ap = argparse.ArgumentParser(description="M6 - Prepara los datos del visor.")
    ap.add_argument("--solo-capas", action="store_true")
    ap.add_argument("--solo-escenarios", action="store_true")
    ap.add_argument("--sin-vivo", action="store_true")
    args = ap.parse_args()

    print("=" * 74)
    print("M6 - Datos del visor -> visor/datos/")
    print("=" * 74)
    SALIDA.mkdir(parents=True, exist_ok=True)
    fijo = vivo.preparar()
    if not args.solo_escenarios:
        capas(fijo)
        resumen(fijo)
    if not args.solo_capas:
        escenarios(fijo, not args.sin_vivo)
    total = sum(f.stat().st_size for f in SALIDA.iterdir()) / 1e6
    print(f"\n  total visor/datos/: {total:.1f} MB")

    # visor/index.html no trae <!doctype> ni <head>: el servicio donde se
    # publica envuelve la pagina con los suyos. Para verlo en local hace falta
    # esa envoltura, o el navegador lo dibuja en modo de compatibilidad.
    cuerpo = (RAIZ / "visor" / "index.html").read_text(encoding="utf-8")
    (RAIZ / "visor" / "_local.html").write_text(
        '<!doctype html>\n<html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        '<style>body{margin:0}</style>\n' + cuerpo + "\n</body></html>\n", encoding="utf-8")
    print("  para verlo: python -m http.server 8765 --directory visor, y abrir "
          "http://localhost:8765/_local.html")


if __name__ == "__main__":
    main()
