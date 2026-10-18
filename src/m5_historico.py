"""
M5 - Los niveles de alerta contra cincuenta anios de historia.

POR QUE EXISTE

    Los niveles de m5_niveles.py salen de 12 provincias-temporal positivas en
    5 temporales de 2024-2026. Con eso se puede mostrar que el metodo sirve,
    pero no fijar cortes: el de roja tiene un intervalo del 90% que va de 23 a
    49%. Este script busca la historia que falta y prueba el modelo contra
    ella.

LAS FUENTES

    Lluvia: CR2MET v2.5 diario, 1970-2021 (m4_cr2met_diario.py), leido en la
    ubicacion de cada pluviometro de VIPNET de Coquimbo y Atacama. Asi la
    variable es la misma que usa la alerta en vivo -la fraccion de la normal
    en la segunda estacion mas mojada de la provincia-, medida sobre la misma
    red, aunque esa red no existiera entonces.

    Activaciones: dos inventarios independientes de los de este proyecto.

      * DesInventar Chile (UNDRR / LA RED), 1970-2014: un registro por
        comuna, fecha y tipo de evento, armado desde la prensa. Se baja
        completo de desinventar.net (DI_export_chl.zip, en data/raw/historico/).
      * Mardones (2019), "Analisis estadistico de precipitaciones
        desencadenantes de flujos de detritos en la Region de Coquimbo",
        memoria de titulo, Universidad de Chile: 117 flujos del catastro de
        SERNAGEOMIN en 7 fechas (Tabla 5.1). Se usan sus fechas y cuencas.

LAS REGLAS, FIJADAS ANTES DE MIRAR LA LLUVIA

    Temporal: dias en que alguna estacion de la region recibe 5 mm o mas,
    juntando los que quedan separados por un solo dia seco. Es el analogo
    diario de m5_alerta_sector (episodios de 5 mm, pausa de 24 h).

    Provincia-temporal: se cuenta si alguna estacion de la provincia recibio
    5 mm en el temporal. Una provincia donde no llovio no es un negativo
    informativo, es un negativo regalado.

    Etiqueta estricta (la que se calibra): hay un registro de aluvion,
    avenida torrencial o deslizamiento, o uno de lluvia, tempestad o
    inundacion cuyo texto habla de quebradas, aluviones, barro, derrumbes,
    rodados o crecidas, en una comuna de la provincia, entre 2 dias antes y 2
    dias despues del temporal. Dos dias y no uno porque DesInventar a veces
    fecha el evento por la noticia. Se descartan los deslizamientos mineros
    (piques, yacimientos, pirquineros): no los gatilla la lluvia.

    Excluida: hay registros de dano por el temporal que no hablan de
    quebradas, o un registro sin provincia esa misma fecha. Se sabe que algo
    paso, no que se activaron quebradas.

    Etiqueta amplia (referencia): cualquier registro de dano por el temporal.

    Periodo de calibracion: 1970-2004. Desde 2005 DesInventar registra la
    mitad que antes en el norte, y un "no hubo registro" deja de ser creible
    como negativo. 2005-2014 se reporta como prueba secundaria.

    Pruebas: (1) VIPNET 2024-2026, con pluviometros de verdad y el inventario
    de este proyecto, que el modelo historico no vio; (2) los flujos de 2015 y
    2017 de la tesis, que solo tienen positivos: se mide que nivel les habria
    dado el modelo.

    Decision: si el modelo historico ordena 2024-2026 con AUC 0,90 o mas, los
    niveles operativos se recalibran con historia mas VIPNET. Si no, se quedan
    los de m5_niveles.py y se dice por que.

Uso:

    python src/m4_cr2met_diario.py     # una vez, ~40 min
    python src/m5_historico.py
"""

from __future__ import annotations

