"""A6: el catalogo de estaciones se guarda con el cache de la ventana."""

from __future__ import annotations

import json

import pandas as pd
import pytest
import requests

import m4_lluvia as m4

INICIO, FIN = "2024-06-01", "2026-08-23"


def estacion(codigo: str, region: int) -> dict:
    return {"codigoEstacion": codigo, "nombre": f"Estacion {codigo}", "latitud": -30.0,
            "longitud": -71.0, "altitud": 100.0, "fuenteEstacion": "INIA", "region": region}


class _Respuesta:
    def __init__(self, cuerpo: dict):
        self._cuerpo = cuerpo

    def raise_for_status(self):
        pass

    def json(self):
        return self._cuerpo


@pytest.fixture
def vipnet(monkeypatch):
    """requests.post simulado; devuelve la lista de consultas que recibio."""
    consultas = []

    def post_falso(url, json=None, timeout=None):
        consultas.append({"url": url, "payload": json})
        return _Respuesta({"data": [estacion("B", 4), estacion("A", 4), estacion("C", 3)]})

    monkeypatch.setattr(requests, "post", post_falso)
    return consultas


def test_segunda_llamada_no_toca_la_red(tmp_path, vipnet):
    c1 = m4.descargar_catalogo(m4.TIPO_PRECIPITACION, cache=tmp_path, inicio=INICIO, fin=FIN)
    c2 = m4.descargar_catalogo(m4.TIPO_PRECIPITACION, cache=tmp_path, inicio=INICIO, fin=FIN)

    assert len(vipnet) == 1
    assert list(c1["codigo"]) == ["A", "B"]           # solo region 4, ordenado
    pd.testing.assert_frame_equal(c1, c2)
    ruta = tmp_path / f"{INICIO}_{FIN}" / f"catalogo_{m4.TIPO_PRECIPITACION}.json"
    assert ruta.exists()
    # Se guarda lo que mando VIPNET, todas las regiones, y con que consulta.
    guardado = json.loads(ruta.read_text(encoding="utf-8"))
    assert len(guardado["data"]) == 3
    assert guardado["consulta"]["fetchDay"] == FIN


def test_otra_region_sale_del_mismo_archivo(tmp_path, vipnet):
    m4.descargar_catalogo(m4.TIPO_PRECIPITACION, cache=tmp_path, inicio=INICIO, fin=FIN)
    atacama = m4.descargar_catalogo(m4.TIPO_PRECIPITACION, region=3, cache=tmp_path,
                                    inicio=INICIO, fin=FIN)
    assert len(vipnet) == 1
    assert list(atacama["codigo"]) == ["C"]


def test_refrescar_vuelve_a_pedir(tmp_path, vipnet):
    m4.descargar_catalogo(m4.TIPO_PRECIPITACION, cache=tmp_path, inicio=INICIO, fin=FIN)
    m4.descargar_catalogo(m4.TIPO_PRECIPITACION, cache=tmp_path, inicio=INICIO, fin=FIN,
                          refrescar=True)
    assert len(vipnet) == 2


def test_cada_tipo_y_cada_ventana_tiene_su_archivo(tmp_path, vipnet):
    m4.descargar_catalogo(m4.TIPO_PRECIPITACION, cache=tmp_path, inicio=INICIO, fin=FIN)
    m4.descargar_catalogo(m4.TIPO_TEMPERATURA, cache=tmp_path, inicio=INICIO, fin=FIN)
    m4.descargar_catalogo(m4.TIPO_PRECIPITACION, cache=tmp_path, inicio=INICIO, fin="2026-09-30")
    assert len(vipnet) == 3
    assert vipnet[2]["payload"]["fetchDay"] == "2026-09-30"


def test_un_catalogo_vacio_aborta(tmp_path, monkeypatch):
    # Cero estaciones no es un catalogo: es una consulta que salio mal.
    monkeypatch.setattr(requests, "post", lambda url, json=None, timeout=None:
                        _Respuesta({"data": [estacion("C", 3)]}))
    with pytest.raises(SystemExit):
        m4.descargar_catalogo(m4.TIPO_PRECIPITACION, cache=tmp_path, inicio=INICIO, fin=FIN)
