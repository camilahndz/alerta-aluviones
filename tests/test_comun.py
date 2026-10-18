"""A3: las comunas salen de una copia local comprobada, sin red."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
import requests

import comun

# Dos comunas de juguete en grados, con tildes como las escribe la BCN.
GEOJSON_FALSO = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature",
         "properties": {"shapeName": "Vicuña", "shapeISO": "", "shapeID": "1"},
         "geometry": {"type": "Polygon", "coordinates": [[
             [-70.8, -30.1], [-70.6, -30.1], [-70.6, -29.9], [-70.8, -29.9], [-70.8, -30.1]]]}},
        {"type": "Feature",
         "properties": {"shapeName": "Río Hurtado", "shapeISO": "", "shapeID": "2"},
         "geometry": {"type": "Polygon", "coordinates": [[
             [-70.8, -30.4], [-70.6, -30.4], [-70.6, -30.2], [-70.8, -30.2], [-70.8, -30.4]]]}},
    ],
}


class _Respuesta:
    def __init__(self, contenido: bytes):
        self.content = contenido

    def raise_for_status(self):
        pass


@pytest.fixture
def llamadas_red(monkeypatch):
    """Cuenta cada requests.get. Si alguno llega aca con copia local, es el error."""
    llamadas = []

    def get_falso(url, *args, **kwargs):
        llamadas.append(url)
        raise AssertionError(f"cargar_comunas pidio {url} teniendo copia local")

    monkeypatch.setattr(requests, "get", get_falso)
    return llamadas


def test_con_copia_local_no_hay_red(tmp_path, monkeypatch, llamadas_red):
    ruta = tmp_path / "comunas.geojson"
    ruta.write_text(json.dumps(GEOJSON_FALSO), encoding="utf-8")
    monkeypatch.setattr(comun, "COMUNAS_LOCAL", ruta)

    comunas = comun.cargar_comunas()

    assert llamadas_red == []
    assert list(comunas.columns) == ["comuna", "clave", "geometry"]
    assert sorted(comunas["clave"]) == ["rio hurtado", "vicuna"]
    assert comunas.crs.to_epsg() == 32719


def test_descarga_truncada_no_queda_en_disco(tmp_path, monkeypatch):
    # La falla real: el GeoJSON llego cortado a la mitad. Se reintenta y, si
    # nunca llega completo, aborta sin dejar una copia mala en disco.
    ruta = tmp_path / "limites" / "comunas.geojson"
    monkeypatch.setattr(comun, "COMUNAS_LOCAL", ruta)
    monkeypatch.setattr(comun.time, "sleep", lambda s: None)
    pedidas = []

    def get_cortado(url, *args, **kwargs):
        pedidas.append(url)
        return _Respuesta(b'{"type": "FeatureCollection", "features": [{"type": ')

    monkeypatch.setattr(requests, "get", get_cortado)

    with pytest.raises(SystemExit):
        comun.cargar_comunas()
    assert len(pedidas) == 5
    assert not ruta.exists()


def test_descarga_completa_se_guarda_y_despues_no_se_pide(tmp_path, monkeypatch):
    ruta = tmp_path / "limites" / "comunas.geojson"
    monkeypatch.setattr(comun, "COMUNAS_LOCAL", ruta)
    pedidas = []

    def get_bueno(url, *args, **kwargs):
        pedidas.append(url)
        return _Respuesta(json.dumps(GEOJSON_FALSO).encode("utf-8"))

    monkeypatch.setattr(requests, "get", get_bueno)
    comun.cargar_comunas()
    comun.cargar_comunas()

    assert pedidas == [comun.URL_COMUNAS]
    assert ruta.exists()


def test_sin_tildes_y_provincias():
    assert comun.sin_tildes("Vicuña") == "vicuna"
    assert comun.sin_tildes("Río Hurtado") == "rio hurtado"
    assert comun.sin_tildes(None) == ""
    assert comun.PROVINCIA_DE[comun.sin_tildes("Paihuano")] == "Elqui"
    assert comun.PROVINCIA_DE["rio hurtado"] == "Limari"
    assert comun.PROVINCIA_DE["los vilos"] == "Choapa"
    # Las 15 comunas de la region, cada una en una sola provincia.
    assert len(comun.PROVINCIA_DE) == 15
    assert list(comun.PROVINCIAS) == ["Elqui", "Limari", "Choapa"]


def test_importar_comun_es_liviano():
    # Lo importan las pruebas, el visor y la alerta en vivo: no debe arrastrar
    # geopandas ni requests hasta que se llame a cargar_comunas.
    codigo = ("import sys; sys.path.insert(0, 'src'); import comun; "
              "print(sorted(m for m in ('geopandas', 'requests', 'pandas') if m in sys.modules))")
    salida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                            check=True, cwd=comun.RAIZ)
    assert salida.stdout.strip() == "[]"


def test_los_scripts_usan_la_misma_copia():
    import m5_alerta_sector as alerta
    import m5_historico as hist
    import m5_validacion as m5
    import m6_alerta_en_vivo as vivo
    import m6_visor as visor

    assert m5.cargar_comunas is comun.cargar_comunas
    assert m5.sin_tildes is comun.sin_tildes
    assert alerta.PROVINCIAS is comun.PROVINCIAS
    assert alerta.PROVINCIA_DE is comun.PROVINCIA_DE
    assert hist.sin_tildes is comun.sin_tildes
    assert vivo.comun is comun
    assert visor.comun is comun


def test_m3_lee_las_comunas_de_comun():
    m3 = pytest.importorskip("m3_exposicion")
    assert m3.cargar_comunas is comun.cargar_comunas
    assert m3.URL_COMUNAS == comun.URL_COMUNAS
