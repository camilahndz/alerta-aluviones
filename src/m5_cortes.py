"""
M5 - Los cortes de ruta reales contra el mapa de exposicion de M3.

LA PREGUNTA

    M3 entrega una lista de puntos donde una via cruza el cauce de una
    quebrada, ordenada por prioridad. Es la parte del modelo que una autoridad
    usaria primero: cuando llega un temporal, que tramos de camino vigilar.
    Los inventarios de 2024 a 2026 traen once cortes o danos de ruta con la via
    nombrada. Este script les hace tres preguntas:

    1. COBERTURA. Habia un candidato de M3 en ese tramo de esa ruta?

    2. CONTRA EL AZAR. Una ruta con un candidato por kilometro "acierta"
       cualquier corte que le pase. Por eso cada acierto se compara con la
       probabilidad de acertar poniendo la misma ventana en un punto al azar de
       la misma ruta. Si el modelo acierta lo mismo que el azar, la lista no
       dice donde, solo dice que la ruta cruza quebradas.

    3. PRIORIDAD. Que tan arriba en la lista estaba el candidato. Se mide como
       cuantos cortes reales quedan cubiertos si se vigilan solo los primeros
       K puntos, contra lo esperable al azar con esos mismos K.

COMO SE UBICA UN CORTE

    La prensa da la ruta y casi nunca el punto exacto. Cada corte se ubica con
    un localizador de OSM: el cauce con el nombre de la quebrada si OSM lo
    tiene, y si no, el caserio del mismo nombre. El centro del corte es el
    punto de la ruta mas cercano al localizador, y la ventana es el tramo de la
    ruta a menos de 1 km de ese centro (1,5 km si el localizador es un
    caserio, porque un caserio es un punto en el centro del pueblo y la
    quebrada que lleva su nombre lo cruza cerca, no encima).

    Cada localizador es un juicio y por eso va escrito en CORTES con su motivo,
    igual que los alias de m5_validacion. Las entradas con via nombrada que no
    se pueden ubicar como un punto van en FUERA, tambien con su motivo. Si
    aparece una entrada nueva con via y no esta en ninguna de las dos tablas,
    el script se detiene: un corte que desaparece en silencio de la prueba es
    el error que no da error.

LA LINEA BASE

    Por cada corte, 2.000 centros al azar sobre la misma ruta, con la misma
    ventana. La fraccion que contiene un candidato es la probabilidad de
    acertar por azar en esa ruta. La suma sobre los cortes es el numero de
    aciertos esperable, y la probabilidad de acertar los que se acertaron o mas
    sale exacta de la distribucion binomial de Poisson (una binomial con una
    probabilidad distinta por corte). Los cortes de una misma ruta no son del
    todo independientes -Leiva y Los Loros comparten candidatos a la entrada
    de Vicuna-, asi que ese valor es aproximado.

LAS TRES VARIANTES

    En octubre de 2026 esta prueba motivo dos cambios en M3: sumar las cuencas
    de clase inundacion (clases_cuenca.CLASES_EXPOSICION) y sumar el area
    drenada en el cruce a la prioridad (ver la cabecera de m3_exposicion.py).
    Las tres variantes salen de la misma corrida de M3, para separar el efecto
    de cada cambio:

        1. la lista de antes: clases susceptibles, orden por clase y via;
        2. con la clase inundacion, mismo orden;
        3. la de M3 actual, con inundacion y con el area en el orden.

    La primera reproduce la lista vieja, porque agregar unidades no mueve los
    cauces ni los puntos de las que ya estaban, y los pesos de clase y via no
    cambiaron. Esta comprobado contra una corrida hecha antes de tocar M3:
    mismos aciertos, misma linea base, misma tabla por K. Solo un rango se
    movio 6 lugares (3.395 a 3.389), por el orden entre puntos empatados.

LO QUE SALIO

    Ver la corrida 2026-10-11_m5_cortes.txt. En resumen:

    * M3 hasta octubre de 2026 tenia candidato en 7 de los 11 cortes, pero
      poniendo la misma ventana al azar en las mismas rutas se esperaban 5,3
      (P = 0,14). Y vigilando el 10% de arriba de la lista se cubrian 4 contra
      3,7 al azar: la lista sabia que rutas cruzan quebradas, no en que punto,
      y su orden no ayudaba. Los cuatro cortes sin candidato caian en cuencas
      de clase inundacion, y la prensa describe agua, no barro: "aumento de
      caudal", una crecida que "sobrepaso la calzada", un socavon.

    * Sumar la inundacion cubre 9 de 11 contra 6,6 al azar (P = 0,07): sube la
      cobertura, pero la lista crece a 9.424 puntos y el azar sube con ella.

    * Sumar el area drenada al orden es lo que cambia el resultado: el 3% de
      arriba de la lista (250 puntos) cubre 4 cortes contra 1,0 al azar
      (P = 0,006), y el 5% cubre 5 contra 2,1 (P = 0,02).

    Las dos ultimas cifras son del cambio que esta prueba motivo. La formula
    se fijo antes de evaluarla y no se movio despues, pero los once cortes son
    los mismos que mostraron el problema: no es validacion independiente. La
    independiente es el invierno de 2027, contra esta lista congelada.

    Dos pares de cortes comparten candidato: Leiva y Los Loros a la entrada de
    Vicuna, y Las Barrancas (2026) y Los Rincones (2025) en la D-427. El
    segundo par son dos cortes reales en el mismo cruce en dos inviernos, y
    cuenta dos veces con razon; el primero puede ser el mismo punto reportado
    con dos nombres.

Uso:

    python src/m5_cortes.py

Lee la salida de M3 y el extracto de OSM. Un par de minutos, menos de 1 GB de
RAM.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m5_calibracion as cal  # noqa: E402
import m5_validacion as m5  # noqa: E402
from clases_cuenca import CLASES_SUSCEPTIBLES  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent

# id del inventario: (ref de la via en OSM, capa del localizador, nombre en
# OSM sin tildes, por que). El nombre se compara entero contra la clave sin
# tildes de m5_validacion y solo dentro de la comuna de la entrada.
CORTES = {
    "11": ("43", "lugar", "tambillos",
           "la prensa dice D-43; en OSM la Ruta 43 lleva ref '43'. OSM no tiene "
           "la quebrada y se ubica por el caserio. Cortada el 19-07 y el 31-07"),
    "12": ("D-427", "lugar", "las barrancas",
           "OSM no tiene la quebrada; el caserio esta sobre la ruta"),
    "14": ("D-205", "cauce", "quebrada del romero",
           "la prensa dice Cajon del Romero; el cauce de ese nombre en La Serena "
           "es Quebrada del Romero, y cruza la D-205"),
    "17": ("41", "cauce", "quebrada los loros",
           "la 'ruta Vicuna-Peralillo' es la Ruta 41 al oriente de Vicuna"),
    "19": ("41", "lugar", "el porotal",
           "km 41 de la Ruta 41; OSM no tiene el cauce"),
    "20": ("41", "cauce", "quebrada de leiva",
           "km 62 de la Ruta 41, a la entrada de Vicuna"),
    "23": ("D-835", "lugar", "llimpo",
           "km 14 de la D-835; OSM no tiene el cauce"),
    "24": ("D-697", "lugar", "la isla",
           "sin nombre de quebrada: 'km 4, sector La Isla - Cogoti'"),
    "25": ("41", "lugar", "cutun alto",
           "como el alias de m5_validacion: OSM tiene el caserio Cutun Alto"),
    "26": ("D-577", "lugar", "el maiten",
           "la prensa escribe El Maite; el caserio El Maiten de Monte Patria "
           "esta sobre la D-577"),
    "137": ("D-427", "cauce", "quebrada los rincones",
            "la prensa dice Ruta 427"),
}

FUERA = {
    "21": "la D-215 corre 42 km por dentro de la quebrada Marquesa: no hay un "
          "punto que ubicar",
    "103": "la fuente dice que no hubo cortes en la D-595",
    "106": "'caminos rurales' sin nombre",
    "108": "'caminos danados' sin nombre",
    "109": "'sin acceso terrestre' sin via nombrada",
}

RADIO_CAUCE_M = 1000.0
RADIO_LUGAR_M = 1500.0
EN_RUTA_M = 25.0            # un candidato pertenece a la ruta si esta a menos de esto
N_AZAR = 2000
SEMILLA = 0
TOPES_K = (100, 250, 500, 1000, 2000)


def leer_vias():
    import geopandas as gpd
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        vias = gpd.read_file(m5.OSM, layer="gis_osm_roads_free", bbox=m5.BBOX,
                             columns=["fclass", "name", "ref"], engine="pyogrio")
    return vias.to_crs(m5.CRS_METRICO)


def revisar_tablas(inv: pd.DataFrame) -> pd.DataFrame:
    """Las entradas con via nombrada tienen que estar en CORTES o en FUERA."""
    con_via = inv[inv["via_afectada"].notna()]
    sueltas = set(con_via["id"]) - set(CORTES) - set(FUERA)
    if sueltas:
        sys.exit(f"Entradas con via afectada que no estan en CORTES ni en FUERA: "
                 f"{sorted(sueltas)}. Agregalas con su motivo antes de evaluar.")
    return con_via


def localizar(capa, clave, comuna, osm, comunas):
    """La geometria del localizador, dentro de la comuna de la entrada."""
    sel = osm[(osm["capa"] == capa) & (osm["clave"] == clave)]
    zona = comunas[comunas["clave"] == m5.sin_tildes(comuna)]
    if zona.empty:
        sys.exit(f"La comuna '{comuna}' no esta en la capa de comunas.")
    sel = sel[sel.intersects(zona.geometry.union_all().buffer(m5.MARGEN_COMUNA_M))]
    if sel.empty:
        sys.exit(f"No encuentro {capa} '{clave}' en {comuna}.")
    return sel.geometry.union_all()


def puntos_al_azar(ruta, n, rng):
    """n puntos uniformes por largo sobre una (multi)linea."""
    partes = list(getattr(ruta, "geoms", [ruta]))
    largos = np.array([p.length for p in partes])
    elegidas = rng.choice(len(partes), size=n, p=largos / largos.sum())
    pos = rng.random(n)
    xy = [partes[i].interpolate(f, normalized=True) for i, f in zip(elegidas, pos)]
    return np.array([(p.x, p.y) for p in xy])


def rango_minimo(centros, cand_xy, cand_rango, radio):
    """Para cada centro, el mejor rango de los candidatos a menos de `radio`."""
    if len(cand_xy) == 0:
        return np.full(len(centros), np.inf)
    d = np.hypot(centros[:, None, 0] - cand_xy[None, :, 0],
                 centros[:, None, 1] - cand_xy[None, :, 1])
    r = np.where(d <= radio, cand_rango[None, :], np.inf)
    return r.min(axis=1)


def cola_binomial_poisson(p, k) -> float:
    """P(X >= k) para una suma de Bernoulli independientes con probabilidades p."""
    dist = np.zeros(len(p) + 1)
    dist[0] = 1.0
    for pi in p:
        dist[1:] = dist[1:] * (1 - pi) + dist[:-1] * pi
        dist[0] *= (1 - pi)
    return float(dist[k:].sum())


def orden_anterior(puntos):
    """El orden de M3 hasta octubre de 2026: mitad clase, mitad via.

    Recalcularlo sobre la salida nueva reproduce la lista vieja, porque los
    pesos de clase y de via no cambiaron y agregar unidades no mueve los
    puntos de las que ya estaban.
    """
    prio = (0.5 * puntos["peso_clase"] + 0.5 * puntos["peso_via"]).round(4)
    return (puntos.assign(_prio=prio)
            .sort_values(["_prio", "melton"], ascending=False, kind="stable")
            .drop(columns="_prio"))


def evaluar(casos, puntos, rotulo, rng_semilla):
    """Cobertura, linea base y prioridad, con los puntos ya en el orden a evaluar."""
    puntos = puntos.reset_index(drop=True)
    puntos["rango"] = np.arange(1, len(puntos) + 1)
    xy = np.column_stack([puntos.geometry.x, puntos.geometry.y])
    n_total = len(puntos)
    topes = [k for k in TOPES_K if k < n_total] + [n_total]

    filas = []
    for c in casos:
        en_ruta = puntos.geometry.distance(c["ruta"]) <= EN_RUTA_M
        cxy = xy[en_ruta.to_numpy()]
        crango = puntos.loc[en_ruta, "rango"].to_numpy(dtype=float)
        rng = np.random.default_rng(rng_semilla)
        azar = rango_minimo(puntos_al_azar(c["ruta"], N_AZAR, rng), cxy, crango, c["radio"])
        obs = rango_minimo(np.array([[c["centro"].x, c["centro"].y]]), cxy, crango, c["radio"])[0]
        fila = {**{k: c[k] for k in ("id", "quebrada", "fecha", "via", "ref", "capa",
                                     "dist_localizador_m", "radio")},
                "largo_ruta_km": c["ruta"].length / 1000,
                "candidatos_en_ruta": int(en_ruta.sum()),
                "acierto": bool(np.isfinite(obs)),
                "mejor_rango": obs if np.isfinite(obs) else np.nan,
                "p_azar": float(np.isfinite(azar).mean())}
        for k in topes:
            fila[f"acierto_k{k}"] = bool(obs <= k)
            fila[f"p_azar_k{k}"] = float((azar <= k).mean())
        filas.append(fila)
    t = pd.DataFrame(filas)

    print(f"\n  {rotulo}: {n_total} candidatos")
    print(f"    {'id':>4} {'quebrada':<20} {'via':<14} {'loc':>5} {'cand.':>5} "
          f"{'azar':>5} {'acierto':>8} {'rango':>6}")
    for _, f in t.iterrows():
        rango = f"{int(f['mejor_rango'])}" if f["acierto"] else "-"
        print(f"    {f['id']:>4} {str(f['quebrada'])[:20]:<20} {str(f['via'])[:14]:<14} "
              f"{f['capa'][:5]:>5} {f['candidatos_en_ruta']:>5} {f['p_azar']:>5.2f} "
              f"{'si' if f['acierto'] else 'no':>8} {rango:>6}")

    obs = int(t["acierto"].sum())
    esperado = t["p_azar"].sum()
    p = cola_binomial_poisson(t["p_azar"].to_numpy(), obs)
    print(f"    aciertos {obs} de {len(t)}; esperable al azar en las mismas rutas "
          f"{esperado:.1f}; P(azar >= {obs}) = {p:.3f}")

    print(f"    vigilando solo los primeros K puntos de la lista:")
    print(f"      {'K':>6} {'% lista':>8} {'cortes cubiertos':>17} {'al azar':>8} {'P(azar >=)':>11}")
    for k in topes:
        o = int(t[f"acierto_k{k}"].sum())
        pz = t[f"p_azar_k{k}"].to_numpy()
        print(f"      {k:>6} {k / n_total:>8.0%} {o:>17} {pz.sum():>8.1f} "
              f"{cola_binomial_poisson(pz, o):>11.3f}")
    return t


def main():
    import geopandas as gpd
    from shapely.ops import nearest_points

    print("=" * 74)
    print("M5 - Cortes de ruta reales contra el mapa de exposicion (M3)")
    print("=" * 74)

    inv = cal.cargar_inventario()
    con_via = revisar_tablas(inv)
    print(f"\nEntradas con via afectada: {len(con_via)}; se evaluan {len(CORTES)}, "
          f"quedan fuera {len(FUERA)}:")
    for i, motivo in FUERA.items():
        print(f"  {i:>4}  {motivo}")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        osm = m5.cargar_osm()
        comunas = m5.cargar_comunas()
    vias = leer_vias()
    unidades = gpd.read_file(RAIZ / "data" / "processed" / "susceptibilidad.gpkg")
    puntos = gpd.read_file(RAIZ / "data" / "processed" / "puntos_corte.gpkg")

    print("\nUbicacion de cada corte:")
    casos = []
    for i, (ref, capa, clave, motivo) in CORTES.items():
        e = inv[inv["id"] == i].iloc[0]
        ruta = vias.loc[vias["ref"] == ref].geometry.union_all()
        if ruta.is_empty:
            sys.exit(f"La ruta ref '{ref}' no esta en el extracto de OSM.")
        geo = localizar(capa, clave, e["comuna"], osm, comunas)
        centro = nearest_points(ruta, geo)[0]
        dist = ruta.distance(geo)
        # La unidad mas chica que contiene el centro dice de que clase es la
        # cuenca que el corte atraviesa, este o no en la lista de M3.
        dentro = unidades[unidades.contains(centro)].sort_values("area_km2")
        unidad = dentro.iloc[0] if len(dentro) else None
        casos.append({"id": i, "quebrada": m5._texto(e["quebrada"]) or "(sin nombre)",
                      "fecha": e["fecha"], "via": e["via_afectada"], "ref": ref,
                      "capa": capa, "dist_localizador_m": round(dist),
                      "radio": RADIO_CAUCE_M if capa == "cauce" else RADIO_LUGAR_M,
                      "ruta": ruta, "centro": centro,
                      "clase_unidad": None if unidad is None else unidad["clase"],
                      "origen_unidad": None if unidad is None else unidad["origen"],
                      "area_unidad_km2": None if unidad is None else unidad["area_km2"]})
        print(f"  {i:>4} {casos[-1]['quebrada'][:20]:<20} {ref:<6} {capa} '{clave}' a "
              f"{dist:>5.0f} m de la ruta; unidad: {casos[-1]['clase_unidad']} "
              f"({casos[-1]['origen_unidad']}, {casos[-1]['area_unidad_km2'] or 0:.0f} km2)")
        print(f"         {motivo}")

    print("\n" + "-" * 74)
    print("Cobertura, linea base y prioridad")
    print("-" * 74)
    if "peso_area" not in puntos.columns:
        sys.exit("puntos_corte.gpkg es de antes de octubre de 2026 (no trae el area en el "
                 "cruce). Corre de nuevo python src/m3_exposicion.py.")
    antes = puntos[puntos["clase"].isin(CLASES_SUSCEPTIBLES)]
    variantes = (
        ("susceptibles, orden anterior", "M3 hasta octubre de 2026: clases susceptibles, "
         "orden por clase y via", orden_anterior(antes)),
        ("con inundacion, orden anterior", "Con la clase inundacion, mismo orden -- "
         "MOTIVO EL CAMBIO", orden_anterior(puntos)),
        ("con inundacion, orden con area", "M3 actual: con inundacion y area en la "
         "prioridad -- MOTIVO EL CAMBIO", puntos.sort_values("rank")),
    )
    tablas = [evaluar(casos, p, rotulo, SEMILLA).assign(variante=nombre)
              for nombre, rotulo, p in variantes]

    tabla = pd.concat(tablas, ignore_index=True)
    extra = pd.DataFrame([{k: c[k] for k in ("id", "clase_unidad", "origen_unidad",
                                             "area_unidad_km2")} for c in casos])
    tabla = tabla.merge(extra, on="id")
    tabla.to_csv(RAIZ / "outputs" / "m5_cortes.csv", index=False, float_format="%.4f")
    print("\n  tabla -> m5_cortes.csv")


if __name__ == "__main__":
    main()
