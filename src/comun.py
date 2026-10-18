"""
Lo que comparten varios hitos: comunas, provincias y nombres sin tildes.

POR QUE ESTE MODULO EXISTE

    Hasta octubre de 2026 habia dos maneras de leer las comunas. M5 y M6 usaban
    una copia local con chequeo (m5_validacion.cargar_comunas) porque la
    descarga desde GitHub llego cortada dos veces el mismo dia; M3 seguia
    leyendolas de la URL en cada corrida. Habia ademas dos `sin_tildes` y dos
    tablas de provincias. Una regla con dos copias termina siendo dos reglas.
    Auditoria del 17-10-2026, A3.

    Aca vive una sola copia de cada cosa.

LIVIANO AL IMPORTAR

    Lo importan las pruebas, la alerta en vivo y el visor. geopandas y requests
    se importan dentro de cargar_comunas, no arriba: quien solo necesita la
    tabla de provincias no paga el costo de cargar GDAL.
"""

from __future__ import annotations

import json
import sys
import time
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CRS_METRICO = "EPSG:32719"   # UTM 19 Sur

# Fuente de comunas: geoBoundaries ADM3, que para Chile viene de la Biblioteca
# del Congreso Nacional (BCN). Se apunta a un commit fijo para que la corrida
# sea reproducible: la copia local es byte a byte el mismo dato.
URL_COMUNAS = (
    "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/"
    "releaseData/gbOpen/CHL/ADM3/geoBoundaries-CHL-ADM3.geojson"
)
COMUNAS_LOCAL = RAIZ / "data" / "raw" / "limites" / "geoBoundaries-CHL-ADM3.geojson"

# La division administrativa vigente de la region (DPA de la SUBDERE). Las
# claves van sin tildes, como las escribe sin_tildes.
PROVINCIAS = {
    "Elqui": ("la serena", "coquimbo", "andacollo", "la higuera", "paihuano", "vicuna"),
    "Limari": ("ovalle", "combarbala", "monte patria", "punitaqui", "rio hurtado"),
    "Choapa": ("illapel", "canela", "los vilos", "salamanca"),
}
PROVINCIA_DE = {c: p for p, comunas in PROVINCIAS.items() for c in comunas}


def sin_tildes(texto) -> str:
    """Minusculas y sin tildes: la clave con que se comparan nombres.

    El inventario escribe "Vicuna", la BCN "Vicuña" y OSM a veces "VICUÑA".
    Un None o un campo vacio da la cadena vacia.
    """
    bajo = str(texto or "").lower()
    return "".join(c for c in unicodedata.normalize("NFD", bajo)
                   if unicodedata.category(c) != "Mn")


def cargar_comunas():
    """Limites comunales en UTM 19S, con columnas comuna, clave y geometry.

    Se bajan una vez y quedan en data/raw/limites/. Hasta octubre de 2026 se
    leian de GitHub en cada corrida, y dos veces el mismo dia llego el archivo
    cortado a la mitad: pyogrio aborta con "Unterminated object", que al menos
    es un error que se ve. Para la alerta en vivo, que corre cada hora, depender
    de esa descarga no sirve. Antes de guardar la copia se comprueba que el JSON
    este completo y traiga comunas: una copia truncada en disco seria peor que
    la descarga, porque se leeria igual en cada corrida siguiente.
    """
    import geopandas as gpd
    import requests

    if not COMUNAS_LOCAL.exists():
        for intento in range(5):
            try:
                r = requests.get(URL_COMUNAS, timeout=180)
                r.raise_for_status()
                if not json.loads(r.content).get("features"):
                    raise ValueError("el GeoJSON llego sin comunas")
                COMUNAS_LOCAL.parent.mkdir(parents=True, exist_ok=True)
                COMUNAS_LOCAL.write_bytes(r.content)
                break
            except (requests.RequestException, ValueError) as e:
                if intento == 4:
                    sys.exit(f"No pude bajar las comunas de {URL_COMUNAS}: {e}")
                time.sleep(10 * (intento + 1))
    comunas = gpd.read_file(COMUNAS_LOCAL).to_crs(CRS_METRICO)
    comunas["clave"] = comunas["shapeName"].map(sin_tildes)
    return comunas[["shapeName", "clave", "geometry"]].rename(
        columns={"shapeName": "comuna"})
