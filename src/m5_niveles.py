"""
M5 - Niveles de alerta por provincia: la lluvia del temporal contra el clima.

LA PREGUNTA

    m5_alerta_sector.py dejo dos cosas medidas. Caine publicado dice bien
    CUANDO un temporal es peligroso para la region, pero no DONDE: en Elqui
    no se activa nunca. Y la lluvia maxima del temporal, sin umbral, ordena
    las provincias mejor que la razon contra Caine. Este script arma con eso
    una alerta por niveles, que es lo que una autoridad emite: amarilla,
    naranja o roja para cada provincia, con una probabilidad detras.

LA VARIABLE

    Una sola: la fraccion de la lluvia normal de un anio que cae en el
    temporal, en la SEGUNDA estacion mas mojada de la provincia. La lluvia del
    temporal sale de los episodios de M4; la normal, de CR2MET 1991-2020
    (m4_climatologia.py). Es la lluvia relativa al clima del lugar, que es la
    correccion que la literatura propone para un gradiente como el de
    Coquimbo (Guzzetti et al., 2008).

    POR QUE LA SEGUNDA Y NO LA MAS MOJADA. La primera version usaba la mas
    mojada, y la auditoria del 11-10-2026 encontro lo que eso cuesta: el
    boletin en vivo de ese dia ponia a Choapa en naranja por una sola
    estacion, Rio Cuncumen antes junta Choapa, con 94,5 mm, cuando sus dos
    vecinas a 1-2 km median 36,6 y 41,8. M4 ya la tenia marcada como ambigua
    por ese mismo patron. Con la mas mojada, un pluviometro malo decide el
    nivel de una provincia entera. Con la segunda, hacen falta dos que lo
    digan. En los tres inviernos el orden casi no cambia (AUC 0,98 con las
    dos lecturas): lo que se gana es que un solo sensor no alcanza.

    Una y no mas porque no hay con que: 12 provincias-temporal positivas en
    tres inviernos, y la regla de m5_calibracion es diez positivos por
    variable. La lluvia antecedente, que el 11 y el 16 de junio de 2025
    muestran que importa -el primero no activo nada con 72 mm, el segundo si
    con 51 sobre suelo mojado-, queda para cuando haya datos.

    Como comparacion se ajusta lo mismo con la lluvia absoluta (mm), y se
    reporta la razon contra Caine de m5_alerta_sector.

EL MODELO Y LOS NIVELES

    P(activaciones en la provincia) = logistica de log10(fraccion). Los
    niveles se fijaron antes de ajustar, en cuartos de probabilidad:

        amarilla   P >= 0,25   una de cada cuatro provincias-temporal asi
                               tuvo activaciones
        naranja    P >= 0,50   una de cada dos
        roja       P >= 0,75   tres de cada cuatro

    Se traducen a fraccion de la normal, que es lo que se le puede decir a
    alguien: "roja si en al menos dos estaciones de la provincia cae mas del
    X% de lo que llueve en un anio".

COMO SE PRUEBA

    1. Entrenar con los inviernos 2024 y 2025, probar en 2026. Es la prueba
       limpia, y es chica: 6 positivos para entrenar.
    2. Dejando fuera un temporal entero a la vez, sobre los tres inviernos.
       Cada provincia-temporal recibe la probabilidad de un modelo que no lo
       vio. Usa todos los datos sin evaluar sobre lo ajustado.

    Los niveles que quedan para operar se ajustan con los tres inviernos; la
    prueba 2 es la estimacion de como se van a comportar.

    Ademas se guardan tres modelos que dejan fuera un invierno cada uno. Son
    los que usa el visor para repasar un temporal: el repaso de julio de 2026
    tiene que mostrar lo que habria dicho un modelo que no conocia 2026, no
    uno ajustado con ese mismo temporal.

    El deshielo (m4_deshielo.py) no entra al modelo: es experimental y tiene
    un caso. Se reporta al lado, como aviso aparte.

LO QUE SALIO

    Corrida 2026-10-11_m5_niveles.txt, con la segunda estacion.

    * Entrenado con 2024-2025 y probado en 2026: AUC 0,97. Las 9
      provincias-temporal que quedaron sin nivel no tuvieron activaciones; las
      5 en naranja o roja, todas; de las 3 en amarilla, una. Con la estacion
      mas mojada daba 1,00: la segunda estacion pierde un caso en la prueba y
      gana que un sensor solo no decida.

    * Dejando fuera un temporal a la vez: AUC 0,96 (0,89 en los regionales) y
      Brier 0,059, contra 0,95 y 0,063 con la estacion mas mojada y 0,88 de la
      razon contra Caine sobre las mismas filas. En Elqui, 0,95.

    * Los niveles para operar: amarilla desde el 16% de la normal anual en al
      menos dos estaciones de la provincia, naranja desde el 23%, roja desde el
      32%.

    * LO QUE ESAS CIFRAS NO DICEN. Las 12 provincias-temporal positivas salen
      de solo 5 temporales, y las provincias de un mismo temporal no son
      independientes. Remuestreando temporales enteros (auditoria del
      11-10-2026, con la estacion mas mojada), el corte de roja tiene un
      intervalo del 90% que va de 23 a 49%. Y el modelo que deja fuera 2025
      sale casi en escalon (19, 20,5 y 22%): con tan pocos positivos, sacar un
      invierno cambia la forma de la curva. Son cortes para operar con cuidado
      y revisar con mas datos, no cortes estimados con precision.

    * El bloque de deshielo de agosto de 2026 queda en alerta en las tres
      provincias sin el indicador de deshielo: medido como temporal entero,
      la lluvia fue mucho mas que la que hacia parecer seco el analisis por
      cuenca y episodio.

    * Lo que falla es un par: el 11 de junio de 2025 llovio sobre el corte y
      no hubo reportes (falsa alarma), y el 16 de junio llovio menos y si hubo
      activaciones (falla). Es la firma de la lluvia antecedente: el segundo
      cayo sobre el suelo que mojo el primero. Con 12 positivos de 5
      temporales no se puede agregar una segunda variable sin sobreajustar.

Uso:

    python src/m4_climatologia.py     # una vez: la normal de CR2MET
    python src/m5_niveles.py
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_lluvia as m4  # noqa: E402
import m5_alerta_sector as alerta  # noqa: E402
import m5_calibracion as cal  # noqa: E402
import m5_validacion as m5  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ZONA = "America/Santiago"

NIVELES = (("amarilla", 0.25), ("naranja", 0.50), ("roja", 0.75))
INICIO_PRUEBA = "2026-04-01"       # el invierno hidrologico 2026 (m4_lluvia.invierno)
PISO_FRACCION = 0.001              # un temporal sin lluvia en la provincia, para el log
PISO_MM = 0.1


def normal_en_estaciones(catalogo: pd.DataFrame, ruta_tif: Path) -> pd.Series:
    """La normal anual en cada estacion; si su celda cae al mar, la media de las vecinas."""
    import rasterio
    with rasterio.open(ruta_tif) as src:
        a = src.read(1)
        inv = ~src.transform
    valores = {}
    for _, e in catalogo.iterrows():
        col, fila = inv * (e["lon"], e["lat"])
        f, c = int(fila), int(col)
        v = a[f, c] if 0 <= f < a.shape[0] and 0 <= c < a.shape[1] else np.nan
        if not np.isfinite(v):
            bloque = a[max(f - 1, 0):f + 2, max(c - 1, 0):c + 2]
            v = np.nanmean(bloque) if np.isfinite(bloque).any() else np.nan
        valores[e["codigo"]] = v
    return pd.Series(valores)


def lluvia_por_temporal(episodios: pd.DataFrame, tor: pd.DataFrame) -> pd.DataFrame:
    """La lluvia de cada estacion en cada temporal: la suma de sus episodios."""
    filas = []
    for _, t in tor.iterrows():
        sel = episodios[(episodios["inicio"] <= t["fin"]) & (episodios["fin"] >= t["inicio"])]
        s = sel.groupby("estacion_codigo")["lluvia_mm"].sum()
        filas.append(pd.DataFrame({"temporal": t["temporal"], "estacion_codigo": s.index,
                                   "lluvia_mm": s.to_numpy()}))
    return pd.concat(filas, ignore_index=True)


def segunda(valores: pd.Series) -> float:
    """El segundo valor mas alto; 0 si en la provincia llovio en una sola estacion."""
    v = valores.sort_values(ascending=False).to_numpy()
    return float(v[1]) if len(v) > 1 else 0.0


def variables(tabla: pd.DataFrame) -> dict:
    return {"fraccion de la normal": np.log10(tabla["fraccion_2"].clip(lower=PISO_FRACCION)),
            "lluvia absoluta (mm)": np.log10(tabla["lluvia_2_mm"].clip(lower=PISO_MM)),
            "fraccion, estacion mas mojada (version anterior)":
                np.log10(tabla["fraccion_max"].clip(lower=PISO_FRACCION))}


def ajustar(x, y):
    # cal.logistica agrega la constante.
    b, _, convergio = cal.logistica(np.asarray(x, dtype=float).reshape(-1, 1), y)
    if not convergio:
        raise RuntimeError("la logistica no convergio (separacion perfecta?)")
    return b


def probabilidad(b, x):
    return 1 / (1 + np.exp(-(b[0] + b[1] * np.asarray(x))))


def corte(b, p):
    """El valor de la variable (en su escala original, no log) donde P = p."""
    return 10 ** ((np.log(p / (1 - p)) - b[0]) / b[1])


def nivel(p) -> np.ndarray:
    n = np.full(len(p), "ninguna", dtype=object)
    for nombre, umbral in NIVELES:
        n[np.asarray(p) >= umbral] = nombre
    return n


def brier(y, p) -> float:
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def tabla_niveles(d: pd.DataFrame, col_p: str, sangria: str = "    "):
    """Cuantas provincias-temporal cayeron en cada nivel y cuantas tuvieron activaciones."""
    niv = nivel(d[col_p])
    print(f"{sangria}{'nivel':<10} {'casos':>6} {'con activaciones':>17} {'tasa':>6}")
    for nombre in ("ninguna",) + tuple(n for n, _ in NIVELES):
        sel = d[niv == nombre]
        pos = int((sel["etiqueta"] == "positivo").sum())
        tasa = f"{pos / len(sel):.2f}" if len(sel) else "-"
        print(f"{sangria}{nombre:<10} {len(sel):>6} {pos:>17} {tasa:>6}")


def main():
    import geopandas as gpd

    print("=" * 74)
    print("M5 - Niveles de alerta por provincia: la lluvia del temporal contra el clima")
    print("=" * 74)

    ruta_tif = RAIZ / "data" / "processed" / "precipitacion_media_anual.tif"
    if not ruta_tif.exists():
        sys.exit(f"Falta {ruta_tif.name}. Corre antes: python src/m4_climatologia.py")

    episodios = pd.read_csv(RAIZ / "outputs" / "m4_episodios.csv")
    for col in ("inicio", "fin"):
        episodios[col] = pd.to_datetime(episodios[col], utc=True)
    tor = alerta.temporales(episodios)

    # --- Estaciones: normal anual y provincia ---
    catalogo = m4.descargar_catalogo(m4.TIPO_PRECIPITACION)
    catalogo = catalogo[catalogo["codigo"].isin(episodios["estacion_codigo"])].copy()
    catalogo["normal_mm"] = catalogo["codigo"].map(normal_en_estaciones(catalogo, ruta_tif))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        comunas = m5.cargar_comunas()
    puntos = gpd.GeoDataFrame(catalogo, geometry=gpd.points_from_xy(catalogo["lon"], catalogo["lat"]),
                              crs="EPSG:4326").to_crs(m5.CRS_METRICO)
    puntos = gpd.sjoin(puntos, comunas[["clave", "geometry"]], how="left", predicate="within")
    catalogo["provincia"] = puntos.drop_duplicates("codigo").set_index("codigo")["clave"].map(
        alerta.PROVINCIA_DE).reindex(catalogo["codigo"]).to_numpy()

    print(f"\nEstaciones con episodios: {len(catalogo)}; normal anual CR2MET 1991-2020: "
          f"mediana {catalogo['normal_mm'].median():.0f} mm, de "
          f"{catalogo['normal_mm'].min():.0f} a {catalogo['normal_mm'].max():.0f}")
    for p in alerta.PROVINCIAS:
        sel = catalogo[catalogo["provincia"] == p]
        print(f"  {p:<7} {len(sel):>3} estaciones, normal mediana {sel['normal_mm'].median():>4.0f} mm")
    sin = catalogo[catalogo["provincia"].isna() | catalogo["normal_mm"].isna()]
    if len(sin):
        print(f"  sin provincia o sin normal, quedan fuera: {', '.join(sin['nombre'])}")
    catalogo = catalogo.drop(sin.index)

    # --- Puntaje por provincia y temporal ---
    lluvia = lluvia_por_temporal(episodios, tor).merge(
        catalogo[["codigo", "provincia", "normal_mm"]], left_on="estacion_codigo",
        right_on="codigo")
    lluvia["fraccion"] = lluvia["lluvia_mm"] / lluvia["normal_mm"]
    puntaje = lluvia.groupby(["temporal", "provincia"]).agg(
        lluvia_max_mm=("lluvia_mm", "max"), fraccion_max=("fraccion", "max"),
        lluvia_2_mm=("lluvia_mm", segunda), fraccion_2=("fraccion", segunda),
        estaciones=("estacion_codigo", "nunique")).reset_index()

    inv = cal.cargar_inventario()
    etq, _, _ = alerta.etiquetar(tor, inv)
    t = etq.merge(puntaje, on=["temporal", "provincia"], how="left").fillna(
        {"lluvia_max_mm": 0.0, "fraccion_max": 0.0, "lluvia_2_mm": 0.0, "fraccion_2": 0.0,
         "estaciones": 0})
    t = t.merge(tor[["temporal", "inicio", "regional"]], on="temporal")
    t["prueba"] = t["inicio"] >= pd.Timestamp(INICIO_PRUEBA, tz=ZONA)
    t["invierno"] = m4.invierno(t["inicio"].dt.tz_convert(ZONA)).to_numpy()

    ruta_deshielo = RAIZ / "outputs" / "m4_deshielo.csv"
    if ruta_deshielo.exists():
        diario = pd.read_csv(ruta_deshielo, index_col="dia", parse_dates=True)["deshielo"]
        activos = set(diario.index[diario.astype(bool)].date)
        fin = tor.set_index("temporal")["fin"]
        t["deshielo"] = [bool(activos & set(pd.date_range(i.tz_convert(ZONA).date(),
                                                         fin[k].tz_convert(ZONA).date()).date))
                         for k, i in zip(t["temporal"], t["inicio"])]

    d = t[t["etiqueta"] != "excluido"].copy()
    d["y"] = (d["etiqueta"] == "positivo").astype(int)
    print(f"\nProvincias-temporal: {len(d)} ({int(d['y'].sum())} positivas), "
          f"{int((t['etiqueta'] == 'excluido').sum())} excluidas")
    print(f"  entrenamiento 2024-2025: {int((~d['prueba']).sum())} "
          f"({int(d.loc[~d['prueba'], 'y'].sum())} positivas); prueba 2026: "
          f"{int(d['prueba'].sum())} ({int(d.loc[d['prueba'], 'y'].sum())} positivas)")

    # --- 1. Entrenar en 2024-2025, probar en 2026 ---
    print("\n" + "-" * 74)
    print("1. Entrenar con 2024-2025, probar en 2026")
    print("-" * 74)
    ent, pru = d[~d["prueba"]], d[d["prueba"]]
    for nombre, x in variables(d).items():
        b = ajustar(x[ent.index], ent["y"].to_numpy())
        p = probabilidad(b, x[pru.index])
        reg = pru["regional"].to_numpy()
        print(f"\n  {nombre}: AUC en 2026 {cal.auc(pru['y'], p):.2f} (regionales "
              f"{cal.auc(pru['y'][reg], p[reg]):.2f}), Brier {brier(pru['y'], p):.3f}")
        if nombre == "fraccion de la normal":
            d.loc[pru.index, "p_holdout"] = p
            tabla_niveles(d.loc[pru.index], "p_holdout")

    # --- 2. Dejando fuera un temporal a la vez ---
    print("\n" + "-" * 74)
    print("2. Dejando fuera un temporal a la vez, tres inviernos")
    print("-" * 74)
    for nombre, x in variables(d).items():
        p = pd.Series(np.nan, index=d.index)
        for tem in d["temporal"].unique():
            fuera = d["temporal"] == tem
            b = ajustar(x[~fuera], d.loc[~fuera, "y"].to_numpy())
            p[fuera] = probabilidad(b, x[fuera])
        reg = d["regional"].to_numpy()
        print(f"\n  {nombre}: AUC {cal.auc(d['y'], p):.2f} (regionales "
              f"{cal.auc(d['y'][reg], p[reg]):.2f}), Brier {brier(d['y'], p):.3f}")
        print("    por provincia (AUC):  " + "   ".join(
            f"{prov} {cal.auc(g['y'], p[g.index]):.2f}" for prov, g in d.groupby("provincia")))
        if nombre == "fraccion de la normal":
            d["p_cruzada"] = p
            tabla_niveles(d, "p_cruzada")

    # Caine no se ajusta, asi que su AUC sobre las mismas filas es comparable
    # con el de la validacion cruzada. Sale de m5_alerta_sector.py.
    ruta_caine = RAIZ / "outputs" / "m5_alerta_provincia.csv"
    if ruta_caine.exists():
        caine = pd.read_csv(ruta_caine)[["temporal", "provincia", "razon_max"]]
        c = d.reset_index().merge(caine, on=["temporal", "provincia"], how="left")
        s = c["razon_max"].fillna(0).to_numpy()
        reg = c["regional"].to_numpy()
        pru_c = c["prueba"].to_numpy()
        print(f"\n  referencia, Caine sin ajustar (m5_alerta_sector): AUC "
              f"{cal.auc(c['y'], s):.2f} (regionales {cal.auc(c['y'][reg], s[reg]):.2f}); "
              f"solo 2026, {cal.auc(c['y'][pru_c], s[pru_c]):.2f}")
        print("    por provincia (AUC):  " + "   ".join(
            f"{prov} {cal.auc(g['y'], g['razon_max'].fillna(0)):.2f}"
            for prov, g in c.groupby("provincia")))

    # --- Los niveles para operar ---
    print("\n" + "-" * 74)
    print("Los niveles para operar, ajustados con los tres inviernos")
    print("-" * 74)
    x = variables(d)["fraccion de la normal"]
    b = ajustar(x, d["y"].to_numpy())
    print("  en al menos dos estaciones de la provincia, la lluvia del temporal llega a:")
    for nombre, umbral in NIVELES:
        print(f"    {nombre:<9} {corte(b, umbral):>6.1%} de la normal anual   (P >= {umbral:.2f})")
    # Los coeficientes con todos sus decimales: m6_alerta_en_vivo.py los copia
    # como constantes congeladas, y este JSON es contra lo que se verifica.
    print(f"  coeficientes: P = 1 / (1 + exp(-({b[0]:.6f} + {b[1]:.6f} * log10(fraccion))))")
    # Un modelo por invierno dejado fuera, para que los repasos del visor no
    # muestren un temporal con un modelo que ya lo conocia.
    sin_invierno = {}
    for invierno in sorted(d["invierno"].unique()):
        fuera = (d["invierno"] == invierno).to_numpy()
        bi = ajustar(x[~fuera], d.loc[~fuera, "y"].to_numpy())
        sin_invierno[str(int(invierno))] = [float(bi[0]), float(bi[1])]
        print(f"  sin el invierno {invierno}: " + ", ".join(
            f"{n} {corte(bi, u):.1%}" for n, u in NIVELES))
    (RAIZ / "outputs" / "m5_niveles_modelo.json").write_text(json.dumps({
        "b0": float(b[0]), "b1": float(b[1]), "piso_fraccion": PISO_FRACCION,
        "niveles": dict(NIVELES), "positivos": int(d["y"].sum()), "casos": int(len(d)),
        "sin_invierno": sin_invierno,
    }, indent=2))
    d["p_final"] = probabilidad(b, x)
    d["nivel"] = nivel(d["p_final"])

    print("\n  Los temporales regionales con el nivel que habria tenido cada provincia")
    print("  (validacion cruzada; + activaciones, - nada, D deshielo):")
    print(f"    {'temporal':<12} " + "".join(f"{p:<26}" for p in alerta.PROVINCIAS))
    for tem, g in d[d["regional"]].groupby("temporal"):
        fecha = g["inicio"].iloc[0].tz_convert(ZONA).strftime("%d-%m-%Y")
        desh = " D" if g.get("deshielo", pd.Series([False])).any() else ""
        celdas = []
        for prov in alerta.PROVINCIAS:
            f = g[g["provincia"] == prov]
            if f.empty:
                celdas.append("x (excluida)".ljust(26))
                continue
            f = f.iloc[0]
            celdas.append(f"{'+' if f['y'] else '-'} {nivel([f['p_cruzada']])[0]:<8} "
                          f"{f['fraccion_2']:>5.0%}".ljust(26))
        print(f"    {fecha:<12} " + "".join(celdas) + desh)

    d.drop(columns=["inicio"]).to_csv(RAIZ / "outputs" / "m5_niveles.csv", index=False,
                                      float_format="%.4f")
    print("\n  tabla -> m5_niveles.csv")


if __name__ == "__main__":
    main()
