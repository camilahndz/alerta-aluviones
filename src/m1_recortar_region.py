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
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
# obtener_limite vive en cobertura.py desde octubre de 2026, para que el primer
# paso de M1 lo tenga antes de verificar el DEM. Ver la cabecera de cobertura.
from cobertura import (COBERTURA_MINIMA, NOMBRE_REGION, URL_REGIONES,  # noqa: E402, F401
                       obtener_limite, verificar_cobertura)

RAIZ = Path(__file__).resolve().parent.parent

CRS_METRICO = "EPSG:32719"


def filtrar(cuencas: gpd.GeoDataFrame, red: gpd.GeoDataFrame,
            limite: gpd.GeoDataFrame, tolerancia_m: float):
    """Selecciona las cuencas que descargan en la region, y su red asociada.

    La tolerancia existe porque las desembocaduras estan sobre la costa, y ahi
    dos datos independientes no calzan al metro: la linea de costa que deduce el
    DEM (donde la elevacion deja de ser positiva) y la del poligono
    administrativo se separan por decenas de metros. Sin tolerancia, quebradas
    costeras que claramente son de la region quedan fuera por esa diferencia.

    Medido sobre una franja de prueba, la separacion entre ambos grupos es
    nitida: 68 cuencas caian a menos de 100 m del limite (desajuste de costas,
    hay que incluirlas) y 45 a mas de 2 km (esas si son de otra region). Los
    500 m por defecto quedan comodamente en medio de esos dos grupos.
    """
    poligono = limite.geometry.union_all()

    # Una cuenca entra si su desembocadura cae dentro de la region. La salida ya
    # viene guardada como par de coordenadas desde m1_terreno.py.
    salidas = gpd.points_from_xy(cuencas["salida_x"], cuencas["salida_y"])
    puntos = gpd.GeoSeries(salidas, crs=CRS_METRICO)
    dentro = puntos.distance(poligono) <= tolerancia_m

    cuencas_region = cuencas[dentro.values].copy()
    cuencas_region = cuencas_region.sort_values("area_km2", ascending=False)
    cuencas_region = cuencas_region.reset_index(drop=True)

    print(f"\nCuencas: {len(cuencas)} en total -> {len(cuencas_region)} descargan en la region")
    if cuencas_region.empty:
        sys.exit("Ninguna cuenca quedo dentro de la region. Revisa el limite y el CRS.")

    # Cuanto de la region queda cubierto. Es normal que no sea el 100%: hay
    # sectores de Coquimbo que drenan hacia Atacama, hacia Valparaiso o hacia
    # Argentina, y esas cuencas pertenecen a la region vecina, no a esta.
    cubierto = cuencas_region.geometry.union_all().intersection(poligono).area
    print(f"  cubren el {100 * cubierto / poligono.area:.0f}% de la superficie regional")

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
    ap.add_argument("--tolerancia-m", type=float, default=500.0,
                    help="Margen para el desajuste entre la costa del DEM y la "
                         "del poligono administrativo.")
    args = ap.parse_args()

    ruta_cuencas = args.procesados / "cuencas.gpkg"
    ruta_red = args.procesados / "red_quebradas.gpkg"
    for ruta in (ruta_cuencas, ruta_red):
        if not ruta.exists():
            sys.exit(f"Falta {ruta}\nCorre antes: python src/m1_terreno.py")

    # Primero el limite y despues la verificacion, que lo necesita. Hasta
    # octubre de 2026 el orden era el inverso y, en una maquina limpia, la
    # verificacion corria sin limite y no verificaba nada. Ver src/cobertura.py.
    ruta_limite = RAIZ / "data" / "raw" / f"limite_{args.region.lower()}.gpkg"
    limite = obtener_limite(ruta_limite, args.region)
    print(f"  superficie de la region: {limite.geometry.area.sum() / 1e6:,.0f} km2")

    # Este script no lee el DEM, pero las cuencas que filtra salieron de el. Se
    # verifica igual: si el DEM en disco es parcial, las cuencas tambien lo son
    # y filtrarlas por region solo esconderia el problema mas abajo.
    verificar_cobertura(args.procesados / "dem_utm19s.tif", ruta_limite,
                        COBERTURA_MINIMA)

    cuencas = gpd.read_file(ruta_cuencas)
    red = gpd.read_file(ruta_red)

    cuencas_region, red_region = filtrar(cuencas, red, limite, args.tolerancia_m)

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