import json
import re
import sys
import warnings
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun  # noqa: E402
import m4_cr2met_diario as diario  # noqa: E402
import m4_lluvia as m4  # noqa: E402
import m5_calibracion as cal  # noqa: E402
import m5_niveles as niv  # noqa: E402
from comun import sin_tildes  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
HISTORICO = RAIZ / "data" / "raw" / "historico"

PROVINCIA_DE = {
    **comun.PROVINCIA_DE,
    "chanaral": "Chanaral", "diego de almagro": "Chanaral",
    "copiapo": "Copiapo", "caldera": "Copiapo", "tierra amarilla": "Copiapo",
    "vallenar": "Huasco", "freirina": "Huasco", "huasco": "Huasco", "alto del carmen": "Huasco",
}
REGION_DE = {p: ("Coquimbo" if p in comun.PROVINCIAS else "Atacama") for p in set(PROVINCIA_DE.values())}

UMBRAL_DIA_MM = 5.0
HOLGURA_DIAS = 2
CALIBRACION = (1970, 2004)
COBERTURA_BAJA = (2005, 2014)

# Mardones (2019), Tabla 5.1, con la cuenca traducida a provincia. "Costeras
# entre Elqui y Limari" y Los Choros quedan dentro de las provincias ya listadas
# para esas fechas.
TESIS = [
    ("1992-03-24", "1992-03-24", ["Limari"]),
    ("1997-06-18", "1997-06-18", ["Elqui"]),
    ("2004-04-23", "2004-04-23", ["Elqui"]),
    ("2006-02-15", "2006-02-15", ["Elqui"]),
    ("2015-03-24", "2015-03-25", ["Limari", "Elqui"]),
    ("2017-05-11", "2017-05-13", ["Elqui", "Limari", "Choapa"]),
    ("2017-06-26", "2017-06-26", ["Elqui"]),
]

TIPOS_CLIMA = ("aluvion", "avenida torrencial", "deslizamiento", "lluvias", "tempestad", "inundacion")
TIPOS_MASA = ("aluvion", "avenida torrencial", "deslizamiento")
# "activ" a secas atrapaba "actividad minera paralizada": se exige la forma verbal.
PALABRAS_QUEBRADA = (r"quebrada|aluvi|barro|lodo|derrumbe|rodado|deslizamient|crecida|desborde|"
                     r"avenida|activaci|se activ|activaron")
PALABRAS_MINA = r"\bmina\b|minero|pique|yacimiento|pirquin|socav|mineral\b"


# =============================================================================
# Las activaciones historicas
# =============================================================================

def desinventar() -> pd.DataFrame:
    """Los registros de clima de Coquimbo y Atacama, clasificados."""
    t = zipfile.ZipFile(HISTORICO / "DI_export_chl.zip").read("DI_export_chl.xml").decode("utf-8", "replace")
    fichas = t[t.find("<fichas>"):t.find("</fichas>")]
    campos = ["serial", "level0", "name1", "name2", "evento", "lugar", "fechano", "fechames",
              "fechadia", "di_comments", "fuentes"]
    filas = []
    for tr in re.findall(r"<TR>(.*?)</TR>", fichas, flags=re.S):
        filas.append({c: (re.search(rf"<{c}>(.*?)</{c}>", tr, flags=re.S) or [None, None])[1]
                      for c in campos})
    d = pd.DataFrame(filas)
    d = d[d["level0"].isin(["03", "04"])].copy()
    d["tipo"] = d["evento"].map(sin_tildes)
    d = d[d["tipo"].isin(TIPOS_CLIMA)].copy()
    d["fecha"] = pd.to_datetime(dict(
        year=pd.to_numeric(d["fechano"]), month=pd.to_numeric(d["fechames"]).fillna(1).clip(1, 12),
        day=pd.to_numeric(d["fechadia"]).fillna(1).clip(1, 31)), errors="coerce")
    texto = (d["lugar"].fillna("") + " " + d["di_comments"].fillna("")).map(sin_tildes)
    d["minero"] = texto.str.contains(PALABRAS_MINA, regex=True)
    d = d[~d["minero"]].copy()
    d["quebrada"] = d["tipo"].isin(TIPOS_MASA) | texto.loc[d.index].str.contains(PALABRAS_QUEBRADA, regex=True)
    # Provincia: la del registro, o la de su comuna; si no hay ninguna, el
    # registro vale para toda la region (y solo sirve para excluir).
    prov = d["name1"].map(lambda s: {"elqui": "Elqui", "limari": "Limari", "choapa": "Choapa",
                                     "copiapo": "Copiapo", "huasco": "Huasco",
                                     "chanaral": "Chanaral"}.get(sin_tildes(s)))
    d["provincia"] = prov.fillna(d["name2"].map(lambda s: PROVINCIA_DE.get(sin_tildes(s))))
    d["region"] = np.where(d["level0"] == "04", "Coquimbo", "Atacama")
    return d[["serial", "fecha", "region", "provincia", "tipo", "quebrada", "lugar", "di_comments"]]


