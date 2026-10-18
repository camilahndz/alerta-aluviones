"""
M1 (extension) - Subcuencas en las confluencias: la unidad que el fenomeno pide.

POR QUE ESTE SCRIPT EXISTE

    `m1_terreno.py` delinea cuencas cortando donde el terreno termina, o sea en
    la costa. Es correcto para una cuenca costera: la quebrada baja, cruza la
    Ruta 5 y descarga al mar, y esa es toda su historia.

    Para el interior es un error de unidad de analisis. Una quebrada de Vicuna
    no desemboca en el mar: desemboca en el rio Elqui. Como el unico corte esta
    en la costa, esa quebrada queda absorbida dentro de la cuenca del Elqui
    -9.408 km2- y nunca se evalua por separado. M2 mira el Elqui entero, le
    calcula un Melton de cuenca de rio, lo clasifica como `inundacion` y lo
    descarta, y con el se van todas las quebradas que contiene.

    El inventario de activaciones de julio de 2026 lo dejo medido:
    de 18 activaciones documentadas, 8 ocurrieron en Vicuna, Paihuano, Illapel
    y Punitaqui, comunas donde el modelo **no tenia ni una sola unidad que
    evaluar**. No es que dijera que ahi no habia peligro: no decia nada.
    Ver docs/inventario_activaciones_2026-07.md.

    Este script agrega la unidad que faltaba.

CUAL ES LA UNIDAD CORRECTA

    Un flujo de detritos se origina en una cuenca empinada y se deposita donde
    el cauce sale de su encajonamiento a un valle abierto: el apice del abanico
    aluvial. La cuenca que alimenta ese abanico es la unidad sobre la que
    Wilford et al. (2004) calibraron la razon de Melton.

    En el terreno, ese punto es **la confluencia**: donde la quebrada entra al
    valle principal. Asi que una subcuenca se define por la boca de un afluente,
    y no por la desembocadura al mar.

    Esto no es solo cubrir mas territorio. Es aplicar el indice sobre el objeto
    para el que fue hecho. Hoy M2 le calcula Melton a cuencas de 11.000 km2 y
    el propio README admite que ahi el numero no significa lo mismo. Con esta
    extension, 7.283 de las 8.136 subcuencas caen en el rango de 0,4 a 10 km2
    donde el indice esta calibrado; antes eran 380 de 444.

QUE CUENTA COMO BOCA DE AFLUENTE

    Cuatro condiciones, todas con su porque:

      1. La celda es cauce (acumulacion sobre el umbral de M1) y la celda de
         aguas abajo tambien, y esa celda de abajo recibe dos o mas cauces: o
         sea, es una confluencia.

      2. De las ramas que entran a esa confluencia, esta NO es la mas caudalosa.
         La mas caudalosa es la continuacion del cauce principal; las otras son
         afluentes. Sin esta condicion el cauce principal se partiria en pedazos
         arbitrarios en cada junta.

      3. El cauce que la recibe drena al menos `--valle-min-km2`. Es lo que
         distingue "quebrada que sale a un valle" de "quebradita que se junta
         con otra quebradita". Sin este corte salen 71.321 bocas, casi todas
         juntas de primer orden en plena ladera, y ademas quedan anidadas unas
         dentro de otras.

      4. El area del afluente esta entre `--area-min-km2` y `--area-max-km2`, y
         es a lo mas `--razon-max` veces la del cauce receptor. Lo primero
         descarta lo que es demasiado chico para formar un abanico y lo
         demasiado grande para ser una quebrada; lo segundo evita tomar por
         afluente a una rama gemela de tamano comparable.

    La condicion 3 tiene un efecto que conviene notar: como una subcuenca
    elegida mide a lo mas `--area-max-km2` y el valle receptor al menos
    `--valle-min-km2`, con los valores por defecto (50 y 200) **las subcuencas
    no se anidan entre si**. Los afluentes de un afluente desembocan en un cauce
    de menos de 50 km2, que no llega a valle.

    Si anidan, en cambio, dentro de las cuencas costeras de rio: la subcuenca de
    Marquesa esta dentro de la cuenca del Elqui. Eso es correcto y no duplica
    nada en la practica, porque M2 clasifica al Elqui como `inundacion` y lo
    deja fuera del analisis. La columna `origen` permite separarlas igual.

POR QUE NO SE VUELVE A CORRER LA HIDROLOGIA

    Este script lee `direccion_flujo.tif` y `acumulacion_flujo.tif` tal como los
    dejo `m1_terreno.py`. El relleno de sumideros y el calculo de direccion de
    flujo -que es la parte cara, la que pide 5,4 GB de RAM sobre 145 millones de
    pixeles- no se repite. Cambiar donde se ponen las bocas no cambia por donde
    corre el agua.

COMO SE ETIQUETAN 8.000 CUENCAS SIN QUE TARDE HORAS

    `m1_terreno.py` delinea una cuenca por vez: parte de la boca y marca todo lo
    que drena hacia ella. Para 950 cuencas toma unos 30 minutos. Para 8.000
    tomaria la tarde entera.

    Aca se hace al reves y de una sola vez, con **duplicacion de punteros**. Por
    cada celda se guarda a donde drena; las bocas se marcan como punto fijo
    (drenan a si mismas). Despues se eleva el puntero al cuadrado -cada celda
    pasa a apuntar a donde apuntaba su destino- y se repite. En unas 15 pasadas
    toda celda apunta a la primera boca que encuentra aguas abajo, que es
    exactamente la subcuenca a la que pertenece.

    Son 15 operaciones vectorizadas sobre el arreglo completo en vez de 8.000
    recorridos: 20 segundos en vez de horas.

Uso:

    python src/m1_subcuencas.py
    python src/m1_subcuencas.py --valle-min-km2 500    # mas selectivo

Escribe data/processed/subcuencas_coquimbo.gpkg y, uniendolas con las cuencas
costeras de m1_recortar_region.py, data/processed/unidades_coquimbo.gpkg, que es
lo que consume M2.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio import features
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from cobertura import COBERTURA_MINIMA, verificar_cobertura  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CRS_METRICO = "EPSG:32719"

# Codigos de direccion de flujo de pysheds y su desplazamiento (fila, columna).
DESPLAZAMIENTO = {
    64: (-1, 0), 128: (-1, 1), 1: (0, 1), 2: (1, 1),
    4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1),
}

# Los id de subcuenca arrancan aca para no chocar con los de m1_terreno.py, que
# van de 1 en adelante. Que se vea en el numero de que mitad del pipeline sale
# una unidad ahorra mas de una confusion al depurar.
ID_BASE_SUBCUENCA = 100_000

# Tope de pasadas de la duplicacion de punteros. El camino de flujo mas largo
# del raster son unos miles de celdas, asi que convergir toma ~15 pasadas. El
# tope existe para que un ciclo en la direccion de flujo -que no deberia
# ocurrir tras el relleno de sumideros, pero mas vale- no cuelgue el script.
MAX_PASADAS = 40


def cargar_flujo(procesados: Path):
    """Lee los rasters de flujo que dejo m1_terreno.py."""
    ruta_fdir = procesados / "direccion_flujo.tif"
    ruta_acc = procesados / "acumulacion_flujo.tif"
    for ruta in (ruta_fdir, ruta_acc):
        if not ruta.exists():
            sys.exit(f"Falta {ruta}\n"
                     "Corre antes: python src/m1_terreno.py "
                     "--umbral-km2 0.15 --area-min-km2 0.4")

    with rasterio.open(ruta_fdir) as src:
        fdir = src.read(1)
        afin = src.transform
        crs = src.crs
    with rasterio.open(ruta_acc) as src:
        acc = src.read(1)

    m2_pixel = abs(afin.a) * abs(afin.e)
    return fdir, acc, afin, crs, m2_pixel


def indice_aguas_abajo(fdir: np.ndarray) -> np.ndarray:
    """Para cada celda, el indice plano de la celda a la que drena.

    Las celdas que drenan fuera del raster apuntan a si mismas. Eso las vuelve
    punto fijo de la duplicacion de punteros, que es justo lo que se quiere: no
    pertenecen a ninguna subcuenca y se descartan despues por no apuntar a una
    boca.
    """
    filas, columnas = fdir.shape
    df = np.zeros(fdir.shape, np.int32)
    dc = np.zeros(fdir.shape, np.int32)
    for codigo, (paso_f, paso_c) in DESPLAZAMIENTO.items():
        es = fdir == codigo
        df[es] = paso_f
        dc[es] = paso_c

    fa = np.arange(filas, dtype=np.int32)[:, None] + df
    ca = np.arange(columnas, dtype=np.int32)[None, :] + dc
    dentro = (fa >= 0) & (fa < filas) & (ca >= 0) & (ca < columnas)
    propio = np.arange(filas * columnas, dtype=np.int64).reshape(filas, columnas)
    abajo = np.where(dentro, fa.astype(np.int64) * columnas + ca, propio)
    return abajo.astype(np.int32).ravel()


def bocas_de_afluente(acc: np.ndarray, abajo: np.ndarray, m2_pixel: float,
                      umbral_celdas: int, valle_min_km2: float,
                      area_min_km2: float, area_max_km2: float,
                      razon_max: float):
    """Las celdas donde una quebrada entra a un valle. Devuelve (indices, areas).

    Ver las cuatro condiciones en la cabecera del archivo.
    """
    n = acc.size
    accr = acc.ravel()
    es_cauce = accr > umbral_celdas

    # Pares cauce -> cauce, o sea aristas de la red de drenaje.
    origen = np.flatnonzero(es_cauce)
    destino = abajo[origen]
    valido = (destino != origen) & es_cauce[destino]
    origen, destino = origen[valido], destino[valido]

    # Una confluencia es una celda que recibe dos o mas cauces.
    entradas = np.bincount(destino, minlength=n)
    en_junta = entradas[destino] >= 2
    origen, destino = origen[en_junta], destino[en_junta]

    # De cada junta, la rama mas caudalosa es la continuacion del cauce
    # principal; las demas son afluentes. Se ordena por junta y, dentro de cada
    # junta, por acumulacion decreciente, y se descarta la primera de cada grupo.
    orden = np.lexsort((-accr[origen], destino))
    origen, destino = origen[orden], destino[orden]
    primera = np.empty(len(destino), bool)
    primera[0] = True
    primera[1:] = destino[1:] != destino[:-1]
    afluente, receptor = origen[~primera], destino[~primera]

    a_km2 = accr[afluente] * m2_pixel / 1e6
    v_km2 = accr[receptor] * m2_pixel / 1e6

    elegidas = (
        (v_km2 >= valle_min_km2)
        & (a_km2 >= area_min_km2)
        & (a_km2 <= area_max_km2)
        & (a_km2 / v_km2 <= razon_max)
    )
    return afluente[elegidas], a_km2[elegidas]


def etiquetar(abajo: np.ndarray, bocas: np.ndarray) -> np.ndarray:
    """Asigna cada celda a la primera boca que encuentra aguas abajo.

    Duplicacion de punteros: ver la explicacion en la cabecera. Devuelve un
    arreglo plano con el indice de la boca, o -1 si la celda no llega a ninguna.
    """
    siguiente = abajo.copy()
    siguiente[bocas] = bocas        # las bocas son punto fijo

    for pasada in range(1, MAX_PASADAS + 1):
        nuevo = siguiente[siguiente]
        if np.array_equal(nuevo, siguiente):
            print(f"  convergio en {pasada} pasadas")
            break
        siguiente = nuevo
    else:
        # Hasta octubre de 2026 esto era un aviso y el script seguia con las
        # etiquetas a medio propagar: las celdas del ciclo, y todo lo que drena
        # hacia el, quedaban asignadas a cualquier cosa. Auditoria 17-10, M5.
        sys.exit(f"La duplicacion de punteros no convergio en {MAX_PASADAS} pasadas.\n"
                 "Eso es un ciclo en la direccion de flujo, que no deberia existir "
                 "despues del relleno de sumideros.\nRevisa direccion_flujo.tif "
                 "(vuelve a correr m1_terreno.py) antes de seguir.")

    es_boca = np.zeros(abajo.size, bool)
    es_boca[bocas] = True
    return np.where(es_boca[siguiente], siguiente, -1)


def vectorizar(etiquetas_planas: np.ndarray, forma, afin, crs,
               m2_pixel: float) -> gpd.GeoDataFrame:
    """Pasa el raster de etiquetas a poligonos, uno por subcuenca.

    Se usa una sola llamada a `features.shapes` sobre el raster completo en vez
    de recortar cuenca por cuenca: con 8.000 unidades, el ida y vuelta por cada
    una cuesta mas que la pasada unica.
    """
    etq = etiquetas_planas.reshape(forma)

    # `features.shapes` necesita un tipo que GDAL sepa manejar. Las etiquetas
    # son indices planos de hasta 145 millones, asi que se renumeran a 1..N.
    unicas, compacto = np.unique(etq[etq >= 0], return_inverse=True)
    renumerado = np.zeros(etq.size, np.int32)
    renumerado[(etq >= 0).ravel()] = compacto + 1
    renumerado = renumerado.reshape(forma)

    print(f"  vectorizando {len(unicas):,} subcuencas...")
    piezas: dict[int, list] = {}
    for geom, valor in features.shapes(renumerado, mask=renumerado > 0,
                                       transform=afin):
        piezas.setdefault(int(valor), []).append(shape(geom))

    filas = []
    for compacto_id, trozos in piezas.items():
        boca = int(unicas[compacto_id - 1])
        geometria = trozos[0] if len(trozos) == 1 else gpd.GeoSeries(trozos).union_all()
        filas.append({"boca_plana": boca, "geometry": geometria})

    gdf = gpd.GeoDataFrame(filas, crs=crs)
    n_pix = np.bincount(compacto + 1, minlength=len(unicas) + 1)[1:]
    mapa_pix = {int(unicas[i]): int(n_pix[i]) for i in range(len(unicas))}
    gdf["pixeles"] = gdf["boca_plana"].map(mapa_pix)
    gdf["area_km2"] = gdf["pixeles"] * m2_pixel / 1e6
    return gdf


def main():
    ap = argparse.ArgumentParser(
        description="M1 - Delinea subcuencas en las confluencias con los valles.")
    ap.add_argument("--procesados", type=Path, default=RAIZ / "data" / "processed")
    # Los defaults salen de config.py, los mismos de m1_terreno y m1_troncos.
    ap.add_argument("--umbral-km2", type=float, default=config.UMBRAL_CAUCE_KM2,
                    help="Area drenada minima para considerar que hay cauce. "
                         "El mismo valor con que M1 definio la red.")
    ap.add_argument("--valle-min-km2", type=float, default=config.VALLE_MIN_KM2,
                    help="Area drenada minima del cauce receptor para que cuente "
                         "como valle principal.")
    ap.add_argument("--area-min-km2", type=float, default=config.AREA_MIN_KM2,
                    help="Area minima de la subcuenca. El mismo valor de M1.")
    ap.add_argument("--area-max-km2", type=float, default=config.AREA_MAX_KM2,
                    help="Area maxima: sobre esto ya no es una quebrada.")
    ap.add_argument("--razon-max", type=float, default=config.RAZON_MAX,
                    help="Razon maxima entre el area del afluente y la del "
                         "receptor, para no tomar ramas gemelas por afluentes.")
    ap.add_argument("--sensibilidad", action="store_true",
                    help="Imprime cuantas subcuencas salen con otros valles.")
    args = ap.parse_args()

    t0 = time.time()
    print("=" * 70)
    print("M1 (extension) - Subcuencas en las confluencias")
    print("=" * 70)

    fdir, acc, afin, crs, m2_pixel = cargar_flujo(args.procesados)
    print(f"Rasters de flujo : {fdir.shape[0]} x {fdir.shape[1]} px, "
          f"pixel {m2_pixel:.0f} m2")

    # La misma salvaguarda que los demas scripts que leen un raster del terreno:
    # si la hidrologia salio de un DEM parcial, todo lo que sigue es parcial.
    verificar_cobertura(args.procesados / "dem_utm19s.tif",
                        RAIZ / "data" / "raw" / "limite_coquimbo.gpkg",
                        COBERTURA_MINIMA)

    umbral_celdas = int(round(args.umbral_km2 * 1e6 / m2_pixel))
    print(f"Umbral de cauce  : {args.umbral_km2} km2 = {umbral_celdas} pixeles")

    print("\nBuscando bocas de afluente...")
    abajo = indice_aguas_abajo(fdir)
    bocas, areas = bocas_de_afluente(
        acc, abajo, m2_pixel, umbral_celdas, args.valle_min_km2,
        args.area_min_km2, args.area_max_km2, args.razon_max)
    print(f"  {len(bocas):,} bocas con valle >= {args.valle_min_km2:.0f} km2")
    if len(bocas) == 0:
        sys.exit("Ninguna boca cumple los criterios. Baja --valle-min-km2.")

    if args.sensibilidad:
        print("\n  Sensibilidad al umbral de valle:")
        print(f"  {'valle (km2)':>12} {'subcuencas':>12}")
        for valle in (50, 100, 200, 500, 1000):
            otras, _ = bocas_de_afluente(
                acc, abajo, m2_pixel, umbral_celdas, valle,
                args.area_min_km2, args.area_max_km2, args.razon_max)
            marca = "  <- el usado" if valle == args.valle_min_km2 else ""
            print(f"  {valle:>12} {len(otras):>12,}{marca}")

    print("\nEtiquetando por duplicacion de punteros...")
    etiquetas = etiquetar(abajo, bocas)
    asignadas = int((etiquetas >= 0).sum())
    print(f"  {asignadas:,} celdas asignadas "
          f"({100 * asignadas / etiquetas.size:.1f}% del raster)")

    sub = vectorizar(etiquetas, fdir.shape, afin, crs, m2_pixel)

    # Coordenadas de la boca, en el mismo formato que usa m1_recortar_region.py
    # para decidir si una unidad pertenece a la region.
    columnas = fdir.shape[1]
    fila_boca = sub["boca_plana"] // columnas
    col_boca = sub["boca_plana"] % columnas
    sub["salida_x"] = afin.c + afin.a * (col_boca + 0.5)
    sub["salida_y"] = afin.f + afin.e * (fila_boca + 0.5)

    # Una subcuenca que toca el borde del raster tiene el area truncada, y eso
    # infla la razon de Melton. Mismo criterio que m1_terreno.py.
    etq2d = etiquetas.reshape(fdir.shape)
    del_borde = set()
    for franja in (etq2d[1, :], etq2d[-2, :], etq2d[:, 1], etq2d[:, -2]):
        del_borde.update(int(v) for v in np.unique(franja) if v >= 0)
    sub["toca_borde"] = sub["boca_plana"].isin(del_borde)

    sub = sub.sort_values("area_km2", ascending=False).reset_index(drop=True)
    sub["id_cuenca"] = ID_BASE_SUBCUENCA + np.arange(1, len(sub) + 1)
    sub["origen"] = "confluencia"

    # --- Recorte a la region, con el mismo criterio que las costeras ---
    ruta_limite = RAIZ / "data" / "raw" / "limite_coquimbo.gpkg"
    if not ruta_limite.exists():
        sys.exit(f"Falta {ruta_limite}\nCorre antes: python src/m1_recortar_region.py")
    limite = gpd.read_file(ruta_limite).to_crs(CRS_METRICO).geometry.union_all()
    bocas_geo = gpd.GeoSeries(
        gpd.points_from_xy(sub["salida_x"], sub["salida_y"]), crs=CRS_METRICO)
    en_region = bocas_geo.within(limite).to_numpy()
    print(f"\nSubcuencas: {len(sub):,} -> {int(en_region.sum()):,} con la boca "
          "dentro de la region")
    sub = sub[en_region].reset_index(drop=True)

    cols = ["id_cuenca", "origen", "salida_x", "salida_y", "pixeles",
            "area_km2", "toca_borde", "geometry"]
    ruta_sub = args.procesados / "subcuencas_coquimbo.gpkg"
    sub[cols].to_file(ruta_sub, layer="subcuencas", driver="GPKG")

    # --- Union con las cuencas costeras ---
    ruta_costeras = args.procesados / "cuencas_coquimbo.gpkg"
    if not ruta_costeras.exists():
        sys.exit(f"Falta {ruta_costeras}\nCorre antes: python src/m1_recortar_region.py")
    costeras = gpd.read_file(ruta_costeras)
    costeras["origen"] = "costera"

    unidades = gpd.GeoDataFrame(
        pd.concat([costeras[cols], sub[cols]], ignore_index=True),
        crs=costeras.crs)
    ruta_unidades = args.procesados / "unidades_coquimbo.gpkg"
    unidades.to_file(ruta_unidades, layer="unidades", driver="GPKG")

    en_rango = int(((sub["area_km2"] >= 0.4) & (sub["area_km2"] <= 10)).sum())
    print(f"\nUnidades de analisis: {len(unidades):,} "
          f"({len(costeras):,} costeras + {len(sub):,} de confluencia)")
    print(f"  area mediana de las subcuencas: {sub['area_km2'].median():.2f} km2")
    print(f"  en el rango de calibracion de Melton (0,4 a 10 km2): "
          f"{en_rango:,} de {len(sub):,}")
    n_borde = int(sub["toca_borde"].sum())
    if n_borde:
        print(f"  {n_borde} tocan el borde del raster (M2 las excluye)")

    print(f"\n  subcuencas -> {ruta_sub.name}")
    print(f"  unidades   -> {ruta_unidades.name}")
    print(f"\nTomo {time.time() - t0:.0f} s")
    print("\nSiguiente paso:")
    print("  python src/m2_susceptibilidad.py --cuencas "
          "data/processed/unidades_coquimbo.gpkg")


if __name__ == "__main__":
    main()
