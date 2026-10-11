"""
M4 - Gatillo: la lluvia sub-diaria que puede activar una quebrada.

La idea de fondo:

    M2 dijo que quebradas *pueden* generar un flujo de detritos. Este script
    arma la otra mitad: cuanta lluvia cayo, en cuanto tiempo, cerca de cada una
    de esas quebradas. Con eso se le pueden aplicar los umbrales publicados que
    viven en m4_umbrales.py.

    El producto no es una prediccion. Es una tabla de pares cuenca-episodio con
    su duracion, su intensidad y su lluvia antecedente, mas una columna por
    umbral. Quien la lea decide.

DE DONDE SALE LA LLUVIA, Y POR QUE DE AHI

    De VIPNET, el Visualizador Hidrometrico Nacional de la DGA
    (vipnet.mop.gob.cl), que expone una API REST publica: sin registro, sin
    token, sin captcha, y con paso de 30 minutos.

    El camino obvio no sirve. DGASAT (snia.mop.gob.cl/dgasat) entrega los mismos
    valores horarios, pero sus botones "Ver Tabla" y "Ver Grafico" estan detras
    de un reCAPTCHA v2. No es automatizable y no se intenta rodear.

    Tampoco se usa CR2MET ni ningun producto diario. La intensidad es
    sub-diaria: 150 mm en cuatro dias y 150 mm en seis horas son el mismo numero
    diario y fenomenos distintos. Y GPM IMERG quedo fuera por dos razones: no
    hizo falta -la mediana de distancia cuenca-estacion es del orden de 16 km,
    bajo el criterio de 30 km que se fijo antes de mirar- y su Final Run no
    cubre 2026.

LAS TRES DECISIONES QUE HAY QUE PODER DEFENDER

    1. Se trabaja con el acumulado, no con la suma de incrementos.

       VIPNET entrega dos campos por paso: `instantaneo`, que es el incremento
       del paso, y `acumulado`, que es el contador corrido de la estacion.
       Parecen redundantes y no lo son. En CUNCUMEN (04703003-K) la suma de
       incrementos da 208,0 mm y el acumulado sube 409,5 mm sobre la misma
       ventana. La diferencia esta justo donde la serie tiene huecos: el
       contador siguio avanzando y no quedo registro de los pasos intermedios.
       Sumar incrementos sub-cuenta exactamente en las estaciones que peor
       transmiten, que son las que mas interesa vigilar.

    2. Sin dato no es cero milimetros.

       La serie se arma sobre una grilla regular de 30 minutos y cada paso queda
       con un valor o con NaN, nunca con un cero de relleno. Un hueco largo
       corta el registro en vez de simular un periodo seco, porque un periodo
       seco falso parte un episodio en dos y le baja la duracion a los dos
       pedazos. Es el mismo error del cuadro vacio contra la consulta fallida
       que arruino tres corridas de M3, por el otro extremo.

    3. Los maximos imposibles de 30 minutos son nieve, no sensores rotos.

       Glaciar Tapado, a 4.065 m, registro 78,0 mm en media hora. En julio a esa
       altura no llueve: nieva, y el pluviometro suelta el equivalente de golpe
       cuando se derrite. El corte no se pone a ojo: con la temperatura de la
       misma red se ajusta dia a dia una recta de temperatura contra altitud y
       se despeja donde cruza los 0 grados. Esa es la isoterma 0 observada. El
       ajuste solo se acepta con 8 estaciones o mas, gradiente entre 2 y 10
       grados por km y R2 sobre 0,70; si no, ese dia queda sin isoterma y se
       dice.

LAS REGLAS DE SELECCION, ESCRITAS ANTES DE MIRAR LOS DATOS

    Se aplican en orden y el reporte dice que estacion cayo por cual:

        R1  estacion  esta en Coquimbo y declara parametro de precipitacion
        R2  estacion  cobertura de la ventana >= 50%
        R3  episodio  sin hueco de transmision adentro
        R4  estacion  incremento maximo de 30 min <= 20 mm
        R5  episodio  la estacion bajo la isoterma 0 observada

    R3 cambio de granularidad despues de mirar los datos, y eso queda escrito.
    La primera version era por estacion -descartar si el desajuste entre suma y
    acumulado pasaba de 0,10- y botaba 24 de las 107, entre ellas LAMBERT, que
    es la estacion mas cercana a 7 de las 21 cuencas criticas. Al ir a ver por
    que fallaban aparecio que el desajuste no estaba repartido sino concentrado
    en un solo hueco por estacion: en LAMBERT, 25,2 mm de un desajuste total de
    25,2 mm caben en un unico hueco de 94 horas del 24 de julio. El mecanismo
    que la regla vigilaba es el correcto, pero el dano esta localizado en el
    tiempo, asi que la regla paso a aplicarse por episodio con el mismo
    criterio. El efecto sobre el resultado se reporta en las dos versiones.

    Las estaciones ambiguas NO se descartan, se marcan. Son pares vecinos que se
    contradicen sin que ninguna regla pueda decidir cual esta mala: LAS BURRAS
    con 343,5 mm contra RIO ILLAPEL EN LAS BURRAS con 1,0 mm a 200 metros; EL
    MAITEN con 1,9 mm contra RIO MOSTAZAL EN CUESTECITA con 531,8 mm a 3,8 km.
    Elegir cual sobrevive mirando cual cuadra mejor con el resultado seria
    elegir el resultado.

LIMITE CONOCIDO: EL CORTE SECO MANDA SOBRE EL RESULTADO

    Un episodio es un bloque de lluvia separado del siguiente por un periodo
    seco. El corte es de 12 horas, centro del rango de 6 a 24 h que la
    literatura usa en clima arido. No hay valor canonico: es un juicio, y por
    eso el script corre la sensibilidad con los dos extremos y la reporta. Entre
    6 y 12 horas el numero de cuencas marcadas cambia varias veces. Es el mismo
    tipo de fragilidad que el umbral de largo de Wilford en M2, y se declara
    igual.

TRES INVIERNOS Y NO UNO (desde octubre de 2026)

    La ventana va del 1 de junio de 2024 al 23 de agosto de 2026. Con un solo
    temporal todas las observaciones son positivas y no hay con que calibrar;
    2024 y 2025 aportan episodios donde llovio y no se reporto nada. Eso obligo
    a tres cambios que no son de forma:

        - la hora: de un desfase fijo de 4 h a la zona America/Santiago, porque
          la ventana cruza seis cambios de hora. Ver ZONA_CHILE.
        - el cache: una subcarpeta por ventana, porque con una carpeta plana
          cambiar la ventana leia en silencio la serie vieja. Ver _ruta_cache.
        - los conteos: se reportan por invierno, porque un total de tres anios
          no dice de cual viene cada positivo.

LA LLUVIA DE LA CUENCA, NO LA DE SU ESTACION (desde octubre de 2026)

    A cada cuenca se le asigna la estacion mas cercana para el RELOJ de la
    lluvia -cuando empezo, cuanto duro-, y la CANTIDAD se escala con un modelo
    entrenado sobre latitud, longitud, altitud y distancia a la costa, si y solo
    si le gana a la estacion cercana dejando estaciones fuera. Todo el
    razonamiento esta en m4_interpolacion.py.

Uso:

    python src/m4_lluvia.py              # usa el cache de data/raw/lluvia/
    python src/m4_lluvia.py --refrescar  # vuelve a pegarle a VIPNET

Si faltan las capas de M1 y M2 el script igual corre la mitad de lluvia y
escribe los episodios; solo se salta el cruce con las cuencas, y lo dice.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clases_cuenca import CLASES_SUSCEPTIBLES  # noqa: E402
import m4_interpolacion as interp  # noqa: E402
from m4_umbrales import (UMBRALES, caine_intensidad_critica,  # noqa: E402
                         evaluar, razon_critica)

RAIZ = Path(__file__).resolve().parent.parent

# --- VIPNET ------------------------------------------------------------------
VIPNET = "https://vipnet.mop.gob.cl"
EP_ESTACIONES = f"{VIPNET}/v1/vipnet/estaciones/valor"
EP_SERIE = f"{VIPNET}/v1/vipnet/estacion/valores"

# tipoEstacion en la API: 0 precipitacion, 1 temperatura, 2 embalse, 3 nieve,
# 4 humedad, 5 viento. La numeracion sale del bundle del visualizador.
TIPO_PRECIPITACION = 0
TIPO_TEMPERATURA = 1

# El codigo de region de la API, que coincide con el numero romano de Coquimbo.
REGION_COQUIMBO = 4

# La API responde fechas en UTC y recibe fetchDay/fetchHour en hora local.
#
# Hasta octubre de 2026 la conversion era un desfase fijo de 4 horas, valido
# porque la ventana caia entera en invierno austral. Con tres inviernos la
# ventana cruza seis cambios de hora, y un desfase fijo corre una hora todo lo
# que cae en horario de verano sin que nada falle. Ahora se usa la zona
# 'America/Santiago' de la base IANA, que sabe cuando cambia la hora cada anio.
#
# La grilla vive en tiempo absoluto, no en hora de reloj. La diferencia importa
# dos veces al anio: el dia que se adelanta la hora tiene 46 pasos de 30 minutos
# y el dia que se atrasa tiene 50. Una grilla de hora de reloj tendria una hora
# repetida en abril -dos lecturas peleando por la misma casilla- y una hora que
# no existe en septiembre, que la serie veria como un hueco de transmision de
# todas las estaciones a la vez.
ZONA_CHILE = ZoneInfo("America/Santiago")

PASO_MIN = 30
PASOS_POR_HORA = 60 // PASO_MIN

# --- Ventana de trabajo ------------------------------------------------------
# Tres inviernos: 2024, 2025 y 2026. La red de VIPNET tiene cobertura util desde
# fines de junio de 2024; junio de ese anio queda casi vacio y no se rellena.
#
# Por que tres y no uno. Con un solo temporal todas las observaciones son
# positivas: hay activaciones documentadas y no hay episodios en que llovio y no
# paso nada. 2025 fue un invierno con lluvia real y solo activaciones menores, y
# eso es lo que permite calibrar con unos inviernos y validar con otro.
#
# Termina el 23 y no el 31 de agosto de 2026 para que el invierno de 2026 sea el
# mismo que valido M5 en su primera version. No se rellena con ceros: ver
# decision 2.
VENTANA_INICIO = "2024-06-01"
VENTANA_FIN = "2026-08-23"

# --- Constantes de las reglas ------------------------------------------------
R2_COBERTURA_MINIMA = 0.50      # fraccion de la ventana con dato
R3_DESAJUSTE_MAXIMO = 0.10      # |suma incrementos / alza acumulado - 1|
R4_INCREMENTO_MAXIMO_MM = 20.0  # en 30 minutos

# Salto del contador. Agregado en octubre de 2026, DESPUES de mirar los datos de
# tres inviernos, y por eso va con la medicion que lo sostiene.
#
# Con la ventana larga R4 paso de botar 4 estaciones a botar 13, y la mayoria
# no era nieve sino fallas del equipo: el 9 y 10 de abril de 2026 cinco
# estaciones registran a la vez cientos de mm en un solo paso entre ceros
# (Cogoti 18 589 mm, Cogoti Embalse 660, Cuncumen 598, Huintil 739, Almendral
# 350); Pupio oscila entre 0 y 737 mm; Rio Claro y Rio Cuncumen suben y bajan
# cientos de mm de un paso a otro. Con R4 por estacion, un salto de abril
# botaba a Cuncumen tambien para el temporal de julio.
#
# La frontera no hubo que inventarla. En tres inviernos, el mayor paso de
# 30 min que NO esta aislado entre pasos secos es de 16,0 mm (Punitaqui),
# salvo uno de 33 mm en Angostura de Pabellon que R4 sigue tratando. Los
# pasos aislados se separan solos en dos familias: de 22 a 81 mm (Glaciar
# Tapado, Los Choros, La Canela, Rio Claro: lo que R4 siempre boto) y de 163 a
# 739 mm (los saltos). Cualquier corte entre 81 y 163 da el mismo resultado;
# 100 queda al medio.
#
# El paso se anula (NaN), no se borra la estacion: es exactamente el
# tratamiento que ya tenia el salto hacia abajo, que es un reinicio.
SALTO_CONTADOR_MM = 100.0

# Isoterma 0 observada: condiciones para aceptar el ajuste del dia.
ISO_MIN_ESTACIONES = 8
ISO_GRADIENTE_MIN_C_KM = 2.0
ISO_GRADIENTE_MAX_C_KM = 10.0
ISO_R2_MINIMO = 0.70

# Episodios.
CORTE_SECO_H = 12.0
CORTES_SENSIBILIDAD_H = (6.0, 12.0, 24.0)
LLUVIA_MINIMA_EPISODIO_MM = 1.0   # bajo esto no es un episodio, es ruido

# Que cuenta como paso seco. No es cero exacto, y la razon es del instrumento:
# un pluviometro de cubeta basculante de la red tiene resolucion de 0,2 mm, asi
# que un paso con menos que eso no es lluvia medida, es la cubeta todavia sin
# volcar. Pedir cero exacto hace que una sola basculada perdida en doce horas
# impida el corte, y entonces dos temporales separados por dos dias de nada
# quedan pegados en un episodio unico: medido sobre la ventana de julio, la
# duracion mediana pasa de 53 a 113 horas. La duracion es la variable que entra
# al umbral, asi que ese pegoteo no es un detalle de conteo.
UMBRAL_SECO_MM = 0.2
UMBRALES_SECO_SENSIBILIDAD_MM = (0.0, 0.1, 0.2, 0.5)
ANTECEDENTES_H = (24, 72, 168)

# Cruce con las cuencas.
DISTANCIA_MAXIMA_KM = 30.0

# Estaciones ambiguas: pares vecinos que se contradicen.
#
# NOTA DE RECONSTRUCCION: estos cortes no estaban escritos en la documentacion
# que sobrevivio, solo tres ejemplos. Estan elegidos para que los tres queden
# marcados, y eso es todo el respaldo que tienen:
#
#   LAS BURRAS 343,5 mm  vs  RIO ILLAPEL EN LAS BURRAS 1,1 mm   a 0,2 km
#   RIO MOSTAZAL EN CUESTECITA  vs  EL MAITEN 1,9 mm            a 3,8 km
#   RIO CUNCUMEN ANTES JUNTA 962,0 mm  vs  CUNCUMEN 409,5 mm    a 2,2 km
#
# El tercero es el que manda sobre la razon: 962/409,5 = 2,35, asi que un corte
# en 10 -o en 3- lo dejaba pasar, y es justamente la estacion de la que depende
# el unico positivo que el trabajo original reporto. Con 2,0 los tres entran.
#
# Que el corte salga de los ejemplos y no de un criterio independiente es una
# debilidad real y por eso esta escrita. Dos pluviometros a 2 km no pueden ver
# una diferencia de mas del doble en un temporal frontal de invierno, que cubre
# cientos de kilometros: esa es la justificacion fisica, y es mas blanda que la
# de cualquier otra constante de este archivo.
AMBIGUA_DISTANCIA_KM = 5.0
AMBIGUA_RAZON = 2.0
AMBIGUA_DIFERENCIA_MM = 50.0


# =============================================================================
# Descarga
# =============================================================================

def _post(url: str, payload: dict, intentos: int = 3) -> dict:
    """POST con reintentos que distingue "no hay dato" de "la consulta fallo".

    Esta distincion es el motivo de que esta funcion exista en vez de una linea
    de requests. En M3 una consulta caida devolvia un cuadro vacio y el pipeline
    la trataba igual que una zona sin vias, y tres corridas salieron con menos
    territorio del que decian. Aca un error de red o un HTTP != 200 aborta; un
    200 con `data` vacio se acepta como lo que es, una estacion que no reporto.
    """
    ultimo = None
    for n in range(intentos):
        try:
            r = requests.post(url, json=payload, timeout=90)
            r.raise_for_status()
            cuerpo = r.json()
        except (requests.RequestException, json.JSONDecodeError) as exc:
            ultimo = exc
            time.sleep(2 * (n + 1))
            continue

        if "data" not in cuerpo:
            raise RuntimeError(
                f"VIPNET respondio 200 pero sin campo 'data' para {payload}.\n"
                "La API cambio de forma. No se sigue: una respuesta que no se "
                "entiende no es una respuesta vacia."
            )
        return cuerpo

    raise RuntimeError(f"VIPNET no respondio despues de {intentos} intentos: {ultimo}")


def _verificar_ventana(inicio: str, fin: str):
    """Aborta si la ventana esta vacia o si la base de zonas horarias no sirve.

    La segunda comprobacion existe porque zoneinfo depende de una base de datos
    que en Windows viene del paquete `tzdata`. Una base vieja no da error: da
    las fechas de cambio de hora que Chile tenia antes, y las horas salen
    corridas en silencio. Se exige que cada invierno de la ventana este en UTC-4
    y cada verano en UTC-3, que es lo minimo que tiene que ser cierto.
    """
    if inicio >= fin:
        sys.exit(f"Ventana vacia: {inicio} no es anterior a {fin}.")

    for anio in range(int(inicio[:4]), int(fin[:4]) + 1):
        for fecha, horas in ((f"{anio}-07-15", -4), (f"{anio}-01-15", -3)):
            desfase = pd.Timestamp(fecha, tz=ZONA_CHILE).utcoffset()
            if desfase != timedelta(hours=horas):
                sys.exit(
                    f"La zona America/Santiago da {desfase} el {fecha} y deberia "
                    f"dar {horas} h.\nLa base de zonas horarias esta mala o "
                    "vieja: pip install --upgrade tzdata"
                )


def descargar_catalogo(tipo: int, region: int = REGION_COQUIMBO) -> pd.DataFrame:
    """Estaciones de la region que declaran el parametro pedido. Es la regla R1.

    Se pide con `mapStatistic` = 0 (acumulado) porque el catalogo viene pegado a
    una consulta de valores; el valor no se usa, solo la ficha de la estacion.
    """
    cuerpo = _post(EP_ESTACIONES, {
        "tipoEstacion": tipo,
        "mapStatistic": 0,
        "currentTabIndex": 0,
        "fetchDay": VENTANA_FIN,
        "fetchHour": 23,
        "hoursRange": 24,
    })

    filas = [{
        "codigo": e["codigoEstacion"],
        "nombre": e["nombre"],
        "lat": e["latitud"],
        "lon": e["longitud"],
        "altitud_m": e.get("altitud"),
        "fuente": e.get("fuenteEstacion"),
        "region": e.get("region"),
    } for e in cuerpo["data"] if e.get("region") == region]

    return pd.DataFrame(filas).sort_values("codigo").reset_index(drop=True)


def descargar_serie(codigo: str, tipo: int, inicio: str, fin: str) -> list[dict]:
    """Serie cruda de una estacion, en una sola consulta.

    `hoursRange` acepta la ventana completa (probado hasta 2.040 h), asi que no
    hace falta paginar. La API interpreta fetchDay/fetchHour en hora local y
    devuelve `fecha` en UTC.

    La comprobacion del codigo devuelto no es paranoia: si el nombre de una
    clave del payload cambia, la API responde 200 con `data` vacio en vez de un
    error. Se verifico en su momento mandando `codigo` en vez de
    `codigoEstacion`: HTTP 200, lista vacia, cero senales de que algo iba mal.
    """
    d_inicio = datetime.fromisoformat(inicio)
    d_fin = datetime.fromisoformat(fin)
    horas = int((d_fin - d_inicio).total_seconds() // 3600) + 24

    cuerpo = _post(EP_SERIE, {
        "codigoEstacion": codigo,
        "tipoEstacion": tipo,
        "fetchDay": fin,
        "fetchHour": 23,
        "hoursRange": horas,
    })

    datos = cuerpo["data"]
    ajenos = {d.get("codigoEstacion") for d in datos} - {codigo}
    if ajenos:
        raise RuntimeError(
            f"Se pidio {codigo} y vinieron datos de {ajenos}. No se sigue."
        )
    return datos


def _ruta_cache(cache: Path, codigo: str, tipo: int, inicio: str, fin: str) -> Path:
    """Una subcarpeta por ventana, y no una carpeta plana.

    Hasta octubre de 2026 el cache era `{tipo}_{codigo}.json` sin mas. Cambiar
    la ventana y correr sin --refrescar leia la serie de la ventana vieja, y el
    resultado salia con 84 dias de lluvia rotulados como tres anios: R2 botaba
    por cobertura a todas las estaciones o, peor, pasaban y nadie notaba que
    faltaba lluvia. Que la ventana este en la ruta hace imposible esa mezcla.

    Va comprimido porque una serie de tres anios pesa unos 6 MB en JSON y son
    220 series. gzip no pierde nada: lo que se lee es byte a byte lo que mando
    la API.
    """
    return cache / f"{inicio}_{fin}" / f"{tipo}_{codigo}.json.gz"


def serie_con_cache(codigo: str, tipo: int, cache: Path, refrescar: bool,
                    inicio: str, fin: str) -> list[dict]:
    """Baja la serie o la lee del disco.

    El cache existe para que una corrida sea reproducible. VIPNET puede rellenar
    datos tarde, asi que dos consultas separadas por un mes no devuelven lo
    mismo: es el mismo problema por el que M3 abandono Overpass. Con el cache,
    la corrida guardada en docs/corridas/ se puede repetir. `--refrescar` es
    para cuando se quiere a proposito el dato de hoy.
    """
    ruta = _ruta_cache(cache, codigo, tipo, inicio, fin)
    if ruta.exists() and not refrescar:
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            return json.load(f)

    datos = descargar_serie(codigo, tipo, inicio, fin)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(ruta, "wt", encoding="utf-8") as f:
        json.dump(datos, f)
    return datos


# =============================================================================
# Serie regular
# =============================================================================

def _hora_local(texto: str) -> pd.Timestamp:
    """Una hora de reloj chilena como instante. Ver ZONA_CHILE.

    `nonexistent` y `ambiguous` resuelven las dos horas raras del anio -la que no
    existe en septiembre y la que se repite en abril- en vez de abortar. Solo
    afectan a una ventana que empiece o termine justo ahi.
    """
    return pd.Timestamp(texto).tz_localize(ZONA_CHILE, ambiguous=False,
                                           nonexistent="shift_forward")


def grilla_regular(inicio: str, fin: str) -> pd.DatetimeIndex:
    """Grilla de 30 minutos en tiempo absoluto, rotulada en hora de Chile.

    Va de las 00:00 del dia de inicio a las 23:30 del dia de fin, hora local.
    Los pasos son de 30 minutos reales aunque el reloj salte: ver ZONA_CHILE.
    """
    return pd.date_range(_hora_local(f"{inicio} 00:00"),
                         _hora_local(f"{fin} 23:30"), freq=f"{PASO_MIN}min")


def _fechas_api(datos: list[dict]) -> pd.Series:
    """Las marcas de tiempo de VIPNET, en UTC, como instantes."""
    return pd.Series(pd.to_datetime([d["fecha"]["$date"] for d in datos], utc=True))


def _a_la_grilla(df: pd.DataFrame, grilla: pd.DatetimeIndex) -> pd.DataFrame:
    """Lleva los registros a la grilla de 30 min redondeando al slot mas cercano.

    No es cosmetico. La red no transmite en punto: hay estaciones que reportan
    a los :59 y a los :29, otras a los :22 y a los :52. Casar por igualdad exacta
    de la marca de tiempo las deja a todas en cero registros, y como el resto del
    pipeline trata "sin registro" como "sin dato", la estacion desaparece sin que
    nada falle. Es otra version del cuadro vacio contra la consulta fallida.

    El desfase es de pocos minutos contra un paso de 30, asi que redondear no
    mueve ningun episodio: solo decide en que casilla cae una lectura que ya
    estaba ahi.

    Se redondea en UTC y despues se pasa a hora de Chile. Al reves no se puede:
    redondear en hora local obliga a pandas a decidir que hacer con la hora que
    se repite en abril, y aborta. Como el desfase de Chile es de horas enteras,
    redondear a 30 minutos da la misma casilla en las dos zonas.
    """
    df = df.copy()
    df["fecha"] = df["fecha"].dt.round(f"{PASO_MIN}min").dt.tz_convert(ZONA_CHILE)
    df = (df.drop_duplicates("fecha", keep="last")
            .set_index("fecha").sort_index()
            .reindex(grilla))
    return df


def _paso_nativo_slots(recibidos: np.ndarray) -> int:
    """Cada cuantos slots de 30 min transmite realmente esta estacion.

    La red es mixta: la mayoria manda cada 30 minutos, pero hay estaciones
    horarias (Glaciar Tapado, por ejemplo). Para una estacion horaria, la mitad
    de los slots de la grilla no tienen lectura, y tratarlos como hueco de
    transmision seria un error de lectura nuestro, no un problema del dato: la
    estacion esta reportando todo lo que le toca reportar.

    Sin esta cuenta, R2 le daria 50% de cobertura a toda estacion horaria y R3
    veria un hueco dentro de cada episodio, o sea que la red horaria entera
    desapareceria del resultado sin dejar rastro en el reporte.
    """
    if len(recibidos) < 3:
        return 1
    return max(1, int(np.median(np.diff(recibidos))))


def serie_precipitacion(datos: list[dict], grilla: pd.DatetimeIndex) -> pd.DataFrame:
    """Arma la serie de mm por paso a partir del contador acumulado.

    Devuelve un DataFrame indexado por la grilla con:
        mm          lluvia del paso, o NaN si no hay dato
        acumulado   el contador tal como lo entrego la estacion
        incremento  el campo `instantaneo`, que se guarda solo para poder
                    comparar los dos caminos y documentar la diferencia

    Que cuenta como hueco y que no:

        Un slot sin lectura dentro de la cadencia normal de la estacion no es un
        hueco: es el espacio entre dos lecturas suyas, y ahi no llovio nada que
        ella no haya contado ya. Queda en 0.

        Un slot sin lectura dentro de un corte de transmision si es un hueco y
        queda en NaN. El slot donde la estacion vuelve conserva el alza completa
        del contador, que es la lluvia de todo el corte junta: es el unico lugar
        donde esa lluvia puede ir sin inventar como se repartio.

    Un salto negativo del contador es un reinicio del equipo, no lluvia
    negativa. Ese paso queda en NaN: cuanto llovio mientras se reiniciaba es
    justamente lo que no se sabe, y un cero seria inventarlo.

    Un salto POSITIVO aislado de mas de SALTO_CONTADOR_MM es lo mismo al reves,
    y queda igual en NaN. Ver SALTO_CONTADOR_MM. `salto_mm` guarda el valor que
    se anulo, para que el reporte pueda decir cuanto fue y donde.
    """
    columnas = ["mm", "acumulado", "incremento", "recuperacion", "salto_mm"]
    if not datos:
        vacio = pd.DataFrame(index=grilla, columns=columnas, dtype="float64")
        vacio["recuperacion"] = False
        return vacio

    df = pd.DataFrame({
        "fecha": _fechas_api(datos),
        "acumulado": [d.get("acumulado", np.nan) for d in datos],
        "incremento": [d.get("instantaneo", np.nan) for d in datos],
    })
    df = _a_la_grilla(df, grilla)

    recibidos = np.flatnonzero(df["acumulado"].notna().to_numpy())
    if len(recibidos) == 0:
        df["mm"] = np.nan
        df["recuperacion"] = False
        df["salto_mm"] = np.nan
        return df[columnas]

    # La lluvia de un slot es cuanto subio el contador desde la ultima lectura.
    mm = df["acumulado"].ffill().diff().to_numpy(dtype="float64", copy=True)

    paso = _paso_nativo_slots(recibidos)
    # Se tolera hasta el doble de la cadencia propia antes de llamarlo corte:
    # una transmision perdida y recuperada no es un hueco de registro.
    tolerancia = max(2, 2 * paso)

    es_hueco = np.zeros(len(df), dtype=bool)
    es_hueco[:recibidos[0]] = True        # antes de la primera lectura
    es_hueco[recibidos[-1] + 1:] = True   # despues de la ultima

    # El slot donde la estacion vuelve despues de un corte no es un paso de 30
    # minutos: trae el alza del contador de todo el corte junta. Su valor es
    # correcto para sumar y enganoso para cualquier cuenta de intensidad, asi
    # que se marca y las reglas que miran intensidad lo excluyen.
    recuperacion = np.zeros(len(df), dtype=bool)
    for a, b in zip(recibidos[:-1], recibidos[1:]):
        if b - a > tolerancia:
            es_hueco[a + 1:b] = True
            recuperacion[b] = True

    mm[es_hueco] = np.nan
    mm[mm < 0] = np.nan                   # reinicio del contador

    # Salto del contador hacia arriba: un paso enorme entre pasos sin lluvia
    # (secos o sin dato). Los vecinos se miran antes de anular nada, para que
    # una racha de saltos seguidos -Pupio oscila entre 0 y 737 mm varias veces
    # en una tarde- se anule entera.
    antes = np.r_[np.nan, mm[:-1]]
    despues = np.r_[mm[1:], np.nan]
    quieto = lambda v: ~(v >= UMBRAL_SECO_MM)   # NaN o seco  # noqa: E731
    salto = ((mm > SALTO_CONTADOR_MM) & ~recuperacion
             & quieto(antes) & quieto(despues))
    df["salto_mm"] = np.where(salto, mm, np.nan)
    mm[salto] = np.nan

    df["mm"] = mm
    df["recuperacion"] = recuperacion
    return df[columnas]


def serie_temperatura(datos: list[dict], grilla: pd.DatetimeIndex) -> pd.Series:
    """Temperatura instantanea sobre la grilla. `acumulado` no aplica aca."""
    if not datos:
        return pd.Series(np.nan, index=grilla, dtype="float64")

    df = pd.DataFrame({
        "fecha": _fechas_api(datos),
        "t": [d.get("instantaneo", np.nan) for d in datos],
    })
    return _a_la_grilla(df, grilla)["t"]


# =============================================================================
# Isoterma 0 observada
# =============================================================================

def isoterma_cero(temperaturas: dict[str, pd.Series],
                  altitudes: dict[str, float]) -> pd.DataFrame:
    """Altitud donde la red mide 0 grados, dia por dia.

    Se ajusta una recta de temperatura media diaria contra altitud y se despeja
    el cruce por cero. Se usa la media del dia y no el maximo ni el minimo
    porque lo que interesa es si el pluviometro paso el dia sobre o bajo la
    linea de nieve, no un instante.

    El ajuste se acepta solo si cumple las tres condiciones de arriba. Un dia
    que no las cumple queda con NaN y se cuenta: preferimos no saber la isoterma
    de un dia a inventarla con cuatro estaciones mal repartidas.

    El dia es el dia de reloj chileno. La media diaria se saca agrupando una sola
    vez por estacion: la version anterior filtraba la serie entera para cada
    dia, y con tres anios eso eran miles de millones de comparaciones.
    """
    medias = {}
    for codigo, serie in temperaturas.items():
        alt = altitudes.get(codigo)
        if alt is None or not np.isfinite(alt):
            continue
        dia_local = serie.index.tz_localize(None).normalize()
        agrupado = serie.groupby(dia_local).agg(["mean", "count"])
        # Menos de 6 h de dato en el dia no alcanza para una media diaria.
        medias[codigo] = agrupado["mean"].where(
            agrupado["count"] >= PASOS_POR_HORA * 6)
    tabla = pd.DataFrame(medias)

    filas = []
    for dia, fila in tabla.iterrows():
        validos = fila.dropna()
        pares = [(float(altitudes[c]), float(t)) for c, t in validos.items()]

        motivo, altitud_0, grad, r2 = "", np.nan, np.nan, np.nan

        if len(pares) < ISO_MIN_ESTACIONES:
            motivo = f"solo {len(pares)} estaciones"
        else:
            alt = np.array([p[0] for p in pares])
            t = np.array([p[1] for p in pares])
            pendiente, intercepto = np.polyfit(alt, t, 1)
            pred = pendiente * alt + intercepto
            ss_res = float(((t - pred) ** 2).sum())
            ss_tot = float(((t - t.mean()) ** 2).sum())
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
            grad = -pendiente * 1000.0     # grados por km, positivo al enfriarse

            if not (ISO_GRADIENTE_MIN_C_KM <= grad <= ISO_GRADIENTE_MAX_C_KM):
                motivo = f"gradiente {grad:.1f} C/km fuera de rango"
            elif not (r2 >= ISO_R2_MINIMO):
                motivo = f"R2 {r2:.2f} bajo el minimo"
            elif pendiente == 0:
                motivo = "recta plana"
            else:
                altitud_0 = float(-intercepto / pendiente)

        filas.append({"dia": pd.Timestamp(dia), "altitud_0_m": altitud_0,
                      "gradiente_c_km": grad, "r2": r2,
                      "n_estaciones": len(pares), "motivo_descarte": motivo})

    return pd.DataFrame(filas).set_index("dia")


# =============================================================================
# Episodios
# =============================================================================

def detectar_episodios(serie: pd.DataFrame, corte_seco_h: float,
                       umbral_seco_mm: float = UMBRAL_SECO_MM) -> pd.DataFrame:
    """Parte la serie de una estacion en episodios de lluvia.

    Un episodio es un bloque de pasos con lluvia separado del siguiente por al
    menos `corte_seco_h` horas SECAS. Seco quiere decir medido y sin lluvia. Un
    hueco de transmision no es seco: no cierra el episodio, lo ensucia, y el
    episodio queda marcado con `tiene_hueco` para que R3 lo descarte despues.

    Esa distincion es el centro del script. Tratar el hueco como periodo seco
    partiria el temporal de julio en pedazos de pocas horas y les bajaria la
    duracion a todos, que es justo la variable que entra al umbral.
    """
    mm = serie["mm"]
    pasos_secos = int(round(corte_seco_h * PASOS_POR_HORA))

    # El episodio empieza y termina en pasos con lluvia medible; los pasos bajo
    # la resolucion del instrumento cuentan como secos para decidir el corte,
    # pero sus milimetros igual entran al total del episodio.
    # El `mm > 0` no es redundante con el umbral: deja que umbral_seco_mm = 0
    # signifique el criterio literal de "cualquier milimetro cuenta", que es con
    # lo que se compara en la tabla de sensibilidad.
    llueve = ((mm > 0) & (mm >= umbral_seco_mm)).to_numpy()
    seco = (mm.notna() & ~llueve).to_numpy()
    recuperacion = serie["recuperacion"].astype(bool).to_numpy()

    episodios = []
    i, n = 0, len(mm)

    while i < n:
        if not llueve[i]:
            i += 1
            continue

        inicio = i
        fin = i
        con_hueco = False
        j = i + 1
        racha_seca = 0

        while j < n:
            if llueve[j]:
                fin = j
                racha_seca = 0
            elif seco[j]:
                racha_seca += 1
                if racha_seca >= pasos_secos:
                    break
            else:                       # hueco: ni seco ni lluvia
                con_hueco = True
                racha_seca = 0
            j += 1

        bloque = mm.iloc[inicio:fin + 1]
        total = float(bloque.sum(skipna=True))

        # Un slot de recuperacion dentro del bloque arrastra la lluvia de todo
        # un corte de transmision a un solo paso de 30 minutos. El total sigue
        # siendo correcto, pero la duracion y la intensidad dejan de serlo, y
        # son justo las dos variables que entran al umbral.
        #
        # El caso que lo delato: HURTADO salia con 373,1 mm en 0,5 h, o sea
        # 746 mm/h, y superaba Caine por dos ordenes de magnitud. Un episodio
        # que empieza en el slot de recuperacion no tiene ningun NaN adentro
        # -el hueco quedo justo antes- asi que la marca de hueco no lo veia.
        con_recuperacion = bool(recuperacion[inicio:fin + 1].any())

        if total >= LLUVIA_MINIMA_EPISODIO_MM:
            # La duracion cuenta el largo del ultimo paso: un episodio de un
            # solo paso dura media hora, no cero.
            duracion_h = (fin - inicio + 1) / PASOS_POR_HORA
            rodante = bloque.rolling(PASOS_POR_HORA, min_periods=1).sum()
            # La segunda lectura del umbral: ver m4_umbrales.razon_critica.
            razon_cr, dur_cr = razon_critica(bloque, PASOS_POR_HORA)
            episodios.append({
                "inicio": mm.index[inicio],
                "fin": mm.index[fin],
                "duracion_h": duracion_h,
                "lluvia_mm": total,
                "i_media_mm_h": total / duracion_h,
                "i_max_60min_mm_h": float(rodante.max(skipna=True)),
                "razon_caine_critica": razon_cr,
                "duracion_critica_h": dur_cr,
                "pasos_sin_dato": int(bloque.isna().sum()),
                "tiene_recuperacion": con_recuperacion,
                "tiene_hueco": bool(con_hueco or bloque.isna().any()
                                    or con_recuperacion),
            })

        i = max(j, fin + 1)

    df = pd.DataFrame(episodios)
    if df.empty:
        return df

    for horas in ANTECEDENTES_H:
        df[f"antecedente_{horas}h_mm"] = [
            float(mm.loc[ini - timedelta(hours=horas):ini].sum(skipna=True))
            for ini in df["inicio"]
        ]
    return df


def invierno(inicio: pd.Series) -> pd.Series:
    """El invierno al que pertenece cada fecha: de abril a marzo del anio siguiente.

    Corta en abril y no en enero porque enero y febrero son justo cuando puede
    llover en la cordillera por el invierno altiplanico, y un corte en enero
    partiria esa temporada en dos. La lluvia frontal, que es la que interesa,
    cae de mayo a septiembre, asi que abril la deja entera de un solo lado.
    """
    fechas = inicio.dt.tz_localize(None)
    return (fechas.dt.year - (fechas.dt.month < 4)).astype(int)


# =============================================================================
# Reglas de seleccion
# =============================================================================

def _diagnostico_estacion(serie: pd.DataFrame, contar_saltos: bool = False) -> dict:
    """Cobertura, incremento maximo, total y desajuste de un tramo de serie."""
    mm = serie["mm"]
    if mm.notna().sum() == 0:
        return {"cobertura": 0.0, "incremento_max_mm": np.nan, "total_mm": 0.0,
                "desajuste": np.nan, "n_saltos": 0, "descartada_por": "R2"}

    cobertura = float(mm.notna().mean())
    total = float(mm.sum(skipna=True))

    # R4 pregunta si la estacion registro un incremento de 30 minutos
    # imposible, y para eso hay que mirar solo incrementos que de verdad
    # sean de 30 minutos. El slot con que una estacion vuelve de un corte
    # trae horas de lluvia juntas y da valores enormes que no son picos de
    # intensidad: CUNCUMEN llega a 201,5 mm en un slot de esos. Contarlo
    # botaria por "nieve" justamente a las estaciones que peor transmiten,
    # que es lo contrario de lo que la regla busca.
    reales = mm[~serie["recuperacion"].astype(bool)]
    if contar_saltos:
        # La version anterior a la regla de saltos, solo para el reporte.
        reales = reales.fillna(serie["salto_mm"])
    incremento_max = float(reales.max(skipna=True)) if reales.notna().any() else np.nan

    # El desajuste de R3 en su version antigua, por estacion. Se calcula y
    # se guarda aunque la regla ya no se aplique aqui: es la cifra que
    # justifica el cambio de granularidad, y sin ella el cambio es una
    # afirmacion sin respaldo.
    suma_incrementos = float(serie["incremento"].sum(skipna=True))
    desajuste = abs(suma_incrementos / total - 1.0) if total > 0 else np.nan

    if cobertura < R2_COBERTURA_MINIMA:
        motivo = "R2"
    elif incremento_max > R4_INCREMENTO_MAXIMO_MM:
        motivo = "R4"
    else:
        motivo = ""
    return {"cobertura": cobertura, "incremento_max_mm": incremento_max,
            "total_mm": total, "desajuste": desajuste,
            "n_saltos": int(serie["salto_mm"].notna().sum()),
            "descartada_por": motivo}


def aplicar_reglas_estacion(series: dict[str, pd.DataFrame], catalogo: pd.DataFrame,
                            por_invierno: bool = True,
                            contar_saltos: bool = False) -> pd.DataFrame:
    """R2 y R4, por estacion e invierno.

    Devuelve una fila por estacion e invierno con el diagnostico y
    `descartada_por`, que queda vacia si pasa. No se borran filas: que el
    reporte pueda decir cual cayo por cual regla es parte del entregable.

    POR QUE POR INVIERNO Y NO POR ESTACION

        Hasta octubre de 2026 las dos reglas miraban la estacion completa, y
        con una ventana de 84 dias eso era lo mismo que mirar un invierno. Con
        tres, una estacion pasaba a responder por toda su historia: Rio Mostazal
        en Cuestecita tiene 99% de cobertura en 2026 y caia por R2 porque en
        2024 no existia, y una falla de abril de 2026 botaba a Cuncumen tambien
        para julio. El dano esta localizado en el tiempo, y la regla pasa a
        aplicarse donde esta el dano. Es el mismo razonamiento, y el mismo
        tipo de cambio despues de mirar los datos, que llevo a R3 de la
        estacion al episodio. El efecto se reporta en las dos versiones.

    `por_invierno=False` y `contar_saltos=True` reproducen la version anterior
    -por estacion, sin anular los saltos del contador- y existen solo para el
    reporte.
    """
    filas = []
    for _, est in catalogo.iterrows():
        serie = series.get(est["codigo"])
        if por_invierno:
            ids = invierno(pd.Series(serie.index)).to_numpy()
            tramos = [(a, serie[ids == a]) for a in np.unique(ids)]
        else:
            tramos = [(None, serie)]
        for a, tramo in tramos:
            filas.append({**est.to_dict(), "invierno": a,
                          **_diagnostico_estacion(tramo, contar_saltos)})
    return pd.DataFrame(filas)


def marcar_ambiguas(catalogo: pd.DataFrame) -> pd.DataFrame:
    """Marca pares vecinos que se contradicen. No descarta a ninguno.

    Dos estaciones a menos de AMBIGUA_DISTANCIA_KM que difieren en mas de un
    factor AMBIGUA_RAZON sobre el total de la ventana no pueden estar las dos
    bien. Cual de las dos esta mala no lo decide ninguna regla disponible, y
    elegir mirando cual cuadra mejor con el resultado seria elegir el resultado.
    Se marcan las dos y el que lea decide.

    Se compara dentro de cada invierno: un total de tres anios mezcla una
    estacion que reporto los tres con una que reporto uno, y la diferencia
    saldria de la cobertura y no de la medicion.
    """
    if "invierno" in catalogo.columns and catalogo["invierno"].notna().any():
        return pd.concat([_marcar_ambiguas(g) for _, g in catalogo.groupby("invierno")])
    return _marcar_ambiguas(catalogo)


def _marcar_ambiguas(catalogo: pd.DataFrame) -> pd.DataFrame:
    cat = catalogo.copy()
    cat["ambigua"] = False
    cat["ambigua_con"] = ""

    validas = cat[(cat["descartada_por"] == "") & cat["total_mm"].notna()]
    lat = np.radians(validas["lat"].to_numpy())
    lon = np.radians(validas["lon"].to_numpy())
    idx = validas.index.to_numpy()

    # Distancia de gran circulo, suficiente a esta escala.
    dlat = lat[:, None] - lat[None, :]
    dlon = lon[:, None] - lon[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat)[:, None] * np.cos(lat)[None, :] * np.sin(dlon / 2) ** 2
    dist_km = 6371.0 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))

    total = validas["total_mm"].to_numpy()
    for p in range(len(idx)):
        for q in range(p + 1, len(idx)):
            if dist_km[p, q] > AMBIGUA_DISTANCIA_KM:
                continue
            alto, bajo = max(total[p], total[q]), min(total[p], total[q])
            if bajo <= 0:
                razon = np.inf if alto > 0 else 1.0
            else:
                razon = alto / bajo
            if razon >= AMBIGUA_RAZON and (alto - bajo) >= AMBIGUA_DIFERENCIA_MM:
                for uno, otro in ((p, q), (q, p)):
                    cat.loc[idx[uno], "ambigua"] = True
                    previo = cat.loc[idx[uno], "ambigua_con"]
                    nombre = cat.loc[idx[otro], "nombre"]
                    cat.loc[idx[uno], "ambigua_con"] = (
                        f"{previo}; {nombre}" if previo else nombre)

    return cat


def aplicar_r5(episodios: pd.DataFrame, altitud_estacion: float,
               iso: pd.DataFrame) -> pd.Series:
    """R5: el episodio vale si la estacion estuvo bajo la isoterma 0 observada.

    Sobre la isoterma lo que cae es nieve, y un pluviometro con nieve no mide
    lluvia: acumula y suelta el equivalente de golpe cuando se derrite, lo que
    fabrica intensidades de 30 minutos que no existieron.

    Un dia sin isoterma ajustada NO descarta el episodio. La regla solo puede
    afirmar con la isoterma en la mano; sin ella se deja pasar y el reporte dice
    cuantos dias quedaron sin ajuste.
    """
    if episodios.empty:
        return pd.Series(dtype="bool")
    if not np.isfinite(altitud_estacion):
        return pd.Series(True, index=episodios.index)

    def bajo_la_linea(inicio, fin):
        # Dias de reloj chileno, igual que el indice de la isoterma.
        dias = pd.date_range(inicio.tz_localize(None).normalize(),
                             fin.tz_localize(None).normalize(), freq="D")
        alturas = iso.reindex(dias)["altitud_0_m"].dropna()
        if alturas.empty:
            return True
        return bool(altitud_estacion < alturas.min())

    return pd.Series(
        [bajo_la_linea(a, b) for a, b in zip(episodios["inicio"], episodios["fin"])],
        index=episodios.index)


# =============================================================================
# Cruce con las cuencas
# =============================================================================

def asignar_estacion(cuencas, catalogo: pd.DataFrame):
    """A cada cuenca, la estacion valida mas cercana a su centroide.

    Es lo mas simple que se puede defender: interpolar entre estaciones daria un
    campo mas suave y mas falso, porque la lluvia orografica cambia mas rapido
    que la distancia entre pluviometros. Con una sola estacion por cuenca, la
    distancia queda en la tabla y el que lea sabe cuanto confiar.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    validas = catalogo[catalogo["descartada_por"] == ""].reset_index(drop=True)
    if validas.empty:
        return None

    estaciones = gpd.GeoDataFrame(
        validas,
        geometry=[Point(x, y) for x, y in zip(validas["lon"], validas["lat"])],
        crs="EPSG:4326").to_crs(cuencas.crs)

    centros = cuencas.copy()
    centros["geometry"] = centros.geometry.centroid

    cercanas = gpd.sjoin_nearest(
        centros, estaciones[["codigo", "nombre", "altitud_m", "ambigua", "geometry"]],
        how="left", distance_col="distancia_m")

    cercanas["distancia_km"] = cercanas["distancia_m"] / 1000.0
    return cercanas.rename(columns={"nombre": "estacion_nombre",
                                    "codigo": "estacion_codigo"})


