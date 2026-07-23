"""
M1 (paso final) - Deja solo las cuencas que le pertenecen a la Region de Coquimbo.

Por que este paso existe:

    La hidrologia se corre sobre un area mas grande que la region, con medio
    grado de margen por lado. No es desprolijidad: hay quebradas cuyas cabeceras
    nacen fuera del limite administrativo, y si cortaramos el DEM justo en la
    frontera esas cuencas quedarian mochas y sus areas saldrian mal. El agua no
    respeta los limites politicos.

    Entonces se procesa de mas y recien al final se filtra. Este script hace ese
    filtro.

El criterio: **una cuenca es de Coquimbo si su desembocadura cae dentro de la
region**. O sea, si el agua descarga aca. La cuenca conserva su geometria
completa aunque sus cabeceras esten en Atacama o Valparaiso, porque hidrologica-
mente esa quebrada es una sola y su area drenada es la que es.

Uso:

    python src/m1_recortar_region.py

Lee lo que dejo m1_terreno.py en data/processed/ y escribe ahi mismo las
versiones filtradas, con el sufijo _coquimbo.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent

CRS_METRICO = "EPSG:32719"

# geoBoundaries, division administrativa de Chile. Se apunta a un commit fijo
# (9469f09) y no a la rama principal, para que el resultado sea reproducible:
# si manana actualizan el dato, este script sigue bajando exactamente el mismo.
#
# Se prefirio esta fuente sobre Natural Earth despues de comparar ambas: da
# 40.576 km2 contra los ~40.580 km2 oficiales de la region, con 182.558 vertices
# de detalle. Natural Earth daba 37.407 km2 (8% de error) con solo 373 vertices.
URL_REGIONES = (
    "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/"
    "releaseData/gbOpen/CHL/ADM1/geoBoundaries-CHL-ADM1.geojson"
)
NOMBRE_REGION = "Coquimbo"


def obtener_limite(cache: Path, nombre: str) -> gpd.GeoDataFrame:
    """Baja el limite regional (o lo lee del cache) y lo deja en UTM 19S."""
    if cache.exists():
        print(f"Limite regional  : {cache} (ya estaba)")
        return gpd.read_file(cache).to_crs(CRS_METRICO)

    cache.parent.mkdir(parents=True, exist_ok=True)
    crudo = cache.parent / "geoBoundaries-CHL-ADM1.geojson"

    # Se baja el archivo entero a disco antes de abrirlo. Leerlo directo desde
    # la URL falla de forma intermitente: GDAL lo lee en streaming y si la
    # conexion se corta a la mitad revienta con "Unterminated array".
    if not crudo.exists() or crudo.stat().st_size == 0:
        print("Bajando division administrativa de Chile...")
        temporal = crudo.with_suffix(".geojson.parcial")
        with urllib.request.urlopen(URL_REGIONES, timeout=300) as respuesta:
            temporal.write_bytes(respuesta.read())
        temporal.rename(crudo)
        print(f"  {crudo.stat().st_size / 1e6:.1f} MB -> {crudo}")

    regiones = gpd.read_file(crudo)

    limite = regiones[
        regiones["shapeName"].str.contains(nombre, case=False, na=False)
    ].copy()
    if limite.empty:
        disponibles = ", ".join(sorted(regiones["shapeName"].dropna()))
        sys.exit(f"No encontre la region '{nombre}'.\nDisponibles: {disponibles}")

    limite.to_file(cache, driver="GPKG")
    print(f"  limite de {nombre} guardado en {cache}")

    return limite.to_crs(CRS_METRICO)


def filtrar(cuencas: gpd.GeoDataFrame, red: gpd.GeoDataFrame,
            limite: gpd.GeoDataFrame):
    """Selecciona las cuencas que descargan en la region, y su red asociada."""
    poligono = limite.geometry.union_all()

    # Una cuenca entra si su desembocadura cae dentro de la region. La salida ya
    # viene guardada como par de coordenadas desde m1_terreno.py.
    salidas = gpd.points_from_xy(cuencas["salida_x"], cuencas["salida_y"])
    dentro = gpd.GeoSeries(salidas, crs=CRS_METRICO).within(poligono)

    cuencas_region = cuencas[dentro.values].copy()
    cuencas_region = cuencas_region.sort_values("area_km2", ascending=False)
    cuencas_region = cuencas_region.reset_index(drop=True)

    print(f"\nCuencas: {len(cuencas)} en total -> {len(cuencas_region)} descargan en la region")
    if cuencas_region.empty:
        sys.exit("Ninguna cuenca quedo dentro de la region. Revisa el limite y el CRS.")

    # Cada tramo de quebrada se asigna a la cuenca donde cae su punto medio.
    # Usar el punto medio en vez de recortar la linea es mas rapido y deja los
    # tramos enteros, que es lo que sirve despues para M2 y M3.
    medios = red.geometry.interpolate(0.5, normalized=True)
    red_puntos = gpd.GeoDataFrame(
        {"id_tramo": red["id_tramo"], "largo_m": red["largo_m"]},
        geometry=medios, crs=red.crs,
    )
    asignados = gpd.sjoin(
        red_puntos,
        cuencas_region[["id_cuenca", "geometry"]],
        how="inner", predicate="within",
    )

    # Se vuelve a la geometria de linea original, ya con la cuenca asignada.
    red_region = red.merge(
        asignados[["id_tramo", "id_cuenca"]].drop_duplicates("id_tramo"),
        on="id_tramo", how="inner",
    )

    print(f"Tramos : {len(red)} en total -> {len(red_region)} dentro de esas cuencas")
    return cuencas_region, red_region


def figura(cuencas, red, limite, ruta_png: Path):
    """Mapa de control: las cuencas seleccionadas sobre el limite regional."""
    fig, ax = plt.subplots(figsize=(9, 12))

    limite.boundary.plot(ax=ax, color="crimson", linewidth=1.6, zorder=3,
                         label="limite regional")
    cuencas.plot(ax=ax, column="area_km2", cmap="YlOrBr", edgecolor="black",
                 linewidth=0.3, legend=True, alpha=0.85,
                 legend_kwds={"label": "area de la cuenca (km2)", "shrink": 0.5})
    red.plot(ax=ax, color="tab:blue", linewidth=0.35, alpha=0.7)
    ax.scatter(cuencas["salida_x"], cuencas["salida_y"], c="black", s=9,
               marker="v", zorder=4, label="desembocaduras")

    ax.set_title(
        f"M1 - Cuencas que descargan en la Region de {NOMBRE_REGION}\n"
        f"{len(cuencas)} cuencas · {cuencas['area_km2'].sum():,.0f} km2 · "
        f"{len(red):,} tramos",
        fontsize=12,
    )
    ax.legend(loc="upper right", fontsize=8)
    ax.set_xticks([])
    ax.set_yticks([])

    fig.tight_layout()
    fig.savefig(ruta_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(
        description="Filtra las cuencas de M1 a las que descargan en la region."
    )
    ap.add_argument("--procesados", type=Path, default=RAIZ / "data" / "processed",
                    help="Carpeta con la salida de m1_terreno.py.")
    ap.add_argument("--region", default=NOMBRE_REGION,
                    help="Nombre de la region a conservar.")
    args = ap.parse_args()

    ruta_cuencas = args.procesados / "cuencas.gpkg"
    ruta_red = args.procesados / "red_quebradas.gpkg"
    for ruta in (ruta_cuencas, ruta_red):
        if not ruta.exists():
            sys.exit(f"Falta {ruta}\nCorre antes: python src/m1_terreno.py")

    limite = obtener_limite(
        RAIZ / "data" / "raw" / f"limite_{args.region.lower()}.gpkg", args.region
    )
    print(f"  superficie de la region: {limite.geometry.area.sum() / 1e6:,.0f} km2")

    cuencas = gpd.read_file(ruta_cuencas)
    red = gpd.read_file(ruta_red)

    cuencas_region, red_region = filtrar(cuencas, red, limite)

    salida_cuencas = args.procesados / "cuencas_coquimbo.gpkg"
    salida_red = args.procesados / "red_quebradas_coquimbo.gpkg"
    cuencas_region.to_file(salida_cuencas, layer="cuencas", driver="GPKG")
    red_region.to_file(salida_red, layer="red_quebradas", driver="GPKG")

    dir_outputs = RAIZ / "outputs"
    dir_outputs.mkdir(parents=True, exist_ok=True)
    ruta_png = dir_outputs / "m1_cuencas_coquimbo.png"
    figura(cuencas_region, red_region, limite, ruta_png)

    print(f"\nSuperficie drenada por esas cuencas: {cuencas_region['area_km2'].sum():,.0f} km2")
    print("\nLas 8 cuencas mas grandes:")
    print(cuencas_region[["id_cuenca", "area_km2"]].head(8).to_string(index=False))
    print(f"\n  vectores -> {salida_cuencas.name}, {salida_red.name}")
    print(f"  figura   -> {ruta_png}")


if __name__ == "__main__":
    main()