# =============================================================================
# La lluvia historica en los pluviometros de VIPNET
# =============================================================================

def estaciones_virtuales():
    import geopandas as gpd

    cat = pd.concat([m4.descargar_catalogo(m4.TIPO_PRECIPITACION, region=r) for r in (3, 4)],
                    ignore_index=True)
    cat["normal_mm"] = cat["codigo"].map(niv.normal_en_estaciones(
        cat, RAIZ / "data" / "processed" / "precipitacion_media_anual.tif"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        comunas = comun.cargar_comunas()
    pts = gpd.GeoDataFrame(cat, geometry=gpd.points_from_xy(cat["lon"], cat["lat"]),
                           crs="EPSG:4326").to_crs(comun.CRS_METRICO)
    pts = gpd.sjoin(pts, comunas[["clave", "geometry"]], how="left", predicate="within")
    cat["provincia"] = pts.drop_duplicates("codigo").set_index("codigo")["clave"].map(
        PROVINCIA_DE).reindex(cat["codigo"]).to_numpy()
    return cat[cat["provincia"].notna() & cat["normal_mm"].notna()].reset_index(drop=True)


def celdas(cat, transform, forma):
    """La celda de la grilla de cada estacion; si cae al mar, la vecina con dato."""
    muestra = diario.leer_mes(2000, 6)[0]
    inv = ~transform
    idx = []
    for lon, lat in zip(cat["lon"], cat["lat"]):
        c, f = inv * (lon, lat)
        f, c = int(f), int(c)
        if not np.isfinite(muestra[f, c]):
            vecinas = [(f + i, c + j) for i in (-1, 0, 1) for j in (-1, 0, 1)
                       if 0 <= f + i < forma[0] and 0 <= c + j < forma[1]
                       and np.isfinite(muestra[f + i, c + j])]
            f, c = vecinas[0] if vecinas else (f, c)
        idx.append((f, c))
    return np.array(idx)


def lluvia_diaria(cat) -> pd.DataFrame:
    """Dia x estacion, en mm, 1970-2021."""
    transform = diario.transformada()
    forma = diario.leer_mes(2000, 6).shape[1:]
    idx = celdas(cat, transform, forma)
    partes = []
    for a in range(diario.PERIODO[0], diario.PERIODO[1] + 1):
        for m in range(1, 13):
            g = diario.leer_mes(a, m)
            dias = pd.date_range(f"{a}-{m:02d}-01", periods=g.shape[0], freq="D")
            partes.append(pd.DataFrame(g[:, idx[:, 0], idx[:, 1]], index=dias, columns=cat["codigo"]))
    return pd.concat(partes)


def temporales(lluvia: pd.DataFrame) -> pd.DataFrame:
    """Dias con 5 mm en alguna estacion, juntando los separados por un dia seco."""
    humedo = (lluvia >= UMBRAL_DIA_MM).any(axis=1)
    dias = humedo.index[humedo]
    grupos, ini, ult = [], None, None
    for d in dias:
        if ini is None:
            ini = ult = d
        elif (d - ult).days <= 2:
            ult = d
        else:
            grupos.append((ini, ult))
            ini = ult = d
    grupos.append((ini, ult))
    return pd.DataFrame(grupos, columns=["inicio", "fin"]).rename_axis("temporal").reset_index()


def segunda(v: np.ndarray) -> float:
    v = np.sort(v[np.isfinite(v)])[::-1]
    return float(v[1]) if len(v) > 1 else 0.0


def tabla_provincias(lluvia, cat, tor) -> pd.DataFrame:
    filas = []
    arr = lluvia.to_numpy()
    idx_dia = {d: i for i, d in enumerate(lluvia.index)}
    for _, t in tor.iterrows():
        a, b = idx_dia[t["inicio"]], idx_dia[t["fin"]] + 1
        total = np.nansum(arr[a:b], axis=0)
        maximo_dia = np.nanmax(arr[a:b], axis=0)
        # Lluvia de los 7 dias anteriores, para la variable antecedente.
        antes = np.nansum(arr[max(0, a - 7):a], axis=0)
        for p, sel in cat.groupby("provincia"):
            k = sel.index.to_numpy()
            if not (maximo_dia[k] >= UMBRAL_DIA_MM).any():
                continue
            frac = total[k] / sel["normal_mm"].to_numpy()
            filas.append({"temporal": t["temporal"], "inicio": t["inicio"], "fin": t["fin"],
                          "provincia": p, "region": REGION_DE[p],
                          "fraccion_2": segunda(frac), "fraccion_max": float(np.nanmax(frac)),
                          "antecedente_2": segunda(antes[k] / sel["normal_mm"].to_numpy()),
                          "dias": (t["fin"] - t["inicio"]).days + 1})
    return pd.DataFrame(filas)


def etiquetar(tabla, di) -> pd.DataFrame:
    tabla = tabla.copy()
    h = pd.Timedelta(days=HOLGURA_DIAS)
    estricta, amplia = [], []
    for _, r in tabla.iterrows():
        en = di[(di["fecha"] >= r["inicio"] - h) & (di["fecha"] <= r["fin"] + h)]
        propios = en[en["provincia"] == r["provincia"]]
        sin_prov = en[en["provincia"].isna() & (en["region"] == r["region"])]
        tesis = any(p == r["provincia"] and pd.Timestamp(a) - h <= r["fin"] and pd.Timestamp(b) + h >= r["inicio"]
                    for a, b, ps in TESIS for p in ps)
        if tesis or propios["quebrada"].any():
            e = "positivo"
        elif len(propios) or len(sin_prov):
            e = "excluido"
        else:
            e = "negativo"
        estricta.append(e)
        amplia.append("positivo" if (tesis or len(propios)) else ("excluido" if len(sin_prov) else "negativo"))
    tabla["etiqueta"] = estricta
    tabla["etiqueta_amplia"] = amplia
    return tabla


# =============================================================================
# El modelo
# =============================================================================

def ajustar(x, y):
    return niv.ajustar(x, y)


def evaluar_prueba(nombre, b, x, y):
    p = niv.probabilidad(b, x)
    print(f"  {nombre}: AUC {cal.auc(y, p):.2f}, Brier {niv.brier(y, p):.3f}, "
          f"{int(y.sum())} positivos de {len(y)}")
    d = pd.DataFrame({"p": p, "etiqueta": np.where(y == 1, "positivo", "negativo")})
    niv.tabla_niveles(d, "p")
    return cal.auc(y, p)


def main():
    print("=" * 74)
    print("M5 - Los niveles de alerta contra cincuenta anios de historia")
    print("=" * 74)

    di = desinventar()
    print(f"\nDesInventar, Coquimbo y Atacama, registros de clima sin los mineros: {len(di)}; "
          f"con quebradas o remocion: {int(di['quebrada'].sum())}; sin provincia: "
          f"{int(di['provincia'].isna().sum())}")

    cat = estaciones_virtuales()
    print(f"Pluviometros de VIPNET usados como estaciones virtuales: {len(cat)} "
          + ", ".join(f"{p} {n}" for p, n in cat["provincia"].value_counts().items()))
    lluvia = lluvia_diaria(cat)
    tor = temporales(lluvia)
    print(f"Temporales 1970-2021: {len(tor)}")

    tabla = etiquetar(tabla_provincias(lluvia, cat, tor), di)
    tabla["anio"] = tabla["inicio"].dt.year
    tabla.to_csv(RAIZ / "outputs" / "m5_historico.csv", index=False, float_format="%.4f")

    def periodo(a, b):
        return tabla[(tabla["anio"] >= a) & (tabla["anio"] <= b)]

    for nombre, (a, b) in (("calibracion", CALIBRACION), ("cobertura baja", COBERTURA_BAJA),
                           ("despues de DesInventar", (2015, 2021))):
        t = periodo(a, b)
        print(f"  {nombre} {a}-{b}: {len(t)} provincias-temporal; positivas {int((t.etiqueta == 'positivo').sum())} "
              f"en {t.loc[t.etiqueta == 'positivo', 'temporal'].nunique()} temporales; "
              f"excluidas {int((t.etiqueta == 'excluido').sum())}")

    # --- Calibracion 1970-2004 ---
    cal_t = periodo(*CALIBRACION)
    d = cal_t[cal_t["etiqueta"] != "excluido"].reset_index(drop=True)
    y = (d["etiqueta"] == "positivo").to_numpy(int)
    x = np.log10(d["fraccion_2"].clip(lower=niv.PISO_FRACCION)).to_numpy()
    b = ajustar(x, y)
    print("\n" + "-" * 74)
    print(f"Calibracion {CALIBRACION[0]}-{CALIBRACION[1]}: {len(d)} casos, {int(y.sum())} positivos "
          f"en {d.loc[y == 1, 'temporal'].nunique()} temporales")
    print("-" * 74)
    print("  cortes: " + ", ".join(f"{n} {niv.corte(b, u):.1%}" for n, u in niv.NIVELES))

    # dejando fuera un temporal a la vez
    p_cv = np.full(len(d), np.nan)
    for t in d["temporal"].unique():
        fuera = (d["temporal"] == t).to_numpy()
        bt = ajustar(x[~fuera], y[~fuera])
        p_cv[fuera] = niv.probabilidad(bt, x[fuera])
    print(f"  validacion cruzada por temporal: AUC {cal.auc(y, p_cv):.2f}, Brier {niv.brier(y, p_cv):.3f}")
    for reg, g in d.groupby("region"):
        k = g.index.to_numpy()
        print(f"    {reg}: AUC {cal.auc(y[k], p_cv[k]):.2f} ({int(y[k].sum())} positivos)")

    # incertidumbre de los cortes, remuestreando temporales enteros
    rng = np.random.default_rng(0)
    tem = d["temporal"].unique()
    por_tem = {t: np.flatnonzero(d["temporal"].to_numpy() == t) for t in tem}
    cortes = []
    for _ in range(500):
        idx = np.concatenate([por_tem[t] for t in rng.choice(tem, len(tem))])
        try:
            bb = ajustar(x[idx], y[idx])
            cortes.append([niv.corte(bb, u) for _, u in niv.NIVELES])
        except Exception:
            continue
    c = np.array(cortes)
    print("  intervalo del 90%, remuestreando temporales: " + ", ".join(
        f"{n} {np.percentile(c[:, k], 5):.0%}-{np.percentile(c[:, k], 95):.0%}"
        for k, (n, _) in enumerate(niv.NIVELES)))

    # la lluvia antecedente, ahora que hay positivos para probarla
    xa = np.log10(d["antecedente_2"].clip(lower=niv.PISO_FRACCION)).to_numpy()
    X2 = np.column_stack([x, xa])
    p2 = np.full(len(d), np.nan)
    for t in d["temporal"].unique():
        fuera = (d["temporal"] == t).to_numpy()
        b2, _, ok = cal.logistica(X2[~fuera], y[~fuera])
        p2[fuera] = 1 / (1 + np.exp(-(b2[0] + X2[fuera] @ b2[1:])))
    print(f"  con lluvia de los 7 dias previos como segunda variable: AUC {cal.auc(y, p2):.2f}, "
          f"Brier {niv.brier(y, p2):.3f}")

    # --- Pruebas ---
    print("\n" + "-" * 74)
    print("Pruebas del modelo historico")
    print("-" * 74)
    v = pd.read_csv(RAIZ / "outputs" / "m5_niveles.csv")
    xv = np.log10(v["fraccion_2"].clip(lower=niv.PISO_FRACCION)).to_numpy()
    auc_vipnet = evaluar_prueba("VIPNET 2024-2026 (pluviometros reales, inventario propio)",
                                b, xv, v["y"].to_numpy())
    reg = v["regional"].to_numpy()
    print(f"    solo temporales regionales: AUC {cal.auc(v['y'][reg], niv.probabilidad(b, xv[reg])):.2f}")

    t2 = periodo(*COBERTURA_BAJA)
    t2 = t2[t2["etiqueta"] != "excluido"]
    evaluar_prueba(f"{COBERTURA_BAJA[0]}-{COBERTURA_BAJA[1]} (DesInventar con menos cobertura)", b,
                   np.log10(t2["fraccion_2"].clip(lower=niv.PISO_FRACCION)).to_numpy(),
                   (t2["etiqueta"] == "positivo").to_numpy(int))

    t3 = periodo(2015, 2021)
    pos = t3[t3["etiqueta"] == "positivo"]
    print(f"\n  Flujos de la tesis en 2015 y 2017 (solo positivos): {len(pos)} provincias-temporal")
    for _, r in pos.iterrows():
        pr = niv.probabilidad(b, np.log10(max(r["fraccion_2"], niv.PISO_FRACCION)))
        print(f"    {r['inicio']:%d-%m-%Y} {r['provincia']:<8} {r['fraccion_2']:>6.0%} de la normal -> "
              f"{niv.nivel([pr])[0]}")

    # --- Decision ---
    print("\n" + "-" * 74)
    print("Decision")
    print("-" * 74)
    salida = {"historico": {"b0": float(b[0]), "b1": float(b[1]),
                            "cortes": {n: float(niv.corte(b, u)) for n, u in niv.NIVELES}},
              "auc_vipnet_2024_2026": float(auc_vipnet)}
    if auc_vipnet >= 0.90:
        xc = np.concatenate([x, xv])
        yc = np.concatenate([y, v["y"].to_numpy()])
        bc = ajustar(xc, yc)
        print(f"  El modelo historico ordena 2024-2026 con AUC {auc_vipnet:.2f} (>= 0,90): se "
              "recalibra con historia mas VIPNET.")
        print("  cortes nuevos: " + ", ".join(f"{n} {niv.corte(bc, u):.1%}" for n, u in niv.NIVELES))
        print(f"  coeficientes: b0 {bc[0]:.6f}, b1 {bc[1]:.6f}; {int(yc.sum())} positivos de {len(yc)}")
        salida["combinado"] = {"b0": float(bc[0]), "b1": float(bc[1]),
                               "cortes": {n: float(niv.corte(bc, u)) for n, u in niv.NIVELES},
                               "positivos": int(yc.sum()), "casos": int(len(yc))}
    else:
        print(f"  El modelo historico ordena 2024-2026 con AUC {auc_vipnet:.2f} (< 0,90): se quedan "
              "los niveles de m5_niveles.py.")
    (RAIZ / "outputs" / "m5_historico_modelo.json").write_text(json.dumps(salida, indent=2))
    print("\n  tablas -> m5_historico.csv, m5_historico_modelo.json")


if __name__ == "__main__":
    main()
