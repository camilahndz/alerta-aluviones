"""
M4 - Umbrales de lluvia intensidad-duracion, con su cita al lado.

La idea de fondo:

    M2 dijo que quebradas *pueden* generar un flujo de detritos. Un umbral I-D
    responde la otra mitad: *cuando*. Se expresa como una curva

        I = alfa * D^(-beta)

    con I la intensidad de lluvia en mm/h y D la duracion del episodio en horas.
    La curva baja hacia la derecha porque un chaparron corto tiene que ser
    violento para gatillar, mientras que una lluvia larga puede ser suave y
    lograrlo por saturacion.

Por que este proyecto no ajusta un umbral propio:

    Una curva I-D se calibra con decenas de pares (episodio, activo / no activo).
    En la ventana de este proyecto hay tres bloques con activaciones
    documentadas. Una curva ajustada sobre tres puntos pasa por los tres y no
    predice nada: seria un ejercicio de dibujo, no de calibracion.

    Lo que se hace en cambio es aplicar umbrales **publicados** y guardar una
    columna por umbral, sin elegir ganador. Es el mismo criterio con que M2
    guarda las dos clasificaciones (Wilford y solo Melton) en vez de decidir por
    el lector.

Por que estos dos y no otros:

    Caine (1980) es el umbral global clasico, el que cita todo el mundo, con un
    rango de validez declarado que va de 10 minutos a 10 dias. Sirve de
    referencia de arriba.

    Ben David-Novak et al. (2004) se calibro en el desierto de Judea, o sea en
    clima hiperarido, que es lo mas parecido a Coquimbo que hay publicado con
    coeficientes verificables. Sirve de referencia de abajo.

    Entre los dos encierran el rango donde deberia caer un umbral local, si
    alguna vez hay datos para ajustarlo. Eso es M5, no M4.

Uso:

    python src/m4_umbrales.py        # imprime los umbrales con sus citas

Tambien se importa desde m4_lluvia.py, que es quien le pasa los episodios.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class Umbral:
    """Un umbral publicado, con todo lo necesario para poder defenderlo.

    `columna` es el nombre que lleva en gatillo.gpkg. `validez` y `cita` no son
    decoracion: un umbral aplicado fuera del rango o de la region donde se
    calibro sigue devolviendo un numero, y ese numero no significa nada. Que la
    advertencia viaje pegada al coeficiente es la unica forma de que nadie la
    lea por separado.
    """

    nombre: str
    columna: str
    forma: str
    validez: str
    cita: str
    advertencia: str
    supera: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray]


# --- Caine (1980) ------------------------------------------------------------
# I = 14,82 * D^(-0,39), con I en mm/h y D en horas.
# Los coeficientes estan verificados contra el articulo original.
CAINE_ALFA = 14.82
CAINE_BETA = 0.39

# Rango de validez declarado por el autor: 10 minutos a 10 dias.
CAINE_D_MIN_H = 10.0 / 60.0
CAINE_D_MAX_H = 240.0


def caine_intensidad_critica(duracion_h):
    """La intensidad que Caine pide para una duracion dada, en mm/h.

    Fuera del rango declarado devuelve NaN en vez de extrapolar. Extrapolar una
    ley de potencia es barato de programar y no significa nada: la curva sigue
    bajando suavemente y entrega un numero con aspecto razonable para una
    duracion sobre la que el autor nunca dijo nada.
    """
    d = np.asarray(duracion_h, dtype="float64")
    critica = CAINE_ALFA * np.power(d, -CAINE_BETA, where=d > 0,
                                    out=np.full_like(d, np.nan))
    fuera = (d < CAINE_D_MIN_H) | (d > CAINE_D_MAX_H)
    return np.where(fuera, np.nan, critica)


def _supera_caine(duracion_h, intensidad_media, intensidad_max_60min):
    """Caine se enuncia sobre la intensidad **media** del episodio."""
    del intensidad_max_60min  # no lo usa; se recibe para tener una sola firma
    critica = caine_intensidad_critica(duracion_h)
    return np.asarray(intensidad_media, dtype="float64") >= critica


# --- Ben David-Novak et al. (2004) -------------------------------------------
# No es una ley de potencia sino un par de cortes: 30 mm/h sostenidos durante al
# menos una hora.
BDN_INTENSIDAD_MM_H = 30.0
BDN_DURACION_MIN_H = 1.0


def _supera_ben_david_novak(duracion_h, intensidad_media, intensidad_max_60min):
    """Se evalua sobre la intensidad maxima en 60 minutos, no sobre la media.

    Porque asi esta enunciado: "30 mm/h durante al menos una hora" es una
    condicion sobre la hora mas intensa del episodio. Usar la media lo volveria
    una condicion sobre el episodio completo, que es un umbral distinto y mucho
    mas exigente. Se han visto ambas lecturas en la literatura secundaria; esta
    es la del articulo.
    """
    del intensidad_media
    return ((np.asarray(intensidad_max_60min, dtype="float64") >= BDN_INTENSIDAD_MM_H)
            & (np.asarray(duracion_h, dtype="float64") >= BDN_DURACION_MIN_H))


UMBRALES = (
    Umbral(
        nombre="Caine (1980)",
        columna="supera_caine",
        forma=f"I = {CAINE_ALFA} * D^(-{CAINE_BETA})",
        validez="D de 10 min a 10 dias; umbral global",
        cita=("Caine, N. (1980). The rainfall intensity-duration control of "
              "shallow landslides and debris flows. Geografiska Annaler A, "
              "62(1-2), 23-27."),
        advertencia=(
            "Es un umbral global armado con eventos de todo el mundo, la mayoria "
            "de climas humedos. Sobre una region arida deberia quedar alto."
        ),
        supera=_supera_caine,
    ),
    Umbral(
        nombre="Ben David-Novak et al. (2004)",
        columna="supera_ben_david_novak",
        forma=f"I >= {BDN_INTENSIDAD_MM_H:.0f} mm/h durante D >= {BDN_DURACION_MIN_H:.0f} h",
        validez="clima hiperarido; se evalua sobre la I maxima en 60 min",
        cita=("Ben David-Novak, H., Morin, E., & Enzel, Y. (2004). Modern extreme "
              "storms and the rainfall thresholds for initiating debris flows on "
              "the hyperarid western escarpment of the Dead Sea, Israel. GSA "
              "Bulletin, 116(5-6), 718-728. doi:10.1130/B25403.2"),
        advertencia=(
            "ADVERTENCIA DE TRANSFERENCIA. Se calibro sobre tormentas convectivas "
            "de desierto: chaparrones cortos y violentos de verano. Coquimbo "
            "recibe lluvia frontal de invierno, larga y suave. Es esperable que "
            "no se active nunca en esta ventana, y su silencio es informacion "
            "sobre el tipo de lluvia, no una falla del umbral."
        ),
        supera=_supera_ben_david_novak,
    ),
)


# --- El hueco, escrito ------------------------------------------------------
#
# GUZZETTI ET AL. (2008) NO ESTA Y DEBERIA ESTAR.
#
# Es el umbral global de referencia despues de Caine, el que actualiza su curva
# con un inventario mucho mayor, y cualquiera que lea este trabajo va a
# preguntar por que no aparece. La razon es que el articulo esta detras de pago
# y sus coeficientes no se pudieron verificar en ninguna fuente abierta.
#
# Escribir de memoria dos numeros bajo el nombre de un autor real es exactamente
# el error que el capitulo 12 del recorrido documenta: una cifra plausible, sin
# procedencia, que despues nadie puede rastrear. Preferimos el hueco visible.
#
# Para cerrarlo hacen falta alfa y beta leidos del articulo, y se agregan como
# un tercer Umbral en la tupla de arriba. Son dos numeros y una cita.
#
#   Guzzetti, F., Peruccacci, S., Rossi, M., & Stark, C. P. (2008). The rainfall
#   intensity-duration control of shallow landslides and debris flows: an
#   update. Landslides, 5(1), 3-17.
#
GUZZETTI_2008_PENDIENTE = None  # alfa, sin verificar -> no se usa
GUZZETTI_2008_EXPONENTE = None  # beta, sin verificar -> no se usa


def evaluar(duracion_h, intensidad_media, intensidad_max_60min) -> dict:
    """Aplica todos los umbrales y devuelve un dict columna -> arreglo de bool.

    Ninguno gana. El que lea gatillo.gpkg ve las dos columnas y decide, igual
    que con `clase` y `clase_melton` en M2.
    """
    return {
        u.columna: u.supera(duracion_h, intensidad_media, intensidad_max_60min)
        for u in UMBRALES
    }


def main():
    print("=" * 74)
    print("M4 - Umbrales I-D aplicados")
    print("=" * 74)

    for u in UMBRALES:
        print(f"\n{u.nombre}")
        print(f"  forma    : {u.forma}")
        print(f"  validez  : {u.validez}")
        print(f"  cita     : {u.cita}")
        print(f"  cuidado  : {u.advertencia}")

    print("\n" + "-" * 74)
    print("Caine, intensidad critica por duracion:")
    print(f"  {'D (h)':>8} {'I critica (mm/h)':>18}")
    for d in (0.5, 1, 3, 6, 12, 24, 48, 72, 144, 240):
        print(f"  {d:>8.1f} {float(caine_intensidad_critica(d)):>18.2f}")

    print("\n" + "-" * 74)
    print("PENDIENTE: Guzzetti et al. (2008) no esta incluido.")
    print("  El articulo esta detras de pago y sus coeficientes no se pudieron")
    print("  verificar en fuente abierta. Ver el comentario en este archivo.")


if __name__ == "__main__":
    main()
