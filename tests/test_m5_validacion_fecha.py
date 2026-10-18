"""A1: una entrada del inventario solo acierta con episodios de su fecha."""

from __future__ import annotations

import math

import pandas as pd
import pytest

import config
import m5_calibracion as cal
import m5_validacion as m5
from m4_umbrales import caine_intensidad_critica

ZONA = "America/Santiago"
LECTURAS = {"episodio": "supera_caine", "ventana critica": "supera_caine_critico"}


def gatillo_dos_temporales() -> pd.DataFrame:
    """Dos cuencas, un temporal fuerte en julio y uno debil en agosto.

    Es la forma del error de la auditoria: Llimpo (15-08) salia predicha con
    216 mm en 53,5 h, que es la lluvia de julio.
    """
    filas = [
        # julio: supera Caine en las dos cuencas
        {"id_cuenca": 1, "inicio": "2026-07-15 10:00", "fin": "2026-07-17 15:30",
         "duracion_h": 53.5, "lluvia_mm": 216.0,
         "supera_caine": True, "supera_caine_critico": True},
        {"id_cuenca": 2, "inicio": "2026-07-15 12:00", "fin": "2026-07-17 22:00",
         "duracion_h": 58.0, "lluvia_mm": 150.0,
         "supera_caine": True, "supera_caine_critico": True},
        # agosto: lluvia debil, no supera nada
        {"id_cuenca": 1, "inicio": "2026-08-15 08:00", "fin": "2026-08-15 14:00",
         "duracion_h": 6.0, "lluvia_mm": 4.6,
         "supera_caine": False, "supera_caine_critico": False},
    ]
    g = pd.DataFrame(filas)
    g["i_media_mm_h"] = g["lluvia_mm"] / g["duracion_h"]
    # gatillo.gpkg guarda las fechas en UTC
    for col in ("inicio", "fin"):
        g[col] = pd.to_datetime(g[col]).dt.tz_localize(ZONA).dt.tz_convert("UTC")
    return g


def test_entrada_de_agosto_no_acierta_con_la_lluvia_de_julio():
    r = m5.emparejar_entrada(gatillo_dos_temporales(), {1}, "2026-08-15", LECTURAS)

    assert r["aciertos"]["episodio"] == set()
    assert r["aciertos"]["ventana critica"] == set()
    assert r["lluvia_max_mm"] == pytest.approx(4.6)
    assert r["duracion_h"] == pytest.approx(6.0)
    esperada = (4.6 / 6.0) / float(caine_intensidad_critica(6.0))
    assert r["razon_max_caine"] == pytest.approx(esperada)


def test_entrada_de_julio_acierta_con_julio():
    r = m5.emparejar_entrada(gatillo_dos_temporales(), {1, 2}, "2026-07-17", LECTURAS)

    assert r["aciertos"]["episodio"] == {1, 2}
    assert r["lluvia_max_mm"] == pytest.approx(216.0)
    assert r["duracion_h"] == pytest.approx(53.5)
    assert r["razon_max_caine"] > 1.0


@pytest.mark.parametrize("fecha, calza", [
    ("2026-07-13", False),   # dos dias antes del inicio
    ("2026-07-14", True),    # inicio - 1 dia
    ("2026-07-18", True),    # fin + 1 dia
    ("2026-07-19", False),   # dos dias despues del fin
])
def test_holgura_de_un_dia(fecha, calza):
    r = m5.emparejar_entrada(gatillo_dos_temporales(), {1}, fecha, LECTURAS)
    assert (r["aciertos"]["episodio"] == {1}) is calza
    assert (not math.isnan(r["lluvia_max_mm"])) is calza


def test_la_fecha_se_lee_en_hora_de_chile():
    # La cuenca 2 termina el 17-07 a las 22:00 de Chile, que en UTC ya es el
    # 18-07. Leida en UTC, la holgura llegaria al 19-07 y calzaria.
    r = m5.emparejar_entrada(gatillo_dos_temporales(), {2}, "2026-07-19", LECTURAS)
    assert r["aciertos"]["episodio"] == set()


def test_sin_episodios_en_la_fecha_no_hay_lluvia():
    r = m5.emparejar_entrada(gatillo_dos_temporales(), {1, 2}, "2026-08-01", LECTURAS)
    assert r["aciertos"]["episodio"] == set()
    assert math.isnan(r["razon_max_caine"])
    assert math.isnan(r["lluvia_max_mm"])
    assert math.isnan(r["duracion_h"])


def test_misma_holgura_que_la_calibracion():
    assert m5.HOLGURA_DIAS == cal.HOLGURA_DIAS == config.HOLGURA_DIAS == 1
