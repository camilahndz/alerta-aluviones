"""
M5 - Evaluacion de las unidades troncales.

La idea de fondo:

    m1_troncos.py agrego 93 troncos -quebradas de mas de 50 km2- porque el
    satelite mostro que las quebradas reportadas se activaron en su tronco y
    no en las unidades chicas que las tocan. Ese hallazgo salio del inventario
    de 2026. Evaluar los troncos contra ese mismo inventario seria ajustar el
    modelo contra su propia validacion: el mismo motivo por el que no se bajo
    --valle-min-km2 para cubrir Cruz de Cana.

    Por eso la evaluacion va en tres niveles, de mas a menos independiente, y
    el tercero lleva la marca puesta:

    1. CONTRA EL SATELITE, sin prensa. Por cada tronco y temporada, la
       fraccion de sus tramos de 2 km donde Sentinel-2 ve cambio (el detector y
       los umbrales de m5_satelite_cauces.py). Fijado antes de mirar:

           activo     la mitad o mas de sus tramos con cambio
           inactivo   un quinto o menos
           dudoso     entre los dos
           sin dato   menos de dos tramos visibles

       La pregunta es si la lluvia del tronco ordena los activos por encima de
       los inactivos. El satelite tiene un sesgo conocido -el lecho reverdece
       menos que las laderas en un anio humedo- que infla "activo", y por eso
       se reporta el AUC y no una precision.

    2. CONTRA LA PRENSA DE 2025. Ese inventario no motivo los troncos.

    3. CONTRA LA PRENSA DE 2026, MARCADO COMO "MOTIVO EL CAMBIO". Se reporta
       porque es la pregunta que importa, pero no cuenta como validacion.

    Como referencia se hace la prueba 1 sobre las unidades chicas, con el mismo
    detector: si la lluvia explica la actividad de los troncos mejor que la de
    las unidades chicas, la unidad nueva esta midiendo algo que la vieja no.

COMO SE EMPAREJA UNA QUEBRADA DE LA PRENSA CON UN TRONCO

    El cauce de OSM de la quebrada nombrada y el cauce principal del tronco
    tienen que compartir al menos 1 km dentro de una franja de 300 m. No basta
    con que la quebrada caiga dentro del poligono del tronco: un afluente
    reportado dentro de Marquesa no dice que Marquesa entera bajo.

LA LLUVIA

    La de M4, que para los troncos es areal (ver m4_interpolacion). Por tronco
    y temporada, el maximo de la razon contra Caine, de la ventana critica y de
    la lluvia de un episodio.

Uso:

    python src/m5_troncos.py

Lee imagenes de AWS para los cauces troncales: unos 15 minutos.
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
import m5_satelite_troncos as st  # noqa: E402
import m5_validacion as m5  # noqa: E402
from m4_umbrales import caine_intensidad_critica  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ZONA = "America/Santiago"

ACTIVO_MIN = 0.5
INACTIVO_MAX = 0.2
TRAMOS_MIN = 2
EMPAREJE_FRANJA_M = 300.0
EMPAREJE_LARGO_M = 1000.0
POSITIVOS = ("aluvion", "activacion", "activacion_menor")

# Las temporadas del satelite (septiembre a septiembre), como en m5_satelite_cauces.
TEMPORADAS = {2025: ("2024-09-18", "2025-09-01"), 2026: ("2025-09-20", "2026-08-24")}


def lluvia_por_temporada(gatillo: pd.DataFrame) -> pd.DataFrame:
    g = gatillo.copy()
    g["razon_caine"] = g["i_media_mm_h"] / caine_intensidad_critica(g["duracion_h"].to_numpy())
    inicio = pd.to_datetime(g["inicio"], utc=True).dt.tz_convert(ZONA)
    partes = []
    for temp, (desde, hasta) in TEMPORADAS.items():
        sel = (inicio > pd.Timestamp(desde, tz=ZONA)) & (inicio <= pd.Timestamp(hasta, tz=ZONA))
        m = g[sel].groupby("id_cuenca").agg(
            razon_caine=("razon_caine", "max"), razon_critica=("razon_caine_critica", "max"),
            lluvia_max_mm=("lluvia_mm", "max")).reset_index()
        m["temporada"] = temp
        partes.append(m)
    return pd.concat(partes, ignore_index=True)


def actividad_satelital(troncos_lineas, umbrales) -> pd.DataFrame:
    """Fraccion de tramos con cambio, por tronco y temporada."""
    import geopandas as gpd

    tramos = []
    for _, t in troncos_lineas.iterrows():
        for x in st.tramos(t.geometry, tronco=t["id_cuenca"]):
            tramos.append(x)
    tr = gpd.GeoDataFrame(tramos, crs=sat.CRS_METRICO)
    tr["id_cuenca"] = [f"s{i}" for i in range(len(tr))]

    elegidas = sat.elegir_escenas(tr.to_crs(4326).total_bounds)
    tr["tesela"] = sat.asignar_teselas(tr, elegidas)
    filas = []
    for t in tr["tesela"].dropna().unique():
        filas += sat.procesar_tesela(t, tr[tr["tesela"] == t], elegidas,
                                     f"EPSG:327{t[:2]}", lambda *_: None)
    r = pd.DataFrame(filas).merge(tr[["id_cuenca", "tronco"]], on="id_cuenca")

    salida = []
    for temp in TEMPORADAS:
        q75, q95, _ = umbrales[temp]
        d, frac = r[f"delta_cauce_{temp}"], r[f"frac_valida_{temp}"]
        ok = d.notna() & (frac >= sat.FRACCION_VALIDA_MIN)
        r_ok = r[ok].assign(cambio=(d[ok] > q95))
        agg = r_ok.groupby("tronco").agg(tramos=("cambio", "size"),
                                         fraccion_cambio=("cambio", "mean")).reset_index()
        agg["temporada"] = temp
        salida.append(agg)
    act = pd.concat(salida, ignore_index=True).rename(columns={"tronco": "id_cuenca"})
    act["clase_sat"] = np.where(act["tramos"] < TRAMOS_MIN, "sin_dato",
                                np.where(act["fraccion_cambio"] >= ACTIVO_MIN, "activo",
                                         np.where(act["fraccion_cambio"] <= INACTIVO_MAX,
                                                  "inactivo", "dudoso")))
    return act


def troncos_reportados(troncos_lineas, osm, comunas) -> pd.DataFrame:
    inv = cal.cargar_inventario()
    filas = []
    for _, e in inv.iterrows():
        temp = sat.cal_temporada(e["fecha"])
        if temp is None or e["evidencia"] not in POSITIVOS or not m5._texto(e["quebrada"]):
            continue
        geo, como = m5.ubicar(e.to_dict(), osm, comunas)
        if geo is None or not como.startswith("cauce"):
            continue
        franja = geo.buffer(EMPAREJE_FRANJA_M)
        comparte = troncos_lineas.geometry.intersection(franja).length
        for cid in troncos_lineas.loc[comparte >= EMPAREJE_LARGO_M, "id_cuenca"]:
            filas.append({"id_cuenca": cid, "temporada": temp, "entrada": e["id"],
                          "quebrada": e["quebrada"], "evidencia": e["evidencia"]})
    return pd.DataFrame(filas)


def evaluar(datos, etiqueta_pos, etiqueta_neg, titulo):
    d = datos[datos["y"].isin((etiqueta_pos, etiqueta_neg))]
    y = (d["y"] == etiqueta_pos).to_numpy(int)
    print(f"\n  {titulo}: {int(y.sum())} contra {int((y == 0).sum())}")
    if y.sum() == 0 or (y == 0).sum() == 0:
        print("    falta una de las dos clases: no se evalua")
        return
    print(f"    {'lectura':<22} {'AUC':>6} {'marca Caine (recall)':>21} {'marca, negativos':>17}")
    for nombre, col in (("Caine publicado", "razon_caine"), ("Caine critica", "razon_critica"),
                        ("lluvia maxima", "lluvia_max_mm")):
        s = d[col].to_numpy(dtype=float)
        aucv = cal.auc(y, np.log(s) if col != "lluvia_max_mm" else s)
        if col == "lluvia_max_mm":
            print(f"    {nombre:<22} {aucv:>6.3f}")
            continue
        m = cal.matriz(y, s >= 1.0)
        print(f"    {nombre:<22} {aucv:>6.3f} {m['recall']:>21.2f} {m['fpr']:>17.2f}")


def main():
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    import geopandas as gpd

    print("=" * 74)
    print("M5 - Evaluacion de las unidades troncales")
    print("=" * 74)

    procesados = RAIZ / "data" / "processed"
    trayectorias = gpd.read_file(procesados / "trayectorias.gpkg").to_crs(sat.CRS_METRICO)
    troncos = gpd.read_file(procesados / "troncos_coquimbo.gpkg")
    lineas = trayectorias[trayectorias["id_cuenca"].isin(troncos["id_cuenca"])].copy()
    print(f"\nTroncos: {len(troncos)}; con cauce principal trazado por M3: {len(lineas)}")
    print(f"  largo del cauce troncal: mediana {lineas.length.median() / 1000:.1f} km, "
          f"total {lineas.length.sum() / 1000:.0f} km")

    gatillo = gpd.read_file(procesados / "gatillo.gpkg")
    lluvia = lluvia_por_temporada(gatillo)

    tabla_sat = pd.read_csv(RAIZ / "outputs" / "m5_satelite_cauces.csv")
    _, umbrales = sat.clasificar(tabla_sat)

    print("\nMidiendo el cambio satelital de los cauces troncales...")
    act = actividad_satelital(lineas, umbrales)
    print("  clase satelital de los troncos, por temporada:")
    print(act.pivot_table(index="clase_sat", columns="temporada", values="id_cuenca",
                          aggfunc="count", fill_value=0).to_string())

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        osm = m5.cargar_osm()
        comunas = m5.cargar_comunas()
    rep = troncos_reportados(lineas, osm, comunas)

    datos = act.merge(lluvia, on=["id_cuenca", "temporada"], how="inner")
    datos = datos.merge(troncos[["id_cuenca", "nombre_osm", "area_km2"]], on="id_cuenca")

    # --- 1. Contra el satelite ---
    print("\n" + "-" * 74)
    print("1. La lluvia contra la actividad satelital (sin prensa)")
    print("-" * 74)
    for temp in TEMPORADAS:
        d = datos[datos["temporada"] == temp].assign(y=lambda x: x["clase_sat"])
        evaluar(d, "activo", "inactivo", f"temporada {temp}, troncos activos contra inactivos")

    # Referencia: la misma prueba sobre las unidades chicas.
    print("\n  Referencia, unidades chicas (clases de m5_satelite_cauces.py):")
    chicas = []
    for temp in TEMPORADAS:
        c = tabla_sat[["id_cuenca", f"clase_{temp}"]].rename(columns={f"clase_{temp}": "y"})
        c["temporada"] = temp
        chicas.append(c)
    chicas = pd.concat(chicas).merge(lluvia, on=["id_cuenca", "temporada"])
    for temp in TEMPORADAS:
        evaluar(chicas[chicas["temporada"] == temp], "cambio", "sin_cambio",
                f"temporada {temp}, unidades chicas con cambio contra sin cambio")

    # --- 2 y 3. Contra la prensa ---
    for temp, rotulo in ((2025, "2. La prensa de 2025 (no motivo los troncos)"),
                         (2026, "3. La prensa de 2026 -- MOTIVO EL CAMBIO, no es validacion")):
        print("\n" + "-" * 74)
        print(rotulo)
        print("-" * 74)
        ids = set(rep.loc[rep["temporada"] == temp, "id_cuenca"])
        d = datos[datos["temporada"] == temp].copy()
        d["y"] = np.where(d["id_cuenca"].isin(ids), "reportado", "no_reportado")
        evaluar(d, "reportado", "no_reportado",
                f"temporada {temp}, troncos reportados contra no reportados (negativos presuntos)")
        r = d[d["y"] == "reportado"].merge(
            rep[rep["temporada"] == temp].groupby("id_cuenca")["quebrada"].agg(
                lambda s: ", ".join(sorted(set(s)))).reset_index(), on="id_cuenca")
        if len(r):
            print("\n    tronco    area   quebrada(s) reportada(s)       Caine  critica  satelite")
            for _, x in r.sort_values("razon_critica", ascending=False).iterrows():
                print(f"    {int(x['id_cuenca'])}  {x['area_km2']:>5.0f}   {x['quebrada'][:28]:<28} "
                      f"{x['razon_caine']:>6.2f} {x['razon_critica']:>8.2f}  "
                      f"{x['clase_sat']} ({x['fraccion_cambio']:.0%})")

    datos.to_csv(RAIZ / "outputs" / "m5_troncos.csv", index=False, float_format="%.4f")
    rep.to_csv(RAIZ / "outputs" / "m5_troncos_reportados.csv", index=False)
    print("\n  tablas -> m5_troncos.csv, m5_troncos_reportados.csv")


if __name__ == "__main__":
    main()
