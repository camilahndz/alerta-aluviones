"""
M6 - La alerta en vivo: el nivel de cada provincia con la lluvia de ahora.

QUE HACE

    Baja de VIPNET la lluvia, la temperatura y la nieve de la region, arma el
    temporal en curso con las mismas reglas con que se calibraron los niveles
    (M4 y m5_alerta_sector) y emite un boletin: el nivel de alerta de cada
    provincia, cuanta lluvia falta para el siguiente, el aviso de deshielo y
    los tramos de ruta que conviene vigilar donde hay alerta.

    Esta pensado para correr solo, cada hora, durante un temporal. Escribe
    outputs/alerta_en_vivo.json (lo que leera el visor) y un boletin con fecha
    en outputs/boletines/.

LAS DECISIONES QUE HAY QUE PODER DEFENDER

    1. El modelo esta congelado. Los coeficientes de los niveles son
       constantes de este archivo, copiadas de la corrida de m5_niveles.py del
       11-10-2026. Una alerta que se recalibra sola cada vez que alguien corre
       M5 no se puede validar: el invierno de 2027 tiene que evaluarse contra
       una regla que no se movio. Si outputs/m5_niveles_modelo.json existe y
       no coincide, el script avisa, no cambia.

    2. Mismas reglas que la calibracion. La serie, R2, R4, los episodios, R3,
       R5 y la isoterma salen de las funciones de m4_lluvia.py; el temporal,
       de m5_alerta_sector.temporales; la lluvia por estacion, de
       m5_niveles.lluvia_por_temporal. Nada se reescribe aca. La diferencia
       inevitable es que R2 y R4 se miran sobre la ventana de 21 dias y no
       sobre el invierno entero, que en vivo todavia no existe.

    3. Una estacion que dejo de transmitir no es una estacion seca. La serie
       de cada estacion se corta en su ultima lectura: si no, los pasos que
       todavia no llegan se leerian como un hueco de transmision, y R3
       botaria justo el episodio que esta ocurriendo. Y una provincia con
       menos de 3 estaciones transmitiendo en las ultimas 3 horas sale
       marcada "datos insuficientes" junto a su nivel: sin dato no es cero.

    4. Se baja solo lo que falta. VIPNET es un servicio publico. La primera
       corrida baja 40 dias; las siguientes, desde la ultima lectura guardada
       menos 24 horas (VIPNET a veces completa datos tarde). El almacen esta
       en data/raw/vivo/.

    5. Dos estaciones, no una. El nivel lo fija la segunda estacion mas
       mojada de la provincia. Asi un pluviometro que mide de mas no puede
       poner sola a una provincia en alerta, que es lo que paso el 11-10-2026
       con Choapa. Ver m5_niveles.py.

    6. Repaso. Con --momento se corre "como si fuera" un momento pasado. Si
       cae dentro de la ventana de M4, los datos salen del cache de M4 y no se
       le pide nada a VIPNET. Asi se valida: --repasar corre el final de cada
       temporal regional de tres inviernos y compara con m5_niveles, y
       --cronologia muestra hora a hora cuando habria subido cada nivel.

Uso:

    python src/m6_alerta_en_vivo.py                               # ahora
    python src/m6_alerta_en_vivo.py --momento "2026-07-18 12:00"   # repaso
    python src/m6_alerta_en_vivo.py --repasar
    python src/m6_alerta_en_vivo.py --cronologia "2026-07-15 00:00" "2026-07-21 00:00" 6

Necesita las salidas de m3_exposicion.py (puntos de corte) y de
m4_climatologia.py (la normal anual).
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_deshielo as desh  # noqa: E402
import m4_lluvia as m4  # noqa: E402
import m5_alerta_sector as alerta  # noqa: E402
import m5_niveles as niv  # noqa: E402
import m5_validacion as m5  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ZONA = m4.ZONA_CHILE

# --- El modelo congelado ------------------------------------------------------
# De m5_niveles.py, corrida 2026-10-11_m5_niveles.txt: logistica sobre los tres
# inviernos, 98 provincias-temporal, 12 positivas, con la fraccion de la normal
# en la SEGUNDA estacion mas mojada de cada provincia. La primera version usaba
# la mas mojada (b0 5,568862, b1 9,776656); se cambio el mismo 11-10 porque una
# sola estacion sospechosa ponia a Choapa en naranja. Ver m5_niveles.py.
B0 = 4.860371
B1 = 7.526972
CALIBRACION = "m5_niveles.py, 11-10-2026, inviernos 2024-2026, segunda estacion"

VENTANA_LLUVIA_D = 21       # el temporal mas largo de tres inviernos duro 13 dias
VENTANA_DATOS_D = 40        # el deshielo mira la linea de nieve de 30 dias atras
SOLAPE_H = 24
VIGENTE_H = 3               # una estacion "transmite" si leyo en las ultimas 3 h
MIN_ESTACIONES = 3
CORTES_POR_PROVINCIA = 10
TIPOS = {"lluvia": m4.TIPO_PRECIPITACION, "temperatura": m4.TIPO_TEMPERATURA,
         "nieve": desh.TIPO_NIEVE}
SIGNO = {"ninguna": "-", "amarilla": "AMARILLA", "naranja": "NARANJA", "roja": "ROJA"}


# =============================================================================
# Datos: cache de M4 para repasar, almacen incremental para vivir
# =============================================================================

def _fecha(registro: dict) -> pd.Timestamp:
    return pd.Timestamp(registro["fecha"]["$date"])


class CacheM4:
    """Las series de tres inviernos del cache de M4, cargadas una vez.

    Se guardan como arreglos y no como la lista de registros de la API: 230
    series de 38.000 registros como diccionarios de Python ocuparian varios GB.
    Al pedir una ventana se rearman los registros con la misma forma que manda
    VIPNET, para que las funciones de M4 los lean igual que siempre.
    """

    def __init__(self):
        self.carpeta = (RAIZ / "data" / "raw" / "lluvia"
                        / f"{m4.VENTANA_INICIO}_{m4.VENTANA_FIN}")
        self.fin = m4._hora_local(f"{m4.VENTANA_FIN} 23:30")
        self._series = {}

    def cubre(self, momento: pd.Timestamp) -> bool:
        return self.carpeta.exists() and momento <= self.fin

    def _cargar(self, codigo, tipo):
        ruta = self.carpeta / f"{tipo}_{codigo}.json.gz"
        if not ruta.exists():
            return None
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            datos = json.load(f)
        if not datos:
            return None
        fechas = pd.to_datetime([d["fecha"]["$date"] for d in datos], utc=True)
        acum = np.array([d.get("acumulado", np.nan) for d in datos], dtype=float)
        inst = np.array([d.get("instantaneo", np.nan) for d in datos], dtype=float)
        return fechas, acum, inst

    def registros(self, codigo, tipo, desde, hasta) -> list[dict]:
        clave = (tipo, codigo)
        if clave not in self._series:
            self._series[clave] = self._cargar(codigo, tipo)
        serie = self._series[clave]
        if serie is None:
            return []
        fechas, acum, inst = serie
        sel = np.flatnonzero((fechas >= desde) & (fechas <= hasta))
        textos = fechas[sel].strftime("%Y-%m-%dT%H:%M:%SZ")
        return [{"fecha": {"$date": t}, "acumulado": None if np.isnan(a) else float(a),
                 "instantaneo": None if np.isnan(i) else float(i), "codigoEstacion": codigo}
                for t, a, i in zip(textos, acum[sel], inst[sel])]


class AlmacenVivo:
    """Lo bajado de VIPNET en vivo, por estacion, y que se completa por partes."""

    def __init__(self):
        self.carpeta = RAIZ / "data" / "raw" / "vivo"
        self.carpeta.mkdir(parents=True, exist_ok=True)

    def registros(self, codigo, tipo, desde, hasta) -> list[dict]:
        ruta = self.carpeta / f"{tipo}_{codigo}.json.gz"
        guardados = []
        if ruta.exists():
            with gzip.open(ruta, "rt", encoding="utf-8") as f:
                guardados = json.load(f)
        ultimo = max((_fecha(d) for d in guardados), default=None)
        pedir_desde = desde if ultimo is None else max(desde, ultimo - pd.Timedelta(hours=SOLAPE_H))
        horas = math.ceil((hasta - pedir_desde).total_seconds() / 3600) + 1
        local = hasta.tz_convert(ZONA)
        cuerpo = m4._post(m4.EP_SERIE, {
            "codigoEstacion": codigo, "tipoEstacion": tipo,
            "fetchDay": local.strftime("%Y-%m-%d"), "fetchHour": local.hour,
            "hoursRange": horas})
        nuevos = cuerpo["data"]
        ajenos = {d.get("codigoEstacion") for d in nuevos} - {codigo}
        if ajenos:
            raise RuntimeError(f"Se pidio {codigo} y vinieron datos de {ajenos}.")
        # Lo nuevo reemplaza a lo guardado en la misma marca de tiempo: es lo
        # que VIPNET completo despues.
        por_fecha = {d["fecha"]["$date"]: d for d in guardados}
        por_fecha.update({d["fecha"]["$date"]: d for d in nuevos})
        corte = hasta - pd.Timedelta(days=VENTANA_DATOS_D + 5)
        todos = sorted((d for d in por_fecha.values() if _fecha(d) >= corte),
                       key=lambda d: d["fecha"]["$date"])
        with gzip.open(ruta, "wt", encoding="utf-8") as f:
            json.dump(todos, f)
        return [d for d in todos if desde <= _fecha(d) <= hasta]


def bajar_todo(fuente, catalogos, momento) -> dict:
    desde = momento - pd.Timedelta(days=VENTANA_DATOS_D)
    tareas = [(nombre, cod) for nombre, cat in catalogos.items() for cod in cat["codigo"]]

    def una(t):
        nombre, cod = t
        return t, fuente.registros(cod, TIPOS[nombre], desde, momento)

    if isinstance(fuente, AlmacenVivo):
        with ThreadPoolExecutor(6) as ex:
            return dict(ex.map(una, tareas))
    return dict(map(una, tareas))


# =============================================================================
# Lo fijo de cada corrida: estaciones, normal, provincia, cortes
# =============================================================================

def preparar() -> dict:
    import geopandas as gpd

    catalogos = {nombre: m4.descargar_catalogo(tipo) for nombre, tipo in TIPOS.items()}
    lluvia = catalogos["lluvia"]
    ruta_tif = RAIZ / "data" / "processed" / "precipitacion_media_anual.tif"
    if not ruta_tif.exists():
        sys.exit(f"Falta {ruta_tif.name}. Corre antes: python src/m4_climatologia.py")
    lluvia["normal_mm"] = lluvia["codigo"].map(niv.normal_en_estaciones(lluvia, ruta_tif))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        comunas = m5.cargar_comunas()
    pts = gpd.GeoDataFrame(lluvia, geometry=gpd.points_from_xy(lluvia["lon"], lluvia["lat"]),
                           crs="EPSG:4326").to_crs(m5.CRS_METRICO)
    pts = gpd.sjoin(pts, comunas[["clave", "geometry"]], how="left", predicate="within")
    prov = pts.drop_duplicates("codigo").set_index("codigo")["clave"].map(alerta.PROVINCIA_DE)
    lluvia["provincia"] = lluvia["codigo"].map(prov)

    ruta_cortes = RAIZ / "data" / "processed" / "puntos_corte.gpkg"
    if not ruta_cortes.exists():
        sys.exit("Falta puntos_corte.gpkg. Corre antes: python src/m3_exposicion.py")
    cortes = gpd.read_file(ruta_cortes, ignore_geometry=True)
    cortes["provincia"] = cortes["comuna"].map(lambda c: alerta.PROVINCIA_DE.get(m5.sin_tildes(c)))
    return {"catalogos": catalogos, "cortes": cortes}


def verificar_modelo():
    ruta = RAIZ / "outputs" / "m5_niveles_modelo.json"
    if not ruta.exists():
        return
    m = json.loads(ruta.read_text())
    if abs(m["b0"] - B0) > 1e-4 or abs(m["b1"] - B1) > 1e-4:
        print(f"  AVISO: m5_niveles_modelo.json trae b0={m['b0']:.6f}, b1={m['b1']:.6f}, "
              f"distintos de los congelados ({B0}, {B1}). La alerta sigue usando los "
              "congelados; actualizarlos es una decision, no un efecto lateral.")


# =============================================================================
# La evaluacion de un momento
# =============================================================================

def probabilidad(fraccion: float, modelo=None) -> float:
    b0, b1 = modelo or (B0, B1)
    return 1 / (1 + math.exp(-(b0 + b1 * math.log10(max(fraccion, niv.PISO_FRACCION)))))


def fraccion_para(p: float, modelo=None) -> float:
    b0, b1 = modelo or (B0, B1)
    return 10 ** ((math.log(p / (1 - p)) - b0) / b1)


def nivel_de(p: float) -> str:
    n = "ninguna"
    for nombre, umbral in niv.NIVELES:
        if p >= umbral:
            n = nombre
    return n


def episodios_en_ventana(datos, catalogos, momento):
    """Episodios validos de la ventana, con las reglas de M4."""
    grilla = pd.date_range(momento - pd.Timedelta(days=VENTANA_LLUVIA_D), momento,
                           freq=f"{m4.PASO_MIN}min")
    temperaturas, altitudes = {}, {}
    for _, e in catalogos["temperatura"].iterrows():
        temperaturas[e["codigo"]] = m4.serie_temperatura(datos[("temperatura", e["codigo"])], grilla)
        altitudes[e["codigo"]] = e["altitud_m"]
    iso = m4.isoterma_cero(temperaturas, altitudes)

    filas, estado = [], []
    for _, e in catalogos["lluvia"].iterrows():
        serie = m4.serie_precipitacion(datos[("lluvia", e["codigo"])], grilla)
        diag = m4._diagnostico_estacion(serie)
        ultima = serie["acumulado"].last_valid_index()
        estado.append({"codigo": e["codigo"], "descartada_por": diag["descartada_por"],
                       "ultima_lectura": ultima})
        if diag["descartada_por"] or ultima is None:
            continue
        eps = m4.detectar_episodios(serie.loc[:ultima], m4.CORTE_SECO_H)
        if eps.empty:
            continue
        eps = eps[~eps["tiene_hueco"]]
        if eps.empty:
            continue
        alt = pd.to_numeric(pd.Series([e["altitud_m"]]), errors="coerce").iloc[0]
        eps = eps[m4.aplicar_r5(eps, alt, iso).to_numpy()]
        if eps.empty:
            continue
        eps.insert(0, "estacion_codigo", e["codigo"])
        filas.append(eps)
    episodios = pd.concat(filas, ignore_index=True) if filas else pd.DataFrame(
        columns=["estacion_codigo", "inicio", "fin", "lluvia_mm"])
    return episodios, pd.DataFrame(estado)


def temporal_en_curso(episodios, momento):
    if episodios.empty or not (episodios["lluvia_mm"] >= alerta.EVENTO_MINIMO_MM).any():
        return None
    tor = alerta.temporales(episodios)
    ultimo = tor.iloc[-1]
    if ultimo["fin"] < momento - pd.Timedelta(hours=alerta.PAUSA_H):
        return None
    return tor.iloc[[-1]].reset_index(drop=True)


def deshielo_hoy(datos, catalogos, momento) -> dict:
    """La condicion de m4_deshielo.py, con los datos de la ventana."""
    dias = pd.date_range((momento - pd.Timedelta(days=VENTANA_DATOS_D)).tz_convert(ZONA)
                         .tz_localize(None).normalize(),
                         momento.tz_convert(ZONA).tz_localize(None).normalize(), freq="D")
    nieve = {}
    for cod in catalogos["nieve"]["codigo"]:
        s = desh.serie_diaria(datos[("nieve", cod)])
        s = s.where((s <= desh.NIEVE_MAX_PLAUSIBLE_CM) & (s >= -10)).clip(lower=0)
        nieve[cod] = s.reindex(dias)
    nieve = pd.DataFrame(nieve)
    # Las mismas cuatro de m4_deshielo: el corte de 50 cm se fijo con su mediana.
    fijas = [c for c in desh.ESTACIONES_NIEVE if c in nieve.columns]
    altas = catalogos["temperatura"][catalogos["temperatura"]["altitud_m"] >= desh.ALTITUD_ALTA_M]
    iso = pd.DataFrame({cod: alt + desh.serie_diaria(datos[("temperatura", cod)]).reindex(dias)
                        / desh.GRADIENTE_C_KM * 1000.0
                        for cod, alt in zip(altas["codigo"], altas["altitud_m"])}).median(axis=1)
    t = pd.DataFrame({"nieve_cm": nieve[fijas].median(axis=1), "isoterma_m": iso})
    t["nevo"] = t["nieve_cm"].diff() >= desh.NIEVE_NUEVA_CM
    t["linea_nieve_m"] = desh.linea_de_nieve(t["isoterma_m"], t["nevo"])
    # El ultimo dia COMPLETO, no el de hoy. m4_deshielo trabaja con medianas de
    # dias enteros, y a las 00:30 el dia de hoy tiene una sola lectura, la mas
    # fria: la condicion se apagaba cada medianoche y se prendia cada mediodia.
    # La nieve acumulada cambia en dias, asi que el desfase no le quita nada.
    hoy = t.iloc[-2]
    activo = bool(hoy["nieve_cm"] >= desh.NIEVE_MIN_CM and hoy["isoterma_m"] > hoy["linea_nieve_m"])
    return {"activo": activo, "dia": str(t.index[-2].date()), "nieve_cm": _num(hoy["nieve_cm"]),
            "isoterma_m": _num(hoy["isoterma_m"]), "linea_nieve_m": _num(hoy["linea_nieve_m"]),
            "estaciones_nieve": int(len(fijas))}


def _num(v, dec=1):
    return None if v is None or not np.isfinite(v) else round(float(v), dec)


def evaluar(momento, fuente, fijo, modelo=None) -> dict:
    """El boletin de un momento. `modelo` = (b0, b1) reemplaza al congelado:
    lo usa el visor para repasar un invierno con el modelo que no lo vio."""
    cat = fijo["catalogos"]
    datos = bajar_todo(fuente, cat, momento)
    episodios, estado = episodios_en_ventana(datos, cat, momento)
    tor = temporal_en_curso(episodios, momento)
    lluvia = cat["lluvia"]

    vigentes = estado[estado["descartada_por"].eq("") & estado["ultima_lectura"].notna()]
    vigentes = vigentes[vigentes["ultima_lectura"] >= momento - pd.Timedelta(hours=VIGENTE_H)]
    n_vigentes = lluvia[lluvia["codigo"].isin(vigentes["codigo"])].groupby("provincia").size()

    provincias = {}
    totales = pd.DataFrame()
    if tor is not None:
        totales = niv.lluvia_por_temporal(episodios, tor).merge(
            lluvia[["codigo", "nombre", "provincia", "normal_mm"]],
            left_on="estacion_codigo", right_on="codigo")
        totales = totales[totales["provincia"].notna() & totales["normal_mm"].notna()]
        totales["fraccion"] = totales["lluvia_mm"] / totales["normal_mm"]

    for p in alerta.PROVINCIAS:
        sel = totales[totales["provincia"] == p] if len(totales) else totales
        orden = sel.sort_values("fraccion", ascending=False) if len(sel) else sel
        # El nivel lo fija la SEGUNDA estacion mas mojada: hacen falta dos que
        # lo digan. Ver m5_niveles.py.
        primera = orden.iloc[0] if len(orden) else None
        segunda = orden.iloc[1] if len(orden) > 1 else None
        frac = float(segunda["fraccion"]) if segunda is not None else 0.0
        prob = probabilidad(frac, modelo)
        nivel = nivel_de(prob) if tor is not None else "ninguna"
        siguiente = None
        for nombre, umbral in niv.NIVELES:
            if prob < umbral:
                f = fraccion_para(umbral, modelo)
                # Lo que falta para que DOS estaciones lleguen al corte: el
                # segundo menor faltante, en mm de la normal de cada una.
                if len(sel) > 1:
                    falta = (f * sel["normal_mm"] - sel["lluvia_mm"]).clip(lower=0).sort_values()
                    i = falta.index[1]
                    siguiente = {"nivel": nombre, "falta_mm": _num(falta[i]),
                                 "estacion": sel.loc[i, "nombre"]}
                else:
                    siguiente = {"nivel": nombre, "fraccion_normal": _num(f, 3)}
                break
        provincias[p] = {
            "nivel": nivel, "probabilidad": _num(prob, 3),
            "fraccion_normal": _num(frac, 3),
            "estacion_que_fija": None if segunda is None else segunda["nombre"],
            "lluvia_temporal_mm": None if segunda is None else _num(segunda["lluvia_mm"]),
            "normal_anual_mm": None if segunda is None else _num(segunda["normal_mm"], 0),
            "estacion_mas_mojada": None if primera is None else primera["nombre"],
            "lluvia_mas_mojada_mm": None if primera is None else _num(primera["lluvia_mm"]),
            "fraccion_mas_mojada": None if primera is None else _num(primera["fraccion"], 3),
            "siguiente_nivel": siguiente,
            "estaciones_transmitiendo": int(n_vigentes.get(p, 0)),
            "datos_insuficientes": bool(n_vigentes.get(p, 0) < MIN_ESTACIONES),
        }

    cortes = []
    con_alerta = [p for p, v in provincias.items() if v["nivel"] != "ninguna"]
    for p in con_alerta:
        sel = fijo["cortes"][fijo["cortes"]["provincia"] == p].sort_values("rank")
        # Un tronco que corre junto a una ruta la cruza decenas de veces, y
        # llenaria la lista con un solo lugar: se deja el primer cruce de cada
        # quebrada con cada via.
        sel = sel.drop_duplicates(subset=["id_cuenca", "via_nombre", "via_tipo"])
        for _, c in sel.head(CORTES_POR_PROVINCIA).iterrows():
            cortes.append({"provincia": p, "rank": int(c["rank"]),
                           "via": c["via_nombre"] if isinstance(c["via_nombre"], str) and c["via_nombre"] else "(sin nombre en OSM)",
                           "tipo_via": c["via_tipo"], "comuna": c["comuna"], "clase": c["clase"],
                           "area_cruce_km2": _num(c["area_cruce_km2"]),
                           "lat": _num(c["lat"], 5), "lon": _num(c["lon"], 5)})

    return {
        "momento": momento.tz_convert(ZONA).isoformat(),
        "fuente": "cache de M4 (repaso)" if isinstance(fuente, CacheM4) else "VIPNET en vivo",
        "calibracion": CALIBRACION,
        "temporal": None if tor is None else {
            "inicio": tor.loc[0, "inicio"].tz_convert(ZONA).isoformat(),
            "ultima_lluvia": tor.loc[0, "fin"].tz_convert(ZONA).isoformat(),
            "estaciones_sobre_5mm": int(tor.loc[0, "estaciones_5mm"])},
        "provincias": provincias,
        "deshielo": deshielo_hoy(datos, cat, momento),
        "cortes_a_vigilar": cortes,
        # La lluvia del temporal en cada estacion, para el visor.
        "lluvia_por_estacion": [] if totales.empty else [
            {"codigo": f["estacion_codigo"], "lluvia_mm": _num(f["lluvia_mm"]),
             "fraccion_normal": _num(f["fraccion"], 3)} for _, f in totales.iterrows()],
        "estaciones": {"lluvia": int(len(lluvia)),
                       "validas_en_ventana": int(estado["descartada_por"].eq("").sum()),
                       "transmitiendo": int(len(vigentes))},
    }


# =============================================================================
# El boletin
# =============================================================================

def boletin(r: dict) -> str:
    m = pd.Timestamp(r["momento"])
    lineas = [f"# Alerta por quebradas, Region de Coquimbo",
              "", f"Emitido para el {m:%d-%m-%Y a las %H:%M} (hora de Chile). "
              f"Fuente: {r['fuente']}. Modelo: {r['calibracion']}.", ""]
    t = r["temporal"]
    if t is None:
        lineas += ["**Sin temporal en curso.** Ninguna estacion acumula un episodio de 5 mm "
                   "en las ultimas 24 horas.", ""]
    else:
        ini = pd.Timestamp(t["inicio"])
        dur = (m - ini).total_seconds() / 86400
        lineas += [f"**Temporal en curso** desde el {ini:%d-%m-%Y %H:%M} ({dur:.1f} dias), "
                   f"con {t['estaciones_sobre_5mm']} estaciones sobre 5 mm.", ""]
    lineas += ["| Provincia | Nivel | Probabilidad | Las dos estaciones mas mojadas | "
               "% de la normal (la segunda) | Para el siguiente nivel | Estaciones transmitiendo |",
               "|---|---|---|---|---|---|---|"]
    for p, v in r["provincias"].items():
        lluvia = (f"{v['estacion_mas_mojada']} {v['lluvia_mas_mojada_mm']:.0f} mm, "
                  f"{v['estacion_que_fija']} {v['lluvia_temporal_mm']:.0f} mm"
                  if v["estacion_que_fija"] else "-")
        s = v["siguiente_nivel"]
        if s is None:
            sig = "ya en roja"
        elif "falta_mm" in s:
            sig = f"{s['nivel']}: faltan {s['falta_mm']:.0f} mm en {s['estacion']}"
        else:
            sig = f"{s['nivel']}: {s['fraccion_normal']:.0%} de la normal"
        trans = f"{v['estaciones_transmitiendo']}" + (" (DATOS INSUFICIENTES)" if v["datos_insuficientes"] else "")
        lineas.append(f"| {p} | **{SIGNO[v['nivel']]}** | {v['probabilidad']:.0%} | {lluvia} | "
                      f"{v['fraccion_normal']:.0%} | {sig} | {trans} |")
    d = r["deshielo"]
    lineas += ["", f"**Deshielo (experimental):** {'ACTIVO' if d['activo'] else 'inactivo'} "
               f"(ultimo dia completo, {d['dia']}). "
               f"Nieve {d['nieve_cm'] if d['nieve_cm'] is not None else '-'} cm "
               f"(mediana de {d['estaciones_nieve']} estaciones), isoterma 0 a "
               f"{d['isoterma_m'] if d['isoterma_m'] is not None else '-'} m, linea de nieve "
               f"{d['linea_nieve_m'] if d['linea_nieve_m'] is not None else '-'} m."
               + (" Con nieve acumulada y la isoterma sobre la linea de nieve, cualquier "
                  "temporal puede activar quebradas con menos lluvia de la que indican los "
                  "niveles." if d["activo"] else "")]
    if r["cortes_a_vigilar"]:
        lineas += ["", "## Tramos de ruta a vigilar", "",
                   "Los primeros de la lista de M3 en cada provincia con alerta: cruces de "
                   "una via con el cauce de una quebrada, ordenados por clase de cuenca, "
                   "jerarquia de la via y area drenada. Son candidatos, no cortes predichos.", "",
                   "| Provincia | Via | Comuna | Area drenada | Clase | Ubicacion |",
                   "|---|---|---|---|---|---|"]
        for c in r["cortes_a_vigilar"]:
            lineas.append(f"| {c['provincia']} | {c['via']} ({c['tipo_via']}) | {c['comuna']} | "
                          f"{c['area_cruce_km2']} km2 | {c['clase']} | {c['lat']}, {c['lon']} |")
    lineas += ["", "## Como leer este boletin", "",
               "El nivel de una provincia sale de la lluvia del temporal en su SEGUNDA "
               "estacion mas mojada, como fraccion de lo que llueve ahi en un anio normal "
               "(CR2MET 1991-2020): hacen falta dos estaciones que lo digan, porque un "
               "pluviometro solo puede fallar. Amarilla: una de cada cuatro provincias en esa situacion tuvo "
               "activaciones de quebradas en 2024-2026; naranja, una de cada dos; roja, tres "
               "de cada cuatro. Dice en que provincias es probable que haya activaciones, "
               "no cuales quebradas: eso los pluviometros no lo resuelven. Calibrado con 12 "
               "casos positivos en tres inviernos: es una herramienta de apoyo, no un "
               "pronostico oficial."]
    return "\n".join(lineas) + "\n"


def imprimir(r: dict):
    m = pd.Timestamp(r["momento"])
    t = r["temporal"]
    cab = "sin temporal en curso" if t is None else \
        f"temporal desde {pd.Timestamp(t['inicio']):%d-%m %H:%M}"
    print(f"\n{m:%d-%m-%Y %H:%M}  ({cab}; {r['estaciones']['transmitiendo']} estaciones "
          f"transmitiendo; {r['fuente']})")
    for p, v in r["provincias"].items():
        aviso = "  DATOS INSUFICIENTES" if v["datos_insuficientes"] else ""
        print(f"  {p:<7} {SIGNO[v['nivel']]:<9} P {v['probabilidad']:.2f}  "
              f"{v['fraccion_normal']:>5.0%} de la normal{aviso}")
    if r["deshielo"]["activo"]:
        print("  deshielo (experimental): ACTIVO")


# =============================================================================
# Orquestacion
# =============================================================================

def momento_de(texto: str | None) -> pd.Timestamp:
    if texto is None:
        ahora = pd.Timestamp.now(tz=ZONA)
    else:
        ahora = m4._hora_local(texto)
    return ahora.floor(f"{m4.PASO_MIN}min").tz_convert("UTC")


def repasar(fijo, cache):
    """El final de cada temporal regional, contra lo que dijo m5_niveles."""
    episodios = pd.read_csv(RAIZ / "outputs" / "m4_episodios.csv")
    for col in ("inicio", "fin"):
        episodios[col] = pd.to_datetime(episodios[col], utc=True)
    tor = alerta.temporales(episodios)
    ref = pd.read_csv(RAIZ / "outputs" / "m5_niveles.csv")
    print("\nRepaso: el final de cada temporal regional, contra m5_niveles "
          "(nivel con el modelo de los tres inviernos)")
    print(f"  {'temporal':<12} " + "".join(f"{p:<26}" for p in alerta.PROVINCIAS))
    iguales = total = 0
    for _, t in tor[tor["regional"]].iterrows():
        momento = (t["fin"] + pd.Timedelta(minutes=30)).floor("30min")
        r = evaluar(momento, cache, fijo)
        celdas = []
        for p in alerta.PROVINCIAS:
            vivo = r["provincias"][p]
            f = ref[(ref["temporal"] == t["temporal"]) & (ref["provincia"] == p)]
            esperado = f["nivel"].iloc[0] if len(f) else "excluida"
            if len(f):
                total += 1
                iguales += vivo["nivel"] == esperado
            marca = "=" if vivo["nivel"] == esperado else "!"
            celdas.append(f"{marca} {vivo['nivel']:<8} ({esperado})".ljust(26))
        print(f"  {t['inicio'].tz_convert(ZONA):%d-%m-%Y}   " + "".join(celdas))
    print(f"\n  mismo nivel en {iguales} de {total} provincias-temporal")


def main():
    ap = argparse.ArgumentParser(description="M6 - La alerta en vivo por provincia.")
    ap.add_argument("--momento", help="'AAAA-MM-DD HH:MM' en hora de Chile; por defecto, ahora")
    ap.add_argument("--repasar", action="store_true")
    ap.add_argument("--cronologia", nargs=3, metavar=("DESDE", "HASTA", "PASO_H"))
    ap.add_argument("--fuente", choices=("auto", "cache", "vivo"), default="auto")
    args = ap.parse_args()

    print("=" * 74)
    print("M6 - Alerta en vivo por provincia")
    print("=" * 74)
    verificar_modelo()
    fijo = preparar()
    cache = CacheM4()

    if args.repasar:
        repasar(fijo, cache)
        return
    if args.cronologia:
        desde, hasta = momento_de(args.cronologia[0]), momento_de(args.cronologia[1])
        paso = pd.Timedelta(hours=float(args.cronologia[2]))
        momento = desde
        while momento <= hasta:
            imprimir(evaluar(momento, cache, fijo))
            momento += paso
        return

    momento = momento_de(args.momento)
    if args.fuente == "cache" or (args.fuente == "auto" and cache.cubre(momento)):
        fuente = cache
    else:
        fuente = AlmacenVivo()
    r = evaluar(momento, fuente, fijo)
    imprimir(r)

    dir_out = RAIZ / "outputs"
    (dir_out / "boletines").mkdir(parents=True, exist_ok=True)
    (dir_out / "alerta_en_vivo.json").write_text(json.dumps(r, indent=2, ensure_ascii=False),
                                                 encoding="utf-8")
    ruta_b = dir_out / "boletines" / f"boletin_{pd.Timestamp(r['momento']):%Y-%m-%d_%H%M}.md"
    ruta_b.write_text(boletin(r), encoding="utf-8")
    print(f"\n  json    -> outputs/alerta_en_vivo.json")
    print(f"  boletin -> outputs/boletines/{ruta_b.name}")


if __name__ == "__main__":
    main()
