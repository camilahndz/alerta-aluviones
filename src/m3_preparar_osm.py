"""
M3 - Baja el extracto de OpenStreetMap de Chile y lo deja listo.

POR QUE ESTE SCRIPT EXISTE

    M3 necesita la red vial y las zonas urbanas de Chile en
    `data/raw/osm/chile.gpkg`. Hasta ahora el README decia "se baja una vez del
    navegador", y eso tiene dos problemas que se pagan juntos.

    El primero es que un archivo bajado a mano no deja constancia de cual se
    bajo. Geofabrik publica un `chile-latest-free.gpkg.zip` que cambia todos los
    dias: dos personas que sigan la misma instruccion con un mes de diferencia
    corren M3 sobre mapas distintos y ninguna de las dos lo sabe. Es el mismo
    problema por el que M3 abandono Overpass -"responde con el mapa de este
    instante"- y seria absurdo volver a caer en el por la puerta de al lado.

    El segundo lo demostro septiembre de 2026: cuando se perdio `data/raw/`, la
    unica pieza que no se pudo reconstruir fue la que nadie habia escrito como
    se obtenia.

    Por eso este script **no baja `latest`**. Pide un snapshot con fecha en el
    nombre, lo deja anotado en `data/raw/osm/PROCEDENCIA.txt`, y esa fecha es la
    que despues se cita.

FUENTE

    Geofabrik, extracto de Chile en formato GeoPackage:
    https://download.geofabrik.de/south-america/chile.html

    Los snapshots fechados viven en la seccion "raw directory index" de esa
    misma pagina, con nombre `chile-AAMMDD-free.gpkg.zip`. Geofabrik los
    conserva varios meses; los muy antiguos solo estan en .shp.zip y .osm.pbf.

    Licencia: ODbL, de OpenStreetMap y sus contribuyentes.

POR QUE EL GPKG Y NO EL PBF

    El .osm.pbf pesa la mitad (349 MB contra 765 MB) pero necesita osmium o
    pyosmium para convertirlo. El GeoPackage lo lee geopandas directo, sin una
    dependencia mas y sin un paso de conversion que pueda salir mal en silencio.
    Para un proyecto que corre en un notebook, 400 MB de disco de mas salen mas
    baratos que una herramienta mas que instalar.

Uso:

    python src/m3_preparar_osm.py                      # ultimo snapshot fechado
    python src/m3_preparar_osm.py --fecha 261008       # uno en particular
    python src/m3_preparar_osm.py --conservar-zip      # no borra el comprimido

Despues de esto, M3 corre solo:

    python src/m3_exposicion.py
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent

PAGINA = "https://download.geofabrik.de/south-america/chile.html"
BASE = "https://download.geofabrik.de/south-america"

CARPETA = RAIZ / "data" / "raw" / "osm"
DESTINO = CARPETA / "chile.gpkg"
PROCEDENCIA = CARPETA / "PROCEDENCIA.txt"

# Un snapshot entero pesa del orden de 765 MB. Si lo que llega es mucho menor,
# no es el archivo: es una pagina de error que el servidor devolvio con codigo
# 200, y descomprimirla fallaria mucho mas lejos del problema.
TAMANO_MINIMO_MB = 500


def snapshots_disponibles() -> list[str]:
    """Las fechas de los .gpkg.zip fechados que Geofabrik tiene hoy, mas nuevo primero.

    Se raspa la pagina en vez de adivinar la fecha porque Geofabrik no publica
    un snapshot por dia en todos los formatos: hay dias que solo tienen .pbf y
    .shp.zip. Pedir una fecha que no existe en gpkg da un 404.
    """
    r = requests.get(PAGINA, timeout=60)
    r.raise_for_status()
    fechas = re.findall(r"chile-(\d{6})-free\.gpkg\.zip", r.text)
    return sorted(set(fechas), reverse=True)


def descargar(fecha: str, destino_zip: Path) -> None:
    """Baja el zip mostrando avance. Aborta si el tamano no cuadra."""
    url = f"{BASE}/chile-{fecha}-free.gpkg.zip"
    print(f"Bajando {url}")

    destino_zip.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino_zip.with_suffix(".zip.parcial")

    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        bajado = 0
        siguiente_aviso = 50 * 1024 * 1024
        with open(parcial, "wb") as f:
            for trozo in r.iter_content(chunk_size=1024 * 1024):
                f.write(trozo)
                bajado += len(trozo)
                if bajado >= siguiente_aviso:
                    pct = f" ({100 * bajado / total:.0f}%)" if total else ""
                    print(f"  {bajado / 1e6:,.0f} MB{pct}")
                    siguiente_aviso += 50 * 1024 * 1024

    mb = parcial.stat().st_size / 1e6
    if mb < TAMANO_MINIMO_MB:
        parcial.unlink()
        sys.exit(f"Solo llegaron {mb:,.0f} MB, y un extracto entero pasa de "
                 f"{TAMANO_MINIMO_MB}. No es el archivo. No se sigue.")

    # El rename al final es a proposito: si la descarga se corta, lo que queda
    # en disco es un .parcial y no un .zip a medias que la proxima corrida
    # tomaria por bueno.
    parcial.replace(destino_zip)
    print(f"  listo: {mb:,.0f} MB")


def extraer(ruta_zip: Path, destino: Path) -> str:
    """Saca el .gpkg del zip y lo deja con nombre fijo. Devuelve el nombre interno."""
    with zipfile.ZipFile(ruta_zip) as z:
        gpkg = [n for n in z.namelist() if n.lower().endswith(".gpkg")]
        if not gpkg:
            sys.exit(f"{ruta_zip.name} no trae ningun .gpkg adentro.")
        if len(gpkg) > 1:
            print(f"AVISO: el zip trae {len(gpkg)} gpkg, se usa {gpkg[0]}")
        interno = gpkg[0]
        print(f"Extrayendo {interno}...")
        with z.open(interno) as origen, open(destino, "wb") as salida:
            shutil.copyfileobj(origen, salida, length=16 * 1024 * 1024)
    return interno


def main():
    ap = argparse.ArgumentParser(
        description="Baja un snapshot fechado del extracto OSM de Chile.")
    ap.add_argument("--fecha", help="AAMMDD del snapshot. Por defecto, el mas nuevo.")
    ap.add_argument("--conservar-zip", action="store_true",
                    help="No borra el comprimido despues de extraer.")
    ap.add_argument("--destino", type=Path, default=DESTINO)
    args = ap.parse_args()

    if DESTINO.exists() and not args.fecha:
        gb = DESTINO.stat().st_size / 1e9
        print(f"Ya existe {DESTINO} ({gb:.2f} GB).")
        if PROCEDENCIA.exists():
            print(PROCEDENCIA.read_text(encoding="utf-8"))
        print("Para reemplazarlo, pasa --fecha con el snapshot que quieras.")
        return

    fecha = args.fecha
    if not fecha:
        print("Consultando que snapshots tiene Geofabrik...")
        disponibles = snapshots_disponibles()
        if not disponibles:
            sys.exit("Geofabrik no lista ningun .gpkg.zip fechado. "
                     "Revisa la pagina a mano: " + PAGINA)
        fecha = disponibles[0]
        print(f"  hay {len(disponibles)}; se usa el mas nuevo: {fecha}")

    CARPETA.mkdir(parents=True, exist_ok=True)
    ruta_zip = CARPETA / f"chile-{fecha}-free.gpkg.zip"

    if not ruta_zip.exists():
        descargar(fecha, ruta_zip)
    else:
        print(f"El zip ya estaba: {ruta_zip.name}")

    interno = extraer(ruta_zip, args.destino)
    gb = args.destino.stat().st_size / 1e9

    PROCEDENCIA.write_text(
        "Extracto de OpenStreetMap usado por M3\n"
        "--------------------------------------\n"
        f"snapshot  : chile-{fecha}-free.gpkg.zip\n"
        f"fecha OSM : 20{fecha[:2]}-{fecha[2:4]}-{fecha[4:6]}\n"
        f"origen    : {BASE}/chile-{fecha}-free.gpkg.zip\n"
        f"archivo   : {interno} -> {args.destino.name} ({gb:.2f} GB)\n"
        f"bajado    : {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}\n"
        "licencia  : ODbL, OpenStreetMap y sus contribuyentes\n"
        "\n"
        "No se usa chile-latest-free.gpkg.zip a proposito: cambia todos los\n"
        "dias y haria que dos corridas separadas no sean comparables, que es\n"
        "justo el motivo por el que M3 dejo de consultar Overpass.\n",
        encoding="utf-8")

    if not args.conservar_zip:
        ruta_zip.unlink()
        print(f"Borrado el comprimido ({ruta_zip.name}); "
              "esta anotado en PROCEDENCIA.txt por si hay que volver a bajarlo.")

    print(f"\nListo: {args.destino} ({gb:.2f} GB)")
    print(f"  procedencia -> {PROCEDENCIA}")
    print("\nSiguiente paso:")
    print("  python src/m3_exposicion.py")


if __name__ == "__main__":
    main()
