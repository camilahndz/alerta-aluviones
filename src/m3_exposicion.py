"""
M3 - Exposicion: donde el flujo cruza lo que la gente usa.

M1 dijo donde estan las quebradas. M2 dijo cuales pueden generar un flujo de
detritos. M3 responde la pregunta que le importa a alguien que no sabe
hidrologia: **que rutas se cortan y que localidades quedan en el camino**.

---------------------------------------------------------------------------
LO QUE ESTE SCRIPT NO ES
---------------------------------------------------------------------------

No es un modelo de propagacion (runout). Un runout de verdad resuelve la
reologia del flujo -viscosidad, friccion, volumen movilizado- y devuelve hasta
donde llega el material y con que espesor. Eso es Nivel 3 (RAMMS, FLO-2D) y
esta explicitamente fuera de alcance.

Lo que hace este script es un **proxy geometrico**: supone que el material baja
por el cauce principal de la cuenca, que es por donde va el agua. Es una
hipotesis razonable -los flujos de detritos son encauzados hasta que llegan al
abanico- pero es una hipotesis, no un calculo.

En consecuencia, cada punto de corte que sale de aca es un **candidato**: un
lugar donde una via cruza el cauce de una quebrada susceptible. No es una
prediccion de que ese corte vaya a ocurrir, ni con que frecuencia.

---------------------------------------------------------------------------
LAS DOS DECISIONES QUE HAY QUE PODER DEFENDER
---------------------------------------------------------------------------

**1. La trayectoria se traza aguas ARRIBA desde la desembocadura.**

Suena al reves y conviene explicar por que no lo es. La desembocadura es, por
como M1 la definio, el ultimo pixel con terreno antes del mar o del borde del
DEM: aguas abajo de ese punto no queda nada que recorrer. Lo que si existe es el
camino que el material baja desde la cabecera hasta esa boca, y ese camino se
reconstruye al reves: parado en la boca, se avanza al vecino que trae mas agua,
y repitiendo se sube por la rama principal dejando fuera los afluentes chicos.
La linea resultante se guarda en sentido cabecera -> boca, que es el sentido en
que viaja el flujo.

**2. No hay parametro de alcance; hay ancho de corredor.**

Exponer un "alcance de runout" en kilometros habria sido inventar un numero: el
alcance real depende del volumen movilizado, que este proyecto no estima. En vez
de eso el unico parametro espacial es el ancho del corredor alrededor del cauce
(45 m por defecto), y su justificacion es puramente geometrica: el cauce se
trazo sobre una grilla de 30 m, asi que su posicion tiene una incertidumbre del
orden de pixel y medio. El corredor absorbe ese desajuste entre el DEM y el
trazado de OSM para no perder cruces reales por unos metros.

Es tolerancia de posicion, no distancia de propagacion. Si alguien lo lee como
lo segundo, esta leyendo mal el modelo.

---------------------------------------------------------------------------
LOS CINCO PASOS
---------------------------------------------------------------------------

    1. Bajar de OpenStreetMap la red vial y las zonas urbanas (con cache).
    2. Trazar, para cada cuenca susceptible, su cauce principal.
    3. Cruzar esos cauces con las vias -> puntos de corte candidatos.
    4. Priorizarlos combinando peligro de la cuenca con importancia de la via.
    5. Marcar aparte que trayectorias entran en zona urbana y en cual.

Uso:

    python src/m3_exposicion.py

Lee lo que dejaron M1 y M2 en data/processed/.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import LineString, Point, box

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

import osmnx as ox  # noqa: E402
from osmnx._errors import InsufficientResponseError  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clases_cuenca import CLASES_SUSCEPTIBLES  # noqa: E402
from cobertura import COBERTURA_MINIMA, verificar_cobertura  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent

CRS_METRICO = "EPSG:32719"   # UTM 19 Sur: metros de verdad
CRS_GEOGRAFICO = "EPSG:4326"  # lo que entrega OSM: grados

# Codificacion D8, la misma que uso M1.
DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)

# Para cada vecino: (desplazamiento fila/col, codigo que ese vecino debe tener
# para estar drenando hacia la celda del centro).
VECINDAD = [
    ((-1, 0), 4), ((-1, 1), 8), ((0, 1), 16), ((1, 1), 32),
    ((1, 0), 64), ((1, -1), 128), ((0, -1), 1), ((-1, -1), 2),
]

# --- Vias que se bajan de OSM -----------------------------------------------
# Se define el filtro a mano en vez de usar network_type="drive" porque ese
# preset excluye las huellas (track), y en la ruralidad de Coquimbo una huella
# cortada puede ser el unico acceso a un caserio.
FILTRO_VIAS = (
    '["highway"~"motorway|trunk|primary|secondary|tertiary|'
    'unclassified|residential|living_street|service|track|road"]'
)

# --- Jerarquia vial ---------------------------------------------------------
# El peso responde a "cuanta gente queda incomunicada si esto se corta".
# Una via troncal cortada aisla una region entera; una huella, un predio.
# Son ordinales elegidos por criterio, no calibrados: se pueden mover.
PESO_VIA = {
    "motorway": 1.00,   # autopista
    "trunk": 1.00,      # troncal (la Ruta 5 aparece como trunk en gran parte)
    "primary": 0.85,    # rutas regionales principales
    "secondary": 0.60,
    "tertiary": 0.45,
    "unclassified": 0.30,  # via publica menor, sin jerarquia asignada en OSM
    "residential": 0.30,
    "living_street": 0.20,
    "road": 0.20,       # sin clasificar en OSM
    "service": 0.15,
    "track": 0.10,      # huella rural
}
PESO_VIA_DEFECTO = 0.15

# --- Peligro de la cuenca ---------------------------------------------------
# Un flujo de detritos arrastra bloques y arrasa; una crecida de detritos mueve
# grava y agua turbia. El corte que produce el primero es mas severo y mas
# dificil de despejar. La razon 1,0 / 0,55 dice "el flujo pesa casi el doble",
# y es un juicio, no una medicion.
PESO_CLASE = {
    "flujo_detritos": 1.00,
    "crecida_detritos": 0.55,
}

# Cuanto pesa cada mitad en la prioridad final. 50/50 porque no hay evidencia
# para inclinarlo: es explicitamente el parametro mas discutible del script.
PONDERADOR_CLASE = 0.5
PONDERADOR_VIA = 0.5

# --- Extracto local de OpenStreetMap -----------------------------------------
# Fuente preferida para la red vial y las zonas urbanas: el extracto de Chile
# que publica Geofabrik, bajado una vez y leido desde disco.
#
# Por que no Overpass, que es lo que este script hacia antes: Overpass es un
# servicio publico gratuito que limita a 2 consultas simultaneas por IP, y M3
# necesita del orden de 48. El 23 de agosto de 2026 se intentaron siete corridas
# y ninguna logro completar la descarga; el servidor dejaba de aceptar la
# conexion a mitad de camino. No es un defecto del servidor: es un bien comun y
# esa cuota existe para que alcance para todos.
#
# El extracto ademas arregla algo mas importante que la disponibilidad. Overpass
# responde con el mapa de este instante, asi que dos corridas separadas por un
# mes no son comparables y ninguna es reproducible. El extracto es una foto con
# fecha: cualquiera que baje el mismo archivo obtiene los mismos puntos de corte.
# Eso es justo la regla que el repositorio se puso en el README.
#
# Se baja del navegador, una vez, sin registro:
#     https://download.geofabrik.de/south-america/chile.html
# Archivo: chile-latest-free.gpkg.zip (~750 MB). Se descomprime chile.gpkg
# dentro de data/raw/osm/. El README del zip trae la fecha exacta del extracto,
# que conviene anotar en la corrida de referencia.
RUTA_EXTRACTO_OSM = RAIZ / "data" / "raw" / "osm" / "chile.gpkg"

CAPA_VIAS = "gis_osm_roads_free"
CAPA_LANDUSE = "gis_osm_landuse_a_free"
CAPA_PLACES = "gis_osm_places_a_free"

# Geofabrik clasifica cada objeto en `fclass` en vez de la etiqueta `highway`
# original de OSM. El vocabulario es el mismo, y estas son las palabras del
# filtro de Overpass de mas abajo (FILTRO_VIAS).
#
# La comparacion se hace por substring y no por igualdad, a proposito: la
# expresion regular de Overpass no esta anclada, asi que "motorway" tambien
# captura "motorway_link". Replicar esa regla aca garantiza que las dos fuentes
# seleccionen exactamente el mismo conjunto de vias. Verificado sobre la Region
# de Coquimbo: entran motorway/trunk/primary/secondary/tertiary y sus _link,
# unclassified, residential, living_street, service y track; quedan fuera
# footway, path, steps, cycleway, pedestrian, bridleway y unknown.
PALABRAS_VIA = ("motorway", "trunk", "primary", "secondary", "tertiary",
                "unclassified", "residential", "living_street", "service",
                "track", "road")

# Clases de uso de suelo que cuentan como zona urbana. Son las mismas que le
# pedia a Overpass.
LANDUSE_URBANO = ("residential", "commercial", "industrial", "retail")
PLACES_URBANO = ("city", "town", "village", "hamlet")


# --- Servidor de Overpass ----------------------------------------------------
# Se usa overpass-api.de, que es el servidor principal y el unico de los
# probados que sirve datos globales.
#
# NO CAMBIAR ESTO POR UN ESPEJO SIN VERIFICAR SU COBERTURA GEOGRAFICA. El 23 de
# agosto de 2026 se probo overpass.osm.ch, que figura en la lista de instancias
# publicas de OSM y respondia rapido y con HTTP 200. Resulto ser un extracto
# regional: para Zurich devuelve las mismas 16.265 vias que el servidor
# principal, y para La Serena devuelve cero. Un espejo asi no da error, da
# vacio, que es el peor resultado posible porque el codigo de aca abajo esta
# escrito justamente para confiar en que "vacio" significa "no hay nada".
#
# La forma de verificar un espejo antes de usarlo es una sola consulta:
#
#     [out:json][timeout:60];way["highway"](-29.95,-71.30,-29.88,-71.22);out count;
#
# Ese recuadro es La Serena. Si devuelve cero, ese servidor no sirve para este
# proyecto por mas rapido que responda.
OVERPASS_URL = "https://overpass-api.de/api"

# --- Reintentos contra Overpass ---------------------------------------------
# Overpass es un servicio publico con limite por IP. Cuando esta cargado
# responde 429, o corta la conexion, o tarda mas que el timeout: los tres casos
# se resuelven esperando y volviendo a pedir. Ver _pedir_a_overpass().
REINTENTOS_OSM = 6
ESPERA_OSM_S = 45
PAUSA_ENTRE_CUADROS_S = 5

# Fuente de comunas: geoBoundaries ADM3, que para Chile viene de la Biblioteca
# del Congreso Nacional (BCN). Se apunta a un commit fijo para que la corrida
# sea reproducible.
URL_COMUNAS = (
    "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/"
    "releaseData/gbOpen/CHL/ADM3/geoBoundaries-CHL-ADM3.geojson"
)


# ===========================================================================
# Paso 1 - Descarga de OpenStreetMap
# ===========================================================================

def _tiles(bbox, paso: float, zona_util=None):
    """Parte un bounding box en cuadros de `paso` grados.

    Overpass -el servidor de OSM- responde mal a consultas muy grandes: se cae
    por timeout o devuelve incompleto. Bajar por cuadros y unir es mas lento en
    numero de consultas pero mucho mas confiable, y como cada cuadro se cachea
    en disco, un corte de red solo obliga a repetir el cuadro que fallo.

    `zona_util` descarta los cuadros donde no hay ninguna trayectoria cerca. Sin
    ese filtro se consultan cuadros de oceano abierto y de alta cordillera que
    no aportan nada y son la mitad del rectangulo: en la primera corrida eso
    significo 25 cuadros -50 consultas- cuando servian menos de la mitad.
    """
    oeste, sur, este, norte = bbox
    x = np.arange(np.floor(oeste / paso) * paso, este, paso)
    y = np.arange(np.floor(sur / paso) * paso, norte, paso)
    # float() y no solo round(): np.arange devuelve np.float64, y esos se
    # imprimen como "np.float64(-72.0)" en los mensajes de error, que despues
    # quedan guardados en docs/corridas/.
    cuadros = [(float(round(i, 4)), float(round(j, 4)),
                float(round(i + paso, 4)), float(round(j + paso, 4)))
               for i in x for j in y]

    if zona_util is None:
        return cuadros
    return [c for c in cuadros if zona_util.intersects(box(c[0], c[1], c[2], c[3]))]


def _fclass_a_highway(fclass: str) -> str:
    """Traduce el `fclass` de Geofabrik a la etiqueta `highway` de OSM.

    Casi siempre son el mismo string. La excepcion son las huellas: Geofabrik
    desglosa `highway=track` segun su etiqueta `tracktype`, produciendo
    track_grade1 a track_grade5, mientras que Overpass las entrega todas como
    `track`.

    Esa diferencia no es cosmetica. PESO_VIA le asigna 0,10 a `track` y
    cualquier valor desconocido cae en PESO_VIA_DEFECTO, que es 0,15. Sin esta
    traduccion, las 238 huellas con tracktype de la Region de Coquimbo pesarian
    mas que las huellas sin el, o sea que una huella rural mejor documentada
    apareceria como via mas importante. Es el tipo de error que no da error.
    """
    if fclass.startswith("track_grade"):
        return "track"
    return fclass


def cargar_osm_extracto(ruta_gpkg: Path, bbox, cache: Path):
    """Lee vias y zonas urbanas del extracto local, recortadas al area de interes.

    Devuelve lo mismo que descargar_osm() -dos GeoDataFrame en UTM 19S- para que
    el resto del script no note la diferencia. Ver el comentario de
    RUTA_EXTRACTO_OSM para por que esta es la fuente preferida.
    """
    oeste, sur, este, norte = bbox
    recuadro = (oeste, sur, este, norte)

    print(f"Leyendo OSM del extracto local: {ruta_gpkg.name}")

    # --- vias ---
    vias = gpd.read_file(ruta_gpkg, layer=CAPA_VIAS, bbox=recuadro,
                         columns=["fclass", "name"], engine="pyogrio")
    antes = len(vias)
    interesan = vias["fclass"].apply(lambda f: any(p in f for p in PALABRAS_VIA))
    vias = vias[interesan].copy()
    vias["highway"] = vias["fclass"].apply(_fclass_a_highway)
    vias = vias[["highway", "name", "geometry"]]
    print(f"  vias: {antes:,} en el recuadro -> {len(vias):,} de los tipos que "
          "interesan")

    # --- zonas urbanas ---
    # Se leen las dos capas y se juntan, igual que la consulta a Overpass pedia
    # landuse y place a la vez. Se conservan solo poligonos, que es lo que el
    # cruce con las trayectorias necesita.
    piezas = []
    suelo = gpd.read_file(ruta_gpkg, layer=CAPA_LANDUSE, bbox=recuadro,
                          columns=["fclass", "name"], engine="pyogrio")
    suelo = suelo[suelo["fclass"].isin(LANDUSE_URBANO)].copy()
    suelo["landuse"] = suelo["fclass"]
    suelo["place"] = None
    piezas.append(suelo[["name", "landuse", "place", "geometry"]])

    lugares = gpd.read_file(ruta_gpkg, layer=CAPA_PLACES, bbox=recuadro,
                            columns=["fclass", "name"], engine="pyogrio")
    lugares = lugares[lugares["fclass"].isin(PLACES_URBANO)].copy()
    lugares["place"] = lugares["fclass"]
    lugares["landuse"] = None
    piezas.append(lugares[["name", "landuse", "place", "geometry"]])

    urbano = gpd.GeoDataFrame(pd.concat(piezas, ignore_index=True),
                              crs=piezas[0].crs)
    urbano = urbano[urbano.geometry.type.isin(["Polygon", "MultiPolygon"])]
    print(f"  zonas urbanas: {len(suelo):,} de uso de suelo + {len(lugares):,} "
          f"de localidad = {len(urbano):,} poligonos")

    if urbano.empty:
        print("  AVISO: ninguna zona urbana en el recuadro. El reporte de "
              "localidades alcanzadas va a salir vacio.")

    # Se guarda el recorte para que una segunda corrida no relea el extracto
    # completo, que son 1,37 GB.
    cache.mkdir(parents=True, exist_ok=True)
    vias.to_file(cache / "vias.gpkg", driver="GPKG")
    if not urbano.empty:
        urbano.to_file(cache / "urbano.gpkg", driver="GPKG")

    return vias.to_crs(CRS_METRICO), urbano.to_crs(CRS_METRICO)


def _pedir_a_overpass(consulta, descripcion: str):
    """Ejecuta una consulta a OSM distinguiendo "vacio" de "fallo".

    Esta funcion existe por una corrida que costo la validez de todo M3.

    El 23 de agosto de 2026 la descarga de OSM se hizo mientras Overpass estaba
    saturado: 10 de los 12 cuadros fallaron por rate limit o timeout. El codigo
    de entonces envolvia la consulta en un `except Exception` que reportaba cero
    vias y seguia, con este comentario:

        # Un cuadro sin ninguna via -mar abierto, alta cordillera- hace que
        # osmnx lance excepcion. No es un error: ahi no hay nada que bajar.

    La premisa era cierta pero incompleta: un cuadro vacio lanza excepcion, si,
    pero tambien la lanza uno que fallo. Atrapando las dos por igual, la corrida
    siguio con una red vial que cubria 19 km de los 113 km de trayectorias y
    produjo 25 puntos de corte, todos amontonados en Canela, porque era el unico
    lugar con caminos descargados. El cuadro que contiene La Serena y Coquimbo
    reporto cero vias; preguntado de nuevo al dia siguiente devolvio 61.386.

    Ninguna cifra de esa corrida era detectable como mala desde la salida: 25
    cortes sobre la Ruta 5 es un resultado perfectamente plausible.

    Entonces: `InsufficientResponseError` es la unica excepcion que significa
    "aca de verdad no hay nada", y es la unica que se deja pasar en silencio.
    Cualquier otra se reintenta, y si insiste se aborta la corrida entera. Es
    preferible no tener resultado a tener uno que cubre un sexto del territorio
    sin decirlo.
    """
    for intento in range(1, REINTENTOS_OSM + 1):
        try:
            return consulta()
        except InsufficientResponseError:
            # Vacio de verdad: mar abierto o alta cordillera sin caminos.
            return None
        except Exception as e:
            if intento == REINTENTOS_OSM:
                sys.exit(
                    f"\nOverpass fallo {REINTENTOS_OSM} veces seguidas en "
                    f"{descripcion}:\n    {type(e).__name__}: {e}\n\n"
                    "La corrida se detiene a proposito. Seguir produciria una red\n"
                    "vial incompleta, y los puntos de corte que salen de una red\n"
                    "incompleta se ven exactamente igual que los buenos: aparecen\n"
                    "solo donde si hubo descarga.\n\n"
                    "Overpass es un servicio publico y se satura. Reintenta en un\n"
                    "rato; los cuadros ya bajados quedan en cache y no se repiten."
                )
            espera = ESPERA_OSM_S * intento
            print(f"      {descripcion}: {type(e).__name__}, "
                  f"reintento {intento}/{REINTENTOS_OSM - 1} en {espera}s...")
            time.sleep(espera)


def descargar_osm(bbox, cache: Path, paso: float, zona_util=None):
    """Baja vias y zonas urbanas del area pedida, con cache en disco.

    Devuelve todo ya reproyectado a UTM 19S. Esa reproyeccion es critica: OSM
    entrega en grados, y si se intersecta en grados las distancias no significan
    nada -un grado de longitud mide distinto en cada latitud- y los resultados
    salen mal sin que nada avise.
    """
    cache.mkdir(parents=True, exist_ok=True)
    ox.settings.cache_folder = str(cache / "_overpass")
    ox.settings.use_cache = True
    ox.settings.overpass_url = OVERPASS_URL
    print(f"Servidor Overpass: {OVERPASS_URL}")

    ruta_vias = cache / "vias.gpkg"
    ruta_urbano = cache / "urbano.gpkg"

    if ruta_vias.exists() and ruta_urbano.exists():
        print("Red vial y zonas urbanas: leidas del cache local")
        vias = gpd.read_file(ruta_vias)
        urbano = gpd.read_file(ruta_urbano)
        return vias.to_crs(CRS_METRICO), urbano.to_crs(CRS_METRICO)

    cuadros = _tiles(bbox, paso, zona_util)
    print(f"Bajando OSM en {len(cuadros)} cuadros de {paso}x{paso} grados "
          "(solo los que tienen trayectorias cerca)...")

    trozos_vias, trozos_urbano = [], []
    vacios = 0
    for i, cuadro in enumerate(cuadros, 1):
        # --- vias ---
        g = _pedir_a_overpass(
            lambda: ox.graph_from_bbox(bbox=cuadro, custom_filter=FILTRO_VIAS,
                                       retain_all=True, truncate_by_edge=True),
            f"vias del cuadro {i}/{len(cuadros)} {cuadro}",
        )
        if g is None:
            n_v = 0
            vacios += 1
        else:
            aristas = ox.graph_to_gdfs(g, nodes=False).reset_index(drop=True)
            trozos_vias.append(aristas[["highway", "name", "geometry"]])
            n_v = len(aristas)

        # --- zonas urbanas ---
        # landuse marca el suelo efectivamente construido; place aporta el
        # nombre de la localidad, que es lo que hace legible el resultado.
        #
        # Se piden en dos consultas separadas y no en una con las dos etiquetas,
        # que seria lo natural. El motivo es medido: el 23 de agosto de 2026 la
        # consulta combinada sobre el cuadro (-72,0 -32,0 -71,5 -31,5) fallo seis
        # veces seguidas contra overpass-api.de, y pedida directamente devolvia
        # HTTP 429 -Too Many Requests- en 13 segundos. Las mismas dos etiquetas
        # pedidas por separado devolvieron HTTP 200 en 1,5 y 1,2 segundos, con 11
        # y 13 elementos. Una consulta que combina landuse y place sobre medio
        # grado le cuesta al servidor mas que las dos mitades sumadas.
        #
        # El resultado es el mismo conjunto: la consulta combinada devuelve la
        # union de ambas etiquetas, y aca se concatenan las dos mitades quitando
        # los elementos que aparecen en las dos (los que tienen ambas etiquetas).
        piezas = []
        for etiqueta, tags in (
            ("landuse", {"landuse": ["residential", "commercial", "industrial", "retail"]}),
            ("place", {"place": ["city", "town", "village", "hamlet"]}),
        ):
            parte = _pedir_a_overpass(
                lambda tags=tags: ox.features_from_bbox(bbox=cuadro, tags=tags),
                f"zonas urbanas ({etiqueta}) del cuadro {i}/{len(cuadros)} {cuadro}",
            )
            if parte is not None and len(parte):
                piezas.append(parte)

        if not piezas:
            n_u = 0
        else:
            u = piezas[0] if len(piezas) == 1 else pd.concat(piezas)
            # osmnx indexa por (element_type, osmid): un elemento etiquetado con
            # landuse y place a la vez vendria en las dos mitades.
            u = u[~u.index.duplicated(keep="first")]
            u = u[u.geometry.type.isin(["Polygon", "MultiPolygon"])]
            if len(u):
                cols = [c for c in ("name", "landuse", "place") if c in u.columns]
                trozos_urbano.append(u[cols + ["geometry"]].reset_index(drop=True))
            n_u = len(u)

        # Pausa deliberada entre cuadros. overpass-api.de admite 2 consultas
        # simultaneas por IP y M3 dispara 24 seguidas; sin este respiro la
        # cuota se agota a mitad de camino y el servidor deja de aceptar la
        # conexion, que es como se manifiesta el limite.
        if i < len(cuadros):
            time.sleep(PAUSA_ENTRE_CUADROS_S)

        marca = "  (vacio)" if n_v == 0 else ""
        print(f"  [{i:>3}/{len(cuadros)}] {n_v:>6} vias  {n_u:>5} poligonos urbanos{marca}")

    if vacios:
        print(f"  {vacios} de {len(cuadros)} cuadros no tienen ninguna via. "
              "Overpass los respondio vacios, no fallaron.")

    if not trozos_vias:
        sys.exit("OSM no devolvio ninguna via. Revisa la conexion o el bbox.")

    vias = gpd.GeoDataFrame(pd.concat(trozos_vias, ignore_index=True),
                            crs=CRS_GEOGRAFICO)
    urbano = (gpd.GeoDataFrame(pd.concat(trozos_urbano, ignore_index=True),
                               crs=CRS_GEOGRAFICO)
              if trozos_urbano else
              gpd.GeoDataFrame({"name": [], "geometry": []}, crs=CRS_GEOGRAFICO))

    # OSM viene con la columna highway a veces como texto y a veces como lista
    # (una via puede tener dos clasificaciones). Se normaliza quedandose con la
    # mas importante, porque de eso depende la prioridad del paso 4.
    vias["highway"] = vias["highway"].apply(_jerarquia_dominante)

    vias.to_file(ruta_vias, driver="GPKG")
    urbano.to_file(ruta_urbano, driver="GPKG")
    print(f"  guardado en {cache}")

    return vias.to_crs(CRS_METRICO), urbano.to_crs(CRS_METRICO)


def _jerarquia_dominante(valor):
    """De una etiqueta highway que puede ser lista, devuelve la de mayor peso."""
    if isinstance(valor, (list, tuple, set)):
        if not valor:
            return "road"
        return max(valor, key=lambda v: PESO_VIA.get(str(v), PESO_VIA_DEFECTO))
    return str(valor)


# ===========================================================================
# Paso 2 - Trayectoria: el cauce principal de cada cuenca
# ===========================================================================

def cauce_principal(fdir, acc, fila, col, transform, min_celdas):
    """Traza el cauce principal caminando aguas ARRIBA desde la desembocadura.

    El metodo: parado en una celda, se mira cual de sus 8 vecinos drena hacia
    ella, y se avanza al que trae mas agua. Repitiendo eso desde la boca de la
    quebrada se recorre la rama principal hasta la cabecera, dejando fuera los
    afluentes chicos.

    Por que aguas arriba y no aguas abajo: la desembocadura es, por definicion,
    el ultimo punto con terreno antes del mar o del borde. Aguas abajo de ahi no
    queda nada que recorrer. La trayectoria del flujo es el camino que baja
    desde la cabecera hasta esa boca, y se reconstruye al reves.

    `min_celdas` corta el trazado cuando el cauce se vuelve tan chico que ya no
    concentra agua: por encima de ese punto hay ladera, no quebrada.
    """
    filas, columnas = fdir.shape
    recorrido = [(fila, col)]
    visitadas = {(fila, col)}

    while True:
        f, c = recorrido[-1]
        mejor, mejor_acc = None, -1.0

        for (df, dc), codigo in VECINDAD:
            vf, vc = f + df, c + dc
            if not (0 <= vf < filas and 0 <= vc < columnas):
                continue
            if (vf, vc) in visitadas:
                continue  # proteccion contra ciclos en zonas planas rellenadas
            if fdir[vf, vc] != codigo:
                continue  # ese vecino no drena hacia aca
            if acc[vf, vc] > mejor_acc:
                mejor, mejor_acc = (vf, vc), acc[vf, vc]

        if mejor is None or mejor_acc < min_celdas:
            break
        recorrido.append(mejor)
        visitadas.add(mejor)

    if len(recorrido) < 2:
        return None

    # De indices de la grilla a coordenadas del mundo, y se invierte el orden
    # para que la linea quede en el sentido natural: cabecera -> boca.
    puntos = [transform * (c + 0.5, f + 0.5) for f, c in reversed(recorrido)]
    return LineString(puntos)


def trazar_trayectorias(cuencas: gpd.GeoDataFrame, ruta_fdir: Path,
                        ruta_acc: Path, umbral_km2: float):
    """Arma la trayectoria de cada cuenca susceptible."""
    print("\nTrazando cauces principales...")

    with rasterio.open(ruta_fdir) as src:
        fdir = src.read(1)
        transform = src.transform
        m2_pixel = abs(transform.a * transform.e)
    with rasterio.open(ruta_acc) as src:
        acc = src.read(1)

    min_celdas = max(1, int(umbral_km2 * 1e6 / m2_pixel))
    print(f"  el cauce se corta bajo {umbral_km2} km2 drenados ({min_celdas} celdas)")

    inverso = ~transform
    registros = []

    for _, cuenca in cuencas.iterrows():
        col, fila = inverso * (cuenca["salida_x"], cuenca["salida_y"])
        fila, col = int(fila), int(col)
        if not (0 <= fila < fdir.shape[0] and 0 <= col < fdir.shape[1]):
            continue

        linea = cauce_principal(fdir, acc, fila, col, transform, min_celdas)
        if linea is None:
            continue

        registros.append({
            "id_cuenca": cuenca["id_cuenca"],
            "clase": cuenca["clase"],
            "melton": cuenca["melton"],
            "area_km2": cuenca["area_km2"],
            "pend_media_g": cuenca["pend_media_g"],
            "largo_cauce_km": linea.length / 1000.0,
            "geometry": linea,
        })

    gdf = gpd.GeoDataFrame(registros, crs=CRS_METRICO)
    print(f"  {len(gdf)} trayectorias trazadas de {len(cuencas)} cuencas")
    print(f"  largo del cauce: mediana {gdf['largo_cauce_km'].median():.2f} km, "
          f"maximo {gdf['largo_cauce_km'].max():.2f} km")
    return gdf


# ===========================================================================
# Verificacion previa al cruce
# ===========================================================================

def verificar_solape(trayectorias: gpd.GeoDataFrame, vias: gpd.GeoDataFrame):
    """Comprueba que ambas capas ocupen el mismo pedazo de mundo.

    Es la trampa clasica de este tipo de cruce: si un CRS quedo mal, las capas
    caen en lugares distintos, la interseccion da cero, y el resultado se lee
    como "no hay riesgo" cuando en realidad es "no se cruzaron los datos".
    Mejor detenerse aca que publicar un cero falso.
    """
    a = trayectorias.total_bounds
    b = vias.total_bounds
    print("\nVerificando que las capas se solapen...")
    print(f"  trayectorias: X {a[0]:>9.0f}-{a[2]:<9.0f} Y {a[1]:>9.0f}-{a[3]:<9.0f}")
    print(f"  red vial    : X {b[0]:>9.0f}-{b[2]:<9.0f} Y {b[1]:>9.0f}-{b[3]:<9.0f}")

    solapan = not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])
    if not solapan:
        sys.exit(
            "Las capas NO se solapan. Casi seguro es un problema de CRS.\n"
            "Con este estado, cualquier resultado seria falso."
        )
    if trayectorias.crs != vias.crs:
        sys.exit(f"CRS distintos: {trayectorias.crs} vs {vias.crs}")
    print(f"  ok, ambas en {trayectorias.crs.to_string()}")


# ===========================================================================
# Pasos 3 y 4 - Puntos de corte y prioridad
# ===========================================================================

def puntos_de_corte(trayectorias, vias, comunas, tolerancia_m: float):
    """Cruza cauces con vias y arma la tabla de cortes candidatos.

    La tolerancia existe por la resolucion del DEM. El cauce se dibujo sobre una
    grilla de 30 m, asi que su posicion tiene una incertidumbre de mas o menos un
    pixel. Exigir que las dos lineas se toquen exactamente perderia cruces
    reales por unos metros de desajuste entre el DEM y el trazado de OSM.
    """
    print("\nCruzando trayectorias con la red vial...")

    # El buffer convierte el cauce en un corredor angosto; la interseccion con
    # la via da el trozo de camino que cae dentro, y su centro es el punto de
    # corte. Se usa sjoin primero para no comparar todo contra todo.
    corredores = trayectorias.copy()
    corredores["geometry"] = corredores.geometry.buffer(tolerancia_m)

    cruces = gpd.sjoin(vias, corredores, how="inner", predicate="intersects")
    print(f"  {len(cruces)} pares via-trayectoria se tocan")

    registros = []
    for _, fila in cruces.iterrows():
        corredor = corredores.loc[fila["index_right"], "geometry"]
        trozo = fila.geometry.intersection(corredor)
        if trozo.is_empty:
            continue

        punto = trozo.centroid
        registros.append({
            "id_cuenca": fila["id_cuenca"],
            "clase": fila["clase"],
            "melton": fila["melton"],
            "area_cuenca_km2": fila["area_km2"],
            "via_nombre": fila.get("name"),
            "via_tipo": fila["highway"],
            "geometry": punto,
        })

    if not registros:
        sys.exit(
            "Cero puntos de corte. Eso no es un hallazgo, es un sintoma.\n"
            "Revisa CRS, extension de la descarga OSM y la tolerancia."
        )

    puntos = gpd.GeoDataFrame(registros, crs=CRS_METRICO)

    # Varias aristas de OSM son trozos de una misma calle, asi que un mismo
    # cruce aparece repetido. Se colapsan los que caen casi encima.
    puntos = _fusionar_cercanos(puntos, radio_m=tolerancia_m)
    print(f"  {len(puntos)} puntos de corte tras fusionar duplicados")

    # --- comuna ---
    puntos = gpd.sjoin(puntos, comunas[["comuna", "geometry"]],
                       how="left", predicate="within").drop(columns="index_right")

    # --- coordenadas en los dos sistemas ---
    puntos["utm_x"] = puntos.geometry.x.round(1)
    puntos["utm_y"] = puntos.geometry.y.round(1)
    geo = puntos.to_crs(CRS_GEOGRAFICO)
    puntos["lon"] = geo.geometry.x.round(6)
    puntos["lat"] = geo.geometry.y.round(6)

    return puntos


def _fusionar_cercanos(puntos: gpd.GeoDataFrame, radio_m: float):
    """Colapsa puntos de la misma cuenca y misma via que caen casi encima."""
    puntos = puntos.copy()
    puntos["_celda"] = list(zip(
        (puntos.geometry.x / radio_m).round().astype(int),
        (puntos.geometry.y / radio_m).round().astype(int),
    ))
    return (puntos
            .drop_duplicates(subset=["id_cuenca", "via_tipo", "via_nombre", "_celda"])
            .drop(columns="_celda")
            .reset_index(drop=True))


def priorizar(puntos: gpd.GeoDataFrame):
    """Ordena los cortes combinando peligro de la cuenca con importancia de la via.

    El criterio: ordenar solo por susceptibilidad respondería "que quebrada es
    mas peligrosa", que es la pregunta de M2 y ya esta contestada. La pregunta
    de M3 es otra: **cual de estos cortes tiene peores consecuencias**. Y ahi una
    cuenca de clase media que corta la Ruta 5 pesa mas que una de clase alta que
    corta una huella, porque la troncal aisla a mucha mas gente.

    prioridad = 0,5 x peligro_de_la_cuenca + 0,5 x importancia_de_la_via

    Los dos terminos van de 0 a 1, asi que la prioridad tambien. Ninguno de los
    pesos esta calibrado: son juicios explicitos, puestos arriba como constantes
    para poder discutirlos y moverlos.
    """
    puntos = puntos.copy()
    puntos["peso_clase"] = puntos["clase"].map(PESO_CLASE).fillna(0.0)
    puntos["peso_via"] = puntos["via_tipo"].map(PESO_VIA).fillna(PESO_VIA_DEFECTO)
    puntos["prioridad"] = (
        PONDERADOR_CLASE * puntos["peso_clase"]
        + PONDERADOR_VIA * puntos["peso_via"]
    ).round(4)

    puntos = puntos.sort_values(
        ["prioridad", "melton"], ascending=False
    ).reset_index(drop=True)
    puntos.insert(0, "rank", puntos.index + 1)
    return puntos


# ===========================================================================
# Paso 5 - Zonas urbanas alcanzadas
# ===========================================================================

def alcance_urbano(trayectorias, urbano):
    """Marca que trayectorias entran en zona poblada, y en cual.

    Este es el dato que le importa a una autoridad: no que se corte un camino,
    sino que el flujo entre donde vive gente. Se reporta aparte a proposito,
    porque significa algo distinto que un corte de ruta.
    """
    print("\nRevisando entrada a zonas urbanas...")
    if urbano.empty:
        print("  no hay poligonos urbanos en la descarga")
        return gpd.GeoDataFrame(columns=["id_cuenca", "clase", "localidad"])

    urbano = urbano[urbano.geometry.is_valid & ~urbano.geometry.is_empty].copy()
    cruces = gpd.sjoin(trayectorias, urbano, how="inner", predicate="intersects")

    if cruces.empty:
        print("  ninguna trayectoria entra en zona urbana")
        return gpd.GeoDataFrame(columns=["id_cuenca", "clase", "localidad"])

    columna = "name" if "name" in cruces.columns else None
    cruces["localidad"] = (cruces[columna].fillna("(poligono sin nombre)")
                           if columna else "(poligono sin nombre)")

    resumen = (cruces[["id_cuenca", "clase", "melton", "localidad"]]
               .drop_duplicates()
               .sort_values(["localidad", "melton"], ascending=[True, False])
               .reset_index(drop=True))

    con_nombre = resumen[resumen["localidad"] != "(poligono sin nombre)"]
    print(f"  {resumen['id_cuenca'].nunique()} trayectorias entran en zona urbana")
    print(f"  {con_nombre['localidad'].nunique()} localidades con nombre alcanzadas")
    return resumen


# ===========================================================================
# Figura
# ===========================================================================

def figura(cuencas, trayectorias, vias, puntos, ruta_png: Path):
    """Mapa general + acercamiento a la zona con mas cortes."""
    colores = {"flujo_detritos": "#b2182b", "crecida_detritos": "#ef8a62"}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 11))

    # --- panel 1: la region completa ---
    cuencas.plot(ax=ax1, color="#e8eef4", edgecolor="#b8c4d0", linewidth=0.2)
    # Solo las vias con jerarquia alta: dibujar las 45.000 residenciales
    # convertiria el mapa en una mancha.
    troncales = vias[vias["highway"].isin(["motorway", "trunk", "primary", "secondary"])]
    troncales.plot(ax=ax1, color="#8c8c8c", linewidth=0.5)

    for clase, color in colores.items():
        sel = cuencas[cuencas["clase"] == clase]
        if not sel.empty:
            sel.plot(ax=ax1, color=color, edgecolor="none", alpha=0.75)

    trayectorias.plot(ax=ax1, color="#2166ac", linewidth=0.7)
    ax1.scatter(puntos["utm_x"], puntos["utm_y"], s=14, c="black",
                marker="x", linewidth=0.8, zorder=5)

    marcas = [mpatches.Patch(facecolor=c, label=k) for k, c in colores.items()]
    marcas += [
        plt.Line2D([], [], color="#2166ac", lw=1.2, label="cauce principal"),
        plt.Line2D([], [], color="#8c8c8c", lw=1.0, label="red vial troncal"),
        plt.Line2D([], [], color="black", marker="x", lw=0, label=f"corte ({len(puntos)})"),
    ]
    ax1.legend(handles=marcas, loc="upper right", fontsize=8)
    ax1.set_title(f"Exposicion vial | {len(trayectorias)} trayectorias, "
                  f"{len(puntos)} puntos de corte", fontsize=12)
    ax1.set_xticks([]); ax1.set_yticks([])

    # --- panel 2: acercamiento donde se concentran los cortes ---
    # El panel general no deja ver nada a escala de quebrada; este muestra el
    # sector con mas cortes, que es donde hay que mirar de verdad.
    if len(puntos):
        cx, cy = puntos["utm_x"].median(), puntos["utm_y"].median()
        lado = 18_000
        recuadro = (cx - lado, cy - lado, cx + lado, cy + lado)

        vias.cx[recuadro[0]:recuadro[2], recuadro[1]:recuadro[3]].plot(
            ax=ax2, color="#c0c0c0", linewidth=0.5)
        troncales.cx[recuadro[0]:recuadro[2], recuadro[1]:recuadro[3]].plot(
            ax=ax2, color="#6b6b6b", linewidth=1.4)
        for clase, color in colores.items():
            sel = cuencas[cuencas["clase"] == clase]
            if not sel.empty:
                sel.cx[recuadro[0]:recuadro[2], recuadro[1]:recuadro[3]].plot(
                    ax=ax2, color=color, alpha=0.55, edgecolor="black", linewidth=0.3)
        trayectorias.cx[recuadro[0]:recuadro[2], recuadro[1]:recuadro[3]].plot(
            ax=ax2, color="#2166ac", linewidth=1.4)

        dentro = puntos[(puntos["utm_x"].between(recuadro[0], recuadro[2]))
                        & (puntos["utm_y"].between(recuadro[1], recuadro[3]))]
        ax2.scatter(dentro["utm_x"], dentro["utm_y"], s=55, facecolor="none",
                    edgecolor="black", linewidth=1.3, zorder=5)
        ax2.set_xlim(recuadro[0], recuadro[2])
        ax2.set_ylim(recuadro[1], recuadro[3])
        ax2.set_title(f"Acercamiento (36 x 36 km) | {len(dentro)} cortes", fontsize=12)
    ax2.set_xticks([]); ax2.set_yticks([])

    fig.tight_layout()
    fig.savefig(ruta_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ===========================================================================
# Orquestacion
# ===========================================================================

def main():
    ap = argparse.ArgumentParser(
        description="M3 - Cruza las quebradas susceptibles con la red vial y urbana."
    )
    ap.add_argument("--procesados", type=Path, default=RAIZ / "data" / "processed")
    ap.add_argument("--cache-osm", type=Path, default=RAIZ / "data" / "raw" / "osm")
    ap.add_argument("--extracto-osm", type=Path, default=RUTA_EXTRACTO_OSM,
                    help="Extracto de Geofabrik con la red vial. Si existe se "
                         "usa en vez de consultar Overpass.")
    ap.add_argument("--umbral-cauce-km2", type=float, default=0.15,
                    help="Area drenada bajo la cual el cauce deja de trazarse. "
                         "Por defecto, el mismo valor con que M1 definio la red.")
    # 45 m es tolerancia geometrica, NO alcance de runout. Ver la nota sobre
    # ancho de corredor en la cabecera del archivo.
    ap.add_argument("--tolerancia-m", type=float, default=45.0,
                    help="Ancho del corredor alrededor del cauce. Absorbe la "
                         "incertidumbre de posicion del DEM de 30 m (~1,5 pixeles). "
                         "No es un alcance de propagacion.")
    ap.add_argument("--paso-tile", type=float, default=0.5,
                    help="Tamano en grados de cada cuadro de descarga OSM.")
    ap.add_argument("--cobertura-minima", type=float, default=COBERTURA_MINIMA,
                    help="Fraccion de la region que el DEM debe cubrir. El "
                         "valor por defecto es el mismo que exige M1: no tiene "
                         "sentido que M3 acepte un DEM que M1 habria rechazado.")
    ap.add_argument("--permitir-cobertura-parcial", action="store_true",
                    help="Corre igual con cobertura insuficiente. Las cifras "
                         "resultantes son provisorias y no publicables.")
    args = ap.parse_args()

    ruta_susc = args.procesados / "susceptibilidad.gpkg"
    ruta_fdir = args.procesados / "direccion_flujo.tif"
    ruta_acc = args.procesados / "acumulacion_flujo.tif"
    for ruta in (ruta_susc, ruta_fdir, ruta_acc):
        if not ruta.exists():
            sys.exit(f"Falta {ruta}\nCorre antes los scripts de M1 y M2.")

    cobertura = verificar_cobertura(
        args.procesados / "dem_utm19s.tif",
        RAIZ / "data" / "raw" / "limite_coquimbo.gpkg",
        args.cobertura_minima,
        args.permitir_cobertura_parcial,
    )

    cuencas = gpd.read_file(ruta_susc)
    objetivo = cuencas[cuencas["clase"].isin(CLASES_SUSCEPTIBLES)].copy()
    print(f"Cuencas susceptibles: {len(objetivo)} de {len(cuencas)}")
    print("  " + " · ".join(f"{k}: {v}" for k, v in
                            objetivo["clase"].value_counts().items()))

    # Paso 2 primero: define el area que hay que bajar de OSM.
    trayectorias = trazar_trayectorias(objetivo, ruta_fdir, ruta_acc,
                                       args.umbral_cauce_km2)

    # Se baja OSM alrededor de las trayectorias, no sobre la region entera: es
    # la misma informacion util con una fraccion de las consultas a Overpass.
    # `zona_util` es el conjunto de trayectorias engordado unos kilometros, y
    # sirve para saltarse los cuadros de mar abierto y de alta cordillera.
    margen = 5_000
    zona_util = (trayectorias.geometry.buffer(margen).union_all()
                 if hasattr(trayectorias.geometry, "union_all")
                 else trayectorias.geometry.buffer(margen).unary_union)
    zona_util_geo = gpd.GeoSeries([zona_util], crs=CRS_METRICO).to_crs(CRS_GEOGRAFICO).iloc[0]

    b = trayectorias.total_bounds
    caja = gpd.GeoSeries([Point(b[0] - margen, b[1] - margen),
                          Point(b[2] + margen, b[3] + margen)],
                         crs=CRS_METRICO).to_crs(CRS_GEOGRAFICO)
    bbox = (caja.iloc[0].x, caja.iloc[0].y, caja.iloc[1].x, caja.iloc[1].y)

    # El extracto local es la fuente preferida; Overpass queda como respaldo
    # para el caso de que alguien corra esto sin haberlo bajado.
    if args.extracto_osm.exists():
        vias, urbano = cargar_osm_extracto(args.extracto_osm, bbox, args.cache_osm)
    else:
        print(f"No encuentro el extracto {args.extracto_osm.name}, "
              "se consultara Overpass.")
        print("  (bajalo de https://download.geofabrik.de/south-america/chile.html"
              " para no depender del servidor)")
        vias, urbano = descargar_osm(bbox, args.cache_osm, args.paso_tile, zona_util_geo)
    print(f"  red vial: {len(vias):,} tramos | zonas urbanas: {len(urbano):,} poligonos")

    verificar_solape(trayectorias, vias)

    print("\nBajando limites comunales...")
    comunas = gpd.read_file(URL_COMUNAS).to_crs(CRS_METRICO)
    comunas = comunas.rename(columns={"shapeName": "comuna"})

    puntos = puntos_de_corte(trayectorias, vias, comunas, args.tolerancia_m)
    puntos = priorizar(puntos)

    # Tanto un resultado vacio como uno desmedido son sintoma de error, no
    # hallazgo: conviene desconfiar antes de interpretar.
    #
    # El control se hace **por cuenca** y no sobre el total, y la razon es un
    # falso positivo real. El tope era 2.000 puntos absolutos, calibrado cuando
    # M2 entregaba 167 cuencas susceptibles. Al agregar las subcuencas de
    # confluencia pasaron a ser 2.589 y el total subio a 3.669, asi que la
    # alarma sono sin que hubiera nada malo: los cortes por cuenca habian
    # BAJADO de 2,5 a 1,4, que es lo esperable porque las quebradas interiores
    # cruzan menos caminos que las costeras.
    #
    # Un tope absoluto mide el tamano del inventario; lo que interesa vigilar es
    # la densidad. Ocho cortes promedio por quebrada si seria sintoma de que la
    # tolerancia esta ensanchando el corredor y cruzando vias que no toca.
    cortes_por_cuenca = len(puntos) / max(len(trayectorias), 1)
    if cortes_por_cuenca > 8:
        print(f"\n  ATENCION: {cortes_por_cuenca:.1f} cortes por cuenca es mucho "
              f"({len(puntos)} puntos sobre {len(trayectorias)} trayectorias).\n"
              "  Revisa la tolerancia antes de creerle al resultado.")
    elif len(puntos) < 10:
        print(f"\n  ATENCION: solo {len(puntos)} puntos de corte. "
              "Revisa que las capas se solapen de verdad.")

    urbanas = alcance_urbano(trayectorias, urbano)

    # --- salidas ---
    args.procesados.mkdir(parents=True, exist_ok=True)
    dir_outputs = RAIZ / "outputs"
    dir_outputs.mkdir(parents=True, exist_ok=True)

    puntos.to_file(args.procesados / "puntos_corte.gpkg",
                   layer="puntos_corte", driver="GPKG")
    trayectorias.to_file(args.procesados / "trayectorias.gpkg",
                         layer="trayectorias", driver="GPKG")

    columnas_csv = ["rank", "prioridad", "via_nombre", "via_tipo", "comuna",
                    "clase", "melton", "area_cuenca_km2", "id_cuenca",
                    "lat", "lon", "utm_x", "utm_y"]
    puntos[columnas_csv].to_csv(dir_outputs / "m3_puntos_corte.csv",
                                index=False, encoding="utf-8-sig")
    if not urbanas.empty:
        urbanas.to_csv(dir_outputs / "m3_localidades.csv",
                       index=False, encoding="utf-8-sig")

    figura(cuencas, trayectorias, vias, puntos,
           dir_outputs / "m3_exposicion.png")

    # --- resumen en pantalla ---
    print("\n" + "=" * 66)
    print(f"Puntos de corte: {len(puntos)}")
    print("\nPor jerarquia de via:")
    for tipo, n in puntos["via_tipo"].value_counts().items():
        print(f"  {tipo:<16} {n:>5}   (peso {PESO_VIA.get(tipo, PESO_VIA_DEFECTO):.2f})")

    print("\nLas 12 vias mas afectadas:")
    top = (puntos.groupby(["via_nombre", "via_tipo"])
           .agg(cortes=("rank", "size"), prioridad_max=("prioridad", "max"))
           .sort_values(["prioridad_max", "cortes"], ascending=False).head(12))
    print(top.to_string())

    print("\nLos 12 cortes de mayor prioridad:")
    cols = ["rank", "prioridad", "via_nombre", "via_tipo", "comuna", "clase", "melton"]
    print(puntos[cols].head(12).to_string(index=False,
                                          float_format=lambda v: f"{v:.2f}"))

    print(f"\n  capa   -> puntos_corte.gpkg, trayectorias.gpkg")
    print(f"  tabla  -> m3_puntos_corte.csv")
    print(f"  figura -> m3_exposicion.png")


if __name__ == "__main__":
    main()
