"""A5: los defaults de M1 son los valores canonicos de config.py."""

from __future__ import annotations

import argparse
import sys

import pytest

import config


class _Capturado(Exception):
    def __init__(self, ns):
        self.ns = ns


def defaults_de(modulo, monkeypatch) -> argparse.Namespace:
    """Los defaults del parser de `modulo.main()`, sin correr el script.

    Se intercepta parse_args: arma el Namespace con una linea de comandos vacia
    y corta ahi, antes de que main lea un solo archivo.
    """
    original = argparse.ArgumentParser.parse_args

    def interceptar(self, args=None, namespace=None):
        raise _Capturado(original(self, []))

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", interceptar)
    monkeypatch.setattr(sys, "argv", [modulo.__name__])
    with pytest.raises(_Capturado) as e:
        modulo.main()
    return e.value.ns


def test_m1_terreno(monkeypatch):
    import m1_terreno

    ns = defaults_de(m1_terreno, monkeypatch)
    assert ns.umbral_km2 == config.UMBRAL_CAUCE_KM2 == 0.15
    assert ns.area_min_km2 == config.AREA_MIN_KM2 == 0.4


def test_m1_subcuencas(monkeypatch):
    import m1_subcuencas

    ns = defaults_de(m1_subcuencas, monkeypatch)
    assert ns.umbral_km2 == config.UMBRAL_CAUCE_KM2
    assert ns.area_min_km2 == config.AREA_MIN_KM2
    assert ns.valle_min_km2 == config.VALLE_MIN_KM2 == 200.0
    assert ns.area_max_km2 == config.AREA_MAX_KM2 == 50.0
    assert ns.razon_max == config.RAZON_MAX == 0.25


def test_m1_troncos(monkeypatch):
    # m1_troncos no expone estos valores por argumentos: los tiene como
    # constantes, y son las reglas de boca de m1_subcuencas.
    import m1_troncos

    assert m1_troncos.UMBRAL_CAUCE_KM2 == config.UMBRAL_CAUCE_KM2
    assert m1_troncos.AREA_MIN_KM2 == config.AREA_MAX_KM2   # donde terminan las subcuencas
    assert m1_troncos.VALLE_MIN_KM2 == config.VALLE_MIN_KM2
    assert m1_troncos.RAZON_MAX == config.RAZON_MAX


def test_m3_umbral_de_cauce(monkeypatch):
    m3 = pytest.importorskip("m3_exposicion")
    ns = defaults_de(m3, monkeypatch)
    assert ns.umbral_cauce_km2 == config.UMBRAL_CAUCE_KM2


def test_los_scripts_leen_config():
    # Que coincidan hoy no basta: tienen que salir de config, para que un
    # cambio alla llegue a todos. Se comprueba cambiando config en un proceso
    # aparte y mirando los defaults.
    import subprocess

    codigo = (
        "import sys, argparse; sys.path.insert(0, 'src'); import config; "
        "config.UMBRAL_CAUCE_KM2 = 9.0; config.AREA_MIN_KM2 = 8.0; "
        "config.VALLE_MIN_KM2 = 7.0; config.AREA_MAX_KM2 = 6.0; config.RAZON_MAX = 0.5; "
        "import m1_terreno, m1_subcuencas, m1_troncos; "
        "orig = argparse.ArgumentParser.parse_args\n"
        "class Alto(Exception): pass\n"
        "def f(self, *a, **k):\n"
        "    print(sorted(vars(orig(self, [])).items(), key=str)); raise Alto\n"
        "argparse.ArgumentParser.parse_args = f\n"
        "for m in (m1_terreno, m1_subcuencas):\n"
        "    try: m.main()\n"
        "    except Alto: pass\n"
        "print(m1_troncos.UMBRAL_CAUCE_KM2, m1_troncos.AREA_MIN_KM2, "
        "m1_troncos.VALLE_MIN_KM2, m1_troncos.RAZON_MAX)\n"
    )
    salida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                            check=True, cwd=config.__file__.rsplit("src", 1)[0])
    lineas = salida.stdout.strip().splitlines()
    assert "('umbral_km2', 9.0)" in lineas[0] and "('area_min_km2', 8.0)" in lineas[0]
    for par in ("('umbral_km2', 9.0)", "('area_min_km2', 8.0)", "('valle_min_km2', 7.0)",
                "('area_max_km2', 6.0)", "('razon_max', 0.5)"):
        assert par in lineas[1]
    assert lineas[2] == "9.0 6.0 7.0 0.5"
