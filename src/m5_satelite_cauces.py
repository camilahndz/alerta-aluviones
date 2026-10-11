"""
M5 - Etiquetas satelitales: que cauces NO cambiaron en cada temporada.

La idea de fondo:

    Hasta octubre de 2026 un "negativo" en este proyecto era la ausencia de una
    nota de prensa: un episodio en que llovio y nadie reporto nada. Eso hace que
    la precision sea una cota inferior y que cualquier calibracion quede
    sesgada hacia arriba. Este script produce negativos OBSERVADOS: cauces que
    Sentinel-2 ve sin cambio entre un septiembre y el siguiente.

    El piloto (m5_satelite_piloto.py) dejo dos lecciones que fijan el diseno:

    1. Hay que comparar la misma epoca del anio. Julio contra septiembre lo
       dominan el reverdecimiento despues de la lluvia y las sombras, que
       cambian con la altura del sol. Aca se compara septiembre con septiembre:
       2024 contra 2025 para la temporada 2025, y 2025 contra 2026 para la
       temporada 2026. Los tres septiembres vienen despues de inviernos con
       lluvia, asi que el reverdecimiento pesa parecido en las dos puntas.

    2. Lo que el satelite ve con claridad es por donde corrio agua con energia,
       y eso no es lo mismo que un flujo de detritos. Por eso las etiquetas que
       salen de aca son sobre todo NEGATIVOS: un cauce que no gano suelo
       desnudo frente a sus propias laderas no recibio sedimento fresco.

LA TRAMPA QUE OBLIGA A MIRAR SOLO LOS NEGATIVOS

    En un anio humedo las laderas reverdecen y el lecho arenoso de un cauce no.
    Medido como "el cauce gano suelo desnudo respecto de sus laderas", eso da un
    cambio positivo sin que haya pasado ningun flujo. O sea que la clase
    "cambio" esta contaminada en una direccion conocida: tiene falsos positivos
    por reverdecimiento diferencial. La clase "sin cambio" no lo esta, porque
    el sesgo empuja hacia arriba: un cauce que ni siquiera asi muestra cambio,
    no lo tuvo.

    Por eso los positivos de la evaluacion siguen siendo los de prensa, y el
    satelite aporta los negativos. La clase "cambio" se reporta, pero no se usa
    como verdad.

LA METRICA

    Para cada cuenca susceptible, sobre su cauce principal (las trayectorias de
    M3):

        delta = mediana(dBSI en el cauce) - mediana(dBSI en sus laderas)

    con dBSI el cambio del indice de suelo desnudo entre los dos septiembres, el
    cauce como una franja de 15 m alrededor de la linea y las laderas como un
    anillo de 45 a 150 m. Restar las laderas descuenta lo que cambio en todo el
    paisaje: un anio mas verde, una escena mas brillante.

    Solo cuentan los pixeles que la capa SCL de las dos fechas clasifica como
    vegetacion, suelo, agua o sin clasificar. Nubes, sombras de nube, sombras
    del relieve y nieve quedan fuera. Una cuenca con menos de la mitad del cauce
    valido, o con menos de 10 pixeles, queda "sin dato".

EL UMBRAL SALE DE UN NULO, NO DE LAS ETIQUETAS

    Elegir el umbral mirando cuales quebradas reporto la prensa seria calibrar
    el detector contra lo que despues se usa para validarlo. En vez de eso, por
    cada cuenca se mide la misma metrica sobre dos lineas paralelas al cauce, a
    200 m a cada lado, ya en la ladera. Esas lineas no son cauces: su delta es
    lo que la metrica da en terreno donde no corrio nada, con las mismas fechas,
    las mismas nubes y el mismo proceso. Su distribucion es el ruido.

    Las clases, fijadas antes de mirar los resultados:

        sin_cambio  delta <= percentil 75 del nulo de esa temporada
        cambio      delta >  percentil 95 del nulo
        dudoso      entre los dos
        sin_dato    menos de la mitad del cauce visible en las dos fechas

LA PRUEBA DEL DETECTOR

    Si el metodo sirve, las quebradas que la prensa reporto activadas tienen
    que mostrar mas cambio que las demas. Se compara en la misma temporada,
    contra todas las cuencas y contra las de la misma comuna. Si no se separan,
    el detector no sirve y se dice: los negativos que produce no valdrian nada.

LO QUE SALIO (corrida del 10-10-2026): EL DETECTOR NO PASA LA PRUEBA

    En 2026 las unidades cerca de las quebradas reportadas cambiaron MENOS que
    las demas: AUC 0,37, y 0,39 contra las de su misma comuna. En 2025, 0,63.
    Con la regla de arriba, estos negativos no se usan.

    m5_satelite_troncos.py explica por que, y el porque importa mas que los
    negativos. El mismo detector, aplicado al TRONCO de cada quebrada
    reportada, ve las activaciones de 2026 con claridad (AUC 0,89 contra sus
    nulos; Santa Gracia cambio en el 82% de sus tramos, Marquesa en el 72%).
    Lo que fallaba era el objeto: 15 de las 23 quebradas reportadas drenan mas
    de 50 km2, el tope de las unidades de M1, y las unidades que las tocan son
    afluentes chicos que no hicieron nada.

    Tampoco sirve a escala de tronco para producir negativos: la mitad de los
    troncos que nadie reporto tambien cambio (46% contra 66%; AUC 0,64 entre
    unos y otros). O la prensa reporto una parte de lo que bajo, o el
    reverdecimiento diferencial pesa mas de lo que este metodo descuenta, y con
    estos datos no se distingue.

Uso:

    python src/m5_satelite_cauces.py                 # las 13 teselas de la region
    python src/m5_satelite_cauces.py --teselas 19JBG  # una sola, para probar

Escribe data/processed/satelite_cauces.gpkg y outputs/m5_satelite_cauces.csv.
Lee las imagenes por ventana desde AWS, sin cuenta: unos 3 GB de transferencia
para la region completa.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parent.parent
STAC = "https://earth-search.aws.element84.com/v1/search"
CRS_METRICO = "EPSG:32719"

# Las tres fechas. Cada ventana cae entre dos sistemas frontales segun VIPNET:
# en septiembre de 2024 lo mas grande es 4,2 mm el 19; en 2025 el frontal
# siguiente es el del 26 de septiembre; 2026 no tiene dato despues del 23 de
# agosto, que es donde termina la ventana de M4.
PERIODOS = {
    2024: ("2024-09-01", "2024-09-18"),
    2025: ("2025-09-01", "2025-09-20"),
    2026: ("2026-08-28", "2026-09-16"),
}
# Temporada = (septiembre de antes, septiembre de despues).
TEMPORADAS = {2025: (2024, 2025), 2026: (2025, 2026)}

BANDAS = ("blue", "red", "nir", "swir16", "scl")
SCL_VALIDO = (4, 5, 6, 7)   # vegetacion, suelo desnudo, agua, sin clasificar

CAUCE_M = 15.0
ANILLO_M = (45.0, 150.0)
NULO_M = 200.0
MARGEN_M = 400.0            # ventana de lectura alrededor del cauce

FRACCION_VALIDA_MIN = 0.5
PIXELES_MIN = 10
PCT_SIN_CAMBIO = 75
PCT_CAMBIO = 95

HILOS = 8
REINTENTOS = 8           # con esperas de 10, 20, 40 y luego 60 s: aguanta ~5 min sin red

# Configuracion de GDAL para leer de AWS. Va al importar el modulo y no en main,
# porque m5_satelite_troncos.py y m5_troncos.py usan estas funciones sin pasar
# por main: la primera version la ponia en main, y un corte de red de un segundo
# tumbo una corrida de 15 minutos de m5_troncos.py.
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("GDAL_CACHEMAX", "512")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")
BLOQUE_CAUCES = 100         # cauces por tanda, para acotar la memoria


# =============================================================================
# Escenas
# =============================================================================

def buscar_escenas(bbox, desde, hasta) -> list[dict]:
    """Todas las escenas Sentinel-2 L2A del recuadro en la ventana, paginando."""
    feats, url = [], STAC
    cuerpo = {"collections": ["sentinel-2-l2a"], "bbox": list(bbox), "limit": 200,
              "datetime": f"{desde}T00:00:00Z/{hasta}T23:59:59Z"}
    while True:
        r = requests.post(url, json=cuerpo, timeout=120)
        r.raise_for_status()
        js = r.json()
        feats += js["features"]
        sig = [l for l in js.get("links", []) if l.get("rel") == "next"]
        if not sig:
            return feats
        cuerpo = sig[0].get("body", cuerpo)
        url = sig[0]["href"]


def tesela(item) -> str:
    return item["id"].split("_")[1]


def _costo(it) -> float:
    """Nube mas pixeles sin dato, en % de la tesela.

    Solo la nube no basta. Una escena del borde de la franja del satelite cubre
    media tesela y por eso trae poca nube: la primera version la elegia, y 665
    cauces quedaban fuera de toda huella.
    """
    p = it["properties"]
    return p.get("eo:cloud_cover", 100) + p.get("s2:nodata_pixel_percentage", 100)


def elegir_escenas(bbox) -> dict:
    """Por tesela y por periodo, la escena con menos nube y menos vacio.

    La nube de la tesela es solo el criterio de eleccion. La que importa es la
    de cada cauce, y esa se mide pixel por pixel con la capa SCL.
    """
    elegidas = {}
    for anio, (desde, hasta) in PERIODOS.items():
        for it in buscar_escenas(bbox, desde, hasta):
            clave = (tesela(it), anio)
            if clave not in elegidas or _costo(it) < _costo(elegidas[clave]):
                elegidas[clave] = it
    return elegidas


def asignar_teselas(cauces, elegidas):
    """A cada cauce, una tesela que lo contenga entero en las tres fechas.

    Las teselas se solapan unos 10 km y el borde de la franja del satelite
    cambia entre pasadas, asi que se exige la ventana completa dentro de la
    huella de las tres escenas. Entre las que cumplen, la de menos nube sumada.
    """
    import geopandas as gpd
    from shapely.geometry import shape

    huellas = {}
    for (t, anio), it in elegidas.items():
        huellas.setdefault(t, []).append((shape(it["geometry"]),
                                          it["properties"]["eo:cloud_cover"]))
    candidatas = []
    for t, lista in huellas.items():
        if len(lista) < len(PERIODOS):
            continue
        huella = lista[0][0]
        for g, _ in lista[1:]:
            huella = huella.intersection(g)
        candidatas.append({"tesela": t, "nube": sum(n for _, n in lista),
                           "geometry": huella})
    teselas = gpd.GeoDataFrame(candidatas, crs="EPSG:4326").to_crs(cauces.crs)

    ventanas = cauces.geometry.buffer(MARGEN_M)
    asignada = []
    for v in ventanas:
        dentro = teselas[teselas.geometry.contains(v)]
        asignada.append(dentro.sort_values("nube")["tesela"].iloc[0] if len(dentro) else None)
    return pd.Series(asignada, index=cauces.index)


# =============================================================================
# Lectura y metrica
# =============================================================================

def leer_banda(href, ventanas_utm, crs_tesela):
    """Lee una banda en la ventana de cada cauce, a 10 m. Devuelve dict id -> arreglo.

    Se abre una sola vez por banda y fecha, y se recorren todos los cauces de la
    tesela con el mismo archivo abierto: GDAL guarda los bloques ya bajados, y
    los cauces vecinos comparten bloques.
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds

    from rasterio.errors import RasterioIOError

    # Un error de red reabre el archivo y sigue desde el cauce donde quedo. Los
    # ya leidos no se repiten. Si el mismo cauce falla REINTENTOS veces, el
    # error sube: no se inventa un arreglo vacio, que se leeria como "sin dato".
    #
    # Cada reintento pide la URL con un parametro distinto. GDAL guarda en
    # memoria lo que bajo de cada URL, y un bloque que llego cortado se
    # releeria cortado desde ahi: el primer reintento fallaba igual que el
    # intento original. S3 ignora el parametro; GDAL lo trata como otro archivo.
    salida = {}
    pendientes = list(ventanas_utm.items())
    for intento in range(REINTENTOS):
        url = href if intento == 0 else f"{href}?reintento={intento}"
        try:
            with rasterio.open(url) as src:
                while pendientes:
                    cid, (x0, y0, x1, y1) = pendientes[0]
                    ancho = int(round((x1 - x0) / 10))
                    alto = int(round((y1 - y0) / 10))
                    w = from_bounds(x0, y0, x1, y1, src.transform)
                    salida[cid] = src.read(1, window=w, out_shape=(alto, ancho), boundless=True,
                                           fill_value=0, resampling=Resampling.nearest)
                    pendientes.pop(0)
            return salida
        except RasterioIOError:
            if intento == REINTENTOS - 1:
                raise
            time.sleep(min(60, 10 * 2 ** intento))
    return salida


