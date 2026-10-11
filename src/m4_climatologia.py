"""
M4 - La precipitacion media anual de CR2MET, para leer la lluvia contra el clima.

POR QUE EXISTE

    m5_alerta_sector.py mostro que Caine no se activa en Elqui en ningun
    temporal de tres inviernos, ni en el del aluvion de Santa Gracia. En la
    region, la lluvia anual cambia varias veces de un extremo a otro, y un
    umbral unico queda alto justo donde llueve menos. La salida de la
    literatura es normalizar: medir cada temporal como fraccion de lo que
    llueve en un anio normal en ese lugar (Guzzetti et al., 2008, usan la
    precipitacion media anual para eso). Cuarenta milimetros en un sitio que
    recibe ochenta al anio no son lo mismo que en uno que recibe cuatrocientos.

LA FUENTE

    CR2MET v2.5 (Boisier et al., Centro de Ciencia del Clima y la Resiliencia,
    Zenodo 10.5281/zenodo.7529682): precipitacion diaria en grilla de 0,05
    grados, 1960-2021, ajustada contra las estaciones de la DGA y la DMC. Es
    el producto de referencia para Chile continental, y docs/contexto.md lo
    pedia desde el principio para la climatologia.

    Se usa la normal 1991-2020, el periodo de referencia vigente de la OMM.

COMO SE BAJA

    CR2MET se publica como un solo zip de 2,5 GB con un NetCDF por mes. No se
    baja entero: se lee el indice del zip por rangos HTTP y se pide cada uno
    de los 360 meses de la normal por separado, unos 3,5 MB comprimidos cada
    uno. Cada mes se verifica contra el CRC del zip, se recorta a la region
    y se guarda solo su total mensual recortado, unos 30 KB. Zenodo entrega
    unos 0,4 MB/s por conexion; con seis en paralelo la primera corrida toma
    del orden de 15 minutos, y las siguientes salen del cache.

    El cache esta en data/raw/cr2met/ y no en data/processed/: es el dato
    original, recortado pero sin transformar mas que sumar los dias del mes.

LOS VALORES

    El NetCDF guarda la lluvia diaria como entero de 16 bits con escala 0,01 y
    desplazamiento 300 (mm/dia = entero * 0,01 + 300), y -32768 donde no hay
    dato: el mar y el otro lado de la cordillera. Un mes con un solo dia sin
    dato en una celda deja esa celda sin dato ese mes: rellenar con cero
    bajaria la media justo en los bordes.

LO QUE SALIO

    Corrida 2026-10-11_m4_climatologia.txt: 1.228 MB comprimidos en 18
    minutos. En la grilla recortada la normal va de 11 mm (el norte de
    Atacama) a 1.413 mm (la alta cordillera, a la latitud de Rio Hurtado).
    La Serena tiene 91,
    Vicuna 123, Ovalle 149, Illapel 211, Copiapo 19: valores conocidos, que es
    la verificacion rapida de que la escala y el desplazamiento estan bien
    aplicados. En las estaciones de VIPNET de Coquimbo, la mediana es de 164
    mm en Elqui, 217 en Limari y 264 en Choapa.

Uso:

    python src/m4_climatologia.py

Escribe data/processed/precipitacion_media_anual.tif (mm/anio, EPSG:4326).
"""

from __future__ import annotations

import argparse
import io
import struct
import sys
import tempfile
import time
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import requests

RAIZ = Path(__file__).resolve().parent.parent

URL_CR2MET = "https://zenodo.org/api/records/7529682/files/CR2MET_pr_v2.5.zip/content"
MIEMBRO = "pr/CR2MET_pr_v2.5_day_{anio}_{mes:02d}_005deg.nc"
NORMAL = (1991, 2020)

# La region con margen, y Atacama completa: la alerta por provincia puede
# extenderse alli con la misma red de VIPNET.
OESTE, SUR, ESTE, NORTE = -72.0, -33.0, -69.0, -25.5

