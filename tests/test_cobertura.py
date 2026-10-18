"""A4: sin limite regional no hay verificacion de cobertura, y eso aborta."""

from __future__ import annotations

import math
import sys

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

import cobertura

CRS = "EPSG:32719"


@pytest.fixture
def raster(tmp_path):
    """Un DEM de juguete de 10 x 10 km en UTM 19S."""
    ruta = tmp_path / "dem.tif"
    with rasterio.open(ruta, "w", driver="GTiff", width=10, height=10, count=1,
                       dtype="float32", crs=CRS,
                       transform=from_origin(300_000, 6_700_000, 1000, 1000)) as dst:
        dst.write(np.ones((1, 10, 10), dtype="float32"))
    return ruta


def limite(tmp_path, caja, nombre="limite.gpkg"):
    ruta = tmp_path / nombre
    gpd.GeoDataFrame({"shapeName": ["Coquimbo"]}, geometry=[box(*caja)], crs=CRS).to_file(
        ruta, driver="GPKG")
    return ruta


def test_sin_limite_aborta(raster, tmp_path):
    with pytest.raises(SystemExit) as e:
        cobertura.verificar_cobertura(raster, tmp_path / "no_existe.gpkg")
    assert "m1_preparar_dem" in str(e.value)


def test_sin_limite_con_permiso_explicito_sigue(raster, tmp_path, capsys):
    f = cobertura.verificar_cobertura(raster, tmp_path / "no_existe.gpkg",
                                      permitir_sin_limite=True)
    assert math.isnan(f)
    assert "SIN VERIFICAR" in capsys.readouterr().out


def test_cobertura_completa_pasa(raster, tmp_path):
    ruta = limite(tmp_path, (302_000, 6_692_000, 308_000, 6_698_000))
    assert cobertura.verificar_cobertura(raster, ruta) == pytest.approx(1.0)


def test_cobertura_parcial_aborta(raster, tmp_path):
    # La mitad de la region queda fuera del raster.
    ruta = limite(tmp_path, (305_000, 6_692_000, 315_000, 6_698_000))
    with pytest.raises(SystemExit):
        cobertura.verificar_cobertura(raster, ruta)


def test_obtener_limite_lee_el_cache_sin_red(tmp_path):
    ruta = limite(tmp_path, (302_000, 6_692_000, 308_000, 6_698_000))
    lim = cobertura.obtener_limite(ruta, "Coquimbo")
    assert len(lim) == 1
    assert lim.crs.to_epsg() == 32719


class _Alto(Exception):
    pass


def test_preparar_dem_obtiene_el_limite_antes_de_verificar(tmp_path, monkeypatch):
    import m1_preparar_dem as prep

    orden = []
    monkeypatch.setattr(prep, "RAIZ", tmp_path)
    monkeypatch.setattr(prep, "obtener_limite", lambda *a, **k: orden.append("obtener"))
    monkeypatch.setattr(prep, "descargar",
                        lambda *a, **k: orden.append("descargar") or [tmp_path / "t.tif"])
    monkeypatch.setattr(prep, "unir", lambda *a, **k: orden.append("unir"))

    def verificar(*a, **k):
        orden.append("verificar")
        raise _Alto

    monkeypatch.setattr(prep, "verificar_cobertura", verificar)
    monkeypatch.setattr(sys, "argv", ["m1_preparar_dem.py"])

    with pytest.raises(_Alto):
        prep.main()
    assert orden == ["obtener", "descargar", "unir", "verificar"]


def test_recortar_region_obtiene_el_limite_antes_de_verificar(tmp_path, monkeypatch):
    import m1_recortar_region as rec

    procesados = tmp_path / "processed"
    procesados.mkdir()
    for nombre in ("cuencas.gpkg", "red_quebradas.gpkg"):
        (procesados / nombre).write_bytes(b"")
    orden = []

    def obtener(*a, **k):
        orden.append("obtener")
        raise _Alto

    monkeypatch.setattr(rec, "obtener_limite", obtener)
    monkeypatch.setattr(rec, "verificar_cobertura", lambda *a, **k: orden.append("verificar"))
    monkeypatch.setattr(sys, "argv", ["m1_recortar_region.py", "--procesados", str(procesados)])

    with pytest.raises(_Alto):
        rec.main()
    assert orden == ["obtener"]