def indices(b):
    """BSI (indice de suelo desnudo) y validez SCL de una fecha."""
    blue, red, nir, swir = (b[k].astype("float32") for k in ("blue", "red", "nir", "swir16"))
    a, v = swir + red, nir + blue
    bsi = (a - v) / np.where(a + v == 0, np.nan, a + v)
    valido = np.isin(b["scl"], SCL_VALIDO)
    return bsi, valido


def delta(dif, valido, franja, anillo):
    """Mediana del cambio en la franja menos mediana en el anillo, con su cobertura."""
    f = franja & valido & np.isfinite(dif)
    a = anillo & valido & np.isfinite(dif)
    n_franja = int(franja.sum())
    frac = f.sum() / n_franja if n_franja else 0.0
    if f.sum() < PIXELES_MIN or a.sum() < PIXELES_MIN:
        return np.nan, frac
    return float(np.median(dif[f]) - np.median(dif[a])), frac


def mascaras(linea, transform, forma):
    """Franja del cauce y anillo de laderas, rasterizados en la ventana."""
    from rasterio.features import rasterize

    def r(g):
        if g.is_empty:
            return np.zeros(forma, dtype=bool)
        return rasterize([(g, 1)], out_shape=forma, transform=transform,
                         fill=0, dtype="uint8").astype(bool)

    franja = r(linea.buffer(CAUCE_M))
    anillo = r(linea.buffer(ANILLO_M[1]).difference(linea.buffer(ANILLO_M[0])))
    return franja, anillo