def interpolar_pares(pares, asignadas, cuencas, validas, vale, series, eventos, iso,
                     procesados: Path, dir_out: Path):
    """Valida la interpolacion y, si le gana a la estacion cercana, la aplica.

    Todo el razonamiento esta en m4_interpolacion.py. Aca se arman las tablas,
    se imprime la comparacion y se escala la lluvia de cada par cuenca-episodio.
    Si el modelo no se adopta, los pares salen con factor 1, que es exactamente
    la asignacion por vecino mas cercano de siempre.
    """

    print("\n" + "-" * 74)
    print("Interpolacion de la lluvia por evento (dejando una estacion fuera)")
    print("-" * 74)

    ruta_dem = procesados / "dem_mosaico_wgs84.tif"
    estaciones = validas[["codigo", "nombre", "lat", "lon"]].copy()
    estaciones["altitud_m"] = pd.to_numeric(validas["altitud_m"], errors="coerce")
    estaciones["dist_costa_km"] = interp.distancia_costa_km(
        estaciones["lon"], estaciones["lat"], ruta_dem)

    tabla = interp.lluvia_por_evento(series, eventos, estaciones["codigo"])

    # La nieve fuera del entrenamiento: el criterio de R5 sobre cada evento.
    ventanas = eventos.rename(columns={"evento": "ev"})
    bajo = []
    for cod, alt in zip(estaciones["codigo"], estaciones["altitud_m"]):
        b = aplicar_r5(ventanas, alt, iso)
        bajo.append(pd.DataFrame({"evento": ventanas["ev"], "estacion_codigo": cod,
                                  "bajo_isoterma": b.to_numpy()}))
    tabla = tabla.merge(pd.concat(bajo), on=["evento", "estacion_codigo"])

    # Solo pares de estaciones validas en el invierno del evento (R2 y R4).
    inv_evento = dict(zip(eventos["evento"], invierno(eventos["inicio"])))
    tabla["vale"] = [(c, inv_evento[e]) in vale
                     for c, e in zip(tabla["estacion_codigo"], tabla["evento"])]
    utiles = tabla[tabla["completo"] & tabla["bajo_isoterma"] & tabla["vale"]]
    resumen = utiles.groupby("evento")["lluvia_mm"].agg(["mean", "size"])
    ev_validos = resumen.index[(resumen["mean"] >= interp.EVENTO_MINIMO_MM)
                               & (resumen["size"] >= interp.EVENTO_MIN_ESTACIONES)]
    entreno = utiles[utiles["evento"].isin(ev_validos)].reset_index(drop=True)

    print(f"  eventos regionales: {len(eventos)}; con media >= "
          f"{interp.EVENTO_MINIMO_MM:.0f} mm y >= {interp.EVENTO_MIN_ESTACIONES} "
          f"estaciones completas: {len(ev_validos)}")
    print(f"  pares estacion-evento para entrenar: {len(entreno)} "
          f"({int((~tabla['bajo_isoterma'] & tabla['evento'].isin(ev_validos)).sum())} "
          "fuera por estar sobre la isoterma 0)")

    val = interp.validar_dejando_fuera(entreno, estaciones)
    metodos = ["media regional", "estacion cercana", *interp.MODELOS]
    res = {m: interp.metricas(val["lluvia_mm"], val[m], val["evento"])
           for m in metodos if val[m].notna().all()}
    print(f"\n  {'metodo':<20} {'MAE mm':>8} {'RMSE mm':>8} {'R2':>7} {'R2 evento':>10}")
    for m, r in res.items():
        print(f"  {m:<20} {r['MAE']:>8.1f} {r['RMSE']:>8.1f} {r['R2']:>7.3f} "
              f"{r['R2_evento']:>10.3f}")
    val.to_csv(dir_out / "m4_interpolacion_validacion.csv", index=False,
               float_format="%.2f")

    # La misma validacion sobre el total del invierno 2026, para comparar con el
    # diagnostico que se hizo sobre totales.
    t26 = []
    for cod in estaciones["codigo"]:
        mm = series[cod]["mm"]
        tramo = mm[(mm.index >= _hora_local("2026-06-01 00:00"))
                   & (mm.index < _hora_local("2026-08-24 00:00"))]
        if len(tramo) and tramo.notna().mean() >= 0.95:
            t26.append({"estacion_codigo": cod, "lluvia_mm": float(tramo.sum())})
    if len(t26) >= 20:
        tv = interp.validar_total(pd.DataFrame(t26), estaciones)
        print(f"\n  Total del invierno 2026 (1-jun a 23-ago), {len(tv)} estaciones con "
              ">= 95% de dato, 4 variables fijas:")
        for m in ("media regional", "estacion cercana", "random forest"):
            r = interp.metricas(tv["lluvia_mm"], tv[m], np.zeros(len(tv)))
            print(f"  {m:<20} {r['MAE']:>8.1f} {r['RMSE']:>8.1f} {r['R2']:>7.3f}")

    # --- La regla de adopcion ---
    modelos = {m: res[m] for m in interp.MODELOS if m in res}
    mejor = min(modelos, key=lambda m: modelos[m]["MAE"])
    ref = res["estacion cercana"]
    adoptado = (modelos[mejor]["MAE"] < ref["MAE"]) and (modelos[mejor]["RMSE"] < ref["RMSE"])
    if adoptado:
        print(f"\n  SE ADOPTA {mejor}: MAE {modelos[mejor]['MAE']:.1f} contra "
              f"{ref['MAE']:.1f} mm de la estacion cercana.")
    else:
        print(f"\n  NO SE ADOPTA: el mejor modelo ({mejor}) no le gana a la estacion "
              "cercana en MAE y RMSE.\n  Los pares quedan con factor 1, la asignacion "
              "por vecino mas cercano.")

    pares = pares.copy()
    escalables = ["lluvia_mm", "i_media_mm_h", "i_max_60min_mm_h",
                  "razon_caine_critica"] + [f"antecedente_{h}h_mm" for h in ANTECEDENTES_H]
    for col in escalables:
        pares[f"{col}_estacion"] = pares[col]
    pares["factor_interpolacion"] = 1.0
    pares["interpolada"] = False

    if adoptado:
        modelo, rasgos = interp.ajustar(entreno, estaciones, mejor)
        # Un punto por unidad chica; una grilla de ~25 por tronco, cuya lluvia
        # es el promedio. Ver interp.puntos_de_prediccion.
        puntos = interp.puntos_de_prediccion(cuencas, procesados / "dem_utm19s.tif")
        puntos["dist_costa_km"] = interp.distancia_costa_km(
            puntos["lon"], puntos["lat"], ruta_dem)
        n_tr = int(cuencas["origen"].eq("tronco").sum()) if "origen" in cuencas.columns else 0
        if n_tr:
            print(f"  lluvia areal: {len(puntos) - (len(cuencas) - n_tr)} puntos "
                  f"para {n_tr} troncos")
        ev_pares = sorted(set(pares["evento"]) & set(ev_validos))
        pred = (interp.predecir(modelo, rasgos, puntos, ev_pares)
                .groupby(["id", "evento"], as_index=False)["lluvia_pred_mm"].mean()
                .rename(columns={"id": "id_cuenca"}))

        medido = tabla[["evento", "estacion_codigo", "lluvia_mm"]].rename(
            columns={"lluvia_mm": "lluvia_evento_estacion_mm"})
        pares = (pares.merge(pred, on=["id_cuenca", "evento"], how="left")
                      .merge(medido, on=["evento", "estacion_codigo"], how="left"))
        bruto = pares["lluvia_pred_mm"] / pares["lluvia_evento_estacion_mm"]
        ok = bruto.notna() & np.isfinite(bruto)
        factor = bruto.clip(interp.FACTOR_MIN, interp.FACTOR_MAX)
        pares.loc[ok, "factor_interpolacion"] = factor[ok]
        pares.loc[ok, "interpolada"] = True
        for col in escalables:
            pares[col] = pares[f"{col}_estacion"] * pares["factor_interpolacion"]

        recortados = int((ok & ((bruto < interp.FACTOR_MIN) | (bruto > interp.FACTOR_MAX))).sum())
        print(f"  pares interpolados: {int(ok.sum())} de {len(pares)} "
              f"(el resto cae en eventos chicos y queda con factor 1)")
        f_ok = pares.loc[ok, "factor_interpolacion"]
        print(f"  factor: mediana {f_ok.median():.2f}, p10 {f_ok.quantile(.1):.2f}, "
              f"p90 {f_ok.quantile(.9):.2f}; {recortados} recortados a "
              f"[{interp.FACTOR_MIN}, {interp.FACTOR_MAX}]")

        for columna, valores in evaluar(pares["duracion_h"], pares["i_media_mm_h"],
                                        pares["i_max_60min_mm_h"]).items():
            pares[columna] = valores
        pares["supera_caine_critico"] = pares["razon_caine_critica"] >= 1.0

    return pares


