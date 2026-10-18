"""A2: un episodio no puede contar su propia lluvia como antecedente."""

from __future__ import annotations

import pandas as pd
import pytest

import m4_lluvia as m4


def serie_sintetica(lluvias: dict[str, float]) -> pd.DataFrame:
    """Cinco dias de grilla de 30 min, medidos y secos salvo `lluvias`."""
    grilla = pd.date_range("2026-07-01 00:00", "2026-07-05 23:30", freq="30min",
                           tz=m4.ZONA_CHILE)
    mm = pd.Series(0.0, index=grilla)
    for hora, valor in lluvias.items():
        mm[pd.Timestamp(hora, tz=m4.ZONA_CHILE)] = valor
    return pd.DataFrame({"mm": mm, "recuperacion": False})


def test_antecedente_no_incluye_el_propio_episodio():
    # 10 mm dos dias antes, y un episodio de 7 + 3 mm.
    serie = serie_sintetica({
        "2026-07-01 12:00": 10.0,
        "2026-07-03 12:00": 7.0,
        "2026-07-03 12:30": 3.0,
    })
    eps = m4.detectar_episodios(serie, corte_seco_h=12.0)

    assert len(eps) == 2
    ep = eps.iloc[1]
    assert ep["inicio"] == pd.Timestamp("2026-07-03 12:00", tz=m4.ZONA_CHILE)
    assert ep["lluvia_mm"] == pytest.approx(10.0)
    assert ep["antecedente_24h_mm"] == pytest.approx(0.0)
    assert ep["antecedente_72h_mm"] == pytest.approx(10.0)
    assert ep["antecedente_168h_mm"] == pytest.approx(10.0)


def test_episodio_de_un_paso_no_es_su_propio_antecedente():
    # El caso de la auditoria: un paso de 10 mm reportaba 10 mm de antecedente.
    serie = serie_sintetica({"2026-07-03 12:00": 10.0})
    eps = m4.detectar_episodios(serie, corte_seco_h=12.0)

    assert len(eps) == 1
    assert eps.iloc[0]["antecedente_24h_mm"] == pytest.approx(0.0)


def test_antecedente_cuenta_justo_hasta_el_paso_anterior():
    # Lluvia en el paso inmediatamente anterior al inicio del episodio, pero
    # bajo el umbral de seco: no abre episodio y si es antecedente.
    serie = serie_sintetica({
        "2026-07-03 11:30": 0.1,
        "2026-07-03 12:00": 5.0,
    })
    eps = m4.detectar_episodios(serie, corte_seco_h=12.0)

    assert len(eps) == 1
    ep = eps.iloc[0]
    assert ep["inicio"] == pd.Timestamp("2026-07-03 12:00", tz=m4.ZONA_CHILE)
    assert ep["antecedente_24h_mm"] == pytest.approx(0.1)
