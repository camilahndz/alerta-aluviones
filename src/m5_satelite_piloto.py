"""
M5 - Piloto satelital: se ve un flujo de detritos de 2026 en Sentinel-2?

La idea de fondo:

    El inventario de este proyecto es de prensa: 32 entradas en 2026 y 44 en
    2024-2025, todas con nombre de quebrada y ninguna con coordenadas. Un
    flujo de detritos deja una cicatriz -material removido en el cauce, un
    deposito en el abanico- que en principio se ve desde satelite por cambio de
    reflectancia. Si eso se pudiera detectar de forma automatica, el inventario
    pasaria de decenas de etiquetas a cientos, y con cientos se vuelve viable
    entrenar susceptibilidad y gatillo.

    Este script NO construye ese inventario. Responde la pregunta previa: con
    Sentinel-2 a 10 m, sobre quebradas con activacion documentada, se ve algo
    que distinga una quebrada activada de una que no?

DE DONDE SALEN LAS IMAGENES, Y POR QUE DE AHI

    De Sentinel-2 L2A publicado como datos abiertos en AWS, con el catalogo
    STAC de Element 84 (earth-search.aws.element84.com). Sin cuenta y sin
    token. El planteamiento original apuntaba a Copernicus Data Space o Google
    Earth Engine: los dos piden cuenta, y un pipeline que depende de una cuenta
    personal no se puede reproducir sin ella. Los COG se leen por ventana, sin
    bajar la escena completa.

    La escena se elige por nubosidad DENTRO de la ventana, con la capa SCL, y
    no por el porcentaje de la escena: la del 11 de julio de 2026 tiene 32% de
    nubes en la escena y 0% sobre las cuatro ventanas.

LO QUE SALIO, Y QUE CONDICIONA LA LINEA SATELITAL

    1. Antes contra despues del temporal (julio contra septiembre de 2026) no
       sirve tal cual. El cambio lo domina el desierto que reverdece despues de
       200 mm: el NDVI sube +0,38 de mediana en El Islon. Y las sombras del
       relieve cambian de julio a septiembre porque el sol sube, lo que pinta
       laderas enteras de rojo en la diferencia.

    2. La misma estacion del anio anterior (septiembre de 2025 contra
       septiembre de 2026) arregla las sombras. En El Rincon de Caimanes queda
       una senal con forma: la red de cauces aparece con mas suelo desnudo que
       un anio antes, y hay manchas puntuales sin vegetacion.

    3. Pero esa senal aparece en TODA la red de drenaje, no solo en la
       quebrada que la prensa reporto. Lo que el satelite ve con claridad es
       por donde corrio agua con energia, que en un temporal de 40 anios es casi
       todo cauce. Separar un flujo de detritos de una crecida de agua no sale
       de una diferencia de indices: hace falta un clasificador entrenado, y
       para entrenarlo hacen falta etiquetas... que es lo que se queria
       producir.

    O sea que la linea satelital es viable pero no es un atajo. La conclusion
    que este piloto dejaba -que al menos entregaria negativos, cauces que NO
    cambiaron- se probo despues en m5_satelite_cauces.py sobre la region
    entera, y no se sostuvo. Ver ese archivo y m5_satelite_troncos.py.

Uso:

    python src/m5_satelite_piloto.py

Escribe un panel PNG por sitio y por comparacion en outputs/m5_satelite/.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import requests

RAIZ = Path(__file__).resolve().parent.parent
STAC = "https://earth-search.aws.element84.com/v1/search"

# Cuatro sitios con activacion documentada en 2026. Las coordenadas son la boca
# de la quebrada o el punto reportado, leidas de OSM con m5_validacion.ubicar.
SITIOS = (
    ("islon_santa_gracia", -71.070, -29.930, "aluvion, entrada 9"),
    ("marquesa", -70.870, -29.930, "activacion, entradas 2 y 21"),
    ("tres_cruces", -70.526, -29.991, "activacion, entrada 10"),
    ("el_rincon_caimanes", -71.119, -31.907, "activacion, entrada 1"),
)
MEDIO_LADO_M = 2500

COMPARACIONES = {
    # nombre: (antes desde, antes hasta, despues desde, despues hasta)
    "antes_despues": ("2026-06-20", "2026-07-15", "2026-08-25", "2026-09-20"),
    "misma_estacion": ("2025-08-25", "2025-09-20", "2026-08-25", "2026-09-20"),
}

# Clases de la capa SCL que no son superficie: sin dato, sombra de nube, nubes
# de probabilidad media y alta, cirros.
SCL_NO_SUELO = (0, 3, 8, 9, 10)


def escenas(lon, lat, desde, hasta):
    r = requests.post(STAC, json={
        "collections": ["sentinel-2-l2a"],
        "intersects": {"type": "Point", "coordinates": [lon, lat]},
        "datetime": f"{desde}T00:00:00Z/{hasta}T23:59:59Z", "limit": 50}, timeout=60)
    r.raise_for_status()
    return sorted(r.json()["features"], key=lambda f: f["properties"]["datetime"])


def leer(item, banda, lon, lat):
    """Una ventana de 5 x 5 km a 10 m, leida directo del COG."""
    import rasterio
    from pyproj import Transformer
    from rasterio.windows import from_bounds

    with rasterio.open(item["assets"][banda]["href"]) as src:
        cx, cy = Transformer.from_crs(4326, src.crs, always_xy=True).transform(lon, lat)
        ventana = from_bounds(cx - MEDIO_LADO_M, cy - MEDIO_LADO_M,
                              cx + MEDIO_LADO_M, cy + MEDIO_LADO_M, src.transform)
        n = int(2 * MEDIO_LADO_M / 10)
        return src.read(1, window=ventana, out_shape=(n, n), boundless=True,
                        fill_value=0).astype("float32")


def mas_despejada(items, lon, lat):
    mejor, fraccion = None, 2.0
    for it in items:
        nube = float(np.isin(leer(it, "scl", lon, lat), SCL_NO_SUELO).mean())
        if nube < fraccion:
            mejor, fraccion = it, nube
        if nube < 0.01:
            break
    return mejor, fraccion


def indices(item, lon, lat):
    b = {k: leer(item, k, lon, lat) for k in ("red", "green", "blue", "nir", "swir16")}
    ndvi = (b["nir"] - b["red"]) / (b["nir"] + b["red"] + 1e-6)
    # Indice de suelo desnudo: sube donde hay roca o sedimento expuesto.
    a = b["swir16"] + b["red"]
    v = b["nir"] + b["blue"]
    bsi = (a - v) / (a + v + 1e-6)
    rgb = np.clip(np.dstack([b["red"], b["green"], b["blue"]]) / 3000, 0, 1)
    return ndvi, bsi, rgb


def panel(nombre, nota, antes, despues, ruta):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 4, figsize=(20, 5.4))
    ax[0].imshow(antes["rgb"])
    ax[0].set_title(f"antes {antes['fecha']} (nube {antes['nube']:.0%})")
    ax[1].imshow(despues["rgb"])
    ax[1].set_title(f"despues {despues['fecha']} (nube {despues['nube']:.0%})")
    im = ax[2].imshow(despues["ndvi"] - antes["ndvi"], cmap="RdBu", vmin=-0.3, vmax=0.3)
    ax[2].set_title("cambio de NDVI")
    plt.colorbar(im, ax=ax[2], fraction=0.046)
    im = ax[3].imshow(despues["bsi"] - antes["bsi"], cmap="PuOr_r", vmin=-0.2, vmax=0.2)
    ax[3].set_title("cambio de BSI (suelo desnudo)")
    plt.colorbar(im, ax=ax[3], fraction=0.046)
    for a in ax:
        a.set_xticks([])
        a.set_yticks([])
    fig.suptitle(f"{nombre} - {nota} - ventana de 5 x 5 km")
    fig.tight_layout()
    fig.savefig(ruta, dpi=80)
    plt.close(fig)


def main():
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    salida = RAIZ / "outputs" / "m5_satelite"
    salida.mkdir(parents=True, exist_ok=True)

    print("=" * 74)
    print("M5 - Piloto satelital sobre quebradas con activacion documentada")
    print("=" * 74)
    print(f"\n{'sitio':<20} {'comparacion':<16} {'antes':>11} {'despues':>11} "
          f"{'dNDVI p50':>10} {'dBSI p95':>9}")

    for comp, (a0, a1, d0, d1) in COMPARACIONES.items():
        for nombre, lon, lat, nota in SITIOS:
            datos = {}
            for etapa, (desde, hasta) in (("antes", (a0, a1)), ("despues", (d0, d1))):
                items = escenas(lon, lat, desde, hasta)
                # Para "antes" del temporal, la mas cercana al evento primero.
                if comp == "antes_despues" and etapa == "antes":
                    items = items[::-1]
                it, nube = mas_despejada(items, lon, lat)
                ndvi, bsi, rgb = indices(it, lon, lat)
                datos[etapa] = {"ndvi": ndvi, "bsi": bsi, "rgb": rgb, "nube": nube,
                                "fecha": it["properties"]["datetime"][:10]}
            panel(nombre, nota, datos["antes"], datos["despues"],
                  salida / f"{comp}_{nombre}.png")
            dn = datos["despues"]["ndvi"] - datos["antes"]["ndvi"]
            db = datos["despues"]["bsi"] - datos["antes"]["bsi"]
            print(f"{nombre:<20} {comp:<16} {datos['antes']['fecha']:>11} "
                  f"{datos['despues']['fecha']:>11} {np.median(dn):>10.3f} "
                  f"{np.percentile(db, 95):>9.3f}")

    print(f"\n  paneles -> outputs/m5_satelite/")


if __name__ == "__main__":
    main()
