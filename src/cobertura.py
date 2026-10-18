"""
Verificacion de cobertura: que el DEM cubra la region antes de calcular nada.

POR QUE ESTE MODULO EXISTE
--------------------------

El 7 de agosto de 2026 el pipeline completo -M1, M2 y las figuras- corrio sobre
un DEM que cubria solo de latitud -29 a -31, o sea al que le faltaba el tercio
sur de la Region de Coquimbo. Ningun script se quejo. La corrida termino bien,
escribio sus capas y dibujo sus mapas, y las cifras resultantes se veian
perfectamente plausibles: 360 cuencas, 16.187 km2 drenados, una clasificacion
por clase con numeros redondos y un ranking ordenado. Solo comparandolas contra
la corrida buena (434 cuencas, 39.487 km2) se hizo evidente que faltaba casi el
60% del territorio.

Hay ademas un efecto de segundo orden peor que el faltante. Las cuencas que el
borde del raster parte por la mitad quedan con el area truncada, y como la razon
de Melton es H/raiz(A), achicar A **infla** el indice. Medido sobre esa misma
corrida: el Melton maximo dio 1,504 contra 1,05 de la corrida completa, y las
cuencas clasificadas como flujo de detritos pasaron de 18 a 38. O sea que el
recorte no solo omite territorio: **fabrica cuencas criticas que no existen**.

Un error que no da error, sino un numero plausible, es el peor tipo de error que
puede tener un modelo. La unica defensa es una comprobacion explicita antes de
calcular, y por eso esta funcion aborta en vez de advertir.

POR QUE ESTA EN UN MODULO APARTE Y NO EN CADA SCRIPT
----------------------------------------------------

La primera version de la comprobacion vivia dentro de `m1_preparar_dem.py`, que
es el script que arma el DEM. Ahi solo protege el momento de la creacion. Pero
`m1_terreno.py`, `m1_recortar_region.py` y `m2_susceptibilidad.py` no arman
nada: leen `data/processed/dem_utm19s.tif` tal como este en disco. Un DEM
parcial que quedo ahi de una corrida anterior, de una prueba con `--bbox` chico
o de una descarga interrumpida entra a los tres sin que nadie lo mire.

Dicho de otro modo: la comprobacion protegia la escritura y el problema estaba
en la lectura. Aca vive una sola copia, y la llaman los cuatro scripts que leen
un DEM, cada uno al empezar y antes de gastar un minuto de calculo.

SIN LIMITE REGIONAL NO HAY COMPROBACION, Y ESO ABORTA
----------------------------------------------------

La primera version avisaba y seguia si faltaba `data/raw/limite_coquimbo.gpkg`.
En una maquina limpia eso pasaba siempre: el limite lo creaba
`m1_recortar_region.py`, el tercer paso, y los dos primeros -que son los que
arman y leen el DEM- corrian sin verificar nada. La red de seguridad estaba
apagada justo en la corrida donde mas falta hace (auditoria del 17-10-2026, A4).

Ahora `obtener_limite` vive aca, `m1_preparar_dem.py` lo llama antes de bajar
el primer tile, y `verificar_cobertura` aborta si el limite no esta, salvo que
quien llama pida explicitamente `permitir_sin_limite=True`.

LIMITE CONOCIDO DE LA COMPROBACION
----------------------------------

Se compara el poligono de la region contra el **rectangulo** de coordenadas del
raster, no contra sus pixeles con dato. Un DEM cuyo rectangulo cubra la region
pero venga vacio por dentro pasaria la prueba. Se acepta porque el caso real que
motivo esto -un recorte geografico- si se detecta, y porque leer 145 millones de
pixeles solo para verificar seria mas caro que el calculo que protege.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import geopandas as gpd
import rasterio
from shapely.geometry import box

# Cuanto de la region tiene que quedar dentro del raster para dejarlo pasar.
# 0,99 y no 0,95: la diferencia entre ambos son ~2.000 km2, que en esta region
# es mas que la superficie de varias de las cuencas que interesan.
COBERTURA_MINIMA = 0.99

RAIZ = Path(__file__).resolve().parent.parent
LIMITE_POR_DEFECTO = RAIZ / "data" / "raw" / "limite_coquimbo.gpkg"
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


def obtener_limite(cache: Path = LIMITE_POR_DEFECTO,
                   nombre: str = NOMBRE_REGION) -> gpd.GeoDataFrame:
    """Baja el limite regional (o lo lee del cache) y lo deja en UTM 19S.

    Vivia en m1_recortar_region.py, el tercer paso de M1. Esta aca para que
    m1_preparar_dem.py, el primero, lo obtenga antes de verificar nada.
    """
    cache = Path(cache)
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


def fraccion_cubierta(ruta_raster: Path, ruta_limite: Path) -> float:
    """Que fraccion del poligono regional cae dentro del rectangulo del raster.

    La cuenta se hace en el CRS del raster y no en uno fijo: asi funciona igual
    con el mosaico en grados que deja `m1_preparar_dem.py` y con el DEM en UTM
    19S que consumen los demas scripts, sin tener que saber cual le toco.
    """
    with rasterio.open(ruta_raster) as src:
        caja = box(*src.bounds)
        crs_raster = src.crs

    region = gpd.read_file(ruta_limite).to_crs(crs_raster).geometry.union_all()
    return region.intersection(caja).area / region.area


def verificar_cobertura(ruta_raster: Path,
                        ruta_limite: Path = LIMITE_POR_DEFECTO,
                        minimo: float = COBERTURA_MINIMA,
                        permitir_parcial: bool = False,
                        etiqueta: str = "DEM",
                        permitir_sin_limite: bool = False) -> float:
    """Aborta si el raster no cubre la region. Devuelve la fraccion cubierta.

    `permitir_parcial` existe para el caso en que alguien quiera a proposito una
    corrida provisoria sobre territorio incompleto. No es un atajo: la salida
    queda marcada como PROVISORIA en consola para que ninguna cifra que salga de
    ahi termine citada por accidente.

    Si falta el archivo del limite, aborta. Hasta octubre de 2026 avisaba y
    devolvia NaN, y en una maquina limpia eso dejaba sin verificar justo los dos
    primeros pasos de M1 (ver la cabecera). `permitir_sin_limite=True` es la
    salida explicita para quien sepa lo que hace; la corrida queda marcada SIN
    VERIFICAR en consola.
    """
    ruta_raster = Path(ruta_raster)
    ruta_limite = Path(ruta_limite)

    if not ruta_raster.exists():
        sys.exit(
            f"No encuentro el {etiqueta} en {ruta_raster}\n"
            "Genera el DEM con: python src/m1_preparar_dem.py"
        )

    if not ruta_limite.exists():
        if permitir_sin_limite:
            print("=" * 70)
            print(f"COBERTURA SIN VERIFICAR: falta {ruta_limite.name}. Las cifras "
                  "que siguen\npueden venir de un DEM parcial sin que nada lo diga.")
            print("=" * 70)
            return float("nan")
        sys.exit(
            f"Falta el limite regional {ruta_limite}, y sin el no se puede verificar\n"
            f"que el {etiqueta} cubra la region. Lo baja el primer paso de M1:\n"
            "    python src/m1_preparar_dem.py"
        )

    cubierto = fraccion_cubierta(ruta_raster, ruta_limite)
    print(f"Cobertura del {etiqueta} sobre la region: {100 * cubierto:.1f}%")

    if cubierto >= minimo:
        return cubierto

    mensaje = (
        f"\nEl {etiqueta} cubre solo el {100 * cubierto:.1f}% de la region "
        f"(minimo exigido: {100 * minimo:.0f}%).\n"
        "Las cifras que saldrian de aca son parciales y no lo pareceria en la\n"
        "salida. Peor: las cuencas cortadas por el borde del raster quedan con\n"
        "el area truncada, lo que infla artificialmente su razon de Melton y las\n"
        "hace aparecer como criticas sin serlo.\n\n"
        "Para arreglarlo, regenera el DEM completo y vuelve a correr M1 y M2:\n"
        "    python src/m1_preparar_dem.py\n"
        "    python src/m1_terreno.py --umbral-km2 0.15 --area-min-km2 0.4\n"
        "    python src/m1_recortar_region.py\n"
        "    python src/m2_susceptibilidad.py"
    )

    if permitir_parcial:
        print("=" * 70)
        print("CORRIDA PARCIAL AUTORIZADA. Las cifras que siguen son PROVISORIAS.")
        print(mensaje)
        print("=" * 70)
        return cubierto

    sys.exit(mensaje + "\n\nSi de verdad quieres una corrida parcial y provisoria,\n"
                       "el unico script que lo permite es M3, con:\n"
                       "    --permitir-cobertura-parcial")
