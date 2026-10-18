"""
Valores canonicos del proyecto, en un solo lugar.

Por que existe: hasta octubre de 2026 cada script tenia sus propios defaults, y
no coincidian. m1_terreno.py pedia un cauce de 0,5 km2 y un area minima de
1 km2 si se corria sin argumentos, mientras m1_subcuencas.py y m1_troncos.py
asumian 0,15 y 0,4. Las corridas buenas pasaban los valores a mano, asi que el
error no se veia; una corrida "por defecto" habria salido con otra red de
quebradas sin que nada avisara (auditoria del 17-10-2026, A5).

Este modulo no importa nada pesado: lo leen scripts de todos los hitos y
tambien las pruebas. Cambiar un valor aca cambia las cifras de todo lo que
viene despues, asi que un cambio aca exige re-correr desde M1.
"""

# --- M1: red de drenaje y unidades de analisis -------------------------------

# Area drenada minima para que una celda sea cauce. La misma en m1_terreno.py
# (red y cuencas costeras), m1_subcuencas.py y m1_troncos.py (bocas) y
# m3_exposicion.py (trayectorias).
UMBRAL_CAUCE_KM2 = 0.15

# Area minima de una unidad de analisis (cuenca costera o subcuenca).
AREA_MIN_KM2 = 0.4

# Area drenada minima del cauce receptor para que cuente como valle.
VALLE_MIN_KM2 = 200.0

# Area maxima de una subcuenca de confluencia. Sobre esto la unidad pasa a ser
# un tronco (m1_troncos.py), con su propio criterio.
AREA_MAX_KM2 = 50.0

# Razon maxima entre el area del afluente y la del receptor: sobre esto son
# ramas gemelas, no un afluente entrando a un valle.
RAZON_MAX = 0.25

# --- M5: emparejar una activacion con un episodio de lluvia --------------------

# Una activacion documentada empareja con un episodio si su fecha cae dentro
# del episodio, con un dia de holgura a cada lado (la prensa fecha el dia en
# que se reporta, no la hora en que bajo). La usan m5_calibracion.py y
# m5_validacion.py, que tienen que medir con la misma regla.
HOLGURA_DIAS = 1
