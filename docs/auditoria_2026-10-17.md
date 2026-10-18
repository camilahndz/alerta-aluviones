# Auditoría del código, 17 de octubre de 2026

Revisión completa de `src/` (29 scripts), `visor/`, README y `docs/contexto.md`
sobre el estado del 11-10-2026 (commit `6f02ef5`). El pipeline no se re-corrió.
Etiquetas: VERIFICADO = comprobado en código o en una salida; INFERIDO = se deduce
del código pero no se midió el efecto.

Documento completo con el plan: https://claude.ai/code/artifact/8aa5b217-dcde-4f4a-9b16-27238f85162a

## Críticos

- **C1** (VERIFICADO). `main` iba 30 commits adelante de `origin/main` (remoto en
  `90062e3`, del 10-10) y `src/m4_cr2met_diario.py` y `src/m5_historico.py` no
  estaban en git. Mismo patrón que perdió M4 el 19-09-2026.
- **C2** (VERIFICADO). `data/raw/` (~2,3 GB) sin respaldo. El cache de VIPNET no se
  puede volver a bajar igual porque VIPNET rellena datos tarde.

## Altos (cambian lo que se mide o se reproduce)

- **A1** (VERIFICADO). `m5_validacion.py` no empareja por fecha.
  `positivas_en_ventana` toma toda la ventana 2026-06-01 a 2026-08-24 y el cálculo
  de `razon_max_caine`, `lluvia_max_mm` y `duracion_h` (líneas ~399-409) usa todos
  los pares de esa ventana. Una activación de agosto se marca "predicha" con la
  lluvia de julio. Evidencia en `outputs/m5_validacion.csv`: Llimpo (15-08)
  predicha con 216,0 mm en 53,5 h; Cutun (16-08) con 242,5 mm en 116,5 h, cifras del
  temporal de julio. `m5_calibracion.py` sí empareja (fecha dentro del episodio
  +-1 día, `HOLGURA_DIAS`). Afecta la tabla de recall julio/agosto del README; no
  afecta calibración ni niveles por provincia.
- **A2** (VERIFICADO con prueba sintética). En `m4_lluvia.detectar_episodios`
  (línea 784) `mm.loc[ini - timedelta(hours=horas):ini]` es inclusivo en los dos
  extremos, así que `antecedente_*` incluye el primer paso del propio episodio. Un
  episodio de un paso de 10 mm reporta 10 mm de antecedente 24 h. Hoy ningún modelo
  ajustado usa esas columnas; sí el README (35 episodios con >50 mm previos).
- **A3** (VERIFICADO). `m3_exposicion.py` línea 1091 lee las comunas con
  `gpd.read_file(URL_COMUNAS)` en cada corrida. `m5_validacion.cargar_comunas()`
  documenta que esa descarga llegó cortada dos veces y ya usa copia local con
  chequeo; M3 no se actualizó.
- **A4** (VERIFICADO). En máquina limpia no se verifica cobertura:
  `data/raw/limite_coquimbo.gpkg` lo crea `m1_recortar_region.py` (tercer paso),
  pero `m1_preparar_dem.py` y `m1_terreno.py` lo piden antes, y
  `cobertura.verificar_cobertura` (líneas 110-112) solo avisa y devuelve NaN si
  falta. Además `m1_recortar_region.main` verifica antes de llamar a
  `obtener_limite`.
- **A5** (VERIFICADO). `m1_terreno.py` líneas 630-633: defaults `--umbral-km2 0.5`
  y `--area-min-km2 1.0`, contra los canónicos 0,15 y 0,4. `m1_subcuencas.py` y
  `m1_troncos.py` asumen 0,15 fijo.
- **A6** (VERIFICADO). `descargar_catalogo` pide el catálogo a VIPNET en cada
  corrida aunque haya cache (`m4_lluvia.py` líneas 1216 y 1231, `m5_niveles.py`
  241, `m4_deshielo.py`, `m6`). Ninguna corrida es offline y una estación nueva
  cambia R1 sin aviso.

## Medios

- **M1** (INFERIDO). `m4_interpolacion.validar_dejando_fuera` deja fuera una
  estación a la vez; hay pares a 0,2 km (Las Burras). Optimista: falta validación
  por bloques espaciales.
- **M2** (VERIFICADO). `m4_lluvia.py` ~1099: el factor de interpolación del evento
  actual también escala `antecedente_*`, que es lluvia de eventos anteriores.
- **M3** (VERIFICADO, declarado en README). Segunda estación, fracción de la normal
  y área en la prioridad se eligieron con los mismos 5 temporales positivos.
  Solución: validación prospectiva preregistrada (2027).
- **M4** (VERIFICADO). `m1_troncos.py` importa `m5_validacion` y `m3_exposicion`
  (M1 depende del extracto OSM) y reescribe `unidades_coquimbo.gpkg` en el lugar:
  re-correr `m1_subcuencas.py` borra los troncos sin aviso.
- **M5** (VERIFICADO). `m1_subcuencas.etiquetar` solo avisa si la duplicación de
  punteros no converge en 40 pasadas (líneas 254-256).
- **M6** (VERIFICADO). `m1_preparar_dem.descargar` (línea 150) une todos los tiles
  de la carpeta, no solo los del bbox.
- **M7** (VERIFICADO). En `m6_alerta_en_vivo.py`, `AlmacenVivo.registros` lanza
  RuntimeError tras 3 intentos y `bajar_todo` no lo captura: una estación caída
  tumba el boletín entero, sin aviso a nadie.
- **M8** (VERIFICADO). `visor/index.html` carga deck.gl desde unpkg (línea 387) y
  fuentes de Google (líneas 3-5) sin `integrity`; el README dice que el visor no
  pide nada a servidores ajenos.

## Bajos

- **B1** Sin pruebas, sin CI, sin `pyproject.toml`, sin versiones fijas.
  `requirements.txt` solo pide mínimos; el `.venv` real usa Python 3.12.10, numpy
  2.5.3, pandas 3.0.6, geopandas 1.2.0, rasterio 1.5.2, pysheds 0.5, scikit-learn
  1.9.1, scipy 1.18.1, osmnx 2.1.1, shapely 2.2.0, pyogrio 0.13.0, pyproj 3.8.0,
  matplotlib 3.11.2, requests 2.34.2, tzdata 2026.5.
- **B2** Ningún comando corre todo: más de 20 pasos, orden en el README.
- **B3** `main` gigantes: complejidad ciclomática `m4_lluvia.main` 46,
  `m5_validacion.main` 34, `m6.evaluar` 28, `m5_niveles.main` 24.
- **B4** Duplicados: `CRS_METRICO` en más de 10 archivos, dos `PROVINCIA_DE`
  (`m5_alerta_sector`, `m5_historico`), dos `sin_tildes`, B0/B1 copiados a mano.
- **B5** ruff: variable `cobertura` sin usar (`m3_exposicion.py` 1041), `numpy`
  sin usar (`m5_alerta_sector.py` 111), `x == x` para NaN (`m5_validacion.py`
  414-416), `__import__("pandas")` (`m1_subcuencas.py` 411).
- **B6** 14 `warnings.simplefilter("ignore")` generales.
- **B7** README de 1.593 líneas usado como bitácora, sin entrada corta ni versión
  en inglés. Deriva: la cabecera de `m3_exposicion.py` aún dice bajar el extracto
  a mano.
- **B8** `m5_historico.py` sin corrida guardada en `docs/corridas/`.

## Resuelto desde agosto

- La salida de localidades de M3 tiene hoy 79 localidades con nombre en 295 filas.
