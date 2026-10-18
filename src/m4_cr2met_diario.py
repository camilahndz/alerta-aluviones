"""
M4 - La lluvia diaria de CR2MET, 1970-2021, para calibrar con la historia.

POR QUE EXISTE

    Los niveles de alerta por provincia (m5_niveles.py) salen de 12
    provincias-temporal positivas en 5 temporales de VIPNET, 2024-2026. Con eso
    el corte de roja tiene un intervalo del 90% que va de 23 a 49%. La red de
    VIPNET no tiene mas historia, pero la variable del modelo no la necesita:
    es la lluvia de un temporal entero, y eso existe dia a dia desde 1960 en
    CR2MET. Este script la baja; m5_historico.py la cruza con los inventarios
    historicos (DesInventar 1970-2014 y la tesis de Mardones, 2019).

QUE BAJA

    Los mismos NetCDF mensuales de CR2MET v2.5 que m4_climatologia.py, por
    rangos dentro del zip de Zenodo y verificados contra su CRC, pero guarda
    cada dia en vez de sumar el mes. Se recorta a la misma ventana (Coquimbo y
    Atacama) y se guarda en decimas de milimetro como entero de 16 bits
    comprimido, con -1 donde no hay dato: un mes ocupa unos cientos de KB.

    1970 porque es donde empieza DesInventar, y 2021 porque es donde termina
    CR2MET v2.5.

Uso:

    python src/m4_cr2met_diario.py      # ~40 min la primera vez; despues, cache

Los meses quedan en data/raw/cr2met/diario/.
"""

from __future__ import annotations

import argparse
import io
import sys
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_climatologia as clim  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "data" / "raw" / "cr2met" / "diario"
PERIODO = (1970, 2021)


def ruta_mes(anio: int, mes: int) -> Path:
    return CARPETA / f"pr_{anio}_{mes:02d}.npz"


def dias_del_mes(datos: bytes, carpeta_tmp: Path):
    """Los dias del mes en la ventana de la region, en decimas de mm (int16, -1 sin dato)."""
    import rasterio
    from rasterio.windows import from_bounds

    with tempfile.NamedTemporaryFile(suffix=".nc", dir=carpeta_tmp, delete=False) as f:
        f.write(datos)
        ruta = Path(f.name)
    try:
        with rasterio.open(f"netcdf:{ruta}:pr") as src:
            ventana = from_bounds(clim.OESTE, clim.SUR, clim.ESTE, clim.NORTE, src.transform)
            ventana = ventana.round_offsets().round_lengths()
            crudo = src.read(window=ventana)
            transform = src.window_transform(ventana)
    finally:
        ruta.unlink()
    mm = crudo.astype("float64") * clim.ESCALA + clim.DESPLAZAMIENTO
    decimas = np.round(np.clip(mm, 0, None) * 10).astype("int16")
    decimas[crudo == clim.SIN_DATO] = -1
    return decimas, transform


def leer_mes(anio: int, mes: int) -> np.ndarray:
    """(dias, filas, columnas) en mm, NaN sin dato."""
    d = np.load(ruta_mes(anio, mes))["pr"].astype("float32")
    d[d < 0] = np.nan
    return d / 10.0


def transformada():
    from affine import Affine
    return Affine(*[float(v) for v in (CARPETA / "transform.txt").read_text().split(",")])


def main():
    ap = argparse.ArgumentParser(description="M4 - Lluvia diaria de CR2MET, 1970-2021.")
    ap.parse_args()
    CARPETA.mkdir(parents=True, exist_ok=True)
    tmp = CARPETA / "_tmp"
    tmp.mkdir(exist_ok=True)

    print("=" * 74)
    print(f"M4 - Lluvia diaria de CR2MET v2.5, {PERIODO[0]}-{PERIODO[1]}")
    print("=" * 74)
    meses = [(a, m) for a in range(PERIODO[0], PERIODO[1] + 1) for m in range(1, 13)]
    faltan = [am for am in meses if not ruta_mes(*am).exists()]
    print(f"\nMeses: {len(meses)}; en cache: {len(meses) - len(faltan)}")
    if not faltan:
        return

    print("Leyendo el indice del zip de Zenodo...")
    indice = {i.filename: i for i in
              zipfile.ZipFile(io.BufferedReader(clim.HTTPRango(clim.URL_CR2MET), 1 << 20)).infolist()}
    nombres = {am: clim.MIEMBRO.format(anio=am[0], mes=am[1]) for am in faltan}
    ausentes = [n for n in nombres.values() if n not in indice]
    if ausentes:
        sys.exit(f"El zip no trae {len(ausentes)} meses, por ejemplo {ausentes[0]}.")
    mb = sum(indice[n].compress_size for n in nombres.values()) / 1e6
    print(f"Bajando {len(faltan)} meses ({mb:.0f} MB comprimidos) con {clim.CONEXIONES} conexiones...")

    t0 = time.time()
    ruta_afin = CARPETA / "transform.txt"
    with ThreadPoolExecutor(clim.CONEXIONES) as ex:
        futuros = {ex.submit(clim.bajar_miembro, indice[nombres[am]]): am for am in faltan}
        for n, fut in enumerate(as_completed(futuros), 1):
            a, m = futuros[fut]
            decimas, transform = dias_del_mes(fut.result(), tmp)
            esperados = pd.Period(f"{a}-{m:02d}").days_in_month
            if decimas.shape[0] != esperados:
                sys.exit(f"{a}-{m:02d} trae {decimas.shape[0]} dias y el mes tiene {esperados}.")
            np.savez_compressed(ruta_mes(a, m), pr=decimas)
            if not ruta_afin.exists():
                ruta_afin.write_text(",".join(str(v) for v in tuple(transform)[:6]))
            if n % 48 == 0 or n == len(faltan):
                print(f"  {n}/{len(faltan)}  ({time.time() - t0:.0f} s)")

    tamanio = sum(f.stat().st_size for f in CARPETA.glob("*.npz")) / 1e6
    print(f"\n  {len(meses)} meses en {CARPETA.relative_to(RAIZ)} ({tamanio:.0f} MB)")


if __name__ == "__main__":
    main()
