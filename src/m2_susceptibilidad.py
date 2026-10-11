"""
M2 - Susceptibilidad: que cuencas son capaces de generar flujos de detritos.

La idea de fondo:

    No toda quebrada que lleva agua genera un aluvion. Para que baje un flujo de
    detritos -barro, piedras y bloques moviendose como una masa densa- la cuenca
    tiene que ser capaz de darle al agua suficiente energia para arrastrar
    material grueso. Una cuenca chica y empinada lo logra; una grande y tendida
    solo produce inundacion de agua limpia.

    Este script mide esa capacidad con variables sacadas del terreno, y clasifica
    cada cuenca segun umbrales publicados.

Por que no inventamos pesos:

    Lo facil seria armar una formula tipo "pendiente x 0,4 + desnivel x 0,3 +
    ..." y elegir los numeros a ojo. El problema es que nadie puede decir si
    esos pesos son correctos, ni siquiera una misma.

    En vez de eso se usa la **razon de Melton**, que tiene umbrales calibrados
    contra eventos reales en la literatura (Wilford et al., 2004, Landslides
    1:61-66; Melton, 1965). Es una sola cuenta, sin parametros libres:

        R = desnivel / raiz(area)

    con el desnivel en km y el area en km2, lo que la deja adimensional.
    Mide cuanta energia potencial tiene la cuenca por unidad de tamano.

    Clasificacion de Wilford:

        R < 0,3                      -> inundacion (agua)
        0,3 <= R < 0,6               -> crecida de detritos
        R >= 0,6 y cuenca corta      -> FLUJO DE DETRITOS (aluvion)
        R >= 0,6 y cuenca larga      -> crecida de detritos

    El largo entra porque una cuenca empinada pero alargada disipa energia en el
    trayecto: el material se va depositando antes de llegar a la salida.

Limite conocido:

    Melton se calibro sobre cuencas de 0,1 a 10 km2. En Coquimbo, 105 de las 174
    cuencas caen en ese rango y 146 estan bajo 50 km2, asi que aplica bien. Las
    pocas cuencas grandes (Elqui, Limari, Choapa) son cuencas de rio, no
    quebradas de aluvion: el script las clasifica igual pero las marca como
    fuera de rango, para no leerlas como si el indice significara lo mismo ahi.

Uso:

    python src/m2_susceptibilidad.py

Lee lo que dejo M1 en data/processed/ y escribe ahi la capa de susceptibilidad.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from rasterio import features
from scipy import ndimage
from shapely.geometry import Point

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clases_cuenca import CLASES  # noqa: E402
from cobertura import COBERTURA_MINIMA, verificar_cobertura  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent

# --- Umbrales de Wilford et al. (2004) ---------------------------------------
# Se dejan como constantes con nombre para que se vea de donde sale cada corte y
# para poder moverlos de un solo lugar si M5 sugiere recalibrarlos.
MELTON_CRECIDA = 0.30      # bajo esto: inundacion de agua
MELTON_FLUJO = 0.60        # sobre esto: potencial de flujo de detritos
LARGO_MAX_FLUJO_KM = 2.7   # cuencas mas largas disipan la energia en el camino

# Melton se calibro en cuencas chicas. Sobre esta area el indice pierde sentido.
AREA_VALIDA_KM2 = 10.0


def estadisticas_por_cuenca(cuencas: gpd.GeoDataFrame, ruta_dem: Path):
    """Calcula altura y pendiente dentro de cada cuenca, en una sola pasada.

    El metodo: se "pinta" cada cuenca sobre la grilla del DEM con su id como
    valor (rasterizar), y despues se le pide a scipy el minimo, maximo y promedio
    de cada grupo de una vez. Es mucho mas rapido que recortar el raster cuenca
    por cuenca, que obligaria a recorrer el archivo 174 veces.
    """
    print("Leyendo el DEM y midiendo cada cuenca...")

    with rasterio.open(ruta_dem) as src:
        elevacion = src.read(1).astype("float32")
        afin = src.transform
        sin_dato = src.nodata if src.nodata is not None else -9999.0
        resolucion = abs(afin.a)
        forma = (src.height, src.width)

    valido = elevacion != sin_dato
    elevacion[~valido] = np.nan

    # Pendiente: cuanto sube o baja el terreno por cada metro que uno avanza.
    # np.gradient da la variacion en cada eje; el arcotangente de su magnitud
    # combinada es la inclinacion real de la ladera, en grados.
    print("  calculando pendientes...")
    dz_dy, dz_dx = np.gradient(elevacion, resolucion, resolucion)
    pendiente = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))
    del dz_dy, dz_dx

    # POR CAPAS QUE NO SE SUPERPONEN
    #
    # La primera version pintaba todas las cuencas en una sola capa de
    # etiquetas, y donde dos se superponen gana la ultima que se pinta. Con las
    # subcuencas de confluencia eso ya pasaba sin que se notara: quedan dentro
    # de las cuencas costeras de rio, y estas se median sin los pixeles de sus
    # subcuencas. No movia ninguna clase porque esas cuencas de rio salen
    # inundacion igual. Con los troncos, que se pintaban al final, el efecto se
    # invirtio y les quito pixeles a tres mil unidades chicas: la clasificacion
    # de las 3.757 de siempre cambio sin que nada fallara.
    #
    # Ahora cada capa sin superposicion -costeras, confluencias- se pinta por
    # separado, y cada tronco aparte en su propia ventana, porque los troncos
    # se anidan entre ellos.
    n = len(cuencas)
    salida = {k: np.full(n, np.nan) for k in
              ("h_min_m", "h_max_m", "h_media_m", "pend_media_g", "pend_p90_g")}
    origen = (cuencas["origen"].fillna("costera").to_numpy()
              if "origen" in cuencas.columns else np.full(n, "costera", dtype=object))

    def medir(elev, pend, etq, ids):
        etq_p = np.where(np.isfinite(pend), etq, 0)
        return {
            "h_min_m": ndimage.minimum(elev, etq, ids),
            "h_max_m": ndimage.maximum(elev, etq, ids),
            "h_media_m": ndimage.mean(elev, etq, ids),
            "pend_media_g": ndimage.mean(pend, etq_p, ids),
            # El percentil 90 de la pendiente: que tan empinado es el sector mas
            # inclinado de la cuenca, ignorando el 10% mas extremo. Va por
            # labeled_comprehension y no por un ciclo, que recorreria el raster
            # completo una vez por cuenca.
            "pend_p90_g": ndimage.labeled_comprehension(
                pend, etq_p, ids, lambda v: np.percentile(v, 90), "float64", np.nan),
        }

    for capa in [o for o in pd.unique(origen) if o != "tronco"]:
        pos = np.flatnonzero(origen == capa)
        sub = cuencas.iloc[pos]
        ids = sub["id_cuenca"].astype(int).tolist()
        etq = features.rasterize(((g, int(i)) for g, i in zip(sub.geometry, ids)),
                                 out_shape=forma, transform=afin, fill=0, dtype="int32")
        etq[~valido] = 0
        for k, v in medir(elevacion, pendiente, etq, ids).items():
            salida[k][pos] = np.asarray(v, dtype="float64")
        del etq

    pos_troncos = np.flatnonzero(origen == "tronco")
    if len(pos_troncos):
        from rasterio.windows import from_bounds
        print(f"  midiendo {len(pos_troncos)} troncos, cada uno en su ventana...")
        for p in pos_troncos:
            g = cuencas.geometry.iloc[p]
            w = from_bounds(*g.bounds, transform=afin).round_offsets().round_lengths()
            f0, c0 = max(int(w.row_off), 0), max(int(w.col_off), 0)
            f1 = min(int(w.row_off + w.height) + 1, forma[0])
            c1 = min(int(w.col_off + w.width) + 1, forma[1])
            af = afin * afin.translation(c0, f0)
            etq = features.rasterize([(g, 1)], out_shape=(f1 - f0, c1 - c0),
                                     transform=af, fill=0, dtype="int32")
            etq[~valido[f0:f1, c0:c1]] = 0
            for k, v in medir(elevacion[f0:f1, c0:c1], pendiente[f0:f1, c0:c1], etq, [1]).items():
                salida[k][p] = float(np.asarray(v).ravel()[0])

    return salida


def largo_cuenca_km(cuencas: gpd.GeoDataFrame) -> np.ndarray:
    """Largo de la cuenca: distancia en linea recta de la salida al punto mas lejano.

    Es la definicion que usa Wilford para su clasificacion. Se mide contra el
    borde de la cuenca, que es donde estan las cabeceras.
    """
    largos = []
    for geom, x, y in zip(cuencas.geometry, cuencas["salida_x"], cuencas["salida_y"]):
        salida = Point(x, y)
        partes = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        distancia = max(
            salida.distance(Point(c)) for parte in partes for c in parte.exterior.coords
        )
        largos.append(distancia / 1000.0)
    return np.array(largos)


def clasificar(melton: np.ndarray, largo_km: np.ndarray):
    """Aplica dos clasificaciones, y devuelve ambas.

    Por que dos y no una:

        La razon de Melton es robusta y se usa igual en todo el mundo. El
        criterio de largo maximo, en cambio, sale del estudio original de
        Wilford en la Columbia Britanica costera -bosque templado lluvioso- y no
        hay evidencia de que el mismo valor sirva en el norte semiarido de Chile.

        Sobre los datos de Coquimbo ese umbral resulta decisivo: varias de las
        cuencas mas energeticas de la region quedan descartadas por diferencias
        de decenas de metros. Elegir un criterio a ciegas seria esconder esa
        sensibilidad.

        Entonces se calculan las dos y se guardan las dos. M5, al comparar
        contra el temporal de julio 2026, va a poder decir cual reproduce mejor
        lo que realmente paso.

    Devuelve (clase_wilford, clase_melton).
    """
    # --- Wilford completo: Melton + largo de la cuenca ---
    wilford = np.full(len(melton), "inundacion", dtype=object)
    wilford[melton >= MELTON_CRECIDA] = "crecida_detritos"
    # Solo las cuencas empinadas Y cortas pueden mandar el material hasta la
    # salida sin depositarlo en el camino.
    wilford[(melton >= MELTON_FLUJO) & (largo_km <= LARGO_MAX_FLUJO_KM)] = "flujo_detritos"

    # --- Solo Melton, sin el criterio regional de largo ---
    solo_melton = np.full(len(melton), "inundacion", dtype=object)
    solo_melton[melton >= MELTON_CRECIDA] = "crecida_detritos"
    solo_melton[melton >= MELTON_FLUJO] = "flujo_detritos"

    return wilford, solo_melton


def calcular(cuencas: gpd.GeoDataFrame, red: gpd.GeoDataFrame, ruta_dem: Path):
    """Arma la tabla de susceptibilidad de cada cuenca."""
    stats = estadisticas_por_cuenca(cuencas, ruta_dem)
    for columna, valores in stats.items():
        cuencas[columna] = valores

    cuencas["desnivel_m"] = cuencas["h_max_m"] - cuencas["h_min_m"]
    cuencas["largo_km"] = largo_cuenca_km(cuencas)

    # --- Razon de Melton ---
    # Desnivel en km sobre raiz del area en km2: queda adimensional.
    cuencas["melton"] = (cuencas["desnivel_m"] / 1000.0) / np.sqrt(cuencas["area_km2"])

    # --- Otras dos medidas de forma, utiles para M3 y M4 ---
    # Densidad de drenaje: cuantos km de cauce hay por km2. Alta = red muy
    # ramificada, el agua llega rapido al cauce principal.
    #
    # Las subcuencas de confluencia que agrega m1_subcuencas.py no estan en la
    # red: sus tramos quedaron asignados a la cuenca costera que las contiene.
    # Para ellas esto da NaN y no cero. La diferencia importa: cero se lee como
    # "no tiene cauces", que de una quebrada es falso y ademas absurdo, mientras
    # que NaN dice lo que pasa de verdad, que es que no se midio. La densidad de
    # drenaje no entra en la clasificacion -`clasificar` solo mira melton y
    # largo_km- asi que no tenerla no invalida nada.
    largo_red = red.groupby("id_cuenca")["largo_m"].sum() / 1000.0
    cuencas["dens_drenaje_km_km2"] = (
        cuencas["id_cuenca"].map(largo_red) / cuencas["area_km2"]
    )

    # Razon de elongacion (Schumm): 1 = cuenca redonda, cerca de 0 = alargada.
    # Las redondas concentran el agua mas rapido en un solo punto.
    cuencas["elongacion"] = (
        2 * np.sqrt(cuencas["area_km2"] / np.pi) / cuencas["largo_km"]
    )

    wilford, solo_melton = clasificar(
        cuencas["melton"].to_numpy(), cuencas["largo_km"].to_numpy()
    )
    cuencas["clase"] = wilford
    cuencas["clase_melton"] = solo_melton
    cuencas["melton_aplicable"] = cuencas["area_km2"] <= AREA_VALIDA_KM2

    # Las cuencas cortadas por el borde del DEM no se pueden clasificar: les
    # falta parte del area, y como Melton es H/raiz(A), un area truncada infla
    # el indice. Dejarlas clasificadas produciria cuencas "criticas" que son
    # puro artefacto del recorte. Se marcan con una clase propia para que se
    # vean en el mapa y para que M3 no las tome como quebradas reales.
    if "toca_borde" in cuencas.columns:
        borde = cuencas["toca_borde"].fillna(False).astype(bool)
        cuencas.loc[borde, "clase"] = "borde_truncado"
        cuencas.loc[borde, "clase_melton"] = "borde_truncado"

    # Los troncos de m1_troncos.py no se clasifican con Melton: miden de 50 a
    # cientos de km2, y el indice esta calibrado hasta 10. Se marcan aparte y
    # se evaluan todos. `clase_melton` queda calculada solo como referencia.
    if "origen" in cuencas.columns:
        tronco = (cuencas["origen"] == "tronco") & (cuencas["clase"] != "borde_truncado")
        cuencas.loc[tronco, "clase"] = "tronco"

    # Ranking por Melton descendente: las mas energeticas primero.
    cuencas = cuencas.sort_values("melton", ascending=False).reset_index(drop=True)
    cuencas.insert(0, "ranking", cuencas.index + 1)
    return cuencas


def figura(cuencas: gpd.GeoDataFrame, ruta_png: Path):
    """Mapa de clases y distribucion del indice."""
    colores = {
        "flujo_detritos": "#b2182b",
        "crecida_detritos": "#ef8a62",
        "inundacion": "#c9d6e5",
    }
    # Los troncos van solo con contorno: estan anidados sobre las unidades
    # chicas y, rellenos, las taparian.
    troncos = cuencas[cuencas["clase"] == "tronco"]
    cuencas = cuencas[cuencas["clase"] != "tronco"]

    fig = plt.figure(figsize=(15, 12))
    ax1 = fig.add_subplot(1, 2, 1)
    ax2 = fig.add_subplot(2, 2, 2)
    ax3 = fig.add_subplot(2, 2, 4)

    # La leyenda se arma con parches propios: geopandas no siempre propaga el
    # argumento `label` al dibujar poligonos, y la leyenda sale vacia.
    marcas = []
    for clase, color in colores.items():
        sel = cuencas[cuencas["clase"] == clase]
        if sel.empty:
            continue
        sel.plot(ax=ax1, color=color, edgecolor="black", linewidth=0.3)
        marcas.append(
            mpatches.Patch(facecolor=color, edgecolor="black", linewidth=0.3,
                           label=f"{clase} ({len(sel)})")
        )

    # Las cuencas capaces de generar flujos de detritos miden entre 0,4 y 3 km2
    # sobre una region de 40.000: a escala regional son invisibles. Se marcan con
    # un circulo en la desembocadura, que es ademas el punto que importa para M3,
    # porque es por ahi por donde el material sale hacia rutas y poblados.
    criticas = cuencas[cuencas["clase"] == "flujo_detritos"]
    if not criticas.empty:
        ax1.scatter(criticas["salida_x"], criticas["salida_y"],
                    s=90, facecolor="none", edgecolor="#b2182b",
                    linewidth=1.6, zorder=5)
        marcas.append(
            plt.Line2D([], [], marker="o", linestyle="none", markersize=9,
                       markerfacecolor="none", markeredgecolor="#b2182b",
                       markeredgewidth=1.6,
                       label=f"salida de cuenca critica ({len(criticas)})")
        )

    if not troncos.empty:
        troncos.boundary.plot(ax=ax1, color="#6a3d9a", linewidth=0.8)
        marcas.append(plt.Line2D([], [], color="#6a3d9a", linewidth=1.2,
                                 label=f"tronco, sin clasificar ({len(troncos)})"))

    ax1.set_title("Susceptibilidad a flujos de detritos\n(clasificacion de Wilford)",
                  fontsize=12)
    ax1.legend(handles=marcas, loc="upper right", fontsize=9)
    ax1.set_xticks([])
    ax1.set_yticks([])

    # Melton vs area: se ve de una que las cuencas chicas son las energeticas.
    for clase, color in colores.items():
        sel = cuencas[cuencas["clase"] == clase]
        ax2.scatter(sel["area_km2"], sel["melton"], c=color, s=18,
                    edgecolor="black", linewidth=0.3, label=clase)
    ax2.axhline(MELTON_FLUJO, color="#b2182b", ls="--", lw=1)
    ax2.axhline(MELTON_CRECIDA, color="#ef8a62", ls="--", lw=1)
    ax2.axvline(AREA_VALIDA_KM2, color="gray", ls=":", lw=1)
    ax2.set_xscale("log")
    ax2.set_xlabel("area de la cuenca (km2, escala log)")
    ax2.set_ylabel("razon de Melton")
    ax2.set_title("Melton vs tamano", fontsize=11)
    ax2.text(AREA_VALIDA_KM2 * 1.15, ax2.get_ylim()[1] * 0.93,
             "limite de validez\ndel indice", fontsize=7, color="gray")

    ax3.scatter(cuencas["pend_media_g"], cuencas["melton"],
                c=[colores.get(c, "#888888") for c in cuencas["clase"]], s=18,
                edgecolor="black", linewidth=0.3)
    ax3.axhline(MELTON_FLUJO, color="#b2182b", ls="--", lw=1)
    ax3.set_xlabel("pendiente media (grados)")
    ax3.set_ylabel("razon de Melton")
    ax3.set_title("Melton vs pendiente media", fontsize=11)

    fig.tight_layout()
    fig.savefig(ruta_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(
        description="M2 - Clasifica las cuencas por susceptibilidad a flujos de detritos."
    )
    ap.add_argument("--procesados", type=Path, default=RAIZ / "data" / "processed")
    # La capa de unidades es un argumento y no una ruta fija porque hay dos
    # juegos validos: las cuencas costeras de m1_recortar_region.py, y esas mas
    # las subcuencas de confluencia que agrega m1_subcuencas.py. Cual se use es
    # una decision de alcance -si el modelo cubre solo la franja costera o
    # tambien los valles interiores- y conviene que quede escrita en el comando
    # que genero cada corrida.
    ap.add_argument("--cuencas", type=Path, default=None,
                    help="Capa de unidades. Por defecto unidades_coquimbo.gpkg "
                         "si existe, si no cuencas_coquimbo.gpkg.")
    ap.add_argument("--red", type=Path, default=None,
                    help="Red de quebradas. Por defecto red_quebradas_coquimbo.gpkg.")
    args = ap.parse_args()

    if args.cuencas is not None:
        ruta_cuencas = args.cuencas
    else:
        con_subcuencas = args.procesados / "unidades_coquimbo.gpkg"
        ruta_cuencas = (con_subcuencas if con_subcuencas.exists()
                        else args.procesados / "cuencas_coquimbo.gpkg")
    ruta_red = args.red or args.procesados / "red_quebradas_coquimbo.gpkg"
    ruta_dem = args.procesados / "dem_utm19s.tif"
    for ruta in (ruta_cuencas, ruta_red, ruta_dem):
        if not ruta.exists():
            sys.exit(f"Falta {ruta}\nCorre antes los scripts de M1.")
    print(f"Unidades de analisis: {ruta_cuencas.name}")

    # El desnivel de cada cuenca sale de este DEM, y el desnivel es la H de
    # H/raiz(A). Si el DEM viene recortado, el indice sale mal por los dos
    # lados. Ver src/cobertura.py.
    verificar_cobertura(ruta_dem, RAIZ / "data" / "raw" / "limite_coquimbo.gpkg",
                        COBERTURA_MINIMA)

    cuencas = gpd.read_file(ruta_cuencas)
    red = gpd.read_file(ruta_red)
    print(f"Cuencas de entrada: {len(cuencas)}")

    cuencas = calcular(cuencas, red, ruta_dem)

    salida = args.procesados / "susceptibilidad.gpkg"
    cuencas.to_file(salida, layer="susceptibilidad", driver="GPKG")

    dir_outputs = RAIZ / "outputs"
    dir_outputs.mkdir(parents=True, exist_ok=True)
    ruta_png = dir_outputs / "m2_susceptibilidad.png"
    figura(cuencas, ruta_png)

    n_borde = int((cuencas["clase"] == "borde_truncado").sum())
    if n_borde:
        print(f"\n{n_borde} cuencas excluidas por tocar el borde del DEM "
              "(area truncada infla Melton)")

    print("\nClasificacion, por los dos criterios:")
    print(f"  {'':<18} {'Wilford':>10} {'solo Melton':>13}")
    for clase in reversed(CLASES):
        n_w = (cuencas["clase"] == clase).sum()
        n_m = (cuencas["clase_melton"] == clase).sum()
        print(f"  {clase:<18} {n_w:>10} {n_m:>13}")

    # Cuantas cuencas dependen del umbral de largo, que es el parametro heredado
    # de otra region y por lo tanto el mas fragil de los dos.
    discrepan = cuencas[cuencas["clase"] != cuencas["clase_melton"]]
    if not discrepan.empty:
        print(f"\n  {len(discrepan)} cuencas cambian de clase segun el criterio de largo.")
        print("  Son las mas energeticas de la region, descartadas solo por ser largas:")
        cols = ["id_cuenca", "area_km2", "largo_km", "melton"]
        print(discrepan.nlargest(5, "melton")[cols].to_string(
            index=False, float_format=lambda v: f"{v:.2f}"))
        print(f"\n  El umbral de {LARGO_MAX_FLUJO_KM} km viene de un estudio en la Columbia")
        print("  Britanica. M5 va a decir si sirve para Coquimbo o hay que recalibrarlo.")

    en_rango = cuencas["melton_aplicable"].sum()
    print(f"\n  {en_rango} de {len(cuencas)} cuencas estan dentro del rango de "
          f"calibracion del indice (<= {AREA_VALIDA_KM2:.0f} km2)")

    print("\nLas 12 cuencas mas susceptibles:")
    cols = ["ranking", "id_cuenca", "area_km2", "desnivel_m", "largo_km",
            "pend_media_g", "melton", "clase"]
    print(cuencas[cols].head(12).to_string(index=False, float_format=lambda v: f"{v:.2f}"))

    print(f"\n  capa   -> {salida.name}")
    print(f"  figura -> {ruta_png}")


if __name__ == "__main__":
    main()