# =============================================================================
# Figura
# =============================================================================

def figura(pares: pd.DataFrame, ruta_png: Path):
    """Log-log de los episodios contra las curvas. Es el grafico canonico I-D."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 6))

    d = np.logspace(np.log10(0.5), np.log10(240), 200)
    ax.plot(d, caine_intensidad_critica(d), "k-", lw=2, label="Caine (1980)")
    ax.axhline(30.0, color="crimson", ls="--", lw=1.5,
               label="Ben David-Novak et al. (2004), I max 60 min")

    if not pares.empty:
        supera = pares["supera_caine"].fillna(False).to_numpy()
        ax.scatter(pares.loc[~supera, "duracion_h"], pares.loc[~supera, "i_media_mm_h"],
                   s=22, c="#4a7fb5", alpha=0.65, edgecolors="none",
                   label="bajo los dos umbrales")
        if supera.any():
            ax.scatter(pares.loc[supera, "duracion_h"], pares.loc[supera, "i_media_mm_h"],
                       s=60, c="crimson", marker="^", label="supera Caine")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("duracion D (h)")
    ax.set_ylabel("intensidad media I (mm/h)")
    ax.set_title("M4 - Episodios de lluvia contra los umbrales publicados")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(loc="upper right", fontsize=9)

    fig.tight_layout()
    fig.savefig(ruta_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


# =============================================================================
# main
# =============================================================================

def main():
    ap = argparse.ArgumentParser(
        description="M4 - Arma la lluvia de 30 min y le aplica los umbrales publicados.")
    ap.add_argument("--refrescar", action="store_true",
                    help="vuelve a pedirle las series a VIPNET en vez de usar el cache")
    ap.add_argument("--inicio", default=VENTANA_INICIO)
    ap.add_argument("--fin", default=VENTANA_FIN)
    ap.add_argument("--corte-seco", type=float, default=CORTE_SECO_H,
                    help="horas secas que separan dos episodios")
    ap.add_argument("--cache", type=Path, default=RAIZ / "data" / "raw" / "lluvia")
    ap.add_argument("--procesados", type=Path, default=RAIZ / "data" / "processed")
    args = ap.parse_args()

    _verificar_ventana(args.inicio, args.fin)
    grilla = grilla_regular(args.inicio, args.fin)

    print("=" * 74)
    print(f"M4 - ventana {args.inicio} a {args.fin}, paso {PASO_MIN} min")
    print(f"     corte seco {args.corte_seco:.0f} h, "
          f"{'refrescando desde VIPNET' if args.refrescar else 'usando cache'}")
    print("=" * 74)

    # --- R1 ---
    catalogo = descargar_catalogo(TIPO_PRECIPITACION)
    print(f"\nR1  estaciones de precipitacion en Coquimbo: {len(catalogo)}")

    # --- Series de lluvia ---
    print("\nBajando series de precipitacion...")
    series = {}
    for n, cod in enumerate(catalogo["codigo"], 1):
        datos = serie_con_cache(cod, TIPO_PRECIPITACION, args.cache,
                                args.refrescar, args.inicio, args.fin)
        series[cod] = serie_precipitacion(datos, grilla)
        if n % 20 == 0 or n == len(catalogo):
            print(f"  {n}/{len(catalogo)}")

    # --- Isoterma 0 observada ---
    print("\nAjustando la isoterma 0 observada, dia a dia...")
    cat_temp = descargar_catalogo(TIPO_TEMPERATURA)
    temperaturas, altitudes = {}, {}
    for cod, alt in zip(cat_temp["codigo"], cat_temp["altitud_m"]):
        datos = serie_con_cache(cod, TIPO_TEMPERATURA, args.cache,
                                args.refrescar, args.inicio, args.fin)
        temperaturas[cod] = serie_temperatura(datos, grilla)
        altitudes[cod] = alt

    iso = isoterma_cero(temperaturas, altitudes)
    con_iso = iso["altitud_0_m"].notna()
    print(f"  {int(con_iso.sum())} de {len(iso)} dias con isoterma ajustada")
    if con_iso.any():
        julio = iso.loc["2026-07-01":"2026-07-31", "altitud_0_m"].dropna()
        if not julio.empty:
            print(f"  mediana de julio: {julio.median():.0f} m")

    # --- Saltos del contador ---
    saltos = [(cod, t, v) for cod, s in series.items()
              for t, v in s["salto_mm"].dropna().items()]
    print(f"\nSaltos del contador anulados (aislados, > {SALTO_CONTADOR_MM:.0f} mm "
          f"en 30 min): {len(saltos)} pasos en {len({c for c, _, _ in saltos})} estaciones")
    nombres = dict(zip(catalogo["codigo"], catalogo["nombre"]))
    for cod, t, v in saltos:
        print(f"    {nombres[cod][:34]:<34} {str(t)[:16]}  {v:>7.1f} mm")

    # --- R2 y R4, por estacion e invierno ---
    reglas = marcar_ambiguas(aplicar_reglas_estacion(series, catalogo))
    inviernos_r = sorted(reglas["invierno"].unique())
    print("\nR2 y R4 por estacion e invierno:")
    print(f"  {'':<28} " + " ".join(f"{a:>6}" for a in inviernos_r))
    for etiqueta, sel in (("R2  descartadas", reglas["descartada_por"] == "R2"),
                          ("R4  descartadas", reglas["descartada_por"] == "R4"),
                          ("    validas", reglas["descartada_por"] == ""),
                          ("    ambiguas (no se descartan)", reglas["ambigua"])):
        print(f"  {etiqueta:<28} " + " ".join(
            f"{int((sel & (reglas['invierno'] == a)).sum()):>6}" for a in inviernos_r))
    antigua = aplicar_reglas_estacion(series, catalogo, por_invierno=False,
                                      contar_saltos=True)
    print("  Con la version anterior (por estacion sobre toda la ventana y sin "
          "anular saltos):")
    print(f"    R2 {int((antigua['descartada_por'] == 'R2').sum())}, "
          f"R4 {int((antigua['descartada_por'] == 'R4').sum())}, quedan "
          f"{int((antigua['descartada_por'] == '').sum())} de {len(antigua)} estaciones")

    # Una estacion entra si es valida en algun invierno; sus episodios, solo en
    # los inviernos donde lo es.
    vale = set(zip(reglas.loc[reglas["descartada_por"] == "", "codigo"],
                   reglas.loc[reglas["descartada_por"] == "", "invierno"]))
    validas = catalogo[catalogo["codigo"].isin({c for c, _ in vale})]
    print(f"    {len(validas)} de {len(catalogo)} estaciones validas en al menos un invierno")

    # --- Episodios ---
    print(f"\nDetectando episodios con corte seco de {args.corte_seco:.0f} h...")
    todos = []
    for cod in validas["codigo"]:
        eps = detectar_episodios(series[cod], args.corte_seco)
        if eps.empty:
            continue
        eps["invierno"] = invierno(eps["inicio"]).to_numpy()
        eps = eps[[(cod, a) in vale for a in eps["invierno"]]]
        if eps.empty:
            continue
        alt = pd.to_numeric(
            validas.loc[validas["codigo"] == cod, "altitud_m"], errors="coerce").iloc[0]
        eps["bajo_isoterma"] = aplicar_r5(eps, alt, iso)
        eps.insert(0, "estacion_codigo", cod)
        eps.insert(1, "estacion_nombre",
                   validas.loc[validas["codigo"] == cod, "nombre"].iloc[0])
        todos.append(eps)

    if not todos:
        sys.exit("No se detecto ningun episodio. Revisa la ventana o el cache.")

    episodios = pd.concat(todos, ignore_index=True)

    # Los eventos regionales se arman con TODOS los episodios, antes de R3 y R5:
    # solo dicen cuando llovio en la region. Ver m4_interpolacion.
    eventos = interp.eventos_regionales(episodios)
    episodios["evento"] = interp.asignar_evento(episodios, eventos)

    n_bruto = len(episodios)
    episodios = episodios[~episodios["tiene_hueco"]]
    n_r3 = n_bruto - len(episodios)
    episodios = episodios[episodios["bajo_isoterma"]]
    n_r5 = n_bruto - n_r3 - len(episodios)

    print(f"R3  episodios descartados por hueco de transmision: {n_r3}")
    print(f"R5  episodios descartados por estar sobre la isoterma 0: {n_r5}")
    print(f"    quedan {len(episodios)} episodios en "
          f"{episodios['estacion_codigo'].nunique()} estaciones")
    print(f"    {len(eventos)} eventos regionales")

    # Con tres inviernos, el conteo agregado esconde de que anio viene cada
    # cosa. Se separa por invierno hidrologico (abril a marzo, ver invierno()),
    # que es la unidad con que despues se calibra y se valida.

    # --- Umbrales ---
    for columna, valores in evaluar(episodios["duracion_h"],
                                    episodios["i_media_mm_h"],
                                    episodios["i_max_60min_mm_h"]).items():
        episodios[columna] = valores

    # Caine leido sobre la peor ventana del episodio en vez de sobre el episodio
    # entero. Es una columna aparte a proposito: no reemplaza la lectura
    # literal, la acompana. Ver m4_umbrales.razon_critica.
    episodios["supera_caine_critico"] = episodios["razon_caine_critica"] >= 1.0

    dir_out = RAIZ / "outputs"
    dir_out.mkdir(parents=True, exist_ok=True)
    ruta_csv = dir_out / "m4_episodios.csv"
    episodios.to_csv(ruta_csv, index=False, float_format="%.3f")

    print("\nEpisodios que superan cada umbral, por invierno:")
    inviernos = sorted(episodios["invierno"].unique())
    print(f"  {'':<32} " + " ".join(f"{a:>6}" for a in inviernos) + f" {'total':>6}")
    print(f"  {'episodios':<32} "
          + " ".join(f"{int((episodios['invierno'] == a).sum()):>6}" for a in inviernos)
          + f" {len(episodios):>6}")
    columnas = [(u.nombre, u.columna) for u in UMBRALES] + [
        ("Caine sobre la ventana critica", "supera_caine_critico")]
    for nombre, col in columnas:
        sup = episodios[col].fillna(False).astype(bool)
        print(f"  {nombre:<32} "
              + " ".join(f"{int(sup[episodios['invierno'] == a].sum()):>6}" for a in inviernos)
              + f" {int(sup.sum()):>6}")

    # --- Sensibilidad a los dos parametros de juicio ---
    def _contar(corte, umbral_seco):
        n_eps, n_sup, duraciones = 0, 0, []
        for cod in validas["codigo"]:
            eps = detectar_episodios(series[cod], corte, umbral_seco)
            if eps.empty:
                continue
            eps = eps[[(cod, a) in vale for a in invierno(eps["inicio"])]]
            eps = eps[~eps["tiene_hueco"]]
            if eps.empty:
                continue
            n_eps += len(eps)
            duraciones.extend(eps["duracion_h"].tolist())
            n_sup += int(evaluar(eps["duracion_h"], eps["i_media_mm_h"],
                                 eps["i_max_60min_mm_h"])["supera_caine"].sum())
        mediana = float(np.median(duraciones)) if duraciones else float("nan")
        return n_eps, n_sup, mediana

    print("\nSensibilidad al corte seco (cuantas horas separan dos episodios):")
    print(f"  {'corte (h)':>10} {'episodios':>11} {'D mediana':>11} {'superan Caine':>15}")
    for corte in CORTES_SENSIBILIDAD_H:
        n_eps, n_sup, mediana = _contar(corte, UMBRAL_SECO_MM)
        marca = "  <- el usado" if corte == args.corte_seco else ""
        print(f"  {corte:>10.0f} {n_eps:>11} {mediana:>11.1f} {n_sup:>15}{marca}")

    print("\nSensibilidad al umbral de paso seco (que cuenta como no llover):")
    print(f"  {'seco < mm':>10} {'episodios':>11} {'D mediana':>11} {'superan Caine':>15}")
    for umbral_seco in UMBRALES_SECO_SENSIBILIDAD_MM:
        n_eps, n_sup, mediana = _contar(args.corte_seco, umbral_seco)
        marca = "  <- el usado" if umbral_seco == UMBRAL_SECO_MM else ""
        print(f"  {umbral_seco:>10.1f} {n_eps:>11} {mediana:>11.1f} {n_sup:>15}{marca}")

    # --- Cruce con las cuencas ---
    ruta_susc = args.procesados / "susceptibilidad.gpkg"
    if not ruta_susc.exists():
        print(f"\nNo esta {ruta_susc.name}: se salta el cruce con las cuencas.")
        print("Para completarlo corre antes M1 y M2. Los episodios ya quedaron en")
        print(f"  {ruta_csv}")
        return

    import geopandas as gpd
    todas = gpd.read_file(ruta_susc)
    cuencas = todas[todas["clase"].isin(CLASES_SUSCEPTIBLES)].copy()
    print(f"\nCuencas de M2: {len(todas)}; susceptibles "
          f"({' + '.join(CLASES_SUSCEPTIBLES)}): {len(cuencas)}")
    if cuencas.empty:
        sys.exit("M2 no dejo ninguna cuenca susceptible. Revisa susceptibilidad.gpkg.")

    # La estacion de cada cuenca se elige invierno por invierno, entre las
    # validas de ese invierno: si la mas cercana cayo por R2 o R4 en 2025, en
    # 2025 la cuenca usa la siguiente, en vez de quedarse sin lluvia.
    partes, asignadas = [], None
    for a in inviernos_r:
        asig = asignar_estacion(cuencas, reglas[reglas["invierno"] == a])
        if asig is None:
            continue
        lejos = int((asig["distancia_km"] > DISTANCIA_MAXIMA_KM).sum())
        print(f"  invierno {a}: mediana de distancia cuenca-estacion "
              f"{asig['distancia_km'].median():.1f} km; {lejos} cuencas sobre el "
              f"criterio de {DISTANCIA_MAXIMA_KM:.0f} km, marcadas en la capa")
        partes.append(asig.merge(episodios[episodios["invierno"] == a],
                                 on="estacion_codigo", how="inner", suffixes=("", "_ep")))
        asignadas = asig if asignadas is None else asignadas
    pares = pd.concat(partes, ignore_index=True)
    pares["fuera_de_criterio"] = pares["distancia_km"] > DISTANCIA_MAXIMA_KM

    # --- Interpolacion: la lluvia de la cuenca y no la de su estacion ---
    pares = interpolar_pares(pares, asignadas, cuencas, validas, vale, series, eventos,
                             iso, args.procesados, dir_out)

    # El GPKG guarda las fechas en UTC. Una columna en hora de Chile mezcla dos
    # desfases (-04 y -03) y no todos los lectores de GPKG lo soportan; UTC es
    # un instante sin ambiguedad, y quien lea lo pasa a America/Santiago.
    capa = pares.copy()
    for col in ("inicio", "fin"):
        capa[col] = capa[col].dt.tz_convert("UTC")
    salida = args.procesados / "gatillo.gpkg"
    capa.to_file(salida, layer="gatillo", driver="GPKG")

    ruta_png = dir_out / "m4_umbral_id.png"
    figura(pares, ruta_png)

    print(f"\nPares cuenca-episodio: {len(pares)}")
    print(f"  cuencas que superan, por invierno (de {len(cuencas)}):")
    print(f"  {'':<34} " + " ".join(f"{a:>6}" for a in inviernos))
    for nombre, col in columnas:
        sup = pares[col].fillna(False).astype(bool)
        print(f"  {nombre:<34} " + " ".join(
            f"{pares.loc[sup & (pares['invierno'] == a), 'id_cuenca'].nunique():>6}"
            for a in inviernos))

    # De que se sostiene cada positivo. Un umbral superado por una sola cuenca
    # no es un hallazgo hasta saber si el dato que lo sostiene aguanta. Con tres
    # inviernos son miles de pares, asi que se cuentan los motivos en vez de
    # listarlos uno por uno.
    positivos = pares[pares["supera_caine"].fillna(False).astype(bool)].copy()
    if not positivos.empty:
        # Un episodio de un solo paso de 30 min aislado entre horas secas no
        # tiene forma de lluvia: es un escalon del contador. Y como la duracion
        # minima posible es media hora, cualquier paso sobre ~9,7 mm supera
        # Caine por construccion.
        objeciones = {
            "estacion marcada como ambigua": positivos["ambigua"].astype(bool),
            "episodio de un solo paso de 30 min": positivos["duracion_h"] <= 0.5,
            f"estacion a mas de {DISTANCIA_MAXIMA_KM:.0f} km": positivos["fuera_de_criterio"],
        }
        print("\n  De que se sostiene cada positivo (cuencas, por invierno):")
        print(f"  {'':<38} " + " ".join(f"{a:>6}" for a in inviernos))
        sospechoso = np.zeros(len(positivos), dtype=bool)
        for motivo, marca in objeciones.items():
            marca = marca.to_numpy(dtype=bool)
            sospechoso |= marca
            print(f"  {motivo:<38} " + " ".join(
                f"{positivos.loc[marca & (positivos['invierno'] == a).to_numpy(), 'id_cuenca'].nunique():>6}"
                for a in inviernos))
        print(f"  {'sin objeciones':<38} " + " ".join(
            f"{positivos.loc[~sospechoso & (positivos['invierno'] == a).to_numpy(), 'id_cuenca'].nunique():>6}"
            for a in inviernos))

        print("\n  Estaciones que sostienen los positivos (cuencas, todos los inviernos):")
        top = positivos.groupby("estacion_nombre")["id_cuenca"].nunique().nlargest(10)
        for nombre, n in top.items():
            print(f"    {nombre[:44]:<44} {n:>5}")

    print(f"\n  capa    -> {salida.name}")
    print(f"  figura  -> {ruta_png.name}")
    print(f"  tabla   -> {ruta_csv.name}")


if __name__ == "__main__":
    main()
