"""
M1 (segunda extension) - Unidades troncales: las quebradas grandes.

La idea de fondo:

    m1_subcuencas.py agrego las unidades que faltaban en los valles interiores:
    una por cada afluente que entra a un valle, de 0,4 a 50 km2. El tope de 50
    km2 decia "sobre esto ya no es una quebrada". En octubre de 2026 el
    satelite mostro que esa frase es falsa para Coquimbo, y lo mostro con las
    quebradas que de verdad se activaron.

    De las 23 quebradas que la prensa reporto activadas en 2025 y 2026 con
    cauce en OpenStreetMap, 15 drenan mas de 50 km2: Santa Gracia, la del
    aluvion del Islon, 1.073 km2; Marquesa, 736. Sentinel-2 ve el cambio en su
    TRONCO (AUC 0,89 contra lineas nulas) y no en las unidades del modelo que
    las tocan, que son afluentes chicos. El modelo estaba evaluando objetos que
    no son los que se activan. Ver src/m5_satelite_troncos.py.

    Este script agrega una segunda clase de unidad: el tronco.

QUE ES UN TRONCO, FIJADO ANTES DE MIRAR COMO RINDE

    Una boca de afluente con las mismas reglas de m1_subcuencas.py -entra a una
    confluencia, no es la rama mas caudalosa, el receptor drena 200 km2 o mas y
    el afluente no pasa de un cuarto del receptor- pero con mas de 50 km2, que
    es exactamente donde terminan las unidades actuales. Sin tope de tamano
    propio: lo acota la razon con el receptor.

    Y que OpenStreetMap no lo llame "Rio". Esta es la regla que separa una
    quebrada de un rio, y se toma de afuera a proposito. Un rio (el Hurtado, el
    Cogoti, el Turbio) tiene caudal permanente y su peligro es el desborde, que
    es otro fenomeno y otro modelo. Una quebrada o un estero es seco casi todo
    el anio y cuando se activa baja con sedimento. Elegir el corte por tamano
    mirando que area tenian las quebradas reportadas habria sido ajustar contra
    la validacion; el nombre lo puso otra gente, por otros motivos.

    El nombre se lee en los ultimos 3 km del cauce principal antes de la boca:
    el nombre de OSM que mas largo comparte con ese tramo. Un tronco sin nombre
    en OSM entra: no hay evidencia de que sea un rio.

POR QUE EL AREA COMPLETA Y NO UNA PARTICION

    m1_subcuencas.py reparte el territorio: cada celda pertenece a la primera
    boca que encuentra aguas abajo, y las unidades no se solapan. Para un tronco
    eso estaria mal. Si la quebrada San Carlos recibe un afluente de 80 km2, ese
    afluente tambien es un tronco, y con una particion San Carlos quedaria sin
    sus 80 km2 de cabecera. La lluvia que entra a San Carlos es la de toda su
    cuenca, asi que cada tronco lleva su area completa, y los troncos quedan
    anidados entre si y sobre las subcuencas chicas. La columna `origen` los
    separa.

QUE NO SE HACE CON ELLOS EN M2

    Melton esta calibrado entre 0,1 y 10 km2 (Wilford et al., 2004). A cientos
    de km2 no hay indice de susceptibilidad publicado que este proyecto pueda
    defender, asi que M2 no los filtra: les pone `clase = "tronco"` y guarda
    su Melton solo como referencia. Todos se evaluan. Es una decision declarada,
    no un olvido, y es el pendiente principal de esta clase de unidad.

Uso:

    python src/m1_troncos.py     # despues de m1_subcuencas.py

Pide cerca de 3 GB de RAM durante unos minutos: lee los rasters de flujo
completos, igual que m1_subcuencas.py.
"""

from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cobertura import COBERTURA_MINIMA, verificar_cobertura  # noqa: E402
from m1_subcuencas import (bocas_de_afluente, cargar_flujo, etiquetar,  # noqa: E402
                           indice_aguas_abajo, vectorizar)

RAIZ = Path(__file__).resolve().parent.parent
CRS_METRICO = "EPSG:32719"

# Los id de tronco arrancan aca: 1..n son costeras, 100.000+ subcuencas.
ID_BASE_TRONCO = 200_000

AREA_MIN_KM2 = 50.0        # donde terminan las subcuencas de m1_subcuencas.py
VALLE_MIN_KM2 = 200.0      # mismas reglas de boca que m1_subcuencas.py
RAZON_MAX = 0.25
UMBRAL_CAUCE_KM2 = 0.15
TRAMO_NOMBRE_M = 3000.0    # largo del cauce, desde la boca, donde se lee el nombre
RADIO_NOMBRE_M = 100.0


