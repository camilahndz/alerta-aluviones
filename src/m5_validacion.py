"""
M5 - Validacion: que dijo el modelo donde sabemos lo que paso.

QUE SE PUEDE MEDIR Y QUE NO

    La tentacion es armar una matriz de confusion y sacar precision, recall y
    AUC. No se puede, y conviene explicar por que antes de mostrar cualquier
    numero.

    Una matriz de confusion necesita saber, para cada cuenca, si se activo o no.
    El inventario que tenemos es de prensa y comunicados: registra donde hubo
    activaciones **que alguien reporto**. Una quebrada que bajo con fuerza en un
    cerro sin camino no esta en ninguna parte, y en la tabla figura igual que
    una que no se movio. O sea que hay positivos observados, pero **no hay
    negativos observados**.

    Con eso se puede estimar una sola cosa, y es la que importa:

        De las activaciones documentadas, cuantas el modelo marco.

    Eso es el recall, o sensibilidad. La precision -de las que el modelo marco,
    cuantas se activaron- NO es estimable: el modelo marca 668 cuencas y el
    inventario tiene 18 entradas. Que 650 no figuren no dice que sean falsos
    positivos; dice que nadie fue a mirar. Reportar una precision calculada
    contra ese inventario seria inventar 2.571 verdaderos negativos.

    Asi que este script reporta recall, reporta entrada por entrada que paso, y
    se niega explicitamente a reportar precision o AUC. Un numero que no se
    puede defender es peor que no tenerlo.

COMO SE UBICA CADA ENTRADA DEL INVENTARIO

    El inventario tiene nombres, no coordenadas. Se buscan en el extracto de
    OpenStreetMap que M3 ya usa, primero entre los cauces con nombre
    (`gis_osm_waterways_free`, donde las quebradas aparecen como "Quebrada X") y
    si no, entre los lugares poblados (`gis_osm_places_free`).

    Catorce de las dieciocho entradas calzan directo. Las otras cuatro necesitan
    un alias, y los cuatro estan escritos en ALIAS con su motivo: la prensa
    escribe "Cutum" y OSM tiene "Cutun Alto", escribe "estero de Punitaqui" y
    OSM tiene "Estero Punitaqui".

POR QUE SE EMPAREJA POR CERCANIA Y NO POR CONTENCION

    Esta es la decision que mas afecta el resultado y la primera version la tuvo
    mal.

    Lo obvio es buscar la unidad que **contiene** el punto reportado. Da el
    resultado equivocado casi siempre, porque la prensa reporta donde se **vio**
    el flujo: un cruce de ruta, un pueblo, un badem. Eso queda en el fondo del
    valle, que pertenece a la cuenca del rio y no a la quebrada que bajo. Con
    contencion, el aluvion del Islon calzaba con la cuenca del Elqui -9.408 km2,
    clase inundacion- y el modelo aparecia fallando cuando en realidad lo que
    fallaba era la pregunta.

    Entonces se buscan las unidades susceptibles a menos de `--radio-km` de la
    ubicacion. Son las quebradas que descargan ahi, que es de lo que habla la
    nota de prensa.

LOS TRES VEREDICTOS

    sin_cobertura   no hay ninguna unidad susceptible cerca. El modelo no se
                    equivoco: nunca evaluo ese lugar. Son fallas de alcance y se
                    cuentan aparte, porque mezclarlas con los errores de
                    prediccion infla el denominador y hace ver al modelo peor de
                    lo que es en lo que si intento.

    no_predicho     hay unidades susceptibles cerca y ninguna supero un umbral
                    de lluvia. Esto si es un error del modelo.

    predicho        al menos una unidad susceptible cerca supero Caine.

Uso:

    python src/m5_validacion.py
    python src/m5_validacion.py --radio-km 5     # mas generoso al emparejar
    python src/m5_validacion.py --solo-fuertes   # solo aluvion y activacion

Escribe outputs/m5_validacion.csv con una fila por entrada del inventario.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clases_cuenca import CLASES_SUSCEPTIBLES  # noqa: E402
from m4_umbrales import caine_intensidad_critica  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CRS_METRICO = "EPSG:32719"

INVENTARIO = RAIZ / "docs" / "inventario_activaciones_2026-07.csv"
OSM = RAIZ / "data" / "raw" / "osm" / "chile.gpkg"

# Recuadro de busqueda en OSM, con margen sobre la region.
BBOX = (-71.80, -32.30, -69.80, -29.00)

# Evidencia que cuenta como activacion defendible de flujo de detritos. Las
# otras -escurrimiento superficial, alerta preventiva- describen agua corriendo
# o un aviso, no material movilizandose. Ver el documento del inventario.
EVIDENCIA_FUERTE = ("aluvion", "activacion")

# Entradas cuyo nombre en prensa no calza literal con OSM. Cada alias es un
# juicio y por eso van con su motivo a la vista, en vez de escondidos en una
# funcion de normalizacion mas agresiva.
#
# La entrada 9 tenia el alias 'islon' porque el inventario no sabia que
# quebrada habia bajado y se ubicaba por el pueblo. Desde octubre de 2026 la
# entrada nombra la quebrada -Santa Gracia, segun SENAPRED- y se ubica por su
# cauce como todas las demas.
ALIAS = {
    "4": ("estero punitaqui",
          "la prensa escribe 'estero de Punitaqui', OSM 'Estero Punitaqui'"),
    "8": ("quebrada martinez",
          "la prensa escribe 'Quebrada de Martinez', OSM 'Quebrada Martinez'"),
    "13": ("cutun alto",
           "la prensa escribe 'Cutum' y 'Cutun'; OSM tiene 'Cutun Alto'"),
    "25": ("cutun alto",
           "la prensa escribe 'Cutun'; OSM tiene 'Cutun Alto'. Igual que la 13"),
}

# La ventana que se valida. gatillo.gpkg cubre tres inviernos desde octubre de
# 2026, y una cuenca que supero Caine en agosto de 2025 no predijo nada de julio
# de 2026. Sin este filtro el recall sube solo por tener mas anios en la capa.
VALIDACION_DESDE = "2026-06-01"
VALIDACION_HASTA = "2026-08-24"    # exclusivo: incluye todo el 23 de agosto

# Si una entrada trae comuna, solo valen los cauces que caen en ella o a menos
# de esto de su borde. Ver ubicar().
MARGEN_COMUNA_M = 2000.0


def sin_tildes(texto) -> str:
    bajo = str(texto or "").lower()
    return "".join(c for c in unicodedata.normalize("NFD", bajo)
                   if unicodedata.category(c) != "Mn")


def cargar_osm() -> gpd.GeoDataFrame:
    """Cauces y lugares con nombre del extracto, en un solo marco."""
    if not OSM.exists():
        sys.exit(f"Falta {OSM}\nCorre antes: python src/m3_preparar_osm.py")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cauces = gpd.read_file(OSM, layer="gis_osm_waterways_free", bbox=BBOX)
        lugares = gpd.read_file(OSM, layer="gis_osm_places_free", bbox=BBOX)

    cauces["capa"] = "cauce"
    lugares["capa"] = "lugar"
    cols = ["name", "fclass", "capa", "geometry"]
    osm = gpd.GeoDataFrame(
        pd.concat([cauces[cols], lugares[cols]], ignore_index=True), crs=cauces.crs)
    osm["clave"] = osm["name"].map(sin_tildes)
    return osm.to_crs(CRS_METRICO)


def cargar_comunas() -> gpd.GeoDataFrame:
    """Limites comunales, de la misma fuente y el mismo commit que usa M3."""
    from m3_exposicion import URL_COMUNAS
    comunas = gpd.read_file(URL_COMUNAS).to_crs(CRS_METRICO)
    comunas["clave"] = comunas["shapeName"].map(sin_tildes)
    return comunas[["shapeName", "clave", "geometry"]].rename(
        columns={"shapeName": "comuna"})


def _texto(valor) -> str:
    """Un campo del inventario como texto; un campo vacio llega como NaN."""
    return "" if pd.isna(valor) else str(valor)


def ubicar(fila: dict, osm: gpd.GeoDataFrame, comunas: gpd.GeoDataFrame | None = None):
    """Devuelve (geometria, como_se_encontro) para una entrada del inventario.

    Los cauces van primero: una entrada que nombra una quebrada se ubica mejor
    por su cauce que por el pueblo del mismo nombre, porque el cauce tiene largo
    y el pueblo es un punto.

    SI LA ENTRADA TRAE COMUNA, SE BUSCA EN ESA COMUNA

        La primera version unia todos los cauces de la region que contenian el
        nombre. Con 18 entradas de julio no se notaba; con el inventario de
        2024-2025 si: hay una Quebrada Las Barrancas en Canela y otra en
        Tongoycillo, y "San Carlos" o "El Arrayan" se repiten en varios valles.
        Unirlas le daba a cada entrada las unidades de todas sus homonimas, y
        un acierto en Tongoycillo contaba para Canela.

        Ahora, si hay comuna, el orden es: un cauce dentro de ella, un lugar
        dentro de ella, y recien entonces lo que haya en la region, con la nota
        FUERA DE COMUNA para que se vea. La comuna lleva un margen de 2 km,
        porque un cauce de borde se dibuja a veces del otro lado.

    EL NOMBRE SE BUSCA COMO PALABRAS COMPLETAS

        Con una busqueda de subcadena, "El Maite" de Monte Patria calzaba con
        "Quebrada El Maiten" de otra comuna. Se exige que el nombre empiece y
        termine en un limite de palabra.
    """
    alias = ALIAS.get(str(fila["id"]))
    clave = alias[0] if alias else sin_tildes(_texto(fila["quebrada"]) or _texto(fila["sector"]))
    if not clave:
        return None, "sin nombre en el inventario"

    zona = None
    comuna = sin_tildes(_texto(fila.get("comuna")))
    if comunas is not None and comuna:
        sel = comunas[comunas["clave"] == comuna]
        if not sel.empty:
            zona = sel.geometry.union_all().buffer(MARGEN_COMUNA_M)

    patron = rf"\b{re.escape(clave)}\b"
    candidatos = {capa: osm[(osm["capa"] == capa)
                            & osm["clave"].str.contains(patron, na=False, regex=True)]
                  for capa in ("cauce", "lugar")}
    sufijo = f" (alias: {alias[1]})" if alias else ""

    if zona is not None:
        for capa, hits in candidatos.items():
            dentro = hits[hits.intersects(zona)]
            if not dentro.empty:
                nota = f"{capa}: {dentro['name'].iloc[0]}"
                if len(dentro) < len(hits):
                    nota += f" ({len(dentro)} de {len(hits)} homonimos, los de {fila['comuna']})"
                return dentro.geometry.union_all(), nota + sufijo

    for capa, hits in candidatos.items():
        if not hits.empty:
            nota = f"{capa}: {hits['name'].iloc[0]}"
            if zona is not None:
                nota += f" FUERA DE COMUNA (ninguno en {fila['comuna']}; {len(hits)} en la region)"
            return hits.geometry.union_all(), nota + sufijo

    return None, "no esta en OSM"


def positivas_en_ventana(gatillo: pd.DataFrame, columna: str,
                         desde: str = VALIDACION_DESDE,
                         hasta: str = VALIDACION_HASTA) -> set:
    """Cuencas que superan el umbral en algun episodio que empieza en la ventana.

    gatillo.gpkg guarda las fechas en UTC; la ventana se fija en hora de Chile.
    """
    inicio = pd.to_datetime(gatillo["inicio"], utc=True).dt.tz_convert("America/Santiago")
    desde = pd.Timestamp(desde, tz="America/Santiago")
    hasta = pd.Timestamp(hasta, tz="America/Santiago")
    en_ventana = (inicio >= desde) & (inicio < hasta)
    supera = gatillo[columna].fillna(False).astype(bool)
    return set(gatillo.loc[en_ventana & supera, "id_cuenca"])


def main():
    ap = argparse.ArgumentParser(
        description="M5 - Compara el modelo contra las activaciones documentadas.")
    ap.add_argument("--procesados", type=Path, default=RAIZ / "data" / "processed")
    ap.add_argument("--radio-km", type=float, default=3.0,
                    help="Distancia dentro de la cual una unidad susceptible "
                         "cuenta como la quebrada que se activo.")
    ap.add_argument("--solo-fuertes", action="store_true",
                    help="Usa solo las entradas con evidencia de aluvion o "
                         "activacion, sin escurrimientos ni alertas.")
    args = ap.parse_args()

    ruta_susc = args.procesados / "susceptibilidad.gpkg"
    ruta_gat = args.procesados / "gatillo.gpkg"
    for ruta in (ruta_susc, ruta_gat, INVENTARIO):
        if not ruta.exists():
            sys.exit(f"Falta {ruta}")

    print("=" * 74)
    print("M5 - Validacion contra el invierno de 2026 (julio y agosto)")
    print("=" * 74)

    inventario = pd.read_csv(INVENTARIO, dtype=str)
    if args.solo_fuertes:
        inventario = inventario[inventario["evidencia"].isin(EVIDENCIA_FUERTE)]
    print(f"\nEntradas del inventario: {len(inventario)}")

    unidades = gpd.read_file(ruta_susc).to_crs(CRS_METRICO)
    susceptibles = unidades[unidades["clase"].isin(CLASES_SUSCEPTIBLES)]
    gatillo = gpd.read_file(ruta_gat)
    # Solo los episodios de la ventana que se valida: ver VALIDACION_DESDE.
    inicio = pd.to_datetime(gatillo["inicio"], utc=True).dt.tz_convert("America/Santiago")
    en_ventana = ((inicio >= pd.Timestamp(VALIDACION_DESDE, tz="America/Santiago"))
                  & (inicio < pd.Timestamp(VALIDACION_HASTA, tz="America/Santiago")))
    print(f"Pares cuenca-episodio en gatillo.gpkg: {len(gatillo):,}; en la ventana "
          f"{VALIDACION_DESDE} a {VALIDACION_HASTA}: {int(en_ventana.sum()):,}")
    gatillo = gatillo[en_ventana]
    # Las dos lecturas del mismo umbral, que M4 guarda en columnas distintas:
    # el episodio entero contra su peor ventana. Ver m4_umbrales.razon_critica.
    LECTURAS = {"episodio": "supera_caine", "ventana critica": "supera_caine_critico"}
    # Las mismas dos lecturas con la lluvia de la estacion, sin interpolar. M4
    # guarda las columnas originales con sufijo _estacion; compararlas mide
    # cuanto del recall viene de la interpolacion y cuanto del umbral.
    if "i_media_mm_h_estacion" in gatillo.columns:
        gatillo["supera_caine_sin_interp"] = (
            gatillo["i_media_mm_h_estacion"]
            >= caine_intensidad_critica(gatillo["duracion_h"].to_numpy()))
        gatillo["supera_critico_sin_interp"] = gatillo["razon_caine_critica_estacion"] >= 1.0
        LECTURAS.update({"episodio, estacion": "supera_caine_sin_interp",
                         "critica, estacion": "supera_critico_sin_interp"})
    positivas_por_lectura = {
        etiqueta: positivas_en_ventana(gatillo, col)
        for etiqueta, col in LECTURAS.items() if col in gatillo.columns
    }
    positivas = positivas_por_lectura["episodio"]
    print(f"Unidades susceptibles: {len(susceptibles):,}")
    for etiqueta, conjunto in positivas_por_lectura.items():
        print(f"Unidades que superan Caine ({etiqueta}): {len(conjunto):,}")

    print("\nUbicando cada entrada en OpenStreetMap...")
    osm = cargar_osm()
    comunas = cargar_comunas()

    radio_m = args.radio_km * 1000
    filas = []
    for _, entrada in inventario.iterrows():
        geo, como = ubicar(entrada.to_dict(), osm, comunas)
        # `or` no sirve: un campo vacio llega como NaN, que es verdadero.
        nombre = (_texto(entrada["quebrada"]) or _texto(entrada["sector"])
                  or "(sin nombre)")

        if geo is None:
            filas.append({**entrada, "nombre": nombre, "ubicacion": como,
                          "n_susceptibles": 0, "n_positivas": 0,
                          "veredicto": "sin_ubicar", "ids_positivas": "",
                          "ids_cercanas": ""})
            continue

        cerca = susceptibles[susceptibles.geometry.distance(geo) <= radio_m]
        acertadas = cerca[cerca["id_cuenca"].isin(positivas)]

        if cerca.empty:
            veredicto = "sin_cobertura"
        elif acertadas.empty:
            veredicto = "no_predicho"
        else:
            veredicto = "predicho"

        # Que tan cerca estuvo la lluvia de lo que Caine pide. Es el numero que
        # convierte una falla en informacion: una quebrada que se activo con el
        # 0,7 de lo que el umbral exige dice donde deberia estar un umbral
        # local, mientras que una que se activo con el 0,05 diria que el
        # mecanismo es otro.
        pares = gatillo[gatillo["id_cuenca"].isin(cerca["id_cuenca"])]
        if pares.empty:
            razon = float("nan")
            lluvia = duracion = float("nan")
        else:
            critica = caine_intensidad_critica(pares["duracion_h"].to_numpy())
            razones = pares["i_media_mm_h"].to_numpy() / critica
            razon = float(np.nanmax(razones)) if len(razones) else float("nan")
            mayor = pares.loc[pares["lluvia_mm"].idxmax()]
            lluvia = float(mayor["lluvia_mm"])
            duracion = float(mayor["duracion_h"])

        filas.append({**entrada, "nombre": nombre, "ubicacion": como,
                      "n_susceptibles": len(cerca), "n_positivas": len(acertadas),
                      "veredicto": veredicto,
                      "razon_max_caine": round(razon, 3) if razon == razon else "",
                      "lluvia_max_mm": round(lluvia, 1) if lluvia == lluvia else "",
                      "duracion_h": round(duracion, 1) if duracion == duracion else "",
                      "ids_positivas": " ".join(
                          str(int(i)) for i in acertadas["id_cuenca"].head(5)),
                      "ids_cercanas": " ".join(
                          str(int(i)) for i in cerca["id_cuenca"])})

    res = pd.DataFrame(filas)

    print(f"\n{'id':>3} {'quebrada':<24} {'evidencia':<17} {'susc':>5} {'pos':>4}  veredicto")
    for _, f in res.iterrows():
        print(f"{f['id']:>3} {str(f['nombre'])[:24]:<24} {f['evidencia'][:17]:<17} "
              f"{f['n_susceptibles']:>5} {f['n_positivas']:>4}  {f['veredicto']}")

    # --- El unico numero defendible ---
    fuertes = res[res["evidencia"].isin(EVIDENCIA_FUERTE)]
    for etiqueta, grupo in (("todas las entradas", res),
                            ("solo evidencia fuerte", fuertes)):
        con_cobertura = grupo[grupo["veredicto"].isin(("predicho", "no_predicho"))]
        aciertos = int((grupo["veredicto"] == "predicho").sum())
        print(f"\n{etiqueta}: {len(grupo)}")
        print(f"  sin ubicar en OSM        {int((grupo['veredicto'] == 'sin_ubicar').sum()):>3}")
        print(f"  sin cobertura del modelo {int((grupo['veredicto'] == 'sin_cobertura').sum()):>3}")
        print(f"  evaluadas y no predichas {int((grupo['veredicto'] == 'no_predicho').sum()):>3}")
        print(f"  predichas                {aciertos:>3}")
        if len(con_cobertura):
            print(f"  RECALL sobre las evaluadas: {aciertos}/{len(con_cobertura)} "
                  f"= {100 * aciertos / len(con_cobertura):.0f}%")

    print("\n  La precision NO se reporta y no es un olvido: el inventario no "
          "tiene\n  negativos observados. Ver la cabecera de este archivo.")

    # --- Recall bajo las dos lecturas del umbral ---
    #
    # M4 guarda dos columnas para Caine: el episodio entero y su peor ventana.
    # Aca se mide cuanto cambia el recall entre una y otra, que es la unica
    # forma de saber si la segunda lectura sirve o solo infla el conteo.
    if len(positivas_por_lectura) > 1:
        print("\n" + "-" * 74)
        print("Recall segun como se lea Caine:")
        # Julio son las 18 entradas con que se cerro M5 la primera vez; agosto
        # es el bloque del 14 al 17, que entro al inventario en octubre de 2026
        # junto con El Porotal. Se separan para que el numero de julio siga
        # siendo comparable con la corrida anterior.
        julio = res[res["fecha"].str.startswith("2026-07")]
        agosto = res[res["fecha"].str.startswith("2026-08")]
        print(f"  {'lectura':<18} {'todas':>14} {'evidencia fuerte':>18} "
              f"{'julio':>14} {'agosto':>14}")
        for etiqueta, conjunto in positivas_por_lectura.items():
            ids = {str(i) for i in conjunto}
            linea = []
            for grupo in (res, res[res["evidencia"].isin(EVIDENCIA_FUERTE)], julio, agosto):
                ev = grupo[~grupo["veredicto"].isin(("sin_cobertura", "sin_ubicar"))]
                aciertos = sum(1 for _, f in ev.iterrows()
                               if set(str(f["ids_cercanas"]).split()) & ids)
                linea.append(f"{aciertos}/{len(ev)} "
                             f"({100 * aciertos / max(len(ev), 1):.0f}%)")
            print(f"  {etiqueta:<18} {linea[0]:>14} {linea[1]:>18} "
                  f"{linea[2]:>14} {linea[3]:>14}")


    # --- Donde cayo la lluvia de las que se activaron ---
    #
    # Esta es la parte util del ejercicio. Saber que el recall es bajo sirve de
    # poco; saber POR CUANTO se quedo corto el umbral dice donde habria que
    # moverlo. Una quebrada que se activo con el 0,7 de lo que Caine pide esta
    # diciendo que el umbral global queda alto para este regimen. Una que se
    # activo con el 0,05 estaria diciendo que el mecanismo es otro.
    evaluadas = res[res["veredicto"].isin(("predicho", "no_predicho"))].copy()
    evaluadas["razon"] = pd.to_numeric(evaluadas["razon_max_caine"], errors="coerce")
    fallas = evaluadas[evaluadas["veredicto"] == "no_predicho"]["razon"].dropna()

    if len(fallas):
        print("\n" + "-" * 74)
        print("Que tan lejos estuvo el umbral en las que fallo:")
        print(f"  minimo {fallas.min():.2f} | mediana {fallas.median():.2f} | "
              f"maximo {fallas.max():.2f}")
        apretadas = int(((fallas >= 0.55) & (fallas <= 0.80)).sum())
        print(f"  {apretadas} de {len(fallas)} caen entre 0,55 y 0,80 de lo que "
              "Caine pide")

        print("\nRecall que daria un umbral escalado (Caine multiplicado por k):")
        print(f"  {'k':>5} {'recall':>14}")
        for k in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5):
            aciertos = int((evaluadas["razon"] >= k).sum())
            marca = "   <- Caine sin tocar" if k == 1.0 else ""
            print(f"  {k:>5.1f} {aciertos:>7}/{len(evaluadas)} "
                  f"({100 * aciertos / len(evaluadas):>3.0f}%){marca}")

        print("\n  ESTE ESCALAMIENTO NO SE ADOPTA, Y LA RAZON IMPORTA.")
        print("  Elegir el k que maximiza el recall sobre este mismo inventario es")
        print("  ajustar el modelo contra su propia validacion: el numero que saldria")
        print("  despues no mediria nada. Ademas las entradas no son independientes")
        print("  -varias comparten la estacion mas cercana, y por eso repiten razon-")
        print(f"  asi que los {len(evaluadas)} casos valen bastante menos de "
              f"{len(evaluadas)} observaciones.")
        print("  Para calibrar en serio hacen falta episodios sin activacion")
        print("  documentada. Eso lo hace m5_calibracion.py, con 2024-2025.")

    dir_out = RAIZ / "outputs"
    dir_out.mkdir(parents=True, exist_ok=True)
    ruta_csv = dir_out / "m5_validacion.csv"
    res.to_csv(ruta_csv, index=False)
    print(f"\n  tabla -> {ruta_csv.name}")


if __name__ == "__main__":
    main()
