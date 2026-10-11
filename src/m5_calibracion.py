"""
M5 - Calibracion: ajustar Caine con dos inviernos y probarlo en un tercero.

La idea de fondo:

    Hasta octubre de 2026 este proyecto no podia calibrar nada. Tenia un solo
    temporal, el de julio de 2026, y todas sus observaciones eran positivas: hay
    activaciones documentadas y no hay ningun episodio en que lloviera y no
    pasara nada. Con eso se puede medir recall y nada mas, y ajustar una curva
    sobre esas mismas observaciones seria ajustar el modelo contra su propia
    validacion.

    M4 ahora cubre tres inviernos. 2024 y 2025 tuvieron lluvia real y, segun la
    prensa, activaciones mayormente menores. Eso aporta lo que faltaba: episodios
    donde llovio y no se reporto nada. Con ellos se ajusta la curva sobre 2024 y
    2025 y se la prueba sobre el invierno de 2026, que el ajuste nunca ve.

QUE ES UNA OBSERVACION

    Un episodio de lluvia en una estacion: el par (estacion, episodio). No el
    par cuenca-episodio.

    Un umbral I-D es un umbral de lluvia, y todas las cuencas que M4 asigna a la
    misma estacion comparten el reloj de su lluvia: el mismo inicio, la misma
    duracion. Contarlas por separado repetiria la misma observacion decenas de
    veces -Cuncumen sostiene 116 cuencas- y le daria a cada estacion un peso
    proporcional a cuantas cuencas tiene alrededor, que no es informacion sobre
    el umbral. La intensidad de la observacion es la mediana de las cuencas de
    esa zona, que con la interpolacion de M4 ya no es igual a la de la estacion.

COMO SE ETIQUETA

    POSITIVO  una activacion documentada cae a menos de 3 km de una cuenca
              susceptible de la zona (el mismo radio de m5_validacion.py) y su
              fecha queda dentro del episodio, con un dia de holgura a cada
              lado porque la prensa fecha la nota, no la crecida.

    EXCLUIDO  ni positivo ni negativo. Tres casos:
              - una entrada de escurrimiento o alerta preventiva: el agua corrio
                o se aviso, pero no hay evidencia de flujo de detritos, y
                tampoco se puede decir que no paso nada;
              - una entrada SIN NOMBRE en la comuna y la fecha -"se activaron
                41 quebradas", "todas las quebradas de Andacollo"-, o sin
                comuna, que entonces cubre toda la region: hubo activaciones
                ahi y no se sabe cuales. Lo mismo una entrada CON nombre que
                no esta en OpenStreetMap: se sabe la comuna, no el lugar;
              - con --positivos fuerte, una activacion menor: no cuenta como
                flujo pero tampoco como nada.

    NEGATIVO  todo lo demas.

    Y aca esta la debilidad, que hay que decir antes de mostrar un numero. El
    negativo es PRESUNTO, no observado. Que la prensa no reporte una activacion
    en un episodio de 2025 es evidencia de que no paso nada importante cerca de
    un camino, no prueba de que no paso nada. Eso tiene dos consecuencias, y las
    dos van en una direccion conocida:

        - La precision que se reporta es una COTA INFERIOR. Si una quebrada
          bajo sin que nadie la reportara, el modelo que la marco aparece como
          falso positivo cuando acerto.
        - La curva ajustada queda sesgada hacia ARRIBA: los positivos no
          reportados, contados como negativos, empujan el umbral a pedir mas
          lluvia de la necesaria.

    Lo que hace defendible el ejercicio es que los dos inviernos de
    entrenamiento si tuvieron cobertura de prensa: los balances de SENAPRED de
    junio y agosto de 2025 nombran quebradas activadas en Canela, Andacollo y
    Los Vilos, asi que el sistema que reporta estaba funcionando.

EL AJUSTE

    Una regresion logistica por maxima verosimilitud sobre log10 D y log10 I:

        logit P(activa) = b0 + bD * log10 D + bI * log10 I

    Cada curva de probabilidad constante es una ley de potencia, y por eso esto
    es exactamente ajustar alfa y beta de Caine:

        I = alfa * D^(-beta),   beta = bD / bI,
                                alfa = 10^((logit(p) - b0) / bI)

    Beta no depende de p: todas las curvas son paralelas en log-log, y el
    ajuste fija su pendiente. Alfa si depende, y hay que elegir p. Se reportan
    dos: p = 0,5, que es la frontera natural del modelo, y el p que maximiza el
    indice de Youden (sensibilidad + especificidad - 1) SOBRE EL ENTRENAMIENTO.
    El de Youden es el que se lleva a la prueba, ya fijo.

    El intervalo de confianza sale de remuestrear EVENTOS completos, no
    observaciones. Las estaciones de un mismo temporal no son independientes:
    si llovio fuerte en Cuncumen, llovio fuerte en Salamanca. Remuestrear
    observaciones sueltas daria un intervalo mas angosto que lo que los datos
    sostienen.

LA PRUEBA

    Sobre el invierno de 2026 (1 de junio a 23 de agosto), con el umbral ya
    fijo, se compara tres curvas con los mismos datos: Caine publicado, Caine
    en su ventana critica y la curva ajustada. Se reporta recall, precision
    (cota inferior), tasa de falsos positivos y AUC. El AUC no depende de
    ningun umbral: mide si la curva ORDENA bien los episodios, que es justo lo
    que el diagnostico dijo que fallaba -el modelo ponia los escurrimientos de
    Carcamo y Punitaqui por encima de las activaciones de Tres Cruces y Las
    Barrancas-.

LA REGRESION CON MAS VARIABLES

    Si los datos alcanzan, se ajusta tambien una logistica sobre Melton, I, D,
    lluvia antecedente de 72 h y altitud. "Alcanzan" se decide con la regla de
    diez positivos por variable, fijada antes de mirar: con cinco variables
    hacen falta 50 positivos de entrenamiento. Si no estan, no se ajusta y se
    dice cuantos hay.

Uso:

    python src/m5_calibracion.py
    python src/m5_calibracion.py --positivos fuerte   # sin activaciones menores
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clases_cuenca import CLASES_SUSCEPTIBLES  # noqa: E402
from m4_umbrales import CAINE_ALFA, CAINE_BETA, caine_intensidad_critica  # noqa: E402
import m5_validacion as m5  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ZONA = "America/Santiago"

INVENTARIOS = (RAIZ / "docs" / "inventario_activaciones_2024-2025.csv",
               RAIZ / "docs" / "inventario_activaciones_2026-07.csv")

POSITIVOS = {
    "amplio": ("aluvion", "activacion", "activacion_menor"),
    "fuerte": ("aluvion", "activacion"),
}
DUDOSOS = ("escurrimiento", "alerta_preventiva")
HOLGURA_DIAS = 1

# Entrenamiento: inviernos hidrologicos 2024 y 2025 (abril a marzo, ver
# m4_lluvia.invierno). Prueba: la ventana de m5_validacion.
INVIERNOS_ENTRENO = (2024, 2025)

POSITIVOS_POR_VARIABLE = 10
VARIABLES_EXTENDIDAS = ["log10_D", "log10_I", "melton", "antecedente_72h_mm", "altitud_m"]

N_REMUESTREOS = 1000


# =============================================================================
# Inventario
# =============================================================================

def cargar_inventario() -> pd.DataFrame:
    partes = [pd.read_csv(r, dtype=str) for r in INVENTARIOS]
    inv = pd.concat(partes, ignore_index=True)
    inv["fecha_d"] = pd.to_datetime(inv["fecha"]).dt.date
    return inv


def ubicar_entradas(inv, osm, comunas, susceptibles, cuenca_estacion, radio_m):
    """Para cada entrada, las estaciones cuyas zonas toca.

    Una entrada con nombre se ubica igual que en m5_validacion y toca las zonas
    de las cuencas susceptibles a menos de `radio_m`. Una entrada sin nombre
    toca todas las zonas de su comuna, o todas, si tampoco trae comuna.
    """
    # Las comunas se comparan sin tildes: el inventario las escribe sin tildes y
    # la capa de la BCN con ellas.
    zona_comuna = (cuenca_estacion.assign(clave=cuenca_estacion["comuna"].map(m5.sin_tildes))
                   .groupby("clave")["estacion_codigo"].agg(set).to_dict())
    todas = set(cuenca_estacion["estacion_codigo"])

    def por_comuna(e):
        comuna = m5._texto(e["comuna"])
        if comuna:
            return zona_comuna.get(m5.sin_tildes(comuna), set()), f"toda la comuna de {comuna}"
        return todas, "toda la region"

    filas = []
    for _, e in inv.iterrows():
        nombre = m5._texto(e["quebrada"]) or m5._texto(e["sector"])
        if nombre:
            geo, como = m5.ubicar(e.to_dict(), osm, comunas)
            if geo is None:
                # Con nombre pero fuera de OSM: se sabe que hubo una activacion
                # en esa comuna ese dia, y no donde. Igual que una sin nombre,
                # no aporta positivo y si quita negativos. Sin este caso, cuatro
                # quebradas de Canela de junio de 2025 desaparecian y la comuna
                # quedaba como si ese dia no hubiera pasado nada.
                estaciones, alcance = por_comuna(e)
                como = f"{como}: {alcance}"
                tipo = "sin_ubicar"
            else:
                cerca = susceptibles[susceptibles.geometry.distance(geo) <= radio_m]
                estaciones = set(cuenca_estacion.loc[
                    cuenca_estacion["id_cuenca"].isin(cerca["id_cuenca"]), "estacion_codigo"])
                tipo = "ubicada" if estaciones else "sin_cobertura"
        else:
            estaciones, alcance = por_comuna(e)
            como = f"sin nombre: {alcance}"
            tipo = "sin_nombre"
        filas.append({**e.to_dict(), "tipo": tipo, "ubicacion": como,
                      "estaciones": estaciones})
    return pd.DataFrame(filas)


# =============================================================================
# Observaciones
# =============================================================================

def observaciones(gatillo: pd.DataFrame) -> pd.DataFrame:
    """Una fila por estacion y episodio, con la mediana de su zona.

    gatillo.gpkg ya trae melton y h_media_m de cada cuenca: M4 las hereda de
    susceptibilidad.gpkg al asignar la estacion.
    """
    g = gatillo
    obs = g.groupby(["estacion_codigo", "inicio"]).agg(
        estacion_nombre=("estacion_nombre", "first"),
        fin=("fin", "first"),
        evento=("evento", "first"),
        invierno=("invierno", "first"),
        duracion_h=("duracion_h", "first"),
        lluvia_mm=("lluvia_mm", "median"),
        i_media_mm_h=("i_media_mm_h", "median"),
        razon_caine_critica=("razon_caine_critica", "median"),
        antecedente_72h_mm=("antecedente_72h_mm", "median"),
        melton=("melton", "median"),
        altitud_m=("h_media_m", "median"),
        n_cuencas=("id_cuenca", "nunique"),
    ).reset_index()
    obs["log10_D"] = np.log10(obs["duracion_h"])
    obs["log10_I"] = np.log10(obs["i_media_mm_h"])
    obs["razon_caine"] = obs["i_media_mm_h"] / caine_intensidad_critica(obs["duracion_h"])
    return obs


def etiquetar(obs: pd.DataFrame, entradas: pd.DataFrame, positivos) -> pd.Series:
    """'positivo', 'negativo' o 'excluido', con las reglas de la cabecera."""
    ini = obs["inicio"].dt.tz_convert(ZONA).dt.date
    fin = obs["fin"].dt.tz_convert(ZONA).dt.date
    holgura = pd.Timedelta(days=HOLGURA_DIAS)
    desde = (pd.to_datetime(ini) - holgura).dt.date
    hasta = (pd.to_datetime(fin) + holgura).dt.date

    etiqueta = pd.Series("negativo", index=obs.index)
    excluir = pd.Series(False, index=obs.index)
    positivo = pd.Series(False, index=obs.index)

    for _, e in entradas.iterrows():
        if not e["estaciones"]:
            continue
        toca = obs["estacion_codigo"].isin(e["estaciones"]) & (desde <= e["fecha_d"]) & (e["fecha_d"] <= hasta)
        if not toca.any():
            continue
        if e["tipo"] in ("sin_nombre", "sin_ubicar") or e["evidencia"] in DUDOSOS:
            excluir |= toca
        elif e["evidencia"] in positivos:
            positivo |= toca
        else:
            excluir |= toca          # activacion menor con --positivos fuerte

    etiqueta[excluir] = "excluido"
    etiqueta[positivo] = "positivo"   # un positivo con nombre gana a la duda

    # Un episodio de un solo paso de 30 min no tiene forma de lluvia, y M4 ya lo
    # marca como objecion: es un escalon del contador. Recoleta tiene uno de
    # 18,4 mm el 16 de diciembre de 2025 que supera Caine por construccion.
    # Contarlo como negativo seria castigar al umbral por un artefacto.
    etiqueta[obs["duracion_h"] <= 0.5] = "excluido"
    return etiqueta


# =============================================================================
# Regresion logistica
# =============================================================================

def logistica(X: np.ndarray, y: np.ndarray, iteraciones: int = 100):
    """Maxima verosimilitud por Newton-Raphson. Devuelve (coef, cov, convergio).

    Se escribe a mano en vez de usar una libreria por dos motivos: devuelve la
    matriz de covarianza, que da los errores estandar, y deja ver cuando no
    converge. Si los positivos quedan perfectamente separados de los negativos,
    la verosimilitud no tiene maximo y los coeficientes crecen sin limite; un
    paquete que no avisa devolveria numeros enormes con aspecto de resultado.
    """
    X = np.column_stack([np.ones(len(X)), X])
    b = np.zeros(X.shape[1])
    for _ in range(iteraciones):
        p = 1 / (1 + np.exp(-(X @ b)))
        W = p * (1 - p)
        H = X.T @ (X * W[:, None])
        g = X.T @ (y - p)
        try:
            paso = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            return b, None, False
        b = b + paso
        if np.max(np.abs(paso)) < 1e-8:
            break
    else:
        return b, None, False
    p = 1 / (1 + np.exp(-(X @ b)))
    H = X.T @ (X * (p * (1 - p))[:, None])
    convergio = bool(np.all(np.isfinite(b)) and np.max(np.abs(b)) < 1e3)
    return b, np.linalg.inv(H), convergio


def curva(b, p: float):
    """(alfa, beta) de la curva de probabilidad p."""
    b0, bD, bI = b
    logit = np.log(p / (1 - p))
    return 10 ** ((logit - b0) / bI), bD / bI


def puntaje(b, obs):
    return b[0] + b[1] * obs["log10_D"].to_numpy() + b[2] * obs["log10_I"].to_numpy()


def youden(y, s):
    """El corte sobre el puntaje que maximiza sensibilidad + especificidad - 1."""
    mejor, corte = -1.0, np.nan
    for c in np.unique(s):
        pred = s >= c
        tpr = (pred & (y == 1)).sum() / max((y == 1).sum(), 1)
        fpr = (pred & (y == 0)).sum() / max((y == 0).sum(), 1)
        if tpr - fpr > mejor:
            mejor, corte = tpr - fpr, c
    return corte, mejor


def auc(y, s) -> float:
    """Area bajo la curva ROC por Mann-Whitney: la probabilidad de que un
    positivo al azar tenga mas puntaje que un negativo al azar."""
    y = np.asarray(y)
    s = np.asarray(s, dtype=float)
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    rangos = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return float((rangos[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2)
                 / (len(pos) * len(neg)))


def matriz(y, pred) -> dict:
    y, pred = np.asarray(y).astype(bool), np.asarray(pred).astype(bool)
    vp, fp = int((pred & y).sum()), int((pred & ~y).sum())
    fn, vn = int((~pred & y).sum()), int((~pred & ~y).sum())
    return {"VP": vp, "FP": fp, "FN": fn, "VN": vn,
            "recall": vp / (vp + fn) if vp + fn else np.nan,
            "precision": vp / (vp + fp) if vp + fp else np.nan,
            "fpr": fp / (fp + vn) if fp + vn else np.nan}


def remuestreo(entreno: pd.DataFrame, p_operacion: float, n: int, semilla: int = 0):
    """Intervalos de alfa y beta remuestreando eventos regionales enteros."""
    rng = np.random.default_rng(semilla)
    eventos = entreno["evento"].unique()
    por_evento = {ev: grupo for ev, grupo in entreno.groupby("evento")}
    betas, alfas, alfas_op, fallidos = [], [], [], 0
    for _ in range(n):
        muestra = pd.concat([por_evento[ev] for ev in rng.choice(eventos, len(eventos))])
        y = (muestra["etiqueta"] == "positivo").to_numpy(int)
        if y.sum() < 2 or y.sum() == len(y):
            fallidos += 1
            continue
        b, _, ok = logistica(muestra[["log10_D", "log10_I"]].to_numpy(), y)
        if not ok or b[2] <= 0:
            fallidos += 1
            continue
        a50, beta = curva(b, 0.5)
        aop, _ = curva(b, p_operacion)
        betas.append(beta)
        alfas.append(a50)
        alfas_op.append(aop)
    return np.array(alfas), np.array(alfas_op), np.array(betas), fallidos


# =============================================================================
# Figura
# =============================================================================

def figura(entreno, prueba, b, p_op, ruta):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ejes = plt.subplots(1, 2, figsize=(13, 5.5), sharey=True)
    d = np.logspace(np.log10(0.5), np.log10(240), 200)
    for ax, datos, titulo in ((ejes[0], entreno, "Entrenamiento: inviernos 2024 y 2025"),
                              (ejes[1], prueba, "Prueba: invierno 2026")):
        for etq, color, marca, tam in (("negativo", "#9aa5b1", "o", 10),
                                       ("excluido", "#e0b04a", "s", 14),
                                       ("positivo", "crimson", "^", 42)):
            sel = datos[datos["etiqueta"] == etq]
            ax.scatter(sel["duracion_h"], sel["i_media_mm_h"], s=tam, c=color,
                       marker=marca, alpha=0.7, edgecolors="none",
                       label=f"{etq} ({len(sel)})")
        ax.plot(d, caine_intensidad_critica(d), "k-", lw=2, label="Caine (1980)")
        if b is not None:
            for p, estilo in ((0.5, "--"), (p_op, ":")):
                a, beta = curva(b, p)
                ax.plot(d, a * d ** (-beta), "b" + estilo, lw=1.8,
                        label=f"ajustada p={p:.2f}: I = {a:.2f} D^-{beta:.2f}")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("duracion D (h)")
        ax.set_title(titulo)
        ax.grid(True, which="both", alpha=0.25)
        ax.legend(fontsize=8, loc="lower left")
    ejes[0].set_ylabel("intensidad media I (mm/h)")
    fig.tight_layout()
    fig.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close(fig)


# =============================================================================
# main
# =============================================================================

def main():
    ap = argparse.ArgumentParser(
        description="M5 - Ajusta Caine sobre 2024-2025 y lo prueba sobre 2026.")
    ap.add_argument("--procesados", type=Path, default=RAIZ / "data" / "processed")
    ap.add_argument("--radio-km", type=float, default=3.0)
    ap.add_argument("--positivos", choices=sorted(POSITIVOS), default="amplio")
    args = ap.parse_args()
    positivos = POSITIVOS[args.positivos]

    print("=" * 74)
    print("M5 - Calibracion de Caine: entrena en 2024-2025, prueba en 2026")
    print("=" * 74)
    print(f"Positivos: {', '.join(positivos)}")

    gatillo = gpd.read_file(args.procesados / "gatillo.gpkg")
    # Se calibra sobre las unidades chicas, como en la corrida del 10-10. Los
    # troncos de m1_troncos.py tienen lluvia areal y otra escala, y meterlos en
    # la mediana de cada zona mezclaria dos objetos en una observacion; se
    # evaluan aparte en m5_troncos.py.
    gatillo = gatillo[gatillo["clase"] != "tronco"]
    for col in ("inicio", "fin"):
        gatillo[col] = pd.to_datetime(gatillo[col], utc=True)
    unidades = gpd.read_file(args.procesados / "susceptibilidad.gpkg").to_crs(m5.CRS_METRICO)
    susceptibles = unidades[unidades["clase"].isin(CLASES_SUSCEPTIBLES)]

    print("\nCargando OSM y comunas...")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        osm = m5.cargar_osm()
        comunas = m5.cargar_comunas()

    # Cada cuenca con su estacion (la de M4) y su comuna (por el centroide).
    cuenca_estacion = gatillo[["id_cuenca", "estacion_codigo"]].drop_duplicates("id_cuenca")
    centros = susceptibles[["id_cuenca", "geometry"]].copy()
    centros["geometry"] = centros.geometry.centroid
    centros = gpd.sjoin(centros, comunas[["comuna", "geometry"]], how="left")
    cuenca_estacion = cuenca_estacion.merge(centros[["id_cuenca", "comuna"]], on="id_cuenca")

    inv = cargar_inventario()
    entradas = ubicar_entradas(inv, osm, comunas, susceptibles, cuenca_estacion,
                               args.radio_km * 1000)
    print(f"\nInventario: {len(inv)} entradas")
    print(entradas.groupby(["tipo"]).size().to_string())
    entradas[["id", "quebrada", "comuna", "fecha", "evidencia", "tipo", "ubicacion"]].assign(
        n_estaciones=entradas["estaciones"].map(len)).to_csv(
        RAIZ / "outputs" / "m5_calibracion_inventario.csv", index=False)

    obs = observaciones(gatillo)
    obs["etiqueta"] = etiquetar(obs, entradas, positivos)

    ini_local = obs["inicio"].dt.tz_convert(ZONA)
    en_prueba = ((ini_local >= pd.Timestamp(m5.VALIDACION_DESDE, tz=ZONA))
                 & (ini_local < pd.Timestamp(m5.VALIDACION_HASTA, tz=ZONA)))
    obs["conjunto"] = np.where(obs["invierno"].isin(INVIERNOS_ENTRENO), "entreno",
                               np.where(en_prueba, "prueba", "fuera"))

    print(f"\nObservaciones estacion-episodio: {len(obs)}")
    tabla = obs.groupby(["conjunto", "etiqueta"]).size().unstack(fill_value=0)
    print(tabla.to_string())

    # Que eventos aportan positivos: si todos salen de un solo temporal, el
    # ajuste describe ese temporal y no un umbral.
    for conj in ("entreno", "prueba"):
        pos = obs[(obs["conjunto"] == conj) & (obs["etiqueta"] == "positivo")]
        if len(pos):
            fechas = pos.groupby("evento")["inicio"].min().dt.tz_convert(ZONA).dt.date
            print(f"\n  positivos de {conj} por evento regional:")
            for ev, n in pos.groupby("evento").size().items():
                print(f"    evento {ev:>4} ({fechas[ev]}): {n}")

    entreno = obs[(obs["conjunto"] == "entreno") & (obs["etiqueta"] != "excluido")].copy()
    prueba = obs[(obs["conjunto"] == "prueba") & (obs["etiqueta"] != "excluido")].copy()
    y_ent = (entreno["etiqueta"] == "positivo").to_numpy(int)
    y_pru = (prueba["etiqueta"] == "positivo").to_numpy(int)

    dir_out = RAIZ / "outputs"
    obs.to_csv(dir_out / "m5_calibracion_observaciones.csv", index=False, float_format="%.4f")

    # --- La precision de Caine publicado, que antes no se podia calcular ---
    print("\n" + "-" * 74)
    print("Caine publicado, ahora con negativos (precision = cota inferior)")
    print("-" * 74)
    print(f"  {'conjunto':<10} {'lectura':<16} {'VP':>4} {'FP':>5} {'FN':>4} {'VN':>5} "
          f"{'recall':>7} {'precision':>10} {'FPR':>6} {'AUC':>6}")
    for nombre, datos, y in (("entreno", entreno, y_ent), ("prueba", prueba, y_pru)):
        for lectura, col in (("episodio", "razon_caine"), ("ventana critica", "razon_caine_critica")):
            s = datos[col].to_numpy()
            m = matriz(y, s >= 1.0)
            print(f"  {nombre:<10} {lectura:<16} {m['VP']:>4} {m['FP']:>5} {m['FN']:>4} "
                  f"{m['VN']:>5} {m['recall']:>7.2f} {m['precision']:>10.3f} "
                  f"{m['fpr']:>6.3f} {auc(y, np.log(s)):>6.3f}")

    # --- El ajuste ---
    print("\n" + "-" * 74)
    print("Ajuste por maxima verosimilitud sobre 2024-2025")
    print("-" * 74)
    print(f"  {len(entreno)} observaciones, {int(y_ent.sum())} positivas")
    b = None
    if y_ent.sum() < 2:
        print("  NO SE AJUSTA: hacen falta al menos dos positivos.")
    else:
        b, cov, ok = logistica(entreno[["log10_D", "log10_I"]].to_numpy(), y_ent)
        if not ok:
            print("  NO CONVERGE: los positivos quedan separados de los negativos y la")
            print("  verosimilitud no tiene maximo. No hay curva que reportar.")
            b = None
        elif b[2] <= 0:
            print(f"  El coeficiente de la intensidad sale {b[2]:.3f}: mas lluvia, MENOS")
            print("  probabilidad de activacion. No es una curva de umbral y no se usa.")
            b = None

    if b is not None:
        ee = np.sqrt(np.diag(cov))
        print(f"  b0 = {b[0]:7.3f} (ee {ee[0]:.3f})")
        print(f"  bD = {b[1]:7.3f} (ee {ee[1]:.3f})   coeficiente de log10 D")
        print(f"  bI = {b[2]:7.3f} (ee {ee[2]:.3f})   coeficiente de log10 I")

        s_ent = puntaje(b, entreno)
        corte, j = youden(y_ent, s_ent)
        p_op = float(1 / (1 + np.exp(-corte)))
        a50, beta = curva(b, 0.5)
        aop, _ = curva(b, p_op)

        alfas, alfas_op, betas, fallidos = remuestreo(entreno, p_op, N_REMUESTREOS)
        ic = lambda v: (np.percentile(v, 2.5), np.percentile(v, 97.5)) if len(v) else (np.nan, np.nan)
        print(f"\n  {'curva':<34} {'alfa':>8} {'IC 95%':>18} {'beta':>6} {'IC 95%':>16}")
        print(f"  {'Caine (1980) publicado':<34} {CAINE_ALFA:>8.2f} {'':>18} {CAINE_BETA:>6.2f}")
        print(f"  {'ajustada, p = 0,50':<34} {a50:>8.2f} "
              f"{'[%.2f, %.2f]' % ic(alfas):>18} {beta:>6.2f} {'[%.2f, %.2f]' % ic(betas):>16}")
        print(f"  {f'ajustada, p = {p_op:.3f} (Youden {j:.2f})':<34} {aop:>8.2f} "
              f"{'[%.2f, %.2f]' % ic(alfas_op):>18} {beta:>6.2f}")
        print(f"  remuestreo por eventos: {N_REMUESTREOS - fallidos} de {N_REMUESTREOS} "
              f"validos ({fallidos} sin positivos o sin convergencia)")

        print("\n  Prueba sobre 2026 con la curva ya fija (p de Youden del entrenamiento):")
        print(f"  {'curva':<26} {'VP':>4} {'FP':>5} {'FN':>4} {'VN':>5} "
              f"{'recall':>7} {'precision':>10} {'FPR':>6} {'AUC':>6}")
        s_pru = puntaje(b, prueba)
        filas = [("Caine publicado", prueba["razon_caine"].to_numpy() >= 1, np.log(prueba["razon_caine"])),
                 ("Caine ventana critica", prueba["razon_caine_critica"].to_numpy() >= 1,
                  np.log(prueba["razon_caine_critica"])),
                 ("ajustada (Youden)", s_pru >= corte, s_pru)]
        for nombre, pred, s in filas:
            m = matriz(y_pru, pred)
            print(f"  {nombre:<26} {m['VP']:>4} {m['FP']:>5} {m['FN']:>4} {m['VN']:>5} "
                  f"{m['recall']:>7.2f} {m['precision']:>10.3f} {m['fpr']:>6.3f} "
                  f"{auc(y_pru, s):>6.3f}")

        # El AUC de toda la prueba mezcla temporales con mecanismos distintos.
        # Se separa por evento regional: los positivos de cada evento contra
        # TODOS los negativos de la prueba, y la lluvia mediana que tuvieron.
        # Un AUC bajo 0,5 dice que las activaciones de ese evento ocurrieron
        # donde llovio MENOS, que es lo que se espera si no las gatillo la lluvia.
        print("\n  Prueba por evento regional con positivos (AUC contra todos los")
        print("  negativos de la prueba; recall = positivos del evento que marca cada curva):")
        print(f"  {'evento':<22} {'pos':>4} {'lluvia med':>11} {'AUC Caine':>10} "
              f"{'critica':>8} {'ajustada':>9} {'recall C':>9} {'critica':>8} {'ajust.':>7}")
        negativos = prueba["etiqueta"] == "negativo"
        for ev, grupo in prueba[prueba["etiqueta"] == "positivo"].groupby("evento"):
            sel = negativos | ((prueba["etiqueta"] == "positivo") & (prueba["evento"] == ev))
            q, yq = prueba[sel], y_pru[sel.to_numpy()]
            fecha = grupo["inicio"].min().tz_convert(ZONA).date()
            rec = [(grupo["razon_caine"] >= 1).mean(),
                   (grupo["razon_caine_critica"] >= 1).mean(),
                   (puntaje(b, grupo) >= corte).mean()]
            print(f"  {f'{ev} ({fecha})':<22} {len(grupo):>4} "
                  f"{grupo['lluvia_mm'].median():>8.1f} mm "
                  f"{auc(yq, np.log(q['razon_caine'])):>10.3f} "
                  f"{auc(yq, np.log(q['razon_caine_critica'])):>8.3f} "
                  f"{auc(yq, puntaje(b, q)):>9.3f} "
                  f"{rec[0]:>9.2f} {rec[1]:>8.2f} {rec[2]:>7.2f}")

        # Si todos los positivos de entrenamiento salen de un solo evento, el
        # remuestreo por eventos no puede medir nada: o saca ese evento y no hay
        # positivos, o lo saca y los positivos son los mismos. El intervalo sale
        # angosto por construccion, y hay que decirlo para que nadie lo lea como
        # precision.
        n_ev_pos = entreno.loc[entreno["etiqueta"] == "positivo", "evento"].nunique()
        if n_ev_pos < 3:
            print(f"\n  ATENCION: los positivos de entrenamiento salen de {n_ev_pos} "
                  "evento(s). Los intervalos")
            print("  del remuestreo no miden incertidumbre real con tan pocos eventos.")

        figura(obs[obs["conjunto"] == "entreno"], obs[obs["conjunto"] == "prueba"],
               b, p_op, dir_out / "m5_calibracion.png")
    else:
        figura(obs[obs["conjunto"] == "entreno"], obs[obs["conjunto"] == "prueba"],
               None, 0.5, dir_out / "m5_calibracion.png")

    # --- La regresion con mas variables, si alcanza ---
    print("\n" + "-" * 74)
    necesarios = POSITIVOS_POR_VARIABLE * len(VARIABLES_EXTENDIDAS)
    print(f"Regresion con {', '.join(VARIABLES_EXTENDIDAS)}")
    print(f"  hacen falta {necesarios} positivos de entrenamiento "
          f"({POSITIVOS_POR_VARIABLE} por variable); hay {int(y_ent.sum())}.")
    if y_ent.sum() < necesarios:
        print("  NO SE AJUSTA. Con menos positivos que eso los coeficientes")
        print("  describen el ruido de esta muestra, no el fenomeno.")
    else:
        datos = entreno.dropna(subset=VARIABLES_EXTENDIDAS)
        media = datos[VARIABLES_EXTENDIDAS].mean()
        desv = datos[VARIABLES_EXTENDIDAS].std()
        Z = ((datos[VARIABLES_EXTENDIDAS] - media) / desv).to_numpy()
        y = (datos["etiqueta"] == "positivo").to_numpy(int)
        bx, covx, okx = logistica(Z, y)
        if not okx:
            print("  No converge.")
        else:
            print("  Coeficientes estandarizados (por desviacion estandar):")
            for v, c, e in zip(["constante"] + VARIABLES_EXTENDIDAS, bx, np.sqrt(np.diag(covx))):
                print(f"    {v:<22} {c:>7.3f} (ee {e:.3f})")
            dp = prueba.dropna(subset=VARIABLES_EXTENDIDAS)
            Zp = ((dp[VARIABLES_EXTENDIDAS] - media) / desv).to_numpy()
            sp = bx[0] + Zp @ bx[1:]
            print(f"  AUC en la prueba de 2026: "
                  f"{auc((dp['etiqueta'] == 'positivo').to_numpy(int), sp):.3f}")

    print(f"\n  observaciones -> m5_calibracion_observaciones.csv")
    print(f"  inventario    -> m5_calibracion_inventario.csv")
    print(f"  figura        -> m5_calibracion.png")


if __name__ == "__main__":
    main()
