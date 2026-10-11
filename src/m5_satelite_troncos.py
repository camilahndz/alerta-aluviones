"""
M5 - Satelite sobre los troncos: donde se activaron de verdad las quebradas.

La idea de fondo:

    m5_satelite_cauces.py midio el cambio de cada cauce de las 2.589 unidades
    susceptibles entre dos septiembres, y la prueba del detector fallo en 2026:
    las unidades cerca de las quebradas reportadas cambiaron MENOS que las
    demas (AUC 0,37). Habia dos explicaciones, y este script las separa.

        a) El detector no sirve: Sentinel-2 a 10 m no ve una activacion.
        b) El detector sirve, pero esta mirando el objeto equivocado. Las
           unidades de M1 miden de 0,4 a 50 km2; Santa Gracia y Marquesa son
           quebradas de cientos de km2. El flujo pasa por el TRONCO, que no es
           ninguna unidad, y las unidades que lo tocan son afluentes chicos que
           pueden no haber hecho nada.

    Para separarlas se hacen tres mediciones con el mismo detector y los
    mismos umbrales que m5_satelite_cauces.py:

    1. El cambio sobre el tronco de cada quebrada reportada, en tramos de 2 km,
       contra sus propias lineas nulas a 200 m. Si los troncos tampoco cambian
       -Santa Gracia destruyo decenas de casas-, el detector falla de raiz.

    2. El mismo cambio sobre troncos de quebradas que NADIE reporto, en las
       mismas comunas. Si cambian tanto como los reportados, el satelite solo
       dice que en 2026 corrio agua por todas partes, y no sirve para producir
       negativos.

    3. El area que drena cada quebrada reportada, leida del raster de
       acumulacion de M1. Si la mayoria pasa de 50 km2, el modelo no tiene
       unidades que las representen.

Uso:

    python src/m5_satelite_troncos.py

Requiere haber corrido antes m5_satelite_cauces.py: lee sus umbrales.
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m5_calibracion as cal  # noqa: E402
import m5_satelite_cauces as sat  # noqa: E402
import m5_validacion as m5  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent

LARGO_TRAMO_M = 2000.0
TRAMO_MIN_M = 300.0
BORDE_M = 150.0          # se ignora el extremo de la linea, que puede tocar el valle
N_CONTROL = 60           # quebradas no reportadas a medir
LARGO_CONTROL_MIN_M = 4000.0
TOPE_UNIDAD_KM2 = 50.0   # --area-max-km2 de m1_subcuencas.py

POSITIVOS = ("aluvion", "activacion", "activacion_menor")


def _lineas(geo):
    from shapely.geometry import LineString
    from shapely.ops import linemerge
    if isinstance(geo, LineString):
        return [geo]
    unida = linemerge(geo)
    return list(getattr(unida, "geoms", [unida]))


def tramos(geo, **atributos) -> list[dict]:
    """Corta una quebrada en tramos de 2 km. Un tronco de 40 km medido entero
    mezcla la cabecera, que no cambio, con el abanico, que si."""
    from shapely.ops import substring
    salida = []
    for ln in _lineas(geo):
        for k in range(int(np.ceil(ln.length / LARGO_TRAMO_M))):
            seg = substring(ln, k * LARGO_TRAMO_M, min((k + 1) * LARGO_TRAMO_M, ln.length))
            if seg.length > TRAMO_MIN_M:
                salida.append({**atributos, "geometry": seg})
    return salida


def medir(tramos_gdf, umbrales) -> pd.DataFrame:
    """El detector de m5_satelite_cauces sobre cada tramo, con sus umbrales."""
    elegidas = sat.elegir_escenas(tramos_gdf.to_crs(4326).total_bounds)
    tramos_gdf = tramos_gdf.copy()
    tramos_gdf["tesela"] = sat.asignar_teselas(tramos_gdf, elegidas)
    filas = []
    for t in tramos_gdf["tesela"].dropna().unique():
        filas += sat.procesar_tesela(t, tramos_gdf[tramos_gdf["tesela"] == t], elegidas,
                                     f"EPSG:327{t[:2]}", lambda *_: None)
    r = pd.DataFrame(filas).merge(tramos_gdf.drop(columns="geometry"), on=["id_cuenca", "tesela"])
    clases = []
    for _, x in r.iterrows():
        temp = x["temporada"]
        d, frac = x[f"delta_cauce_{temp}"], x[f"frac_valida_{temp}"]
        q75, q95, _ = umbrales[temp]
        if pd.isna(d) or frac < sat.FRACCION_VALIDA_MIN:
            clases.append("sin_dato")
        else:
            clases.append("cambio" if d > q95 else "sin_cambio" if d <= q75 else "dudoso")
    r["clase"] = clases
    r["delta"] = [x[f"delta_cauce_{x['temporada']}"] for _, x in r.iterrows()]
    r["nulo_a"] = [x[f"delta_nulo_a_{x['temporada']}"] for _, x in r.iterrows()]
    r["nulo_b"] = [x[f"delta_nulo_b_{x['temporada']}"] for _, x in r.iterrows()]
    return r[r["clase"] != "sin_dato"]


def auc_contra_nulo(r) -> float:
    nulo = pd.concat([r["nulo_a"], r["nulo_b"]]).dropna()
    y = np.r_[np.ones(len(r)), np.zeros(len(nulo))]
    return cal.auc(y, np.r_[r["delta"].to_numpy(), nulo.to_numpy()])


def area_drenada_km2(geo, acc) -> float:
    """El area mayor que drena la quebrada, del raster de acumulacion de M1.

    Se recorre la linea cada 30 m, se toma el maximo de una ventana de 3 x 3
    celdas -la linea de OSM y el cauce del DEM no coinciden al metro- y se
    ignoran los ultimos 150 m de cada punta, donde la linea puede tocar el
    valle que la recibe y devolver el area del rio.
    """
    vals = []
    for ln in _lineas(geo):
        if ln.length < 2 * BORDE_M + 100:
            continue
        for d in np.arange(BORDE_M, ln.length - BORDE_M, 30.0):
            p = ln.interpolate(d)
            fila, col = acc.index(p.x, p.y)
            if 1 <= fila < acc.height - 1 and 1 <= col < acc.width - 1:
                v = acc.read(1, window=((fila - 1, fila + 2), (col - 1, col + 2)))
                v = np.where(v == acc.nodata, np.nan, v)
                if np.isfinite(v).any():
                    vals.append(np.nanmax(v))
    celda_m2 = abs(acc.res[0] * acc.res[1])
    return float(np.nanmax(vals)) * celda_m2 / 1e6 if vals else np.nan


def main():
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    import geopandas as gpd
    import rasterio

    print("=" * 74)
    print("M5 - El detector satelital sobre los troncos de las quebradas")
    print("=" * 74)

    tabla = pd.read_csv(RAIZ / "outputs" / "m5_satelite_cauces.csv")
    _, umbrales = sat.clasificar(tabla)
    for temp, (q75, q95, n) in umbrales.items():
        print(f"Umbrales de m5_satelite_cauces, temporada {temp}: p75 {q75:+.4f}, p95 {q95:+.4f}")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        osm = m5.cargar_osm()
        comunas = m5.cargar_comunas()
    inv = cal.cargar_inventario()

    # --- 1 y 3: troncos reportados y su area ---
    acc = rasterio.open(RAIZ / "data" / "processed" / "acumulacion_flujo.tif")
    filas_tr, areas, vistas = [], [], set()
    for _, e in inv.iterrows():
        temp = sat.cal_temporada(e["fecha"])
        if not m5._texto(e["quebrada"]) or temp is None or e["evidencia"] not in POSITIVOS + ("escurrimiento",):
            continue
        geo, como = m5.ubicar(e.to_dict(), osm, comunas)
        if geo is None or not como.startswith("cauce"):
            continue
        if e["quebrada"] not in {a["quebrada"] for a in areas}:
            areas.append({"quebrada": e["quebrada"], "temporada": temp, "evidencia": e["evidencia"],
                          "area_km2": area_drenada_km2(geo, acc)})
        # Marquesa, Santa Gracia, Los Loros y San Carlos tienen dos entradas en
        # 2026. El satelite ve la temporada entera, asi que se miden una vez.
        if e["evidencia"] in POSITIVOS and (e["quebrada"], temp) not in vistas:
            vistas.add((e["quebrada"], temp))
            filas_tr += tramos(geo, quebrada=e["quebrada"], temporada=temp,
                               evidencia=e["evidencia"])
    areas = pd.DataFrame(areas).sort_values("area_km2")
    tr = gpd.GeoDataFrame(filas_tr, crs=sat.CRS_METRICO)
    tr["id_cuenca"] = [f"t{i}" for i in range(len(tr))]

    print("\n" + "-" * 74)
    print("1. Cambio sobre el tronco de las quebradas reportadas (tramos de 2 km)")
    print("-" * 74)
    rep = medir(tr, umbrales)
    print(f"  {'temporada':<10} {'tramos':>7} {'cambio':>7} {'sin_cambio':>11} "
          f"{'delta med':>10} {'AUC vs nulo':>12}")
    for temp in sat.TEMPORADAS:
        w = rep[rep["temporada"] == temp]
        print(f"  {temp:<10} {len(w):>7} {int((w['clase'] == 'cambio').sum()):>7} "
              f"{int((w['clase'] == 'sin_cambio').sum()):>11} {w['delta'].median():>+10.4f} "
              f"{auc_contra_nulo(w):>12.3f}")
    print("\n  Por quebrada, temporada 2026:")
    q26 = rep[rep["temporada"] == 2026].groupby("quebrada").agg(
        tramos=("delta", "size"), delta_mediana=("delta", "median"),
        fraccion_cambio=("clase", lambda c: (c == "cambio").mean()))
    print(q26.sort_values("fraccion_cambio", ascending=False).round(3).to_string())

    # --- 2: control de troncos no reportados ---
    print("\n" + "-" * 74)
    print("2. Control: quebradas que nadie reporto, en las mismas comunas, 2026")
    print("-" * 74)
    nombres_inv = {m5.sin_tildes(x) for x in inv["quebrada"].dropna()}
    comunas_rep = {m5.sin_tildes(c) for c in inv.loc[
        inv["fecha"].str.startswith("2026") & inv["evidencia"].isin(POSITIVOS), "comuna"].dropna()}
    zona = comunas[comunas["clave"].isin(comunas_rep)].geometry.union_all()
    q = osm[(osm["capa"] == "cauce") & osm["clave"].str.startswith("quebrada", na=False)].copy()
    q = q[q.intersects(zona)]
    q["base"] = (q["clave"].str.replace("quebrada ", "", regex=False)
                 .str.replace("^de ", "", regex=True))
    q = q[~q["base"].isin(nombres_inv)].dissolve(by="name").reset_index()
    q = q[q.geometry.length > LARGO_CONTROL_MIN_M]
    q = q.sample(n=min(N_CONTROL, len(q)), random_state=0)
    filas_c = []
    for _, e in q.iterrows():
        filas_c += tramos(e.geometry, quebrada=e["name"], temporada=2026, evidencia="ninguna")
    ctl = gpd.GeoDataFrame(filas_c, crs=sat.CRS_METRICO)
    ctl["id_cuenca"] = [f"c{i}" for i in range(len(ctl))]
    con = medir(ctl, umbrales)
    r26 = rep[rep["temporada"] == 2026]
    print(f"  {len(q)} quebradas no reportadas, {len(con)} tramos con dato")
    print(f"  {'':<14} {'tramos':>7} {'cambio':>8} {'delta med':>10} {'AUC vs nulo':>12}")
    for etq, w in (("reportadas", r26), ("no reportadas", con)):
        print(f"  {etq:<14} {len(w):>7} {(w['clase'] == 'cambio').mean():>8.0%} "
              f"{w['delta'].median():>+10.4f} {auc_contra_nulo(w):>12.3f}")
    y = np.r_[np.ones(len(r26)), np.zeros(len(con))]
    print(f"  AUC reportadas contra no reportadas: "
          f"{cal.auc(y, np.r_[r26['delta'].to_numpy(), con['delta'].to_numpy()]):.3f}")

    # --- 3: area ---
    print("\n" + "-" * 74)
    print("3. Area que drena cada quebrada reportada (raster de acumulacion de M1)")
    print("-" * 74)
    print(areas.round(1).to_string(index=False))
    n_area = int(areas["area_km2"].notna().sum())
    sobre = int((areas["area_km2"] > TOPE_UNIDAD_KM2).sum())
    print(f"\n  mediana {areas['area_km2'].median():.0f} km2; {sobre} de {n_area} pasan de "
          f"{TOPE_UNIDAD_KM2:.0f} km2, el tope de las unidades de m1_subcuencas.py")

    rep.drop(columns=[c for c in rep.columns if c.startswith(("delta_", "frac_"))]).to_csv(
        RAIZ / "outputs" / "m5_satelite_troncos.csv", index=False, float_format="%.5f")
    con.drop(columns=[c for c in con.columns if c.startswith(("delta_", "frac_"))]).to_csv(
        RAIZ / "outputs" / "m5_satelite_control.csv", index=False, float_format="%.5f")
    areas.to_csv(RAIZ / "outputs" / "m5_area_quebradas_reportadas.csv", index=False,
                 float_format="%.1f")
    print("\n  tablas -> m5_satelite_troncos.csv, m5_satelite_control.csv, "
          "m5_area_quebradas_reportadas.csv")


if __name__ == "__main__":
    main()
