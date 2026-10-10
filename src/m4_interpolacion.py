"""
M4 - Interpolacion: cuanta lluvia le toco a cada cuenca, y no solo a su estacion.

La idea de fondo:

    Hasta octubre de 2026 a cada cuenca se le asignaba la lluvia de la estacion
    mas cercana a su centroide, tal cual. Se midio cuanto vale eso dejando una
    estacion fuera y prediciendola con las demas, sobre 87 estaciones:

        media regional      MAE 100,7 mm   R2  0,000
        estacion cercana    MAE  90,9 mm   R2 -0,194
        random forest       MAE  74,8 mm   R2  0,294

    La estacion cercana le gana apenas a la media regional en error absoluto y
    le pierde en R2: a cada cuenca se le estaba asignando una lluvia que es casi
    ruido. Este modulo reemplaza esa asignacion por un modelo entrenado, y solo
    si demuestra que es mejor.

QUE SE PREDICE: LLUVIA POR EVENTO, NO EL TOTAL DEL INVIERNO

    El umbral no se aplica al total del invierno sino a cada episodio. Un modelo
    entrenado sobre totales sabe que el interior del Choapa es mas lluvioso que
    la costa, pero no sabe que el frontal del 16 de junio de 2025 se cargo al
    Choapa y el de julio de 2026 al Elqui.

    Ahora, los episodios son de cada estacion: empiezan y terminan a horas
    distintas, asi que no hay un "episodio 7" que sea el mismo en todas. Por eso
    se arman EVENTOS REGIONALES: se juntan las ventanas de lluvia de todas las
    estaciones que se solapan en el tiempo. El sistema frontal del 17 al 22 de
    julio es un evento, aunque cada estacion lo haya visto empezar a otra hora.
    Por cada evento y estacion se suma la lluvia, y eso es lo que el modelo
    aprende a predecir.

LAS VARIABLES

    Fijas del lugar, las cuatro que fija el planteamiento: latitud, longitud,
    altitud y distancia a la costa.

    Del evento, dos: la media regional y la latitud donde se concentro la
    lluvia (el centroide de las estaciones ponderado por lo que midio cada una).
    Sin ellas el modelo daria el mismo patron espacial para todos los eventos,
    que es justamente lo que se quiere superar. Se calculan con las estaciones
    de entrenamiento: en la validacion la estacion que se deja fuera no aporta a
    la media del evento que se le pide predecir.

    El objetivo no es la lluvia en mm sino la lluvia dividida por la media
    regional del evento. Un bosque aleatorio no extrapola: si se le pide mm
    directos, un temporal mas grande que todos los de entrenamiento sale
    recortado al maximo visto. Como fraccion de la media, el temporal grande es
    un patron como cualquier otro.

LA NIEVE QUEDA FUERA DEL ENTRENAMIENTO

    Sobre la isoterma 0 un pluviometro de cubeta no mide la nieve, y por eso las
    estaciones altas registran MENOS que las bajas: sobre 1.500 m el gradiente
    se invierte con R2 0,68. Un bosque entrenado con eso aprenderia que la
    altura reduce la lluvia, y se lo aplicaria a las cuencas altas. Se excluye
    del entrenamiento todo par estacion-evento con la estacion sobre la isoterma
    0 observada ese dia: el mismo criterio de R5, aplicado al modelo.

COMO LLEGA A LA CUENCA

    La cuenca conserva el reloj de su estacion mas cercana -cuando empezo a
    llover, cuanto duro- y la cantidad se escala por el cociente entre lo que el
    modelo predice para la cuenca y lo que midio la estacion en ese evento.

        lluvia de la cuenca = lluvia de la estacion * factor
        factor = prediccion en la cuenca / lluvia de la estacion en el evento

    Asi D, I, la ventana critica y la lluvia antecedente salen del mismo codigo
    de M4 sin reescribirlo. La duracion no se toca: el frontal pasa por el valle
    a la misma hora aunque arriba llueva mas. El factor se acota entre 0,25 y 4,
    porque una estacion con muy poca lluvia en un evento chico daria cocientes
    enormes que no son informacion sino division por casi cero.

LA REGLA DE ADOPCION

    Se valida dejando una estacion fuera, sobre todos los eventos, contra las
    dos referencias del diagnostico: la media regional y la estacion cercana.
    Si el modelo no le gana a la estacion cercana en MAE y en RMSE, NO se adopta:
    la capa queda con factor 1 -la asignacion de siempre- y el reporte lo dice.

    Se prueban dos modelos, random forest y gradient boosting, y se queda el de
    menor MAE. Elegir entre dos con la misma validacion que despues se reporta
    infla un poco el numero; con dos candidatos el efecto es chico, y se dice.

Se usa desde m4_lluvia.py. Correrlo solo no hace nada.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

CRS_METRICO = "EPSG:32719"

# Un evento entra al entrenamiento y a la validacion si la media regional pasa
# de esto. Bajo 5 mm la mayoria de las estaciones mide cero o una basculada, y
# el patron espacial es ruido de instrumento.
EVENTO_MINIMO_MM = 5.0
EVENTO_MIN_ESTACIONES = 20

FACTOR_MIN = 0.25
FACTOR_MAX = 4.0

VARIABLES_FIJAS = ["lat", "lon", "altitud_m", "dist_costa_km"]
VARIABLES_EVENTO = ["media_evento_mm", "lat_centro_evento"]
VARIABLES = VARIABLES_FIJAS + VARIABLES_EVENTO

# Distancia a la costa: el DEM se lee a 300 m. Para una variable que va de 0 a
# 200 km no hace falta mas, y leerlo entero pide 600 MB de RAM.
DEM_DIEZMADO = 10


# =============================================================================
# Distancia a la costa
# =============================================================================

def distancia_costa_km(lon, lat, ruta_dem) -> np.ndarray:
    """Distancia en km desde cada punto a la linea de costa.

    La costa sale del mismo DEM de M1: Copernicus GLO-30 pone el mar en 0. Se
    toma el mar conectado al borde oeste -para no confundir una laguna o un
    embalse con el oceano- y la costa es toda celda de tierra que lo toca.
    """
    import rasterio
    from rasterio.enums import Resampling
    from scipy import ndimage
    from scipy.spatial import cKDTree
    from pyproj import Transformer

    with rasterio.open(ruta_dem) as src:
        alto = src.height // DEM_DIEZMADO
        ancho = src.width // DEM_DIEZMADO
        z = src.read(1, out_shape=(alto, ancho), resampling=Resampling.nearest)
        transform = src.transform * src.transform.scale(
            src.width / ancho, src.height / alto)
        nodata = src.nodata

    mar = (z <= 0) | ((z == nodata) if nodata is not None else False)
    etiquetas, _ = ndimage.label(mar)
    oceano = np.isin(etiquetas, np.unique(etiquetas[:, 0][mar[:, 0]]))
    costa = ~oceano & ndimage.binary_dilation(oceano)

    filas, cols = np.nonzero(costa)
    xs, ys = rasterio.transform.xy(transform, filas, cols)
    a_utm = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)
    cx, cy = a_utm.transform(np.asarray(xs), np.asarray(ys))
    px, py = a_utm.transform(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float))

    dist, _ = cKDTree(np.column_stack([cx, cy])).query(np.column_stack([px, py]))
    return dist / 1000.0


# =============================================================================
# Eventos regionales
# =============================================================================

def eventos_regionales(episodios: pd.DataFrame) -> pd.DataFrame:
    """Junta las ventanas de lluvia de todas las estaciones que se solapan.

    Recibe todos los episodios detectados, incluidos los que R3 y R5 descartan:
    aca solo importa CUANDO llovio en la region, y un episodio con un hueco
    adentro igual dice que estaba lloviendo.
    """
    tramos = episodios[["inicio", "fin"]].sort_values("inicio").to_numpy()
    eventos = []
    ini, fin = tramos[0]
    for a, b in tramos[1:]:
        if a <= fin:
            fin = max(fin, b)
        else:
            eventos.append((ini, fin))
            ini, fin = a, b
    eventos.append((ini, fin))
    df = pd.DataFrame(eventos, columns=["inicio", "fin"])
    df.insert(0, "evento", np.arange(len(df)))
    return df


def asignar_evento(episodios: pd.DataFrame, eventos: pd.DataFrame) -> np.ndarray:
    """El evento que contiene a cada episodio. Siempre hay uno: ver arriba."""
    pos = eventos["inicio"].searchsorted(episodios["inicio"], side="right") - 1
    return eventos["evento"].to_numpy()[pos]


def lluvia_por_evento(series: dict[str, pd.DataFrame], eventos: pd.DataFrame,
                      codigos) -> pd.DataFrame:
    """Lluvia de cada estacion en cada evento.

    `lluvia_mm` es la suma con lo que haya. `completo` dice si esa suma es el
    total verdadero, y solo esos pares entran al entrenamiento.

    Un hueco adentro del evento NO lo invalida, y la razon es la decision 1 de
    M4: se trabaja con el acumulado, asi que el paso donde la estacion vuelve de
    un corte trae la lluvia de todo el corte junta. Para la intensidad eso es
    un problema; para el total del evento es exactamente lo que hace falta. La
    primera version pedia dato en todos los pasos y dejaba 2 eventos de 17
    utilizables en el invierno de 2026, botando totales que eran correctos.

    Lo que si lo invalida es un hueco que no termina en un paso de recuperacion
    dentro del evento: o el corte cruza el borde -y parte de su lluvia cae fuera
    de la ventana- o es un reinicio del contador, donde la lluvia del paso se
    perdio. Y un evento que empieza en hueco, por lo mismo.
    """
    filas = []
    for cod in codigos:
        s = series[cod]
        mm = s["mm"].to_numpy()
        rec = s["recuperacion"].astype(bool).to_numpy()
        a = s.index.searchsorted(eventos["inicio"])
        b = s.index.searchsorted(eventos["fin"], side="right")
        for ev, i, j in zip(eventos["evento"], a, b):
            tramo = mm[i:j]
            filas.append({
                "evento": ev, "estacion_codigo": cod,
                "lluvia_mm": float(np.nansum(tramo)),
                "completo": _total_exacto(tramo, rec[i:j]),
            })
    return pd.DataFrame(filas)


def _total_exacto(tramo: np.ndarray, recuperacion: np.ndarray) -> bool:
    """Cada racha de NaN del tramo termina en un paso de recuperacion adentro."""
    # El primer paso no puede ser hueco ni recuperacion: en los dos casos el
    # corte empezo antes del evento y su lluvia no se sabe de que lado cayo.
    if len(tramo) == 0 or not np.isfinite(tramo[0]) or recuperacion[0]:
        return False
    falta = ~np.isfinite(tramo)
    if not falta.any():
        return True
    # Pasos donde termina una racha de NaN: el siguiente tiene que existir,
    # tener dato y ser el paso donde la estacion volvio.
    fin_racha = np.flatnonzero(falta & ~np.append(falta[1:], False))
    siguiente = fin_racha + 1
    if siguiente[-1] >= len(tramo):
        return False
    return bool(recuperacion[siguiente].all())


def rasgos_evento(tabla: pd.DataFrame, estaciones: pd.DataFrame) -> pd.DataFrame:
    """Media regional y latitud del centro de la lluvia, por evento."""
    t = tabla.merge(estaciones[["codigo", "lat"]], left_on="estacion_codigo",
                    right_on="codigo")
    t["peso_lat"] = t["lluvia_mm"] * t["lat"]
    g = t.groupby("evento").agg(media_evento_mm=("lluvia_mm", "mean"),
                                suma=("lluvia_mm", "sum"),
                                suma_lat=("peso_lat", "sum"),
                                n_estaciones=("lluvia_mm", "size"))
    # Un evento donde nadie midio nada no tiene centro: se le pone el de la red.
    g["lat_centro_evento"] = (g["suma_lat"] / g["suma"].where(g["suma"] > 0)
                              ).fillna(t["lat"].mean())
    return g[["media_evento_mm", "lat_centro_evento", "n_estaciones"]]


# =============================================================================
# Modelos y validacion
# =============================================================================

def _modelo(nombre: str):
    """Los dos candidatos, con hiperparametros de manual y no ajustados.

    Ajustar hiperparametros con la misma validacion que despues se reporta seria
    otra forma de ajustar contra la propia prueba. Se usan valores corrientes y
    se dejan fijos.
    """
    if nombre == "random forest":
        from sklearn.ensemble import RandomForestRegressor
        return RandomForestRegressor(n_estimators=300, min_samples_leaf=3,
                                     random_state=0, n_jobs=-1)
    from sklearn.ensemble import HistGradientBoostingRegressor
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05,
                                         min_samples_leaf=10, random_state=0)


MODELOS = ("random forest", "gradient boosting")


def _con_rasgos(tabla, estaciones, rasgos):
    t = tabla.merge(estaciones[["codigo"] + VARIABLES_FIJAS],
                    left_on="estacion_codigo", right_on="codigo")
    return t.merge(rasgos[VARIABLES_EVENTO], left_on="evento", right_index=True)


def metricas(real, pred, evento) -> dict:
    """MAE, RMSE y dos R2.

    El R2 sobre todos los pares queda alto para cualquier metodo, porque la
    mayor parte de la varianza es que unos eventos llueven mas que otros, y eso
    lo sabe hasta la media regional. El R2 dentro del evento mide lo que de
    verdad se le pide al metodo: repartir la lluvia en el espacio. Es 1 menos el
    error sobre la varianza alrededor de la media real de cada evento.
    """
    real, pred = np.asarray(real, float), np.asarray(pred, float)
    err = real - pred
    medias = pd.Series(real).groupby(np.asarray(evento)).transform("mean").to_numpy()
    return {
        "MAE": float(np.mean(np.abs(err))),
        "RMSE": float(np.sqrt(np.mean(err ** 2))),
        "R2": float(1 - np.sum(err ** 2) / np.sum((real - real.mean()) ** 2)),
        "R2_evento": float(1 - np.sum(err ** 2) / np.sum((real - medias) ** 2)),
    }


def validar_dejando_fuera(tabla: pd.DataFrame, estaciones: pd.DataFrame) -> pd.DataFrame:
    """Deja fuera cada estacion, entrena con las demas y la predice.

    Devuelve una fila por par estacion-evento con la lluvia real y la predicha
    por cada metodo. Las referencias se calculan con las mismas estaciones de
    entrenamiento: la media regional es la media de las demas, y la estacion
    cercana es la mas proxima que tuvo dato completo en ese evento.
    """
    from scipy.spatial.distance import cdist
    from pyproj import Transformer

    a_utm = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)
    x, y = a_utm.transform(estaciones["lon"].to_numpy(float), estaciones["lat"].to_numpy(float))
    dist = pd.DataFrame(cdist(np.column_stack([x, y]), np.column_stack([x, y])),
                        index=estaciones["codigo"], columns=estaciones["codigo"])
    lluvia = tabla.pivot(index="evento", columns="estacion_codigo", values="lluvia_mm")

    salida = []
    for cod in tabla["estacion_codigo"].unique():
        prueba = tabla[tabla["estacion_codigo"] == cod]
        entreno = tabla[tabla["estacion_codigo"] != cod]
        rasgos = rasgos_evento(entreno, estaciones)
        X = _con_rasgos(entreno, estaciones, rasgos)
        Xp = _con_rasgos(prueba, estaciones, rasgos)
        objetivo = X["lluvia_mm"] / X["media_evento_mm"]

        fila = Xp[["evento", "estacion_codigo", "lluvia_mm"]].copy()
        fila["media regional"] = Xp["media_evento_mm"].to_numpy()

        orden = dist.loc[cod].drop(cod).sort_values().index
        cercana = []
        for ev in Xp["evento"]:
            vecinas = lluvia.loc[ev].reindex(orden).dropna()
            cercana.append(float(vecinas.iloc[0]) if len(vecinas) else np.nan)
        fila["estacion cercana"] = cercana

        for nombre in MODELOS:
            m = _modelo(nombre).fit(X[VARIABLES], objetivo)
            fila[nombre] = m.predict(Xp[VARIABLES]) * Xp["media_evento_mm"].to_numpy()
        salida.append(fila)

    return pd.concat(salida, ignore_index=True)


def validar_total(totales: pd.DataFrame, estaciones: pd.DataFrame) -> pd.DataFrame:
    """La misma validacion sobre un total de temporada, con las 4 variables fijas.

    Existe para poder comparar con el diagnostico, que se hizo sobre totales y
    no sobre eventos. No decide la adopcion.
    """
    from scipy.spatial.distance import cdist
    from pyproj import Transformer
    from sklearn.ensemble import RandomForestRegressor

    t = totales.merge(estaciones[["codigo"] + VARIABLES_FIJAS],
                      left_on="estacion_codigo", right_on="codigo").reset_index(drop=True)
    a_utm = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)
    x, y = a_utm.transform(t["lon"].to_numpy(float), t["lat"].to_numpy(float))
    d = cdist(np.column_stack([x, y]), np.column_stack([x, y]))
    np.fill_diagonal(d, np.inf)

    filas = []
    for i in range(len(t)):
        resto = t.drop(index=i)
        rf = RandomForestRegressor(n_estimators=300, min_samples_leaf=3,
                                   random_state=0, n_jobs=-1)
        rf.fit(resto[VARIABLES_FIJAS], resto["lluvia_mm"])
        filas.append({"lluvia_mm": t.loc[i, "lluvia_mm"],
                      "media regional": resto["lluvia_mm"].mean(),
                      "estacion cercana": t.loc[int(np.argmin(d[i])), "lluvia_mm"],
                      "random forest": float(rf.predict(t.loc[[i], VARIABLES_FIJAS])[0])})
    return pd.DataFrame(filas)


def ajustar(tabla: pd.DataFrame, estaciones: pd.DataFrame, nombre: str):
    """El modelo final, con todas las estaciones."""
    rasgos = rasgos_evento(tabla, estaciones)
    X = _con_rasgos(tabla, estaciones, rasgos)
    modelo = _modelo(nombre).fit(X[VARIABLES], X["lluvia_mm"] / X["media_evento_mm"])
    return modelo, rasgos


def predecir(modelo, rasgos: pd.DataFrame, puntos: pd.DataFrame,
             eventos) -> pd.DataFrame:
    """Lluvia predicha en cada punto para cada evento, en mm.

    `puntos` trae un id y las cuatro variables fijas. Sale una fila por punto y
    evento.
    """
    salida = []
    for ev in eventos:
        X = puntos.copy()
        X["evento"] = ev
        for v in VARIABLES_EVENTO:
            X[v] = rasgos.loc[ev, v]
        X["lluvia_pred_mm"] = modelo.predict(X[VARIABLES]) * rasgos.loc[ev, "media_evento_mm"]
        salida.append(X[["id", "evento", "lluvia_pred_mm"]])
    return pd.concat(salida, ignore_index=True)
