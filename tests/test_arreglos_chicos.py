"""Arreglos chicos de la auditoria: M5, M6 y M7. No cambian cifras."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# =============================================================================
# M5: la duplicacion de punteros que no converge aborta
# =============================================================================


def test_etiquetar_cadena_simple():
    import m1_subcuencas as sub

    # 0 -> 1 -> 2 (boca) -> 3 -> 3 (sale del raster)
    abajo = np.array([1, 2, 3, 3], dtype=np.int32)
    etiquetas = sub.etiquetar(abajo, np.array([2]))
    assert list(etiquetas) == [2, 2, 2, -1]


def test_etiquetar_con_ciclo_aborta():
    import m1_subcuencas as sub

    # Las celdas 0 -> 1 -> 2 -> 0 forman un ciclo de tres: la duplicacion de
    # punteros salta 2, 4, 8... pasos, que en un ciclo de 3 nunca vuelve al
    # mismo lugar, y oscila para siempre. (Un ciclo de 2 si converge: cada
    # celda termina apuntandose a si misma.) Antes solo avisaba y seguia con
    # etiquetas a medias.
    abajo = np.array([1, 2, 0, 3], dtype=np.int32)
    with pytest.raises(SystemExit) as e:
        sub.etiquetar(abajo, np.array([3]))
    assert "ciclo" in str(e.value)


# =============================================================================
# M6: solo se unen los tiles del bbox
# =============================================================================


def test_descargar_devuelve_solo_los_tiles_del_bbox(tmp_path, monkeypatch):
    import m1_preparar_dem as prep

    bbox = (-71.5, -30.5, -70.5, -29.5)          # cuatro tiles
    pedidos = prep.tiles_de_bbox(bbox)
    assert len(pedidos) == 4
    # Tres del bbox en disco (el cuarto es mar), mas uno de otra corrida.
    for n in pedidos[:3]:
        (tmp_path / f"{n}.tif").write_bytes(b"x")
    ajeno = prep.nombre_tile(-40, -73)
    (tmp_path / f"{ajeno}.tif").write_bytes(b"x")

    estados = {n: "ya estaba" for n in pedidos[:3]} | {pedidos[3]: "sin datos (mar)"}
    monkeypatch.setattr(prep, "descargar_tile", lambda n, d: (n, estados[n]))

    tiles = prep.descargar(bbox, tmp_path, hilos=1)

    assert sorted(t.stem for t in tiles) == sorted(pedidos[:3])
    assert ajeno not in {t.stem for t in tiles}


# =============================================================================
# M7: una estacion que falla en vivo queda sin dato, y el boletin lo dice
# =============================================================================


class _FuenteQueFalla:
    """Una fuente que responde para todas las estaciones menos las de `caidas`."""

    def __init__(self, caidas):
        self.caidas = set(caidas)

    def registros(self, codigo, tipo, desde, hasta):
        if codigo in self.caidas:
            raise RuntimeError(f"VIPNET no respondio despues de 3 intentos ({codigo})")
        return [{"fecha": {"$date": "2026-07-17T12:00:00Z"}, "acumulado": 1.0,
                 "codigoEstacion": codigo}]


def _catalogos(codigos_lluvia):
    vacio = pd.DataFrame({"codigo": pd.Series([], dtype=str)})
    return {"lluvia": pd.DataFrame({"codigo": codigos_lluvia}),
            "temperatura": vacio, "nieve": vacio}


def test_bajar_todo_sigue_si_una_estacion_falla():
    import m6_alerta_en_vivo as vivo

    momento = pd.Timestamp("2026-07-18 12:00", tz="UTC")
    datos, fallidas = vivo.bajar_todo(_FuenteQueFalla({"B"}), _catalogos(["A", "B", "C"]),
                                      momento)

    assert datos[("lluvia", "B")] == []
    assert len(datos[("lluvia", "A")]) == 1
    assert fallidas == [("lluvia", "B")]


def test_bajar_todo_aborta_si_fallan_todas_las_de_lluvia():
    import m6_alerta_en_vivo as vivo

    momento = pd.Timestamp("2026-07-18 12:00", tz="UTC")
    with pytest.raises(SystemExit) as e:
        vivo.bajar_todo(_FuenteQueFalla({"A", "B"}), _catalogos(["A", "B"]), momento)
    assert "ninguna" in str(e.value).lower()


def test_el_boletin_dice_cuantas_fallaron():
    import m6_alerta_en_vivo as vivo

    r = {
        "momento": "2026-07-18T08:00:00-04:00", "fuente": "VIPNET en vivo",
        "calibracion": "prueba", "temporal": None,
        "provincias": {p: {"nivel": "ninguna", "probabilidad": 0.0, "fraccion_normal": 0.0,
                           "estacion_que_fija": None, "lluvia_temporal_mm": None,
                           "estacion_mas_mojada": None, "lluvia_mas_mojada_mm": None,
                           "siguiente_nivel": {"nivel": "amarilla", "fraccion_normal": 0.16},
                           "estaciones_transmitiendo": 4, "datos_insuficientes": False}
                       for p in ("Elqui", "Limari", "Choapa")},
        "deshielo": {"activo": False, "dia": "2026-07-17", "nieve_cm": None,
                     "isoterma_m": None, "linea_nieve_m": None, "estaciones_nieve": 0},
        "cortes_a_vigilar": [],
        "estaciones": {"lluvia": 3, "validas_en_ventana": 2, "transmitiendo": 2,
                       "sin_respuesta": 1, "sin_respuesta_codigos": ["lluvia B"]},
    }
    texto = vivo.boletin(r)
    assert "1 estacion" in texto and "no respondi" in texto and "lluvia B" in texto
