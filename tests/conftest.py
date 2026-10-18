"""
Configuracion comun de las pruebas.

Dos cosas, y las dos son defensas:

    1. Pone src/ en el path, para importar los scripts como modulos igual que
       se importan entre ellos (`import m4_lluvia as m4`).

    2. Corta la red en todas las pruebas. Las pruebas usan datos sinteticos
       chicos, nunca data/ ni VIPNET. Una prueba que sin querer le pega a la
       API pasaria o fallaria segun el dia, y una que pasa por la red no prueba
       el codigo sino el servicio. Si alguna intenta conectarse, revienta con
       un error que lo dice.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class RedCortada(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    def prohibido(*args, **kwargs):
        raise RedCortada("Una prueba intento conectarse a la red. Las pruebas no "
                         "tocan la red: simula la llamada con monkeypatch.")

    monkeypatch.setattr(socket.socket, "connect", prohibido)
    monkeypatch.setattr(socket, "create_connection", prohibido)
