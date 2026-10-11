"""
M5 - La alerta por provincia y por temporal, 2024-2026.

LA PREGUNTA

    m5_calibracion.py evalua el umbral por estacion y episodio, y ahi los
    negativos son debiles: que una quebrada no salga en la prensa no dice que
    no se activo. Pero una autoridad no decide por quebrada. SENAPRED declara
    alertas por comuna o por provincia y por temporal: "alerta temprana
    preventiva para la provincia de Limari por sistema frontal". La pregunta
    de este script es esa: **cuando llega un temporal, el modelo dice bien en
    que provincias va a haber activaciones?**

    A esa escala el negativo pesa mas. Que en un temporal ninguna fuente
    reporte ninguna quebrada activada en una provincia entera es bastante mas
    creible que lo mismo para una quebrada. Sigue siendo un negativo presunto,
    y por eso la precision que sale es una cota inferior, pero ya es una cifra
    con que discutir.

LOS TEMPORALES

    Se arman con los episodios de M4 que pasan de 5 mm (el mismo minimo de
    m4_interpolacion: bajo eso el patron es ruido de instrumento) y se juntan
    los que se solapan o quedan a menos de 24 h. No se usan los eventos
    regionales de M4, que juntan todo lo que se solapa sin minimo: encadenan
    chubascos sueltos y uno de ellos va del 31-07 al 07-11-2025.

    Salen 34 temporales en tres inviernos. Muchos son una estacion con 6 mm,
    negativos faciles que inflan cualquier AUC. Por eso todo se reporta dos
    veces: con todos, y solo con los regionales, que son los que tienen al
    menos 5 estaciones sobre 5 mm. Los dos minimos se fijaron antes de mirar
    los resultados.

LAS ETIQUETAS

    Por provincia y temporal, con las reglas de m5_calibracion:

        positivo   alguna entrada con evidencia de activacion (aluvion,
                   activacion, activacion menor) en una comuna de la
                   provincia, con fecha dentro del temporal +- 1 dia;
        excluido   solo entradas dudosas (escurrimiento, alerta preventiva),
                   o una entrada sin comuna ese mismo temporal: se sabe que
                   hubo activaciones en la region y no donde;
        negativo   nada.

    Las entradas del 13-06-2024 son anteriores a la red de VIPNET y no caen
    en ningun temporal medido. Se listan para que no desaparezcan en
    silencio.

LOS PUNTAJES

    Por provincia y temporal, sobre las cuencas susceptibles de la provincia
    (la comuna se lee en el centroide de la cuenca):

        alerta Caine     alguna cuenca supera Caine publicado en algun
                         episodio del temporal. Es la regla binaria.
        razon maxima     el maximo de I / I_Caine(D), lectura del episodio.
        razon critica    el maximo de la lectura de ventana critica de M4.
        lluvia maxima    el maximo de la lluvia de un episodio, sin umbral.

    La lluvia maxima es la linea base: si Caine no ordena mejor que "donde
    llovio mas", el umbral no esta aportando nada.

    El nivel regional es el mismo calculo sin separar provincias: un
    temporal, una fila.

LO QUE SALIO

    Corrida 2026-10-11_m5_alerta_sector.txt. Caine publicado se aplica tal
    cual, sin ajustar nada, asi que los tres inviernos son fuera de muestra.

    * CUANDO, a escala regional, funciona. De los 15 temporales regionales,
      6 tuvieron activaciones reportadas; Caine avisa en 4 y da una falsa
      alarma en los otros 9 (precision 0,80, AUC 0,91). Los dos que no ve son
      el 16-06-2025 (activaciones menores en Canela con 51 mm) y el bloque de
      deshielo del 11 al 18-08-2026.

    * DONDE, a escala de provincia, no. Recall 0,25 y precision 0,43 en los
      temporales regionales. Y el patron es uno: en Elqui Caine no se activa
      en ningun temporal, ni en el de julio de 2026 con el aluvion de Santa
      Gracia. Un umbral global aplicado sobre un gradiente de lluvia que va
      del desierto al semiarido queda alto justo en la provincia mas seca.

    * La linea base le gana. La lluvia maxima del temporal, sin umbral,
      ordena las provincias mejor que la razon contra Caine (AUC 0,86 contra
      0,78 en los temporales regionales). Con 12 positivos la diferencia no es
      concluyente, pero alcanza para decir que Caine no aporta sobre la lluvia
      sola, y que su corte esta mal puesto para Elqui.

    * Con el indicador de deshielo de m4_deshielo.py ("Caine o deshielo"),
      en los temporales regionales el recall por provincia sube de 0,25 a
      0,67 y la precision de 0,43 a 0,67, con la misma tasa de falsas
      alarmas; por temporal, el recall sube de 0,67 a 0,83. El indicador se
      diseno mirando el bloque de agosto: es experimental, ver su cabecera.

    De ahi el paso siguiente: niveles de alerta por provincia que miren la
    lluvia relativa al clima de cada zona, calibrados con 2024-2025 y
    probados en 2026, con esta misma tabla.

Uso:

    python src/m5_alerta_sector.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m5_calibracion as cal  # noqa: E402
import m5_validacion as m5  # noqa: E402
from m4_interpolacion import EVENTO_MINIMO_MM  # noqa: E402
from m4_umbrales import caine_intensidad_critica  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ZONA = "America/Santiago"

# La division administrativa vigente de la region (DPA de la SUBDERE). Las
# claves van sin tildes, como las escribe m5_validacion.sin_tildes.
PROVINCIAS = {
    "Elqui": ("la serena", "coquimbo", "andacollo", "la higuera", "paihuano", "vicuna"),
    "Limari": ("ovalle", "combarbala", "monte patria", "punitaqui", "rio hurtado"),
    "Choapa": ("illapel", "canela", "los vilos", "salamanca"),
}
PROVINCIA_DE = {c: p for p, comunas in PROVINCIAS.items() for c in comunas}

PAUSA_H = 24
REGIONAL_MIN_ESTACIONES = 5
POSITIVOS = cal.POSITIVOS["amplio"]
PUNTAJES = (("razon maxima", "razon_max"), ("razon critica", "critica_max"),
            ("lluvia maxima", "lluvia_max_mm"))


def temporales(episodios: pd.DataFrame) -> pd.DataFrame:
    """Junta los episodios de mas de 5 mm que se solapan o quedan a menos de 24 h."""
    nucleos = episodios[episodios["lluvia_mm"] >= EVENTO_MINIMO_MM].sort_values("inicio")
    pausa = pd.Timedelta(hours=PAUSA_H)
    grupos, ini, fin, miembros = [], None, None, []
    for _, e in nucleos.iterrows():
        if ini is not None and e["inicio"] > fin + pausa:
            grupos.append((ini, fin, miembros))
            ini, miembros = None, []
        if ini is None:
            ini, fin = e["inicio"], e["fin"]
        fin = max(fin, e["fin"])
        miembros.append(e)
    grupos.append((ini, fin, miembros))

    filas = []
    for i, (a, b, m) in enumerate(grupos):
        m = pd.DataFrame(m)
        filas.append({"temporal": i, "inicio": a, "fin": b,
                      "estaciones_5mm": m["estacion_codigo"].nunique(),
                      "lluvia_max_estacion_mm": m["lluvia_mm"].max()})
    t = pd.DataFrame(filas)
    t["regional"] = t["estaciones_5mm"] >= REGIONAL_MIN_ESTACIONES
    return t


def provincia_de_cuencas(unidades, comunas) -> pd.Series:
    import geopandas as gpd
    centros = unidades[["id_cuenca", "geometry"]].copy()
    centros["geometry"] = centros.geometry.centroid
    centros = gpd.sjoin(centros, comunas[["clave", "geometry"]], how="left", predicate="within")
    centros = centros.drop_duplicates("id_cuenca")
    return centros.set_index("id_cuenca")["clave"].map(PROVINCIA_DE)


def etiquetar(tor: pd.DataFrame, inv: pd.DataFrame):
    """Etiqueta por provincia y temporal, y la del temporal entero."""
    inv = inv.copy()
    inv["provincia"] = inv["comuna"].map(lambda c: PROVINCIA_DE.get(m5.sin_tildes(m5._texto(c))))
    holgura = pd.Timedelta(days=cal.HOLGURA_DIAS)
    desde = (tor["inicio"].dt.tz_convert(ZONA).dt.normalize() - holgura).dt.date
    hasta = (tor["fin"].dt.tz_convert(ZONA).dt.normalize() + holgura).dt.date

    filas, region, usadas = [], [], set()
    for t, d, h in zip(tor["temporal"], desde, hasta):
        dentro = inv[(inv["fecha_d"] >= d) & (inv["fecha_d"] <= h)]
        usadas |= set(dentro["id"])
        fuertes = dentro[dentro["evidencia"].isin(POSITIVOS)]
        sin_comuna = dentro["provincia"].isna().any()
        for p in PROVINCIAS:
            de_p = dentro[dentro["provincia"] == p]
            if de_p["evidencia"].isin(POSITIVOS).any():
                e = "positivo"
            elif len(de_p) or sin_comuna:
                e = "excluido"
            else:
                e = "negativo"
            filas.append({"temporal": t, "provincia": p, "etiqueta": e,
                          "entradas": ",".join(de_p["id"])})
        e = "positivo" if len(fuertes) else ("excluido" if len(dentro) else "negativo")
        region.append({"temporal": t, "etiqueta": e, "entradas": ",".join(dentro["id"])})
    sueltas = inv[~inv["id"].isin(usadas)]
    return pd.DataFrame(filas), pd.DataFrame(region), sueltas


def puntajes(gatillo: pd.DataFrame, tor: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    """Los cuatro puntajes por temporal (y por provincia, si `por` la incluye)."""
    g = gatillo.copy()
    g["temporal"] = -1
    for _, t in tor.iterrows():
        solapa = (g["inicio"] <= t["fin"]) & (g["fin"] >= t["inicio"])
        g.loc[solapa, "temporal"] = t["temporal"]
    g = g[g["temporal"] >= 0]
    g["razon"] = g["i_media_mm_h"] / caine_intensidad_critica(g["duracion_h"])
    return g.groupby(["temporal"] + por).agg(
        cuencas=("id_cuenca", "nunique"),
        cuencas_caine=("id_cuenca", lambda s: s[g.loc[s.index, "supera_caine"].astype(bool)].nunique()),
        razon_max=("razon", "max"),
        critica_max=("razon_caine_critica", "max"),
        lluvia_max_mm=("lluvia_mm", "max"),
    ).reset_index()


def evaluar(tabla: pd.DataFrame, titulo: str):
    d = tabla[tabla["etiqueta"] != "excluido"]
    y = (d["etiqueta"] == "positivo").to_numpy(int)
    print(f"\n  {titulo}: {int(y.sum())} positivos, {int((y == 0).sum())} negativos, "
          f"{int((tabla['etiqueta'] == 'excluido').sum())} excluidos")
    if y.sum() == 0 or (y == 0).sum() == 0:
        print("    falta una de las dos clases: no se evalua")
        return
    reglas = [("alerta Caine (alguna cuenca lo supera)", d["cuencas_caine"] > 0)]
    if "deshielo" in d.columns:
        reglas.append(("Caine o deshielo (experimental)",
                       (d["cuencas_caine"] > 0) | d["deshielo"].astype(bool)))
    for nombre, pred in reglas:
        m = cal.matriz(y, pred)
        print(f"    {nombre:<40} VP {m['VP']:>2}  FP {m['FP']:>2}  FN {m['FN']:>2}  "
              f"VN {m['VN']:>2}  |  recall {m['recall']:.2f}  precision "
              f"{m['precision']:.2f}  falsas alarmas {m['fpr']:.2f}")
    print("    AUC (ordena los positivos sobre los negativos?):  " + "   ".join(
        f"{nombre} {cal.auc(y, d[col].to_numpy(dtype=float)):.2f}" for nombre, col in PUNTAJES))


def main():
    import geopandas as gpd

    print("=" * 74)
    print("M5 - La alerta por provincia y por temporal")
    print("=" * 74)

    procesados = RAIZ / "data" / "processed"
    episodios = pd.read_csv(RAIZ / "outputs" / "m4_episodios.csv")
    gatillo = gpd.read_file(procesados / "gatillo.gpkg", ignore_geometry=True)
    for df in (episodios, gatillo):
        for col in ("inicio", "fin"):
            df[col] = pd.to_datetime(df[col], utc=True)

    tor = temporales(episodios)
    print(f"\nTemporales: {len(tor)} (episodios de {EVENTO_MINIMO_MM:g} mm o mas, pausa "
          f"de {PAUSA_H} h); regionales, con {REGIONAL_MIN_ESTACIONES} estaciones o mas: "
          f"{int(tor['regional'].sum())}")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        comunas = m5.cargar_comunas()
    unidades = gpd.read_file(procesados / "susceptibilidad.gpkg").to_crs(m5.CRS_METRICO)
    unidades = unidades[unidades["id_cuenca"].isin(gatillo["id_cuenca"])]
    prov = provincia_de_cuencas(unidades, comunas)
    print(f"\nCuencas con lluvia en M4: {len(unidades)}; por provincia: "
          + ", ".join(f"{p} {n}" for p, n in prov.value_counts().items())
          + f"; fuera de la region por el centroide: {int(prov.isna().sum())}")
    gatillo["provincia"] = gatillo["id_cuenca"].map(prov)

    inv = cal.cargar_inventario()
    etq_prov, etq_reg, sueltas = etiquetar(tor, inv)
    if len(sueltas):
        print(f"\nEntradas del inventario fuera de todo temporal medido: {len(sueltas)}")
        for f, g in sueltas.groupby("fecha"):
            print(f"  {f}: {len(g)} entradas ({', '.join(g['id'])})")

    p_prov = puntajes(gatillo[gatillo["provincia"].notna()], tor, ["provincia"])
    p_reg = puntajes(gatillo, tor, [])
    t_prov = etq_prov.merge(p_prov, on=["temporal", "provincia"], how="left").fillna(
        {"cuencas": 0, "cuencas_caine": 0, "razon_max": 0, "critica_max": 0, "lluvia_max_mm": 0})
    t_reg = etq_reg.merge(p_reg, on="temporal", how="left").fillna(
        {"cuencas": 0, "cuencas_caine": 0, "razon_max": 0, "critica_max": 0, "lluvia_max_mm": 0})
    for t in (t_prov, t_reg):
        t["regional"] = t["temporal"].map(tor.set_index("temporal")["regional"])

    # El indicador de deshielo de m4_deshielo.py es regional: cuatro estaciones
    # de nieve no alcanzan para tres provincias, y el bloque de agosto se activo
    # en las tres. Un temporal lo tiene si algun dia suyo tiene la condicion.
    ruta_deshielo = RAIZ / "outputs" / "m4_deshielo.csv"
    if ruta_deshielo.exists():
        diario = pd.read_csv(ruta_deshielo, index_col="dia", parse_dates=True)["deshielo"]
        dias_activos = set(diario.index[diario.astype(bool)].date)
        con_deshielo = {}
        for _, t in tor.iterrows():
            dias = pd.date_range(t["inicio"].tz_convert(ZONA).date(),
                                 t["fin"].tz_convert(ZONA).date(), freq="D").date
            con_deshielo[t["temporal"]] = bool(dias_activos & set(dias))
        tor["deshielo"] = tor["temporal"].map(con_deshielo)
        for t in (t_prov, t_reg):
            t["deshielo"] = t["temporal"].map(con_deshielo)
        print(f"\nTemporales con condicion de deshielo (m4_deshielo.py): "
              + ", ".join(t["inicio"].tz_convert(ZONA).strftime("%d-%m-%Y")
                          for _, t in tor[tor["deshielo"]].iterrows()))
    else:
        print("\nSin outputs/m4_deshielo.csv: se evalua solo Caine. "
              "Corre python src/m4_deshielo.py para sumar el indicador.")

    print("\n" + "-" * 74)
    print("Los temporales regionales")
    print("-" * 74)
    print("  + positivo, - negativo, x excluido; entre parentesis, cuencas sobre Caine;")
    print("  D, condicion de deshielo")
    print(f"  {'temporal':<23} {'est.':>4} {'mm max':>7} {'':>2}  " + "".join(f"{p:<16}" for p in PROVINCIAS))
    marca = {"positivo": "+", "negativo": "-", "excluido": "x"}
    for _, t in tor[tor["regional"]].iterrows():
        a = t["inicio"].tz_convert(ZONA).strftime("%d-%m-%Y")
        b = t["fin"].tz_convert(ZONA).strftime("%d-%m")
        celdas = []
        for p in PROVINCIAS:
            f = t_prov[(t_prov["temporal"] == t["temporal"]) & (t_prov["provincia"] == p)].iloc[0]
            celdas.append(f"{marca[f['etiqueta']]} ({int(f['cuencas_caine'])})".ljust(16))
        d = "D" if t.get("deshielo", False) else ""
        print(f"  {a} al {b:<9} {t['estaciones_5mm']:>4} {t['lluvia_max_estacion_mm']:>7.0f} {d:>2}  "
              + "".join(celdas))

    print("\n" + "-" * 74)
    print("Por provincia y temporal")
    print("-" * 74)
    evaluar(t_prov, "todos los temporales")
    evaluar(t_prov[t_prov["regional"]], "solo los regionales")

    print("\n" + "-" * 74)
    print("Por temporal, la region entera")
    print("-" * 74)
    evaluar(t_reg, "todos los temporales")
    evaluar(t_reg[t_reg["regional"]], "solo los regionales")

    tor.to_csv(RAIZ / "outputs" / "m5_temporales.csv", index=False)
    t_prov.to_csv(RAIZ / "outputs" / "m5_alerta_provincia.csv", index=False, float_format="%.4f")
    t_reg.to_csv(RAIZ / "outputs" / "m5_alerta_region.csv", index=False, float_format="%.4f")
    print("\n  tablas -> m5_temporales.csv, m5_alerta_provincia.csv, m5_alerta_region.csv")


if __name__ == "__main__":
    main()
