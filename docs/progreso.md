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

Próximo paso exacto: prompt 1B de `docs/prompts_10_dias.md` (empieza por
`pytest`, después `m4_lluvia.py` con cache).