def procesar_tesela(t, cauces_t, elegidas, crs_tesela, registro):
    """Todas las metricas de los cauces de una tesela, en tandas.

    Las tandas se arman con cauces vecinos (ordenados por franjas de 10 km y
    despues por x) para que compartan los bloques de imagen ya bajados.
    """
    orden = cauces_t.assign(_f=(cauces_t.geometry.centroid.y // 10000),
                            _x=cauces_t.geometry.centroid.x).sort_values(["_f", "_x"])
    filas = []
    for i in range(0, len(orden), BLOQUE_CAUCES):
        filas += _procesar_tanda(t, orden.iloc[i:i + BLOQUE_CAUCES], elegidas, crs_tesela)
    registro(f"  {t}: {len(filas)} cauces")
    return filas


def _procesar_tanda(t, cauces_t, elegidas, crs_tesela):
    from rasterio.transform import from_origin
    from shapely.geometry import LineString

    geoms = cauces_t.to_crs(crs_tesela)
    ventanas = {}
    for cid, g in zip(geoms["id_cuenca"], geoms.geometry):
        x0, y0, x1, y1 = g.buffer(MARGEN_M).bounds
        # Alinear a la grilla de 10 m de Sentinel-2, que en UTM cae en multiplos de 10.
        x0, y0 = np.floor(x0 / 10) * 10, np.floor(y0 / 10) * 10
        x1, y1 = np.ceil(x1 / 10) * 10, np.ceil(y1 / 10) * 10
        ventanas[cid] = (x0, y0, x1, y1)

    # Las 15 lecturas (5 bandas x 3 fechas) en paralelo: el cuello es la red.
    trabajos = {(anio, banda): elegidas[(t, anio)]["assets"][banda]["href"]
                for anio in PERIODOS for banda in BANDAS}
    with ThreadPoolExecutor(HILOS) as ex:
        fut = {k: ex.submit(leer_banda, href, ventanas, crs_tesela) for k, href in trabajos.items()}
        datos = {k: f.result() for k, f in fut.items()}

    filas = []
    for cid, g in zip(geoms["id_cuenca"], geoms.geometry):
        x0, y0, x1, y1 = ventanas[cid]
        forma = datos[(2024, "red")][cid].shape
        transform = from_origin(x0, y1, 10, 10)
        lineas = {"cauce": g}
        for signo, nombre in ((1, "nulo_a"), (-1, "nulo_b")):
            try:
                lineas[nombre] = g.offset_curve(signo * NULO_M)
            except Exception:  # noqa: BLE001 - una linea degenerada no aborta la region
                lineas[nombre] = LineString()
        masc = {k: mascaras(v, transform, forma) for k, v in lineas.items()}

        idx = {anio: indices({b: datos[(anio, b)][cid] for b in BANDAS}) for anio in PERIODOS}
        fila = {"id_cuenca": cid, "tesela": t}
        for temp, (antes, despues) in TEMPORADAS.items():
            dif = idx[despues][0] - idx[antes][0]
            valido = idx[antes][1] & idx[despues][1]
            for k, (franja, anillo) in masc.items():
                d, frac = delta(dif, valido, franja, anillo)
                fila[f"delta_{k}_{temp}"] = d
                if k == "cauce":
                    fila[f"frac_valida_{temp}"] = frac
        filas.append(fila)
    return filas


# =============================================================================
# Clases y prueba del detector
# =============================================================================

def clasificar(tabla: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Aplica los percentiles del nulo de cada temporada."""
    umbrales = {}
    for temp in TEMPORADAS:
        nulo = pd.concat([tabla[f"delta_nulo_a_{temp}"], tabla[f"delta_nulo_b_{temp}"]]).dropna()
        q75, q95 = np.percentile(nulo, PCT_SIN_CAMBIO), np.percentile(nulo, PCT_CAMBIO)
        umbrales[temp] = (q75, q95, len(nulo))
        d = tabla[f"delta_cauce_{temp}"]
        sin_dato = d.isna() | (tabla[f"frac_valida_{temp}"] < FRACCION_VALIDA_MIN)
        clase = np.where(d > q95, "cambio", np.where(d <= q75, "sin_cambio", "dudoso"))
        tabla[f"clase_{temp}"] = np.where(sin_dato, "sin_dato", clase)
    return tabla, umbrales


def cuencas_reportadas(cauces, osm, comunas, radio_m=300.0):
    """Cuencas cuyo cauce pasa a menos de `radio_m` de cada quebrada de la prensa.

    Mas estricto que los 3 km de m5_validacion: aca se quiere la quebrada que
    se nombro, no las unidades que descargan cerca, porque se va a comparar su
    cauce con el de las vecinas.
    """
    import m5_calibracion as cal
    import m5_validacion as m5

    inv = cal.cargar_inventario()
    filas = []
    for _, e in inv.iterrows():
        if not (m5._texto(e["quebrada"]) or m5._texto(e["sector"])):
            continue
        geo, _ = m5.ubicar(e.to_dict(), osm, comunas)
        if geo is None:
            continue
        cerca = cauces[cauces.geometry.distance(geo) <= radio_m]
        temporada = cal_temporada(e["fecha"])
        for cid in cerca["id_cuenca"]:
            filas.append({"id_cuenca": cid, "temporada": temporada,
                          "evidencia": e["evidencia"], "entrada": e["id"],
                          "comuna": e["comuna"]})
    return pd.DataFrame(filas)


def cal_temporada(fecha: str) -> int | None:
    """La temporada satelital (septiembre a septiembre) a la que cae una fecha."""
    for temp, (antes, despues) in TEMPORADAS.items():
        if PERIODOS[antes][1] < fecha <= PERIODOS[despues][0]:
            return temp
    return None


def main():
    ap = argparse.ArgumentParser(description="M5 - Cauces sin cambio desde Sentinel-2.")
    ap.add_argument("--teselas", nargs="*", help="procesar solo estas teselas (prueba)")
    ap.add_argument("--procesados", type=Path, default=RAIZ / "data" / "processed")
    args = ap.parse_args()


    import geopandas as gpd

    print("=" * 74)
    print("M5 - Etiquetas satelitales de cauces, septiembre contra septiembre")
    print("=" * 74)

    cauces = gpd.read_file(args.procesados / "trayectorias.gpkg").to_crs(CRS_METRICO)
    # Desde octubre de 2026 M3 traza tambien la clase inundacion, que este
    # detector no se diseno para mirar.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from clases_cuenca import CLASES_SUSCEPTIBLES
    cauces = cauces[cauces["clase"].isin(CLASES_SUSCEPTIBLES)].reset_index(drop=True)
    print(f"\nCauces principales de cuencas susceptibles (M3): {len(cauces)}")

    bbox = cauces.to_crs(4326).total_bounds
    elegidas = elegir_escenas(bbox)
    cauces["tesela"] = asignar_teselas(cauces, elegidas)
    sin_tesela = int(cauces["tesela"].isna().sum())
    print(f"  {sin_tesela} cauces sin una tesela que los contenga en las tres fechas")

    print("\nEscenas elegidas (nube de la tesela, %):")
    for t in sorted(cauces["tesela"].dropna().unique()):
        partes = [f"{elegidas[(t, a)]['properties']['datetime'][:10]} "
                  f"({elegidas[(t, a)]['properties']['eo:cloud_cover']:.1f})" for a in PERIODOS]
        print(f"  {t}  {'  '.join(partes)}  {int((cauces['tesela'] == t).sum()):>4} cauces")

    teselas = sorted(cauces["tesela"].dropna().unique())
    if args.teselas:
        teselas = [t for t in teselas if t in args.teselas]

    print("\nLeyendo ventanas de 5 bandas x 3 fechas...")
    t0 = time.time()
    filas = []
    for t in teselas:
        sel = cauces[cauces["tesela"] == t]
        crs_t = f"EPSG:327{t[:2]}"
        filas += procesar_tesela(t, sel, elegidas, crs_t, print)
        print(f"    {time.time() - t0:.0f} s", flush=True)

    tabla, umbrales = clasificar(pd.DataFrame(filas))

    print("\nNulo (lineas paralelas a 200 m) y clases, por temporada:")
    for temp, (q75, q95, n) in umbrales.items():
        c = tabla[f"clase_{temp}"].value_counts()
        print(f"  {temp}: nulo n={n}, p75 {q75:+.4f}, p95 {q95:+.4f} | " + ", ".join(
            f"{k} {int(c.get(k, 0))}" for k in ("sin_cambio", "dudoso", "cambio", "sin_dato")))
        d = tabla[f"delta_cauce_{temp}"].dropna()
        print(f"        delta del cauce: p25 {d.quantile(.25):+.4f}, mediana {d.median():+.4f}, "
              f"p75 {d.quantile(.75):+.4f}")

    # --- La prueba del detector ---
    print("\n" + "-" * 74)
    print("Prueba del detector: las quebradas de la prensa contra las demas")
    print("-" * 74)
    import warnings

    import m5_calibracion as cal
    import m5_validacion as m5
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        osm = m5.cargar_osm()
        comunas = m5.cargar_comunas()
    rep = cuencas_reportadas(cauces, osm, comunas)

    # Comuna de cada cauce, por su punto medio: la comparacion justa es contra
    # cauces del mismo paisaje, que reverdecieron parecido.
    medio = cauces[["id_cuenca"]].copy()
    medio["geometry"] = cauces.geometry.interpolate(0.5, normalized=True)
    medio = gpd.sjoin(gpd.GeoDataFrame(medio, crs=cauces.crs),
                      comunas[["comuna", "geometry"]], how="left")
    comuna_de = medio.drop_duplicates("id_cuenca").set_index("id_cuenca")["comuna"]

    for temp in TEMPORADAS:
        r = rep[(rep["temporada"] == temp)
                & rep["evidencia"].isin(("aluvion", "activacion", "activacion_menor"))]
        ids = set(r["id_cuenca"])
        d = tabla.set_index("id_cuenca")[f"delta_cauce_{temp}"]
        clase = tabla.set_index("id_cuenca")[f"clase_{temp}"]
        y = d.index.isin(ids).astype(int)
        ok = d.notna().to_numpy()
        print(f"\n  temporada {temp}: {len(ids)} cuencas reportadas por la prensa "
              f"({int((y[ok] == 1).sum())} con dato)")
        if (y[ok] == 1).sum():
            print(f"    AUC del delta, reportadas contra todas:          "
                  f"{cal.auc(y[ok], d.to_numpy()[ok]):.3f}")
            comunas_rep = set(comuna_de.reindex(list(ids)).dropna())
            sel = ok & comuna_de.reindex(d.index).isin(comunas_rep).to_numpy()
            print(f"    AUC del delta, contra las de sus mismas comunas: "
                  f"{cal.auc(y[sel], d.to_numpy()[sel]):.3f}  ({int(sel.sum())} cauces)")
            for etq, s in (("reportadas", y == 1), ("resto", y == 0)):
                c = clase[s].value_counts(normalize=True)
                print(f"    {etq:<11} " + ", ".join(
                    f"{k} {100 * c.get(k, 0):.0f}%" for k in ("sin_cambio", "dudoso", "cambio", "sin_dato")))

    salida = cauces[["id_cuenca", "geometry"]].merge(tabla, on="id_cuenca", how="left")
    salida.to_file(args.procesados / "satelite_cauces.gpkg", driver="GPKG")
    tabla.to_csv(RAIZ / "outputs" / "m5_satelite_cauces.csv", index=False, float_format="%.5f")
    rep.to_csv(RAIZ / "outputs" / "m5_satelite_reportadas.csv", index=False)
    print(f"\n  capa  -> satelite_cauces.gpkg")
    print(f"  tabla -> m5_satelite_cauces.csv, m5_satelite_reportadas.csv")


if __name__ == "__main__":
    main()
