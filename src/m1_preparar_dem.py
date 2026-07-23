"""
M1 (paso previo) - Baja el DEM Copernicus GLO-30 y lo deja listo para el analisis.

Por que Copernicus GLO-30 y no el ALOS PALSAR "12,5 m" que dice el README:

    Los productos ALOS PALSAR RTC de alta resolucion se generan a partir de
    NED13, que solo cubre Estados Unidos, o de SRTM 30 m. Para Chile aplica el
    segundo caso, y la documentacion de ASF lo dice explicitamente: esos
    productos son "up sampled from the 30-m version to 12.5 m". O sea, los
    pixeles miden 12,5 m pero el detalle real sigue siendo de 30 m. Interpolar
    no agrega informacion: da archivos seis veces mas pesados con la misma
    cantidad de terreno adentro.

    Copernicus GLO-30 son 30 m reales, derivados de TanDEM-X, con cobertura
    global uniforme y sin registro. A igual resolucion efectiva, es mejor dato.

Este script hace tres cosas:

    1. Descarga los tiles de 1x1 grado que cubren la zona pedida.
    2. Los une en un solo raster continuo.
    3. Lo reproyecta a UTM 19S, que es donde un metro mide un metro.

Uso:

    python src/m1_preparar_dem.py

Los tiles crudos quedan en data/raw/ (tal como los entrega Copernicus, sin
tocar) y el DEM armado en data/processed/. Asi se respeta la regla del repo:
todo lo de processed/ se puede reconstruir desde raw/.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.warp import Resampling, calculate_default_transform, reproject

RAIZ = Path(__file__).resolve().parent.parent

BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"
CRS_METRICO = "EPSG:32719"  # UTM 19 Sur

# Region de Coquimbo con medio grado de margen por lado.
#
# El margen no es capricho: hay quebradas cuyas cabeceras nacen fuera del limite
# regional. Si recortaramos al poligono administrativo, esas cuencas quedarian
# cortadas y sus areas saldrian mal. Se procesa de mas y se filtra al final.
BBOX_COQUIMBO = (-72.5, -33.0, -69.5, -28.5)  # oeste, sur, este, norte


def nombre_tile(lat_sur: int, lon_oeste: int) -> str:
    """Arma el nombre de un tile a partir de su esquina suroeste.

    Copernicus nombra cada tile por esa esquina. Verificado contra el archivo
    real: Copernicus_DSM_COG_10_S30_00_W071_00_DEM cubre lat -30 a -29 y
    lon -71 a -70.
    """
    ns = "S" if lat_sur < 0 else "N"
    ew = "W" if lon_oeste < 0 else "E"
    return (
        f"Copernicus_DSM_COG_10_"
        f"{ns}{abs(lat_sur):02d}_00_{ew}{abs(lon_oeste):03d}_00_DEM"
    )


def tiles_de_bbox(bbox) -> list[str]:
    """Lista los tiles de 1x1 grado necesarios para cubrir un bounding box."""
    oeste, sur, este, norte = bbox
    lats = range(int(np.floor(sur)), int(np.ceil(norte)))
    lons = range(int(np.floor(oeste)), int(np.ceil(este)))
    return [nombre_tile(la, lo) for la in lats for lo in lons]


def descargar_tile(nombre: str, destino: Path) -> tuple[str, str]:
    """Baja un tile. Devuelve (nombre, estado) para poder informar al final.

    Los tiles que caen enteros en el oceano no existen en el bucket y responden
    404. No es un error: simplemente ahi no hay terreno que bajar.
    """
    archivo = destino / f"{nombre}.tif"
    if archivo.exists() and archivo.stat().st_size > 0:
        return nombre, "ya estaba"

    url = f"{BUCKET}/{nombre}/{nombre}.tif"
    try:
        # Se baja a un archivo temporal y recien al final se renombra, para que
        # una descarga interrumpida no deje un .tif corrupto que el script
        # despues de por bueno.
        temporal = archivo.with_suffix(".tif.parcial")
        with urllib.request.urlopen(url, timeout=120) as respuesta:
            temporal.write_bytes(respuesta.read())
        temporal.rename(archivo)
        return nombre, "descargado"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return nombre, "sin datos (mar)"
        return nombre, f"error HTTP {e.code}"
    except Exception as e:  # red caida, timeout, disco lleno
        return nombre, f"error: {type(e).__name__}"


def descargar(bbox, carpeta: Path, hilos: int) -> list[Path]:
    """Descarga en paralelo todos los tiles del bbox."""
    carpeta.mkdir(parents=True, exist_ok=True)
    nombres = tiles_de_bbox(bbox)
    print(f"Tiles necesarios para cubrir el area: {len(nombres)}")

    resultados = {}
    with ThreadPoolExecutor(max_workers=hilos) as pool:
        futuros = {pool.submit(descargar_tile, n, carpeta): n for n in nombres}
        for i, futuro in enumerate(as_completed(futuros), 1):
            nombre, estado = futuro.result()
            resultados[nombre] = estado
            print(f"  [{i:>3}/{len(nombres)}] {nombre[-18:]:>18}  {estado}")

    fallidos = {n: e for n, e in resultados.items() if e.startswith("error")}
    if fallidos:
        print(f"\n{len(fallidos)} tiles fallaron:")
        for n, e in fallidos.items():
            print(f"  {n}: {e}")
        sys.exit("Vuelve a correr el script: los que ya bajaron no se repiten.")

    disponibles = sorted(carpeta.glob("Copernicus_DSM_*.tif"))
    sin_datos = sum(1 for e in resultados.values() if "mar" in e)
    if sin_datos:
        print(f"  ({sin_datos} tiles son puro oceano y no existen, es normal)")

    print(f"Tiles con terreno: {len(disponibles)}")
    return disponibles


def unir(tiles: list[Path], salida: Path):
    """Une los tiles en un solo raster continuo.

    Sobre el oceano abierto no existen tiles de Copernicus (dan 404), asi que el
    mosaico queda con huecos donde el mar no toca tierra. Hay que rellenarlos con
    "sin dato" (-9999) y NO con 0, que es el valor por defecto de merge. Si se
    quedaran en 0, el paso siguiente los confundiria con terreno a nivel del mar
    e interpolaria alturas falsas en el borde, generando quebradas fantasma.
    """
    print("\nUniendo tiles...")
    fuentes = [rasterio.open(t) for t in tiles]
    try:
        merge(
            fuentes, dst_path=salida, nodata=-9999,
            dst_kwds={"compress": "deflate", "tiled": True},
        )
    finally:
        for f in fuentes:
            f.close()

    with rasterio.open(salida) as s:
        print(f"  mosaico: {s.width} x {s.height} px en {s.crs}")
    return salida


def reproyectar(entrada: Path, salida: Path, resolucion: float, enmascarar_mar: bool):
    """Pasa el mosaico a UTM 19S y opcionalmente saca el oceano.

    Copernicus entrega el DEM en grados (EPSG:4326). En grados los pixeles no
    son cuadrados y las areas salen deformadas, asi que se reproyecta a UTM 19S,
    donde las coordenadas estan en metros.

    Sobre el mar: el DEM trae el oceano costero como una superficie plana en 0 m.
    Una planicie perfecta de ese tamano le da trabajo inutil al acondicionamiento
    hidrologico y ademas confunde el borde de las cuencas. Marcandola como
    "sin dato", cada quebrada termina limpiamente en la linea de costa, que es
    justo donde queremos su desembocadura.

    Clave: se le pasa `src_nodata=-9999` a reproject. Sin eso, la interpolacion
    no distingue los huecos (mar abierto sin tile) del terreno y mezcla ambos,
    inventando alturas intermedias en el borde de los datos. Esas alturas falsas
    son positivas, asi que la mascara de mar (que borra lo que vale <= 0) no las
    atrapa, y terminan como quebradas fantasma sobre el oceano.
    """
    print("\nReproyectando a UTM 19S...")

    with rasterio.open(entrada) as origen:
        transformacion, ancho, alto = calculate_default_transform(
            origen.crs, CRS_METRICO, origen.width, origen.height,
            *origen.bounds, resolution=resolucion,
        )
        perfil = origen.profile.copy()
        perfil.update(
            crs=CRS_METRICO, transform=transformacion, width=ancho, height=alto,
            dtype="float32", nodata=-9999, compress="deflate", tiled=True,
            BIGTIFF="IF_SAFER",
        )

        print(f"  destino: {ancho} x {alto} px a {resolucion:.0f} m")

        with rasterio.open(salida, "w", **perfil) as destino:
            datos = np.full((alto, ancho), -9999, dtype="float32")
            reproject(
                source=rasterio.band(origen, 1),
                destination=datos,
                src_transform=origen.transform,
                src_crs=origen.crs,
                src_nodata=-9999,   # los huecos de mar abierto no se interpolan
                dst_transform=transformacion,
                dst_crs=CRS_METRICO,
                dst_nodata=-9999,
                resampling=Resampling.bilinear,
                num_threads=0,  # 0 = usa todos los nucleos disponibles
            )

            if enmascarar_mar:
                mar = (datos <= 0) & (datos != -9999)
                datos[mar] = -9999
                print(f"  {mar.sum():,} pixeles de mar marcados como sin dato")

            destino.write(datos, 1)

    return salida


def main():
    ap = argparse.ArgumentParser(
        description="Baja el DEM Copernicus GLO-30 y lo deja listo para M1."
    )
    ap.add_argument("--bbox", type=float, nargs=4, default=BBOX_COQUIMBO,
                    metavar=("OESTE", "SUR", "ESTE", "NORTE"),
                    help="Area a cubrir en grados. Por defecto, Coquimbo con margen.")
    ap.add_argument("--resolucion", type=float, default=30.0,
                    help="Resolucion de salida en metros.")
    ap.add_argument("--hilos", type=int, default=8,
                    help="Descargas simultaneas.")
    ap.add_argument("--conservar-mar", action="store_true",
                    help="No enmascarar el oceano (por defecto se enmascara).")
    args = ap.parse_args()

    carpeta_tiles = RAIZ / "data" / "raw" / "copernicus_dem30"
    carpeta_salida = RAIZ / "data" / "processed"
    carpeta_salida.mkdir(parents=True, exist_ok=True)

    tiles = descargar(args.bbox, carpeta_tiles, args.hilos)
    if not tiles:
        sys.exit("No se descargo ningun tile con terreno. Revisa el bbox.")

    mosaico = carpeta_salida / "dem_mosaico_wgs84.tif"
    unir(tiles, mosaico)

    dem_final = carpeta_salida / "dem_utm19s.tif"
    reproyectar(mosaico, dem_final, args.resolucion, not args.conservar_mar)

    tamano_gb = dem_final.stat().st_size / 1e9
    print(f"\nListo: {dem_final} ({tamano_gb:.2f} GB)")
    print("\nSiguiente paso:")
    print("  python src/m1_terreno.py")


if __name__ == "__main__":
    main()