def es_rio(nombre) -> bool:
    if not isinstance(nombre, str):
        return False
    n = nombre.strip().lower()
    return n.startswith("rio ") or n.startswith("río ")


def nombre_osm(linea, cauces_osm) -> str | None:
    """El nombre de OSM que mas largo comparte con el tramo final del cauce."""
    from shapely.ops import substring

    if linea is None or linea.length == 0:
        return None
    # La linea va de cabecera a boca: el tramo final es el de la boca.
    tramo = substring(linea, max(0.0, linea.length - TRAMO_NOMBRE_M), linea.length)
    zona = tramo.buffer(RADIO_NOMBRE_M)
    cerca = cauces_osm[cauces_osm.intersects(zona)]
    if cerca.empty:
        return None
    largo = cerca.geometry.intersection(zona).length
    nombre = cerca.loc[largo.idxmax(), "name"]
    # OSM tiene cauces dibujados sin nombre: el campo llega como NaN.
    return nombre if isinstance(nombre, str) and nombre.strip() else None


def main():
    ap = argparse.ArgumentParser(description="M1 - Unidades troncales (quebradas de mas de 50 km2).")
    ap.add_argument("--procesados", type=Path, default=RAIZ / "data" / "processed")
    args = ap.parse_args()

    t0 = time.time()
    print("=" * 70)
    print("M1 (segunda extension) - Troncos de las quebradas grandes")
    print("=" * 70)

    fdir, acc, afin, crs, m2_pixel = cargar_flujo(args.procesados)
    verificar_cobertura(args.procesados / "dem_utm19s.tif",
                        RAIZ / "data" / "raw" / "limite_coquimbo.gpkg", COBERTURA_MINIMA)
    umbral_celdas = int(round(UMBRAL_CAUCE_KM2 * 1e6 / m2_pixel))

    print("\nBuscando bocas de afluente de mas de 50 km2...")
    abajo = indice_aguas_abajo(fdir)
    bocas, areas = bocas_de_afluente(acc, abajo, m2_pixel, umbral_celdas, VALLE_MIN_KM2,
                                     AREA_MIN_KM2, np.inf, RAZON_MAX)
    print(f"  {len(bocas)} bocas")

    # --- Region y borde, antes de lo caro ---
    columnas = fdir.shape[1]
    sx = afin.c + afin.a * (bocas % columnas + 0.5)
    sy = afin.f + afin.e * (bocas // columnas + 0.5)
    limite = gpd.read_file(RAIZ / "data" / "raw" / "limite_coquimbo.gpkg").to_crs(
        CRS_METRICO).geometry.union_all()
    en_region = gpd.GeoSeries(gpd.points_from_xy(sx, sy), crs=CRS_METRICO).within(limite).to_numpy()
    print(f"  {int(en_region.sum())} con la boca dentro de la region")

    # --- Particion y arbol: cada tronco con su area completa ---
    print("\nEtiquetando por duplicacion de punteros...")
    etq = etiquetar(abajo, bocas)
    piezas = vectorizar(etq, fdir.shape, afin, crs, m2_pixel)
    pieza_de = dict(zip(piezas["boca_plana"], piezas.geometry))
    # El padre de un tronco es el tronco al que pertenece la celda de abajo de
    # su boca. Recorriendo hacia arriba se juntan todos los descendientes.
    padre = {int(b): int(etq[abajo[b]]) for b in bocas}
    hijos: dict[int, list[int]] = {}
    for b, p in padre.items():
        if p >= 0 and p != b:
            hijos.setdefault(p, []).append(b)

    def descendientes(b):
        pila, todos = [b], []
        while pila:
            x = pila.pop()
            todos.append(x)
            pila.extend(hijos.get(x, []))
        return todos

    # El borde del raster: un tronco que lo toca tiene el area truncada.
    del_borde = set()
    for franja in (etq.reshape(fdir.shape)[1, :], etq.reshape(fdir.shape)[-2, :],
                   etq.reshape(fdir.shape)[:, 1], etq.reshape(fdir.shape)[:, -2]):
        del_borde.update(int(v) for v in np.unique(franja) if v >= 0)

    filas = []
    for b, a, x, y, dentro in zip(bocas, areas, sx, sy, en_region):
        if not dentro:
            continue
        desc = descendientes(int(b))
        geo = gpd.GeoSeries([pieza_de[d] for d in desc if d in pieza_de]).union_all()
        filas.append({"boca_plana": int(b), "salida_x": x, "salida_y": y,
                      "pixeles": int(round(a * 1e6 / m2_pixel)), "area_km2": float(a),
                      "toca_borde": any(d in del_borde for d in desc),
                      "n_troncos_dentro": len(desc) - 1, "geometry": geo})
    troncos = gpd.GeoDataFrame(filas, crs=CRS_METRICO)
    del etq, abajo

    # --- Nombre en OSM y descarte de los rios ---
    print("\nLeyendo el nombre de cada tronco en OpenStreetMap...")
    import m5_validacion as m5
    from m3_exposicion import cauce_principal
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        osm = m5.cargar_osm()
    cauces_osm = osm[osm["capa"] == "cauce"]

    inverso = ~afin
    lineas, nombres = [], []
    for x, y in zip(troncos["salida_x"], troncos["salida_y"]):
        col, fila = inverso * (x, y)
        ln = cauce_principal(fdir, acc, int(fila), int(col), afin, umbral_celdas)
        lineas.append(ln)
        nombres.append(nombre_osm(ln, cauces_osm))
    troncos["nombre_osm"] = nombres
    troncos["es_rio"] = troncos["nombre_osm"].map(es_rio)

    print(f"  {len(troncos)} troncos en la region; con nombre en OSM: "
          f"{int(troncos['nombre_osm'].notna().sum())}")
    # Limite conocido de la regla: "Rio Seco" queda fuera aunque su nombre dice
    # lo contrario de un rio permanente. La regla se fijo antes de mirar y no se
    # ajusta caso a caso; queda anotado.
    print(f"  descartados por llamarse Rio: {int(troncos['es_rio'].sum())}")
    for n in sorted(troncos.loc[troncos["es_rio"], "nombre_osm"].unique()):
        print(f"    {n}")
    print(f"  descartados por tocar el borde del raster: "
          f"{int((~troncos['es_rio'] & troncos['toca_borde']).sum())}")

    troncos = troncos[~troncos["es_rio"] & ~troncos["toca_borde"]].copy()
    troncos = troncos.sort_values("area_km2", ascending=False).reset_index(drop=True)
    troncos["id_cuenca"] = ID_BASE_TRONCO + np.arange(1, len(troncos) + 1)
    troncos["origen"] = "tronco"

    print(f"\nTroncos que entran: {len(troncos)}")
    print(f"  area: mediana {troncos['area_km2'].median():.0f} km2, "
          f"p90 {troncos['area_km2'].quantile(.9):.0f}, maximo {troncos['area_km2'].max():.0f}")
    print(f"  con nombre: {int(troncos['nombre_osm'].notna().sum())}; los mayores:")
    for _, t in troncos.head(15).iterrows():
        print(f"    {int(t['id_cuenca'])}  {t['area_km2']:>7.0f} km2  {t['nombre_osm'] if pd.notna(t['nombre_osm']) else '(sin nombre)'}")

    cols = ["id_cuenca", "origen", "salida_x", "salida_y", "pixeles", "area_km2",
            "toca_borde", "geometry"]
    troncos[cols + ["nombre_osm", "n_troncos_dentro"]].to_file(
        args.procesados / "troncos_coquimbo.gpkg", layer="troncos", driver="GPKG")

    # --- Union con las demas unidades, sin duplicar si se corre dos veces ---
    ruta_unidades = args.procesados / "unidades_coquimbo.gpkg"
    if not ruta_unidades.exists():
        sys.exit(f"Falta {ruta_unidades}\nCorre antes: python src/m1_subcuencas.py")
    unidades = gpd.read_file(ruta_unidades)
    previas = int((unidades["origen"] == "tronco").sum())
    unidades = unidades[unidades["origen"] != "tronco"]
    unidades = gpd.GeoDataFrame(pd.concat([unidades[cols], troncos[cols]], ignore_index=True),
                                crs=unidades.crs)
    unidades.to_file(ruta_unidades, layer="unidades", driver="GPKG")
    print(f"\nUnidades de analisis: {len(unidades):,} "
          + " + ".join(f"{v:,} {k}" for k, v in unidades["origen"].value_counts().items())
          + (f" (se reemplazaron {previas} troncos de una corrida anterior)" if previas else ""))
    print(f"\n  troncos  -> troncos_coquimbo.gpkg")
    print(f"  unidades -> {ruta_unidades.name}")
    print(f"\nTomo {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
