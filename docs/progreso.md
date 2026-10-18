# Progreso del plan de 10 días

Plan y reglas: `docs/prompts_10_dias.md`. Hallazgos: `docs/auditoria_2026-10-17.md`.

## Fase 1A (17-10-2026): corregir A1 a A6 con prueba primero — HECHA

Solo código y pruebas; no se re-corrió M1, M3, M4 ni M5. Corrida de pruebas:
`docs/corridas/2026-10-17_pruebas_fase1a.txt` (42 pruebas pasan; ruff E, F y B
baja de 57 a 55 avisos, ninguno en código nuevo).

Hecho:

- `tests/` con pytest (`tests/conftest.py` pone `src/` en el path y corta la red
  en todas las pruebas). pytest y ruff en el `.venv` y en `requirements.txt`.
- `src/config.py`: valores canónicos de M1 (cauce 0,15 km², área mínima 0,4,
  valle 200, área máxima 50, razón 0,25) y `HOLGURA_DIAS = 1`.
- `src/comun.py`: `cargar_comunas` (copia local con chequeo), `sin_tildes`,
  `PROVINCIAS`, `PROVINCIA_DE`, `URL_COMUNAS`. Liviano al importar.
- A2 `m4_lluvia.detectar_episodios`: el antecedente termina en el paso anterior
  al inicio del episodio.
- A1 `m5_validacion.emparejar_entrada`: cada entrada acierta solo con episodios
  de su fecha ±1 día; lo mismo para razón, lluvia y duración y para la tabla de
  recall de julio y agosto. Aborta si una entrada no trae fecha.
- A3 M3, `m5_validacion`, `m5_alerta_sector`, `m5_historico` y los dos M6 usan
  `comun.py`. M3 ya no lee la URL.
- A4 `obtener_limite` en `cobertura.py`; `m1_preparar_dem` lo obtiene antes del
  primer tile; `m1_recortar_region` lo obtiene antes de verificar;
  `verificar_cobertura` aborta sin límite salvo `permitir_sin_limite=True`.
- A5 `m1_terreno`, `m1_subcuencas`, `m1_troncos` y M3 toman los defaults de
  `config.py`.
- A6 `descargar_catalogo` guarda `catalogo_<tipo>.json` (respuesta completa,
  consulta y fecha de bajada) en la carpeta de la ventana y lo reutiliza salvo
  `--refrescar`. Aborta si la región queda sin estaciones.
- M5 `m1_subcuencas.etiquetar` aborta si no converge. M6 `m1_preparar_dem` une
  solo los tiles del bbox. M7 `m6_alerta_en_vivo.bajar_todo`: una estación que
  falla queda sin dato y el boletín dice cuántas y cuáles; si fallan todas las
  de lluvia, aborta.
- B5: variable `cobertura`, `numpy` sin usar, `x == x` y `__import__("pandas")`.

Para tener en cuenta en 1B:

- La primera corrida de M4 sin catálogo en cache lo baja de VIPNET y lo guarda.
  La corrida del 10-10 tenía R1 = 107 estaciones; si cambia, cambia todo M4.
- Con A1, las entradas fechadas el 31-07 se emparejan con el episodio del 31 de
  julio (el README lo lista aparte: 23,9 mm de mediana) y no con el temporal del
  17 al 22. Eso mueve la tabla de recall, la de Caine × k y la conclusión de
  que Caine queda "un 30% alto". Hay que leerlo con la corrida guardada.

## Fase 1B (17-10-2026): re-correr y dejar las cifras verdaderas — HECHA

Código sin cambios (commit `d70926f`); solo corridas y documentación. Antes de
correr: 42 pruebas pasan, y los catálogos de VIPNET de hoy traen los mismos
códigos que las series del cache (107 de lluvia, 113 de temperatura y 10 de
nieve). R1 sigue en 107.

Corridas, cada una con su "Verificación" contra la anterior:

- `docs/corridas/2026-10-17_m4_antecedente.txt` (`m4_lluvia.py` y
  `m4_deshielo.py`). En `m4_episodios.csv` solo cambian las tres columnas
  `antecedente_*`: bajan en los 1.188 episodios, exactamente el primer paso. Con
  más de 50 mm en 72 h, en 2026 hay 35 → 34 episodios; Río Choapa 265,6 → 265,2 mm
  y Caimanes 239,4 → 239,0. En `gatillo.gpkg` hay además diferencias de 1e-16
  relativo en la lluvia interpolada: el random forest con `n_jobs=-1` suma los
  árboles en distinto orden. No es un cambio del modelo, pero para la fase 2
  significa que `gatillo.gpkg` no sale idéntico byte a byte. Los catálogos
  quedaron en `data/raw/lluvia/2024-06-01_2026-08-23/catalogo_{0,1,3}.json`.
- `docs/corridas/2026-10-17_m5_m6_validacion_fecha.txt` (las tres variantes de
  `m5_validacion.py`, la calibración, la alerta por sector, los niveles y
  `m6 --repasar`). Recall con troncos, episodio: 6/26 → 4/26 (agosto 2/11 → 0/11);
  ventana crítica 20/26 → 10/26 (julio 12/15 → 9/15, agosto 8/11 → 1/11). Llimpo y
  Pichasca pasan a no predichas. El "Caine 30% alto" solo vale para el temporal
  del 17 al 22 de julio (9 entradas). La calibración, la alerta por sector y los
  niveles salen idénticos; b0 y b1 iguales a los congelados de m6; el repaso da 41
  de 41.
- `docs/corridas/2026-10-17_m3_exposicion.txt`. `puntos_corte.gpkg` es idéntico:
  9.424 puntos, las mismas 18 comunas, los mismos atributos y la misma geometría.
  El visor no se regeneró.

README: el párrafo de antecedente de M4, la línea de la interpolación en M5 (de
40%-72% a 24%-36%), "Cómo se corre M5", "Resultado de M5", "Las fallas son el
hallazgo" con su párrafo "Corrección del 17 de octubre de 2026", y las corridas
nuevas en "Reproducibilidad". `docs/contexto.md`: el AUC de los niveles (1,00 y
0,95 eran de la versión con la estación más mojada; la vigente es 0,97 y 0,96).

Quedó sin tocar, porque no viene de la 1B: en el README, la tabla de salidas de M4
(`gatillo.gpkg` con "11.591 filas"; hoy son 30.499) y la sección de la auditoría
del 11-10 ("No hay pruebas automáticas", "La alerta en vivo no avisa si falla"),
que la fase 1A ya resolvió. Las dos son de la fase 2 o 3, cuando el README pase a
`docs/bitacora.md`.

Próximo paso exacto: prompt 2 de `docs/prompts_10_dias.md` (un comando, pruebas
y CI). La regla de hash del punto 5 aplica a `m4_episodios.csv` y
`m5_validacion.csv`; `gatillo.gpkg` necesita comparación con tolerancia.
