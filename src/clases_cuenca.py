"""
Vocabulario de clases de cuenca: una sola definicion de a que cuencas se mira.

POR QUE ESTE MODULO EXISTE
--------------------------

M2 clasifica las 444 cuencas de la region en tres clases segun la razon de
Melton, y los dos hitos que vienen despues trabajan sobre el mismo subconjunto:
las 167 cuencas capaces de mover material solido. M3 les calcula la exposicion
vial y M4 les aplica los umbrales de lluvia. Son las dos mitades de una misma
pregunta -M2 dice cuales pueden, M3 donde pegaria, M4 cuando- y por lo tanto
tienen que estar hablando de las mismas 167 cuencas.

Hasta ahora la tupla estaba escrita dos veces y encima con dos nombres
distintos: `CLASES_OBJETIVO` en `m3_exposicion.py` y `CLASES_SUSCEPTIBLES` en
`m4_lluvia.py`. Con dos copias, cambiar una y olvidar la otra no produce ningun
error: los dos scripts siguen corriendo, los dos siguen escribiendo sus capas y
sus tablas, y las cifras siguen viendose plausibles. Lo unico que pasa es que la
exposicion vial queda calculada sobre un universo de cuencas y los umbrales de
lluvia sobre otro, y nada en la salida lo dice. Es la misma familia de problema
que el DEM truncado que motivo `cobertura.py` y que el cuadro vacio de M3: **el
error que no da error**. La defensa es que la definicion exista una sola vez, y
que la contencion entre el total y el subconjunto se compruebe al importar.

POR QUE ACA Y NO EN m2_susceptibilidad.py
-----------------------------------------

Las clases las produce M2, asi que el lugar natural para nombrarlas seria
`m2_susceptibilidad.py`. No se puede: importar ese modulo arrastra matplotlib,
rasterio, scipy y geopandas, y M4 no necesita nada de eso. M4 es un script de
series de tiempo que le pega a una API y cuenta episodios de lluvia; tanto le
sobra lo geoespacial que ni siquiera importa geopandas al cargar el modulo, lo
deja para el unico momento en que cruza con las cuencas. Colgarle el stack de
figuras y rasteres a cambio de dos strings seria pagar varios segundos de
arranque y tres dependencias por una constante.

De ahi la forma de este archivo: **no importa nada**, ni de terceros ni de la
biblioteca estandar. Es la condicion para que cualquier hito pueda leerlo sin
heredar el equipaje de otro. `cobertura.py` resolvio el mismo problema de
duplicacion -una funcion copiada en varios scripts- y la convencion que dejo es
esta: una sola copia en un modulo propio, con el por que escrito donde vive la
definicion y no repetido en cada llamador.

QUE QUEDA FUERA Y POR QUE
-------------------------

La clase `inundacion` -277 de las 444 cuencas- no entra. Por definicion de
Melton son cuencas grandes y tendidas que producen crecida de agua limpia, no
material solido. Preguntarle a una cuenca de clase inundacion que vias le corta
su flujo de detritos, o si supera un umbral de flujos de detritos, no es una
pregunta conservadora: es una pregunta mal planteada, y ademas meteria 277 filas
de ruido que bajarian cualquier porcentaje que uno quiera leer en las tablas. Si
M2 ya dijo que la cuenca no puede, M3 y M4 no tienen nada que decir sobre ella.

EXCEPTO PARA LA EXPOSICION, DESDE OCTUBRE DE 2026
-------------------------------------------------

El argumento de arriba vale para M4: un umbral de flujos de detritos no tiene
nada que decir sobre una cuenca que no los produce. Para M3 resulto mal
planteado, y lo mostro la prueba contra los cortes reales (m5_cortes.py). De 11
cortes de ruta con la via nombrada en 2024-2026, cuatro caen en cuencas de clase
inundacion y M3 no tenia ningun candidato ahi. La prensa describe agua, no
barro: "aumento de caudal" en la D-427, una crecida que "sobrepaso la calzada"
de la misma ruta un anio antes, un socavon en la D-697. O sea que M2 acerto el
proceso, y M3 se equivocaba de pregunta: la que importa para una via no es "que
flujo de detritos la corta" sino "que agua la corta".

Por eso M3 usa CLASES_EXPOSICION, que suma la inundacion con un peso menor, y
M4 sigue usando CLASES_SUSCEPTIBLES. La regla se tomo de la validacion, asi que
las cifras de m5_cortes con la clase nueva no son validacion independiente.

Las cuencas marcadas `borde_truncado` por M2 tampoco estan aca, y es por otro
motivo: no son una clase de susceptibilidad sino cuencas cuya area quedo cortada
por el borde del DEM, o sea un dato que no se puede evaluar. Quedan fuera por no
figurar en `CLASES`.
"""

from __future__ import annotations

# Las tres clases de Wilford que escribe M2 en la columna `clase` de
# susceptibilidad.gpkg, en orden de menos a mas energetica. El orden es parte de
# la constante: M2 recorre la lista al reves para imprimir el resumen de la mas
# critica a la menos.
#
# `tronco` va al final y fuera de esa escala. Desde octubre de 2026 M1 agrega
# las quebradas de mas de 50 km2 (m1_troncos.py), y a esa escala la razon de
# Melton no esta calibrada: M2 no las clasifica por energia, las marca como
# tronco. Ver la cabecera de m1_troncos.py.
CLASES = ("inundacion", "crecida_detritos", "flujo_detritos", "tronco")

# El subconjunto que M3 y M4 analizan: las cuencas capaces de mover algo mas que
# agua limpia, mas los troncos. Los troncos entran todos porque no hay indice
# con que filtrarlos, no porque se sepa que son susceptibles.
CLASES_SUSCEPTIBLES = ("flujo_detritos", "crecida_detritos", "tronco")

# El universo de M3: todo lo que puede cortar una via con agua o con barro. Ver
# "EXCEPTO PARA LA EXPOSICION" en la cabecera. M3 excluye ademas los rios, con la
# misma regla que m1_troncos.py: su peligro es el desborde, otro fenomeno.
CLASES_EXPOSICION = CLASES_SUSCEPTIBLES + ("inundacion",)

# Que el subconjunto este contenido en el total no es decorativo: es lo que hace
# que esta unificacion sirva de algo. Un error de tipeo en cualquiera de las dos
# tuplas, o una clase que M2 renombre sin avisar, deja a M3 y M4 filtrando por un
# valor que no existe en la columna `clase` y devolviendo cero cuencas sin que
# nada falle. Mejor reventar al importar, antes de calcular, que entregar una
# tabla vacia que se lee como "ninguna cuenca cumple".
_sobrantes = (set(CLASES_SUSCEPTIBLES) | set(CLASES_EXPOSICION)) - set(CLASES)
if _sobrantes:
    raise AssertionError(
        f"CLASES_SUSCEPTIBLES o CLASES_EXPOSICION nombran clases que no estan en "
        f"CLASES: {_sobrantes}. Las tuplas tienen que describir la misma "
        "clasificacion de M2."
    )
