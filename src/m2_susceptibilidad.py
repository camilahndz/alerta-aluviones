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
import rasterio
from rasterio import features
from scipy import ndimage
from shapely.geometry import Point

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent

# --- Umbrales de Wilford et al. (2004) ---------------------------------------
# Se dejan como constantes con nombre para que se vea de donde sale cada corte y
# para poder moverlos de un solo lugar si M5 sugiere recalibrarlos.
MELTON_CRECIDA = 0.30      # bajo esto: inundacion de agua
MELTON_FLUJO = 0.60        # sobre esto: potencial de flujo de detritos
LARGO_MAX_FLUJO_KM = 2.7   # cuencas mas largas disipan la energia en el camino

# Melton se calibro en cuencas chicas. Sobre esta area el indice pierde sentido.
AREA_VALIDA_KM2 = 10.0

CLASES = ["inundacion", "crecida_detritos", "flujo_detritos"]


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

        etiquetas = features.rasterize(
            ((geom, int(i)) for geom, i in zip(cuencas.geometry, cuencas["id_cuenca"])),
            out_shape=(src.height, src.width),
            transform=afin,
            fill=0,
            dtype="int32",
        )

    valido = elevacion != sin_dato
    etiquetas[~valido] = 0
    elevacion[~valido] = np.nan

    ids = cuencas["id_cuenca"].astype(int).tolist()

    h_min = np.array(ndimage.minimum(elevacion, etiquetas, ids), dtype="float64")
    h_max = np.array(ndimage.maximum(elevacion, etiquetas, ids), dtype="float64")
    h_media = np.array(ndimage.mean(elevacion, etiquetas, ids), dtype="float64")

    # Pendiente: cuanto sube o baja el terreno por cada metro que uno avanza.
    # np.gradient da la variacion en cada eje; el arcotangente de su magnitud
    # combinada es la inclinacion real de la ladera, en grados.
    print("  calculando pendientes...")
    dz_dy, dz_dx = np.gradient(elevacion, resolucion, resolucion)
    pendiente = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))

    # En el borde del terreno el gradiente toca celdas sin dato y sale NaN.
    # Esas celdas se sacan del promedio en vez de contaminarlo.
    etiquetas_pend = np.where(np.isfinite(pendiente), etiquetas, 0)
    pend_media = np.array(ndimage.mean(pendiente, etiquetas_pend, ids), dtype="float64")

    # El percentil 90 de la pendiente: que tan empinado es el sector mas
    # inclinado de la cuenca, ignorando el 10% mas extremo para no quedarse con
    # un pixel raro. Va por labeled_comprehension y no por un ciclo, porque un
    # ciclo tendria que recorrer el raster completo una vez por cuenca: con 434
    # cuencas sobre 160 millones de pixeles eso son horas de calculo.
    pend_p90 = np.array(
        ndimage.labeled_comprehension(
            pendiente, etiquetas_pend, ids,
            lambda valores: np.percentile(valores, 90), "float64", np.nan,
        ),
        dtype="float64",
    )

    return {
        "h_min_m": h_min,
        "h_max_m": h_max,
        "h_media_m": h_media,
        "pend_media_g": pend_media,
        "pend_p90_g": pend_p90,
    }


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


def clasificar(melton: np.ndarray, largo_km: np.ndarray) -> np.ndarray:
    """Aplica la clasificacion de Wilford: que tipo de evento puede generar."""
    clase = np.full(len(melton), "inundacion", dtype=object)
    clase[melton >= MELTON_CRECIDA] = "crecida_detritos"

    # Solo las cuencas empinadas Y cortas pueden mandar el material hasta la
    # salida sin depositarlo en el camino.
    capaz = (melton >= MELTON_FLUJO) & (largo_km <= LARGO_MAX_FLUJO_KM)
    clase[capaz] = "flujo_detritos"
    return clase


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
    largo_red = red.groupby("id_cuenca")["largo_m"].sum() / 1000.0
    cuencas["dens_drenaje_km_km2"] = (
        cuencas["id_cuenca"].map(largo_red).fillna(0) / cuencas["area_km2"]
    )

    # Razon de elongacion (Schumm): 1 = cuenca redonda, cerca de 0 = alargada.
    # Las redondas concentran el agua mas rapido en un solo punto.
    cuencas["elongacion"] = (
        2 * np.sqrt(cuencas["area_km2"] / np.pi) / cuencas["largo_km"]
    )

    cuencas["clase"] = clasificar(
        cuencas["melton"].to_numpy(), cuencas["largo_km"].to_numpy()
    )
    cuencas["melton_aplicable"] = cuencas["area_km2"] <= AREA_VALIDA_KM2

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
                c=[colores[c] for c in cuencas["clase"]], s=18,
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
    args = ap.parse_args()

    ruta_cuencas = args.procesados / "cuencas_coquimbo.gpkg"
    ruta_red = args.procesados / "red_quebradas_coquimbo.gpkg"
    ruta_dem = args.procesados / "dem_utm19s.tif"
    for ruta in (ruta_cuencas, ruta_red, ruta_dem):
        if not ruta.exists():
            sys.exit(f"Falta {ruta}\nCorre antes los scripts de M1.")

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

    print("\nClasificacion (Wilford et al., 2004):")
    for clase in reversed(CLASES):
        sel = cuencas[cuencas["clase"] == clase]
        print(f"  {clase:<18} {len(sel):>4} cuencas   {sel['area_km2'].sum():>9,.0f} km2")

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
