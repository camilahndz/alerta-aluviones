"""
M1 - Deja el limite de la Region de Coquimbo listo para el resto del pipeline.

POR QUE ESTE SCRIPT EXISTE

    `data/raw/limite_coquimbo.gpkg` es el poligono contra el que `cobertura.py`
    comprueba que el DEM cubra la region, o sea la salvaguarda que impide que
    una corrida parcial pase por completa. Los cinco scripts que leen un DEM
    dependen de el.

    Hasta septiembre de 2026 ese archivo simplemente estaba en disco. En el log
    de la corrida del 23 de agosto aparece como "(ya estaba)", sin fuente
    anotada en ninguna parte. Cuando se perdio `data/raw/` no quedo forma de
    regenerarlo, y la regla del repositorio -si se borra lo derivado, se tiene
    que poder reconstruir- fallaba justo en la pieza que vigila a las demas.

    Este script cierra ese hueco: deja escrito de donde sale el poligono y lo
    reconstruye con un comando.

FUENTE

    Biblioteca del Congreso Nacional de Chile (BCN), Mapoteca, mapas
    vectoriales: "Division regional: poligonos de las regiones de Chile".

        https://www.bcn.cl/siit/mapas_vectoriales

    Se elige la BCN y no OpenStreetMap porque es la division politico
    administrativa oficial y porque tiene una version fechada: el material
    corresponde a ediciones de 2014, 2017 y diciembre de 2018 segun la propia
    pagina. OSM habria servido y no habria necesitado descarga manual, pero su
    trazado cambia sin aviso y eso es exactamente lo que M3 ya rechazo cuando
    abandono Overpass.

    Condiciones de uso: libre, citando a la BCN como fuente.

LIMITE CONOCIDO

    El shapefile de la BCN trae el territorio continental. Para lo que aqui se
    usa -comprobar que un DEM cubra la region- eso basta y sobra: las islas no
    tienen quebradas que entren al modelo. Si alguna vez el alcance cambia, hay
    que volver a mirar esto.

Uso:

    1. Bajar el zip de la BCN y dejarlo en data/raw/ sin descomprimir:
       https://www.bcn.cl/obtienearchivo?id=repositorio/10221/10398/2/Regiones.zip

    2. python src/m1_limite_region.py

Escribe data/raw/limite_coquimbo.gpkg y no toca nada mas.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

import geopandas as gpd

RAIZ = Path(__file__).resolve().parent.parent

ZIP_POR_DEFECTO = RAIZ / "data" / "raw" / "Regiones.zip"
SALIDA = RAIZ / "data" / "raw" / "limite_coquimbo.gpkg"

FUENTE = ("Biblioteca del Congreso Nacional de Chile, Mapoteca, "
          "division regional (https://www.bcn.cl/siit/mapas_vectoriales)")

# Como aparece Coquimbo en la tabla de la BCN. Se buscan varias formas porque
# el nombre del campo y la grafia cambian entre ediciones del shapefile, y
# fallar por una tilde seria una perdida de tiempo evitable.
PATRON_COQUIMBO = r"coquimbo"

# El shapefile viene en coordenadas geograficas. Se deja asi a proposito:
# `cobertura.py` reproyecta al CRS del raster que le toque, de modo que el mismo
# archivo sirve para el mosaico en grados y para el DEM en UTM 19S.
CRS_SALIDA = "EPSG:4326"


def _buscar_shapefile(ruta_zip: Path) -> str:
    """Devuelve la ruta interna del .shp dentro del zip de la BCN."""
    with zipfile.ZipFile(ruta_zip) as z:
        shp = [n for n in z.namelist() if n.lower().endswith(".shp")]
    if not shp:
        sys.exit(f"{ruta_zip.name} no contiene ningun .shp. "
                 "Revisa que sea el zip de division regional de la BCN.")
    if len(shp) > 1:
        print(f"AVISO: el zip trae {len(shp)} shapefiles, se usa {shp[0]}")
    return shp[0]


def _columna_de_nombre(gdf: gpd.GeoDataFrame) -> str:
    """Encuentra la columna que trae el nombre de la region.

    Se busca por contenido y no por nombre de campo: entre ediciones la columna
    se ha llamado `Region`, `NOM_REG` y `nom_reg`, y amarrarse a una sola haria
    que el script se caiga con la proxima version del archivo.
    """
    for col in gdf.columns:
        if col == "geometry":
            continue
        if gdf[col].astype(str).str.contains(PATRON_COQUIMBO, case=False,
                                             na=False).any():
            return col
    sys.exit("Ninguna columna del shapefile menciona Coquimbo. "
             "Puede que sea el archivo de comunas o de provincias.")


def main():
    ap = argparse.ArgumentParser(
        description="Extrae el poligono de la Region de Coquimbo del zip de la BCN.")
    ap.add_argument("--zip", type=Path, default=ZIP_POR_DEFECTO,
                    help="Zip de division regional bajado de la BCN.")
    ap.add_argument("--salida", type=Path, default=SALIDA)
    args = ap.parse_args()

    if not args.zip.exists():
        sys.exit(
            f"No encuentro {args.zip}\n\n"
            "Bajalo de la BCN y dejalo ahi sin descomprimir:\n"
            "  https://www.bcn.cl/obtienearchivo"
            "?id=repositorio/10221/10398/2/Regiones.zip\n"
            "(o desde https://www.bcn.cl/siit/mapas_vectoriales, "
            "'Division regional')"
        )

    interno = _buscar_shapefile(args.zip)
    print(f"Leyendo {interno} desde {args.zip.name}...")
    regiones = gpd.read_file(f"zip://{args.zip}!{interno}")
    print(f"  {len(regiones)} regiones, CRS {regiones.crs}")

    columna = _columna_de_nombre(regiones)
    coquimbo = regiones[regiones[columna].astype(str).str.contains(
        PATRON_COQUIMBO, case=False, na=False)]
    if coquimbo.empty:
        sys.exit("No quedo ninguna fila al filtrar por Coquimbo.")

    print(f"  columna de nombre: '{columna}' -> {len(coquimbo)} fila(s)")

    coquimbo = coquimbo.to_crs(CRS_SALIDA)
    disuelto = gpd.GeoDataFrame(
        {"region": ["Coquimbo"], "fuente": [FUENTE]},
        geometry=[coquimbo.geometry.union_all()],
        crs=CRS_SALIDA)

    oeste, sur, este, norte = disuelto.total_bounds
    print(f"\nBbox del poligono: {oeste:.2f}, {sur:.2f}, {este:.2f}, {norte:.2f}")

    # El bbox declarado en m1_preparar_dem.py: lat -32,22 a -29,07 y lon -71,71
    # a -69,84. Si el poligono que acaba de salir no se parece a eso, no es la
    # Region de Coquimbo y mas vale saberlo ahora que despues de procesar 160
    # millones de pixeles.
    esperado = (-71.71, -32.22, -69.84, -29.07)
    if (abs(oeste - esperado[0]) > 0.5 or abs(sur - esperado[1]) > 0.5
            or abs(este - esperado[2]) > 0.5 or abs(norte - esperado[3]) > 0.5):
        sys.exit(
            f"El poligono no cuadra con la Region de Coquimbo.\n"
            f"  esperado aprox: {esperado}\n"
            f"  obtenido      : ({oeste:.2f}, {sur:.2f}, {este:.2f}, {norte:.2f})\n"
            "No se escribe nada."
        )

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    disuelto.to_file(args.salida, layer="limite_coquimbo", driver="GPKG")
    print(f"\nListo: {args.salida}")
    print(f"  area: {disuelto.to_crs('EPSG:32719').area.iloc[0] / 1e6:,.0f} km2")
    print("\nSiguiente paso:")
    print("  python src/m1_terreno.py --umbral-km2 0.15 --area-min-km2 0.4")


if __name__ == "__main__":
    main()