ESCALA, DESPLAZAMIENTO, SIN_DATO = 0.01, 300.0, -32768
CONEXIONES = 6
REINTENTOS = 5


class HTTPRango(io.RawIOBase):
    """Archivo de solo lectura sobre HTTP con Range: zipfile lee solo el indice."""

    def __init__(self, url: str):
        self.url, self.pos = url, 0
        self.size = int(requests.head(url, allow_redirects=True, timeout=60)
                        .headers["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, desplazamiento, desde=0):
        self.pos = {0: desplazamiento, 1: self.pos + desplazamiento,
                    2: self.size + desplazamiento}[desde]
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        fin = min(self.pos + len(b), self.size) - 1
        r = requests.get(self.url, headers={"Range": f"bytes={self.pos}-{fin}"}, timeout=180)
        r.raise_for_status()
        b[:len(r.content)] = r.content
        self.pos += len(r.content)
        return len(r.content)


def bajar_miembro(info: zipfile.ZipInfo) -> bytes:
    """Un miembro del zip remoto, descomprimido y verificado contra su CRC.

    Cada hilo pide su propio rango: el objeto ZipFile no se puede compartir
    entre hilos, porque guarda la posicion de lectura.
    """
    ultimo = None
    for intento in range(REINTENTOS):
        try:
            a = info.header_offset
            # 30 bytes de cabecera local mas nombre y campo extra, que puede
            # no medir lo mismo que en el indice central: se pide holgura.
            r = requests.get(URL_CR2MET, timeout=300, headers={
                "Range": f"bytes={a}-{a + 30 + 1024 + info.compress_size}"})
            r.raise_for_status()
            crudo = r.content
            if crudo[:4] != b"PK\x03\x04":
                raise ValueError("cabecera local invalida")
            largo_nombre, largo_extra = struct.unpack("<HH", crudo[26:30])
            inicio = 30 + largo_nombre + largo_extra
            comprimido = crudo[inicio:inicio + info.compress_size]
            if info.compress_type == zipfile.ZIP_DEFLATED:
                datos = zlib.decompressobj(-15).decompress(comprimido)
            elif info.compress_type == zipfile.ZIP_STORED:
                datos = comprimido
            else:
                raise ValueError(f"compresion {info.compress_type} no soportada")
            if zlib.crc32(datos) != info.CRC or len(datos) != info.file_size:
                raise ValueError("CRC o largo no coinciden")
            return datos
        except Exception as e:      # red o archivo corrupto: se reintenta
            ultimo = e
            time.sleep(min(60, 5 * 2 ** intento))
    raise RuntimeError(f"{info.filename}: fallo {REINTENTOS} veces ({ultimo})")


def total_mensual(datos: bytes, carpeta_tmp: Path):
    """Suma los dias del mes en la ventana de la region. Devuelve (total, transform)."""
    import rasterio
    from rasterio.windows import from_bounds

    with tempfile.NamedTemporaryFile(suffix=".nc", dir=carpeta_tmp, delete=False) as f:
        f.write(datos)
        ruta = Path(f.name)
    try:
        # El driver netCDF de GDAL necesita un archivo de verdad, no memoria.
        with rasterio.open(f"netcdf:{ruta}:pr") as src:
            ventana = from_bounds(OESTE, SUR, ESTE, NORTE, src.transform)
            ventana = ventana.round_offsets().round_lengths()
            crudo = src.read(window=ventana)
            transform = src.window_transform(ventana)
    finally:
        ruta.unlink()
    sin_dato = (crudo == SIN_DATO).any(axis=0)
    total = (crudo.astype("float64") * ESCALA + DESPLAZAMIENTO).sum(axis=0)
    total[sin_dato] = np.nan
    return total.astype("float32"), transform


def main():
    ap = argparse.ArgumentParser(description="M4 - Precipitacion media anual de CR2MET.")
    ap.add_argument("--cache", type=Path, default=RAIZ / "data" / "raw" / "cr2met")
    ap.add_argument("--procesados", type=Path, default=RAIZ / "data" / "processed")
    args = ap.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    tmp = args.cache / "_tmp"
    tmp.mkdir(exist_ok=True)

    print("=" * 74)
    print(f"M4 - Precipitacion media anual, CR2MET v2.5, normal {NORMAL[0]}-{NORMAL[1]}")
    print("=" * 74)

    meses = [(a, m) for a in range(NORMAL[0], NORMAL[1] + 1) for m in range(1, 13)]
    ruta_mes = {(a, m): args.cache / f"pr_{a}_{m:02d}.npy" for a, m in meses}
    faltan = [am for am in meses if not ruta_mes[am].exists()]
    print(f"\nMeses de la normal: {len(meses)}; en cache: {len(meses) - len(faltan)}")

    ruta_afin = args.cache / "transform.txt"
    if faltan:
        print(f"Leyendo el indice del zip de Zenodo...")
        indice = {i.filename: i for i in
                  zipfile.ZipFile(io.BufferedReader(HTTPRango(URL_CR2MET), 1 << 20)).infolist()}
        ausentes = [MIEMBRO.format(anio=a, mes=m) for a, m in faltan
                    if MIEMBRO.format(anio=a, mes=m) not in indice]
        if ausentes:
            sys.exit(f"El zip no trae {len(ausentes)} meses, por ejemplo {ausentes[0]}.")
        mb = sum(indice[MIEMBRO.format(anio=a, mes=m)].compress_size for a, m in faltan) / 1e6
        print(f"Bajando {len(faltan)} meses ({mb:.0f} MB comprimidos) con {CONEXIONES} "
              "conexiones...")
        t0 = time.time()
        with ThreadPoolExecutor(CONEXIONES) as ex:
            futuros = {ex.submit(bajar_miembro, indice[MIEMBRO.format(anio=a, mes=m)]): (a, m)
                       for a, m in faltan}
            for n, fut in enumerate(as_completed(futuros), 1):
                a, m = futuros[fut]
                total, transform = total_mensual(fut.result(), tmp)
                np.save(ruta_mes[(a, m)], total)
                if not ruta_afin.exists():
                    ruta_afin.write_text(",".join(str(v) for v in tuple(transform)[:6]))
                if n % 30 == 0 or n == len(faltan):
                    print(f"  {n}/{len(faltan)}  ({time.time() - t0:.0f} s)")

    from affine import Affine
    import rasterio

    transform = Affine(*[float(v) for v in ruta_afin.read_text().split(",")])
    anuales = np.stack([sum(np.load(ruta_mes[(a, m)]) for m in range(1, 13))
                        for a in range(NORMAL[0], NORMAL[1] + 1)])
    media = anuales.mean(axis=0).astype("float32")

    ruta = args.procesados / "precipitacion_media_anual.tif"
    with rasterio.open(ruta, "w", driver="GTiff", height=media.shape[0], width=media.shape[1],
                       count=1, dtype="float32", crs="EPSG:4326", transform=transform,
                       nodata=np.nan) as dst:
        dst.write(media, 1)
        dst.update_tags(fuente="CR2MET v2.5, Boisier et al., doi 10.5281/zenodo.7529682",
                        normal=f"{NORMAL[0]}-{NORMAL[1]}", unidades="mm/anio")

    validos = media[np.isfinite(media)]
    print(f"\nPrecipitacion media anual {NORMAL[0]}-{NORMAL[1]}: {media.shape[1]} x "
          f"{media.shape[0]} celdas de 0,05 grados")
    print(f"  minimo {validos.min():.0f} mm, mediana {np.median(validos):.0f} mm, "
          f"maximo {validos.max():.0f} mm")
    print(f"  raster -> {ruta.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
