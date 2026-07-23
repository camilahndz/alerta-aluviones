"""
M1 - Terreno: de un DEM crudo a la red de quebradas y sus cuencas.

El DEM (modelo de elevacion) es una grilla donde cada pixel guarda la altura del
terreno. A partir de esa sola capa se puede deducir por donde escurre el agua, y
eso es lo que hace este script, en cinco pasos:

    1. Cargar el DEM y revisar que este en un sistema de coordenadas usable.
    2. Acondicionarlo: tapar los hoyos artificiales donde el agua quedaria atrapada.
    3. Direccion de flujo: hacia cual de sus 8 vecinos drena cada pixel.
    4. Acumulacion de flujo: cuantos pixeles drenan hacia cada pixel.
    5. Delinear la red de quebradas y las cuencas que las alimentan.

Uso tipico:

    python src/m1_terreno.py

Con opciones:

    python src/m1_terreno.py --dem data/raw/dem.tif --umbral-km2 0.5

Todo lo que produce va a data/processed/ (rasters y vectores) y outputs/ (una
figura de control para revisar a ojo que el resultado tenga sentido).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pyproj
import rasterio
from rasterio import features
from shapely.geometry import shape
from shapely.ops import unary_union

matplotlib.use("Agg")  # backend sin ventana: solo guardamos PNG, no mostramos nada
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compat_pysheds  # noqa: E402,F401  parche numpy 2, tiene que ir antes de pysheds
from pysheds.grid import Grid  # noqa: E402
from pysheds.sview import Raster, ViewFinder  # noqa: E402

# Raiz del proyecto = carpeta que contiene a src/. Asi el script funciona igual
# corriendolo desde la raiz o desde cualquier otra parte.
RAIZ = Path(__file__).resolve().parent.parent

# UTM 19 Sur: el sistema proyectado que corresponde a la Region de Coquimbo.
# Lo usamos para medir areas y distancias en metros.
CRS_METRICO = "EPSG:32719"

# Mapa de direcciones de flujo D8. Cada numero codifica hacia donde drena el
# pixel, empezando en el Norte y girando en el sentido del reloj:
# N, NE, E, SE, S, SO, O, NO.
DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)


# --------------------------------------------------------------------------
# Paso 1 - Cargar el DEM
# --------------------------------------------------------------------------

def cargar_dem(ruta_dem: Path):
    """Abre el DEM, lo rodea con un anillo sin dato y arma la grilla de pysheds.

    El anillo no es decorativo: es un rodeo obligado a un bug de pysheds.

    Antes de delinear una cuenca, `catchment()` llama internamente a `_pop_rim`,
    que pone en cero todo el borde del raster de direcciones de flujo, y lo hace
    modificando el arreglo en el lugar. La libreria tiene un `_replace_rim` para
    devolverlo a su estado original, pero nunca lo invoca. Eso provoca dos
    problemas:

      - Una desembocadura ubicada en el borde pierde a sus vecinos de aguas
        arriba, que quedan en cero. La cuenca sale de un par de pixeles, o
        directamente revienta con segmentation fault.
      - El dano es acumulativo: cada llamada deja el raster mas roto para la
        siguiente, asi que a partir de la segunda cuenca los resultados ya no
        son confiables.

    Agregando un anillo de celdas sin dato alrededor, ninguna desembocadura real
    queda en el borde del arreglo, y lo unico que pysheds destruye es ese
    relleno artificial, que de todas formas nace sin direccion de flujo valida.

    Tambien avisa si el DEM viene en coordenadas geograficas (grados). No es un
    error fatal, pero conviene saberlo: en grados, un pixel no mide lo mismo en
    el eje X que en el Y, y las areas salen distorsionadas.
    """
    if not ruta_dem.exists():
        sys.exit(
            f"No encuentro el DEM en {ruta_dem}\n"
            "Genera el DEM con: python src/m1_preparar_dem.py\n"
            "O pasa la ruta de otro archivo con --dem."
        )

    with rasterio.open(ruta_dem) as origen:
        elevacion = origen.read(1)
        afin_original = origen.transform
        crs = origen.crs
        sin_dato = origen.nodata if origen.nodata is not None else -9999.0

    print(f"DEM cargado    : {ruta_dem}")
    print(f"  dimensiones  : {elevacion.shape[0]} filas x {elevacion.shape[1]} columnas")
    print(f"  CRS          : {crs.to_string()}")
    validos = elevacion[elevacion != sin_dato]
    print(f"  altura min/max: {validos.min():.0f} / {validos.max():.0f} m")

    if crs.is_geographic:
        print(
            "  AVISO: el DEM esta en grados. Las areas se calculan reproyectando\n"
            f"         a {CRS_METRICO}, pero el analisis queda mas limpio si\n"
            "         reproyectas el DEM a UTM 19S antes de correr esto."
        )

    # Anillo de una celda. El origen de las coordenadas se corre exactamente una
    # celda hacia el noroeste, para que el resto de la grilla siga cayendo sobre
    # el mismo terreno que antes.
    con_anillo = np.pad(elevacion, 1, constant_values=sin_dato)
    afin_anillo = rasterio.Affine(
        afin_original.a, afin_original.b, afin_original.c - afin_original.a,
        afin_original.d, afin_original.e, afin_original.f - afin_original.e,
    )

    mirador = ViewFinder(
        affine=afin_anillo,
        shape=con_anillo.shape,
        crs=pyproj.Proj(crs.to_wkt()),
        nodata=sin_dato,
    )
    dem = Raster(con_anillo, viewfinder=mirador)
    grid = Grid(viewfinder=mirador)

    return grid, dem, crs, afin_original


def area_pixel_m2(grid, crs) -> float:
    """Superficie de un pixel en metros cuadrados.

    Si el DEM esta proyectado (metros), es simplemente ancho x alto. Si esta en
    grados, se aproxima: un grado de latitud son ~111320 m, y un grado de
    longitud son esos mismos 111320 m achicados por el coseno de la latitud.
    """
    afin = grid.affine
    ancho, alto = abs(afin.a), abs(afin.e)

    if not crs.is_geographic:
        return ancho * alto

    lat_media = np.radians(grid.bbox[1] + (grid.bbox[3] - grid.bbox[1]) / 2)
    m_por_grado_lat = 111_320.0
    m_por_grado_lon = m_por_grado_lat * np.cos(lat_media)
    return (ancho * m_por_grado_lon) * (alto * m_por_grado_lat)


# --------------------------------------------------------------------------
# Paso 2 - Acondicionar el DEM
# --------------------------------------------------------------------------

def acondicionar(grid, dem):
    """Deja el DEM hidrologicamente coherente: que el agua siempre pueda salir.

    Un DEM crudo tiene defectos que rompen el escurrimiento:

      - Pozos (pits): un pixel mas bajo que sus 8 vecinos. Casi siempre es ruido
        del sensor, no un hoyo real.
      - Depresiones: hondonadas de varios pixeles sin salida, donde el agua
        quedaria estancada y la red de drenaje se cortaria.
      - Planicies (flats): zonas perfectamente horizontales donde no hay un
        "abajo" definido y el algoritmo no sabe hacia donde mandar el agua.

    Los tres se arreglan rellenando o inclinando levemente el terreno. Es una
    modificacion deliberada del DEM: el objetivo no es que sea mas fiel a la
    realidad, sino que el agua escurra de principio a fin sin quedarse pegada.
    """
    print("\nAcondicionando el DEM...")

    sin_pozos = grid.fill_pits(dem)
    print("  pozos rellenados")

    sin_depresiones = grid.fill_depressions(sin_pozos)
    print("  depresiones rellenadas")

    acondicionado = grid.resolve_flats(sin_depresiones)
    print("  planicies resueltas")

    return acondicionado


# --------------------------------------------------------------------------
# Pasos 3 y 4 - Direccion y acumulacion de flujo
# --------------------------------------------------------------------------

def direccion_y_acumulacion(grid, dem_acondicionado):
    """Calcula hacia donde va el agua (D8) y cuanta llega a cada pixel.

    D8 es la regla mas simple y la mas usada: cada pixel manda toda su agua al
    vecino con la mayor pendiente descendente, sin repartir. El resultado es un
    raster donde cada celda guarda el codigo de direccion (ver DIRMAP).

    La acumulacion cuenta, para cada pixel, cuantos pixeles de mas arriba
    terminan drenando por ahi. Es el numero clave del script: los valores altos
    dibujan exactamente el fondo de las quebradas, porque el agua se concentra
    en los cauces.
    """
    print("\nCalculando escurrimiento...")

    fdir = grid.flowdir(dem_acondicionado, dirmap=DIRMAP)
    print("  direccion de flujo (D8) lista")

    acc = grid.accumulation(fdir, dirmap=DIRMAP)
    print(f"  acumulacion lista (maximo: {int(np.nanmax(acc)):,} pixeles)")

    return fdir, acc


# --------------------------------------------------------------------------
# Paso 5a - Red de quebradas
# --------------------------------------------------------------------------

def extraer_red(grid, fdir, acc, umbral_celdas: int, crs) -> gpd.GeoDataFrame:
    """Convierte los pixeles de alta acumulacion en lineas de quebrada.

    La definicion de "cauce" es un umbral: todo pixel que reciba agua de mas de
    `umbral_celdas` pixeles se considera parte de la red. Bajarlo densifica la
    red hasta incluir surcos que no son quebradas reales; subirlo deja fuera las
    quebradas chicas, que para aluviones son justamente las que importan.
    """
    print(f"\nExtrayendo red de drenaje (umbral: {umbral_celdas:,} pixeles)...")

    mascara_cauces = acc > umbral_celdas
    if not mascara_cauces.any():
        sys.exit(
            "Ningun pixel supera el umbral: la red saldria vacia.\n"
            "Baja --umbral-km2 y vuelve a intentar."
        )

    red = grid.extract_river_network(fdir, mascara_cauces, dirmap=DIRMAP)

    geometrias = [shape(f["geometry"]) for f in red["features"]]
    gdf = gpd.GeoDataFrame({"geometry": geometrias}, crs=crs.to_string())

    # Largo de cada tramo en metros, medido en un CRS proyectado.
    gdf["largo_m"] = gdf.to_crs(CRS_METRICO).length
    gdf = gdf.sort_values("largo_m", ascending=False).reset_index(drop=True)
    gdf.insert(0, "id_tramo", gdf.index + 1)

    print(f"  {len(gdf)} tramos, {gdf['largo_m'].sum() / 1000:.1f} km de red en total")
    return gdf


# --------------------------------------------------------------------------
# Paso 5b - Cuencas
# --------------------------------------------------------------------------

def puntos_de_salida(grid, fdir, acc, umbral_celdas: int, valido, separacion_px: int = 3):
    """Encuentra las desembocaduras: por donde el agua abandona el terreno.

    Una desembocadura es **la ultima celda con terreno antes del vacio**, y esa
    distincion es la clave de esta funcion. El agua de las celdas del borde
    drena hacia las celdas sin dato (el mar, o el anillo que agregamos al
    cargar), asi que ahi la acumulacion tambien se dispara. Pero esas celdas no
    son terreno: no tienen cuenca que delinear, y pedirle a pysheds que lo haga
    termina en segmentation fault.

    Entonces se exige que la celda cumpla tres condiciones a la vez:

      - que acumule bastante agua, o sea que sea un cauce y no una ladera;
      - que sea terreno de verdad, no una celda sin dato;
      - que su vecino de aguas abajo sea vacio, este fuera del arreglo, o que
        pysheds le haya asignado el codigo -2 ("drena fuera de la grilla").

    En la costa de Coquimbo esto corresponde a la boca de cada quebrada, que es
    justo el punto desde el cual queremos delinear la cuenca hacia arriba.

    Ojo con la contracara: si el DEM esta recortado a un rectangulo, el corte
    tambien genera salidas que no son desembocaduras reales, solo cauces
    cortados por el borde. Se filtran despues por area minima.
    """
    # Desplazamiento (fila, columna) que implica cada codigo de direccion.
    desplazamiento = {
        64: (-1, 0), 128: (-1, 1), 1: (0, 1), 2: (1, 1),
        4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1),
    }

    filas, columnas = fdir.shape
    fdir_arr = np.asarray(fdir)
    acc_arr = np.asarray(acc)

    # Todo vectorizado: en un DEM real esto son millones de celdas y recorrerlas
    # una por una en Python tomaria minutos.
    df = np.zeros(fdir_arr.shape, dtype=np.int32)
    dc = np.zeros(fdir_arr.shape, dtype=np.int32)
    for codigo, (paso_f, paso_c) in desplazamiento.items():
        es_codigo = fdir_arr == codigo
        df[es_codigo] = paso_f
        dc[es_codigo] = paso_c

    fila_abajo = np.arange(filas)[:, None] + df
    col_abajo = np.arange(columnas)[None, :] + dc

    sin_direccion = ~np.isin(fdir_arr, DIRMAP)
    fuera_del_borde = (
        (fila_abajo < 0) | (fila_abajo >= filas)
        | (col_abajo < 0) | (col_abajo >= columnas)
    )

    # A donde apunta cada celda, con los indices recortados para no salirse del
    # arreglo al consultar. Las que apuntaban afuera ya quedaron marcadas arriba.
    destino_vacio = ~valido[
        np.clip(fila_abajo, 0, filas - 1),
        np.clip(col_abajo, 0, columnas - 1),
    ]

    es_salida = (
        (acc_arr > umbral_celdas)
        & valido  # la celda misma tiene que ser terreno
        & (sin_direccion | fuera_del_borde | destino_vacio)
    )

    indices = np.argwhere(es_salida)
    if indices.size == 0:
        return []

    # Las mas caudalosas primero: son las cuencas principales.
    orden = np.argsort(-acc_arr[es_salida])
    indices = indices[orden]

    # Dos celdas contiguas en la misma boca darian cuencas casi identicas.
    # Nos quedamos solo con la de mayor acumulacion de cada grupo.
    aceptadas = []
    for fila, col in indices:
        if any(
            abs(fila - f) <= separacion_px and abs(col - c) <= separacion_px
            for f, c, _ in aceptadas
        ):
            continue
        aceptadas.append((int(fila), int(col), float(acc_arr[fila, col])))

    return aceptadas


def vecinos_aguas_arriba(fdir_arr, acc_arr, fila, col):
    """Devuelve los vecinos que drenan hacia (fila, col), el mas caudaloso primero.

    Para cada uno de los 8 vecinos se comprueba si su codigo de direccion apunta
    de vuelta a la celda central. Se usa como plan B cuando la delineacion falla
    justo en la boca de la quebrada.
    """
    # (desplazamiento del vecino, codigo que ese vecino debe tener para drenar al centro)
    vecindad = [
        ((-1, 0), 4), ((-1, 1), 8), ((0, 1), 16), ((1, 1), 32),
        ((1, 0), 64), ((1, -1), 128), ((0, -1), 1), ((-1, -1), 2),
    ]
    filas, columnas = fdir_arr.shape
    encontrados = []

    for (paso_f, paso_c), codigo in vecindad:
        vf, vc = fila + paso_f, col + paso_c
        if 0 <= vf < filas and 0 <= vc < columnas and fdir_arr[vf, vc] == codigo:
            encontrados.append((vf, vc, float(acc_arr[vf, vc])))

    encontrados.sort(key=lambda v: v[2], reverse=True)
    return encontrados


def mascara_cuenca(grid, fdir, fila, col):
    """Cuenca aportante a una celda, como mascara booleana.

    Se pasa el indice (columna, fila) directamente en vez de convertir a
    coordenadas del mundo y dejar que pysheds las vuelva a convertir: ese ida y
    vuelta redondea mal y a veces cae en una celda vecina sin nada aguas arriba,
    devolviendo una cuenca de un solo pixel.
    """
    cuenca = grid.catchment(
        x=int(col), y=int(fila), fdir=fdir, dirmap=DIRMAP,
        xytype="index", routing="d8",
    )
    return np.asarray(cuenca) > 0


def delinear_cuencas(grid, fdir, acc, umbral_celdas, area_min_km2, crs, m2_pixel, valido):
    """Delinea, para cada desembocadura, todo el terreno que drena hacia ella.

    Delinear una cuenca es caminar la direccion de flujo al reves: partir del
    punto de salida y marcar todo pixel cuya agua termine pasando por ahi. Cada
    cuenca resultante es una quebrada completa, y es la unidad sobre la que
    despues se calcula susceptibilidad (M2) y lluvia gatillante (M4).

    Hay una verificacion incorporada: la acumulacion de la celda de salida ya
    dice cuantos pixeles deberian drenar por ahi, asi que sirve de control
    gratis. Si la cuenca sale mucho mas chica que ese numero, se reintenta desde
    la celda inmediatamente aguas arriba, que drena practicamente lo mismo.

    Con el anillo sin dato que agrega cargar_dem(), esto ya no deberia saltar
    nunca: era la forma en que se manifestaba el bug del borde de pysheds. Se
    deja como red de seguridad, y avisa cuando actua. Si lo ves saltar seguido,
    algo anda mal en el DEM y vale la pena mirarlo.
    """
    print("\nDelineando cuencas...")

    salidas = puntos_de_salida(grid, fdir, acc, umbral_celdas, valido)
    print(f"  {len(salidas)} desembocaduras candidatas")

    afin = grid.affine
    fdir_arr = np.asarray(fdir)
    acc_arr = np.asarray(acc)
    registros = []
    reintentos = 0

    for fila, col, acumulacion in salidas:
        mascara = mascara_cuenca(grid, fdir, fila, col)

        # Control: la cuenca deberia tener del orden de `acumulacion` pixeles.
        if mascara.sum() < 0.5 * acumulacion:
            for vf, vc, _ in vecinos_aguas_arriba(fdir_arr, acc_arr, fila, col):
                alternativa = mascara_cuenca(grid, fdir, vf, vc)
                if alternativa.sum() >= 0.5 * acumulacion:
                    mascara, fila, col = alternativa, vf, vc
                    reintentos += 1
                    break

        n_pixeles = int(mascara.sum())
        if n_pixeles == 0:
            continue

        # Recortamos al rectangulo que contiene la cuenca antes de vectorizar:
        # sin esto, cada cuenca obliga a recorrer el raster completo.
        filas_ocupadas, cols_ocupadas = np.where(mascara)
        f0, f1 = filas_ocupadas.min(), filas_ocupadas.max() + 1
        c0, c1 = cols_ocupadas.min(), cols_ocupadas.max() + 1
        recorte = mascara[f0:f1, c0:c1].astype(np.uint8)
        afin_recorte = afin * rasterio.Affine.translation(c0, f0)

        poligonos = [
            shape(geom)
            for geom, valor in features.shapes(
                recorte, mask=recorte.astype(bool), transform=afin_recorte
            )
            if valor == 1
        ]
        if not poligonos:
            continue

        # Union de todas las partes: asi la geometria cubre exactamente la
        # mascara de la que sale `area_km2`, y ambas cifras concuerdan.
        geometria = poligonos[0] if len(poligonos) == 1 else unary_union(poligonos)

        x_salida, y_salida = afin * (col + 0.5, fila + 0.5)
        registros.append({
            "geometry": geometria,
            "salida_x": x_salida,
            "salida_y": y_salida,
            "pixeles": n_pixeles,
            "area_km2": n_pixeles * m2_pixel / 1e6,
        })

    if reintentos:
        print(f"  {reintentos} cuencas delineadas desde una celda aguas arriba de la boca")

    if not registros:
        sys.exit("No se pudo delinear ninguna cuenca. Revisa el umbral y el DEM.")

    gdf = gpd.GeoDataFrame(registros, crs=crs.to_string())

    # Fuera las cuencas insignificantes: suelen ser artefactos del recorte del DEM.
    antes = len(gdf)
    gdf = gdf[gdf["area_km2"] >= area_min_km2].copy()
    if antes != len(gdf):
        print(f"  {antes - len(gdf)} cuencas descartadas por area < {area_min_km2} km2")

    if gdf.empty:
        sys.exit(
            f"Todas las cuencas quedaron bajo {area_min_km2} km2. "
            "Baja --area-min-km2 o revisa el DEM."
        )

    gdf = gdf.sort_values("area_km2", ascending=False).reset_index(drop=True)
    gdf.insert(0, "id_cuenca", gdf.index + 1)

    print(f"  {len(gdf)} cuencas delineadas ({gdf['area_km2'].sum():.1f} km2 en total)")
    print(f"  la mayor: {gdf['area_km2'].iloc[0]:.1f} km2")
    return gdf


# --------------------------------------------------------------------------
# Guardado y figura de control
# --------------------------------------------------------------------------

def guardar_raster(ruta: Path, datos, afin_original, crs, dtype, nodata):
    """Escribe un array como GeoTIFF comprimido, conservando la georreferencia.

    Se le quita el anillo que agregamos al cargar, para que la salida calce
    pixel a pixel con el DEM de entrada.
    """
    recortado = np.asarray(datos)[1:-1, 1:-1]
    with rasterio.open(
        ruta, "w",
        driver="GTiff",
        height=recortado.shape[0],
        width=recortado.shape[1],
        count=1,
        dtype=dtype,
        crs=crs,
        transform=afin_original,
        nodata=nodata,
        compress="deflate",
        tiled=True,
        BIGTIFF="IF_SAFER",
    ) as dst:
        dst.write(recortado.astype(dtype), 1)


def figura_control(dem, acc, red, cuencas, grid, ruta_png: Path):
    """Mapa rapido para revisar a ojo que el resultado tenga sentido.

    Esta es la verificacion que ningun numero reemplaza: si las lineas azules no
    caen en el fondo de los valles, o si los bordes de las cuencas cruzan por la
    mitad de una ladera en vez de seguir las cumbres, algo se rompio en el
    acondicionamiento y no vale la pena seguir a M2.

    Los rasters se dibujan con `extent` en coordenadas del mundo real para que
    los vectores calcen encima sin ninguna conversion.
    """
    xmin, ymin, xmax, ymax = grid.bbox
    extension = (xmin, xmax, ymin, ymax)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 7))

    ax1.imshow(np.asarray(dem), cmap="terrain", extent=extension)
    cuencas.boundary.plot(ax=ax1, color="black", linewidth=0.8)
    red.plot(ax=ax1, color="tab:blue", linewidth=1.2)
    ax1.set_title("Elevacion + cuencas y quebradas delineadas")

    # Escala logaritmica: sin ella, un par de pixeles enormes en la desembocadura
    # aplastan todo el resto y el mapa se ve negro.
    ax2.imshow(np.log1p(np.asarray(acc)), cmap="cubehelix", extent=extension)
    ax2.scatter(cuencas["salida_x"], cuencas["salida_y"],
                c="red", s=28, marker="v", zorder=3, label="desembocaduras")
    ax2.set_title("Acumulacion de flujo (escala log)")
    ax2.legend(loc="lower left", fontsize=8)

    for ax in (ax1, ax2):
        ax.set_xticks([])
        ax.set_yticks([])

    fig.suptitle(
        f"M1 - Terreno | {len(cuencas)} cuencas, {len(red)} tramos, "
        f"{cuencas['area_km2'].sum():.0f} km2",
        fontsize=13,
    )
    fig.tight_layout()
    fig.savefig(ruta_png, dpi=140, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------
# Orquestacion
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="M1 - Delinea quebradas y cuencas desde un DEM.")
    # El DEM de entrada vive en processed/ y no en raw/ porque es un derivado:
    # lo produce m1_preparar_dem.py uniendo y reproyectando los tiles crudos.
    ap.add_argument("--dem", type=Path,
                    default=RAIZ / "data" / "processed" / "dem_utm19s.tif",
                    help="GeoTIFF de elevacion de entrada.")
    ap.add_argument("--salida", type=Path, default=RAIZ / "data" / "processed",
                    help="Carpeta donde escribir los resultados.")
    ap.add_argument("--umbral-km2", type=float, default=0.5,
                    help="Area drenada minima para considerar que hay cauce (km2).")
    ap.add_argument("--area-min-km2", type=float, default=1.0,
                    help="Cuencas mas chicas que esto se descartan.")
    args = ap.parse_args()

    args.salida.mkdir(parents=True, exist_ok=True)
    dir_outputs = RAIZ / "outputs"
    dir_outputs.mkdir(parents=True, exist_ok=True)

    grid, dem, crs, afin_original = cargar_dem(args.dem)

    # El umbral se pide en km2 porque es lo interpretable, pero el algoritmo
    # trabaja contando pixeles. Aca se traduce de uno al otro.
    m2_pixel = area_pixel_m2(grid, crs)
    umbral_celdas = max(1, int(args.umbral_km2 * 1e6 / m2_pixel))
    print(f"  pixel        : {m2_pixel:,.0f} m2 -> umbral = {umbral_celdas:,} pixeles")

    # Que celdas son terreno de verdad. Sirve para no confundir el vacio (el mar,
    # o el anillo que agrega cargar_dem) con una desembocadura.
    valido = np.asarray(dem) != dem.nodata

    dem_acondicionado = acondicionar(grid, dem)
    fdir, acc = direccion_y_acumulacion(grid, dem_acondicionado)
    red = extraer_red(grid, fdir, acc, umbral_celdas, crs)
    cuencas = delinear_cuencas(
        grid, fdir, acc, umbral_celdas, args.area_min_km2, crs, m2_pixel, valido
    )

    print("\nGuardando resultados...")
    guardar_raster(args.salida / "dem_acondicionado.tif", dem_acondicionado, afin_original, crs, "float32", -9999)
    guardar_raster(args.salida / "direccion_flujo.tif", fdir, afin_original, crs, "int16", 0)
    guardar_raster(args.salida / "acumulacion_flujo.tif", acc, afin_original, crs, "float32", -9999)
    red.to_file(args.salida / "red_quebradas.gpkg", layer="red_quebradas", driver="GPKG")
    cuencas.to_file(args.salida / "cuencas.gpkg", layer="cuencas", driver="GPKG")

    ruta_png = dir_outputs / "m1_terreno.png"
    figura_control(dem, acc, red, cuencas, grid, ruta_png)

    print(f"  rasters y vectores -> {args.salida}")
    print(f"  figura de control  -> {ruta_png}")
    print("\nListo. Abre el PNG y revisa que las quebradas sigan los valles.")


if __name__ == "__main__":
    main()
