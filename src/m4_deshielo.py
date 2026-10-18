"""
M4 - Indicador experimental de deshielo: nieve acumulada y lluvia encima.

POR QUE EXISTE

    El bloque del 11 al 18 de agosto de 2026 activo veinte zonas con una
    lluvia mediana de 4,6 mm. Ninguna cuenca supero Caine, y la prensa lo
    atribuyo al "derretimiento acelerado de la nieve acumulada" con lluvia en
    altura. Un umbral de lluvia no puede ver eso: le falta la variable. Este
    script la agrega con dos redes de VIPNET que M4 no usaba para esto, la de
    nieve (tipoEstacion 3) y la temperatura de las estaciones altas.

LO QUE MIDE, DIA POR DIA

    nieve_cm       La mediana de la altura de nieve en las cuatro estaciones
                   de nieve con dato en al menos el 80% de los dias de
                   2024-2026, fijadas por codigo en ESTACIONES_NIEVE: Cerro
                   Olivares, Glaciar Tapado, Quebrada Larga y El Soldado, de
                   3.293 a 4.065 m, de Elqui a Choapa. Las otras
                   seis empezaron a transmitir en 2025 o 2026, y una mediana
                   sobre un conjunto que cambia de un anio a otro compara
                   redes, no inviernos.

    isoterma_m     La altura de 0 grados, extrapolada desde las estaciones de
                   temperatura sobre 3.000 m con el gradiente estandar de
                   6,5 grados por km. No es la isoterma de m4_lluvia.py, que
                   ajusta una recta sobre toda la red y la acepta solo con R2
                   de 0,70 o mas. Eso se cumple en dias de temporal; fuera de
                   ellos la inversion termica de la costa rompe la recta, y el
                   bloque de agosto queda entero sin isoterma. Las estaciones
                   altas estan sobre la inversion, y extrapolar menos de un km
                   con el gradiente estandar se equivoca en cientos de metros,
                   no en miles.

    linea_nieve_m  La isoterma mas baja de los dias en que nevo -la mediana
                   de nieve subio 5 cm o mas- en los 30 dias anteriores.
                   Sobre esa altura quedo nieve.

    deshielo       nieve_cm de 50 o mas, e isoterma_m sobre linea_nieve_m.
                   Hay nieve acumulada, y la franja de 0 grados esta sobre su
                   borde inferior: esa nieve esta recibiendo lluvia o
                   derritiendose.

LO QUE NO ES

    Un umbral calibrado. Hay un solo evento de deshielo documentado, y con uno
    no se calibra nada. Los 50 cm son una descripcion de que 2026 fue
    distinto: estas cuatro estaciones nunca pasaron de 40 cm en 2024 ni de
    23 cm en 2025, y estaban entre 111 y 136 cm al empezar cada temporal de
    2026 posterior a julio. Cualquier corte entre 41 y 110 cm da el mismo
    resultado sobre estos tres inviernos, y 50 es el numero redondo mas bajo
    de ese hueco. El invierno siguiente con mucha nieve dira si sirve.

    Tampoco es regional por provincia. Cuatro estaciones no alcanzan para
    tres provincias, y el bloque de agosto se activo en las tres.

LO QUE SALIO

    Corrida 2026-10-11_m4_deshielo.txt. La nieve maxima de las cuatro
    estaciones fue de 40 cm en 2024, 23 cm en 2025 y 157 cm en 2026, el 24 de
    julio, despues del temporal. La condicion de deshielo no aparece nunca en
    2024 ni en 2025, y en 2026 queda activa del 22 de julio al 23 de agosto
    (mas el 19 y 20 de julio, en medio de la nevada): un mes de nieve
    acumulada con la isoterma sobre la linea de nieve de julio. Lo que la
    vuelve peligrosa es que llueva encima, y por eso m5_alerta_sector.py la
    cruza con los temporales: la tienen el de julio, el del 30 de julio, el
    chico del 4 de agosto y el bloque del 11 al 18.

    En la alerta, "Caine o deshielo" sube el recall por provincia en los
    temporales regionales de 0,25 a 0,67 y la precision de 0,43 a 0,67, con
    la misma tasa de falsas alarmas. Pero de los cinco aciertos que agrega,
    tres son el bloque de agosto que motivo el indicador. Uno (Elqui en el
    temporal de julio) sale de dos dias de la condicion en medio de la
    nevada, que no es deshielo. El quinto, Elqui el 30 de julio, es lluvia
    con la isoterma a 3.800 m sobre la nieve recien caida: deshielo
    plausible, pero no documentado como tal. Es una hipotesis bien planteada
    con un caso a favor, no un resultado.

Uso:

    python src/m4_deshielo.py

Baja diez series de nieve de VIPNET (o las lee del cache de M4) y lee del
cache las de temperatura. Un par de minutos, menos de 1 GB.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_lluvia as m4  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent

TIPO_NIEVE = 3
GRADIENTE_C_KM = 6.5          # atmosfera estandar (ICAO)
ALTITUD_ALTA_M = 3000.0
COBERTURA_NIEVE_MIN = 0.80
NIEVE_MIN_CM = 50.0

# Las cuatro estaciones con registro completo en 2024-2026, fijadas por codigo.
# El corte de 50 cm se refiere a la mediana de estas cuatro: si despues la red
# crece y entran otras, el umbral tiene que seguir midiendo lo mismo. Sin fijarlas,
# m6_alerta_en_vivo.py, que mira 40 dias, tomaba ocho estaciones y comparaba otra
# mediana contra el mismo corte. COBERTURA_NIEVE_MIN queda como control: si una
# de las cuatro baja de ahi, el reporte lo dice.
ESTACIONES_NIEVE = ("04300001-2",   # Cerro Olivares, 3.566 m
                    "04300004-7",   # Glaciar Tapado en Los Corrales, 4.065 m
                    "04520006-K",   # Quebrada Larga, 3.550 m
                    "04700002-5")   # El Soldado, 3.293 m
NIEVE_NUEVA_CM = 5.0
DIAS_LINEA_NIEVE = 30

# La serie de nieve trae valores imposibles: 99.990 en Glaciar Tapado, 8.054
# en Los Azules. Mas de 4 m en estas estaciones no se ha medido nunca (el maximo
# plausible de la ventana es 2,9 m en Cerro Vega Negra), y bajo cero es ruido
# del sensor en torno a suelo desnudo.
NIEVE_MAX_PLAUSIBLE_CM = 400.0


def serie_diaria(datos: list[dict]) -> pd.Series:
    """Mediana diaria de una serie de VIPNET, por dia de reloj chileno."""
    if not datos:
        return pd.Series(dtype=float)
    s = pd.Series([d.get("instantaneo", np.nan) for d in datos],
                  index=m4._fechas_api(datos), dtype=float)
    s = s.tz_convert(m4.ZONA_CHILE)
    return s.groupby(s.index.tz_localize(None).normalize()).median()


def nieve_regional(cache: Path, refrescar: bool, inicio: str, fin: str):
    catalogo = m4.descargar_catalogo(TIPO_NIEVE, cache=cache, refrescar=refrescar,
                                     inicio=inicio, fin=fin)
    dias = pd.date_range(inicio, fin, freq="D")
    tabla = {}
    for cod in catalogo["codigo"]:
        datos = m4.serie_con_cache(cod, TIPO_NIEVE, cache, refrescar, inicio, fin)
        s = serie_diaria(datos)
        s = s.where((s <= NIEVE_MAX_PLAUSIBLE_CM) & (s >= -10)).clip(lower=0)
        tabla[cod] = s.reindex(dias)
    tabla = pd.DataFrame(tabla)
    cobertura = tabla.notna().mean()
    fijas = [c for c in ESTACIONES_NIEVE if c in tabla.columns]
    print(f"\nEstaciones de nieve en Coquimbo: {len(catalogo)}; las de referencia "
          f"(ESTACIONES_NIEVE): {len(fijas)} de {len(ESTACIONES_NIEVE)}")
    for _, e in catalogo.iterrows():
        marca = "  referencia" if e["codigo"] in fijas else ""
        print(f"  {e['nombre'][:32]:<32} {e['altitud_m']:>5.0f} m  "
              f"cobertura {cobertura[e['codigo']]:>4.0%}{marca}")
    bajas = [c for c in fijas if cobertura[c] < COBERTURA_NIEVE_MIN]
    if bajas or len(fijas) < len(ESTACIONES_NIEVE):
        print(f"  AVISO: estaciones de referencia sin dato o bajo el "
              f"{COBERTURA_NIEVE_MIN:.0%}: la mediana mezcla menos estaciones que las "
              "que fijaron el corte de 50 cm.")
    return tabla[fijas].median(axis=1), tabla[fijas].notna().sum(axis=1)


def isoterma_altas(cache: Path, refrescar: bool, inicio: str, fin: str):
    catalogo = m4.descargar_catalogo(m4.TIPO_TEMPERATURA, cache=cache, refrescar=refrescar,
                                     inicio=inicio, fin=fin)
    altas = catalogo[catalogo["altitud_m"] >= ALTITUD_ALTA_M]
    dias = pd.date_range(inicio, fin, freq="D")
    tabla = {}
    for cod, alt in zip(altas["codigo"], altas["altitud_m"]):
        datos = m4.serie_con_cache(cod, m4.TIPO_TEMPERATURA, cache, refrescar, inicio, fin)
        t = serie_diaria(datos).reindex(dias)
        tabla[cod] = alt + t / GRADIENTE_C_KM * 1000.0
    tabla = pd.DataFrame(tabla)
    print(f"\nEstaciones de temperatura sobre {ALTITUD_ALTA_M:.0f} m: {len(altas)}")
    return tabla.median(axis=1), tabla.notna().sum(axis=1)


def linea_de_nieve(isoterma: pd.Series, nevo: pd.Series) -> pd.Series:
    """La isoterma mas baja de los dias con nieve nueva en los 30 dias previos."""
    iso_nevada = isoterma.where(nevo)
    return iso_nevada.shift(1).rolling(DIAS_LINEA_NIEVE, min_periods=1).min()


def figura(t: pd.DataFrame, ruta: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
    a1.plot(t.index, t["nieve_cm"], color="#2166ac", lw=1.2)
    a1.axhline(NIEVE_MIN_CM, color="#b2182b", lw=0.8, ls="--",
               label=f"{NIEVE_MIN_CM:.0f} cm")
    a1.set_ylabel("nieve (cm), mediana\nde 4 estaciones")
    a1.legend(loc="upper left", fontsize=8)
    a2.plot(t.index, t["isoterma_m"], color="#888888", lw=0.8, label="isoterma 0")
    a2.plot(t.index, t["linea_nieve_m"], color="#2166ac", lw=1.2,
            label="linea de nieve (30 dias)")
    a2.set_ylabel("altitud (m)")
    a2.legend(loc="upper left", fontsize=8)
    for ax in (a1, a2):
        ymin, ymax = ax.get_ylim()
        ax.fill_between(t.index, ymin, ymax, where=t["deshielo"], color="#ef8a62",
                        alpha=0.35, lw=0)
        ax.set_ylim(ymin, ymax)
    a1.set_title("Indicador experimental de deshielo (naranjo: condicion activa)")
    fig.tight_layout()
    fig.savefig(ruta, dpi=130)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="M4 - Indicador experimental de deshielo.")
    ap.add_argument("--refrescar", action="store_true")
    ap.add_argument("--inicio", default=m4.VENTANA_INICIO)
    ap.add_argument("--fin", default=m4.VENTANA_FIN)
    ap.add_argument("--cache", type=Path, default=m4.CACHE_LLUVIA)
    args = ap.parse_args()

    print("=" * 74)
    print(f"M4 - Indicador experimental de deshielo, {args.inicio} a {args.fin}")
    print("=" * 74)

    nieve, n_nieve = nieve_regional(args.cache, args.refrescar, args.inicio, args.fin)
    iso, n_iso = isoterma_altas(args.cache, args.refrescar, args.inicio, args.fin)

    t = pd.DataFrame({"nieve_cm": nieve, "estaciones_nieve": n_nieve,
                      "isoterma_m": iso, "estaciones_temperatura": n_iso})
    t["nevo"] = t["nieve_cm"].diff() >= NIEVE_NUEVA_CM
    t["linea_nieve_m"] = linea_de_nieve(t["isoterma_m"], t["nevo"])
    t["deshielo"] = ((t["nieve_cm"] >= NIEVE_MIN_CM)
                     & (t["isoterma_m"] > t["linea_nieve_m"])).fillna(False)
    t.index.name = "dia"

    print("\nNieve maxima por invierno (mediana de las estaciones usadas):")
    for anio, g in t.groupby(t.index.year):
        print(f"  {anio}: {g['nieve_cm'].max():>5.0f} cm, el {g['nieve_cm'].idxmax():%d-%m}")

    activos = t.index[t["deshielo"]]
    print(f"\nDias con condicion de deshielo: {len(activos)}")
    if len(activos):
        tramos = (pd.Series(activos).diff() != pd.Timedelta(days=1)).cumsum()
        for _, g in pd.Series(activos).groupby(tramos.to_numpy()):
            print(f"  {g.iloc[0]:%d-%m-%Y} al {g.iloc[-1]:%d-%m-%Y}")

    dir_out = RAIZ / "outputs"
    t.to_csv(dir_out / "m4_deshielo.csv", float_format="%.1f")
    figura(t, dir_out / "m4_deshielo.png")
    print("\n  tabla  -> m4_deshielo.csv")
    print("  figura -> m4_deshielo.png")


if __name__ == "__main__":
    main()
