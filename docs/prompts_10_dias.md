# Prompts por fase para Claude Code (10 días)

Cada prompt se pega como primer mensaje de una sesión nueva de Claude Code abierta
en la carpeta del repositorio. Una fase por sesión. Si la sesión se corta o se
llena, abre otra y pega el **prompt de retomar** (al final).

Contexto de todos los prompts: `docs/auditoria_2026-10-17.md` (hallazgos con
archivo y línea). Fuera de estos 10 días quedan IMERG, Atacama y las fases 6 y 7,
que dependen del invierno de 2027.

## Calendario

| Día | Qué | Prompt |
|---|---|---|
| 1 | Fase 0 a mano (30 min) y empezar 1A | Fase 0 + 1A |
| 2 | Terminar 1A | retomar |
| 3 | Re-correr y corregir cifras | 1B |
| 4-5 | Un comando, pruebas y CI | 2 |
| 6 | Alerta automática y visor público | 3A |
| 7 | Probar en GitHub y ajustar | 3B |
| 8 | 50 años de historia | 4A |
| 9 | Pronóstico con Open-Meteo | 4B |
| 10 | Dejar listo para congelar v1.0 | 5 |

## Reglas comunes (todos los prompts piden leer y cumplir esto)

1. Lee primero `CLAUDE.md`, `docs/contexto.md`, `docs/auditoria_2026-10-17.md` y
   `docs/progreso.md` si existe. Del README lee solo las secciones que vas a tocar.
2. Git: puedes usar `git status`, `git diff` y `git log`. No ejecutes `git add`,
   `commit`, `push`, `checkout`, `stash`, `merge` ni `reset`, no configures
   `user.name` ni `user.email` y no toques `.git/config` ni hooks. Al final propón
   los comandos para que yo los copie, en una línea por commit:
   `git add <archivos> && git commit -m "<mensaje>" && git push origin main`.
   Mensajes en español, sin tildes, de 50 caracteres o menos, con el estilo del
   repo (`M4: corta el antecedente antes del episodio`), sin `Co-Authored-By`.
3. Python: usa `.venv\Scripts\python.exe` (Windows). No instales nada global. Si
   hace falta un paquete, va al `.venv` y a los archivos de dependencias, y lo dices.
4. No borres nada en `data/`, `outputs/` ni `docs/corridas/` sin preguntarme. No
   cambies los coeficientes congelados `B0` y `B1` de `src/m6_alerta_en_vivo.py`
   salvo que la fase 5 lo diga y yo lo apruebe.
5. Antes de editar, muéstrame un plan de 15 líneas o menos y espera mi "ok".
   Después trabaja seguido, sin preguntar, salvo bloqueo real o una decisión que
   no se puede deshacer.
6. Cada error se arregla con prueba primero: escribe la prueba, muéstrame que
   falla, arregla, muéstrame que pasa.
7. Ninguna cifra entra al README ni a `docs/` sin una corrida guardada en
   `docs/corridas/AAAA-MM-DD_<nombre>.txt` (salida completa de consola más una
   sección final "Verificación" que la compara con la corrida anterior).
8. Antes de un comando que tarde más de 5 minutos, avísame cuánto estimas. No
   repitas la hidrología de M1 (`m1_terreno.py`, ~36 min) si la fase no lo pide.
9. Estilo del repo: cada script explica en su docstring qué hace y por qué;
   comentarios en español sin tildes como el código existente. Mantén la filosofía
   de `docs/contexto.md`: un error que no da error es el peor error, así que
   aborta en vez de advertir y cuenta lo que entra y lo que sale de cada paso.
10. Cada vez que cierres un bloque de trabajo, actualiza `docs/progreso.md` (qué se
    hizo, qué falta, próximo paso exacto) para poder retomar en otra sesión.
11. Cuando expliques un cambio, una línea en palabras simples, y define cada sigla
    la primera vez.
12. Informe final, corto: archivos cambiados, cifras que cambiaron (antes y después,
    con su corrida), cuántas pruebas pasan, lo que quedó pendiente, cada afirmación
    marcada VERIFICADO, INFERIDO o SUPUESTO, los comandos git, y una sección
    `### Próximos Pasos` con "Para Camila (MÍO)" y "Pendientes del sistema".

## Fase 0, a mano (no es un prompt)

- [ ] Subir lo pendiente:
  `git add src/m4_cr2met_diario.py src/m5_historico.py docs/auditoria_2026-10-17.md docs/prompts_10_dias.md && git commit -m "docs: auditoria y prompts; agrega M4/M5 historico" && git push origin main`
- [ ] Copiar `data/raw/` completo a Google Drive o a un disco externo.
- [ ] Decidir si el repositorio pasa a público (necesario en la fase 3 para que
      GitHub Actions y Pages sean gratis sin límite).

## Prompt 1A. Corregir los errores, con prueba primero

```text
Fase 1A de alerta-aluviones: corregir los hallazgos A1 a A6 de la auditoría, con prueba primero.

Lee docs/prompts_10_dias.md (sección "Reglas comunes") y cúmplelas toda la sesión. Después lee docs/auditoria_2026-10-17.md, que trae cada hallazgo con archivo y línea.

Alcance: solo código y pruebas. No re-corras M1, M3 ni M4 completos (eso es la fase 1B).

1. Crea tests/ con pytest (agrégalo al .venv y a requirements.txt) y un conftest.py que ponga src/ en el path. Las pruebas usan datos sintéticos chicos, nunca data/.
2. Para cada hallazgo, en este orden: prueba que lo reproduce, muéstrame que falla, arreglo, muéstrame que pasa.
   - A2 antecedente. Un episodio no puede contar su propia lluvia como antecedente. Prueba: 10 mm dos días antes y un episodio de 7 + 3 mm; antecedente_24h debe dar 0 y antecedente_72h 10. Arreglo en detectar_episodios, cortando en el paso anterior al inicio.
   - A1 validación por fecha. En m5_validacion, una entrada solo puede acertar con episodios cuya ventana [inicio - 1 día, fin + 1 día] contenga su fecha (la misma holgura de m5_calibracion.HOLGURA_DIAS). Lo mismo para razon_max_caine, lluvia_max_mm y duracion_h. Saca esa lógica a una función pura y pruébala con un gatillo sintético de dos temporales, uno en julio y otro en agosto.
   - A3 comunas. Crea src/comun.py, liviano al importar, con cargar_comunas (la versión con copia local y chequeo de m5_validacion), sin_tildes, PROVINCIAS y PROVINCIA_DE. Haz que m3_exposicion, m5_validacion, m5_alerta_sector, m5_historico y m6 lo usen; M3 ya no lee la URL directo. Prueba: con un archivo local falso, cargar_comunas no hace ninguna llamada de red (monkeypatch de requests).
   - A4 cobertura en máquina limpia. El límite regional se obtiene en el primer paso (m1_preparar_dem) y verificar_cobertura aborta si falta el límite, salvo un flag explícito. Mueve obtener_limite a un lugar que ambos importen. Prueba: sin archivo de límite, verificar_cobertura termina con error.
   - A5 parámetros. Los valores canónicos (cauce 0,15 km2, área mínima 0,4 km2, valle 200 km2, área máxima 50 km2, razón 0,25) viven en src/config.py y todos los scripts los toman de ahí como default. Prueba: los defaults de argparse de m1_terreno, m1_subcuencas y m1_troncos coinciden con config.
   - A6 catálogo. descargar_catalogo guarda el catálogo junto al cache de la ventana (data/raw/lluvia/<ventana>/catalogo_<tipo>.json) y lo reutiliza salvo --refrescar. Prueba con requests simulado: la segunda llamada no toca la red.
3. Arreglos chicos que no cambian cifras: M5 (abortar si la duplicación de punteros no converge), M6 (unir solo los tiles del bbox), M7 (en la alerta en vivo, una estación que falla queda como "sin dato", el boletín sigue y dice cuántas fallaron) y de B5 la variable sin usar, el import sin usar, el x == x y el __import__("pandas").
4. Al final corre ruff y pytest y muéstrame el resumen.

Criterio de término: todas las pruebas pasan, cada hallazgo A1 a A6 tiene al menos una prueba que fallaba antes del arreglo, y el informe lista qué cifras del README van a cambiar cuando se re-corra.
```

## Prompt 1B. Re-correr y dejar las cifras verdaderas

```text
Fase 1B de alerta-aluviones: re-correr lo que cambió con los arreglos de la fase 1A y dejar el README con cifras verdaderas.

Lee docs/prompts_10_dias.md (Reglas comunes) y cúmplelas. Lee docs/auditoria_2026-10-17.md y docs/progreso.md.

1. Confirma con pytest que todo pasa antes de correr nada.
2. Re-corre en este orden y guarda cada salida en docs/corridas/ con su sección "Verificación" contra la corrida anterior equivalente: m4_lluvia.py (con cache; la primera vez guardará el catálogo, anota si R1 sigue en 107 estaciones), m4_deshielo.py, m5_validacion.py, m5_validacion.py --solo-fuertes, m5_calibracion.py, m5_alerta_sector.py, m5_niveles.py y m6_alerta_en_vivo.py --repasar.
3. Comprobaciones obligatorias:
   - En outputs/m4_episodios.csv, lluvia, duración e intensidades deben quedar idénticas a la corrida del 10-10 y solo cambiar las columnas antecedente_*. Si cambia otra cosa, detente y explícame por qué.
   - Si los coeficientes finales de m5_niveles cambian, NO toques B0 y B1 de m6; repórtalo.
   - m6 --repasar debe seguir dando 41 de 41.
   - m5_validacion: tabla de recall de julio y de agosto, antes y después del arreglo A1.
4. Re-corre m3_exposicion.py y verifica que puntos_corte.gpkg tiene el mismo número de puntos y las mismas comunas que la corrida del 11-10. Si es idéntico, dilo y no regeneres el visor.
5. Actualiza en README.md y docs/contexto.md solo las cifras que cambiaron, y agrega en la sección de M5 un párrafo "Corrección del <fecha>" que diga qué estaba mal (validación sin fecha, antecedente con su propio paso) y cuánto cambió, con el estilo del README.

Criterio de término: cada cifra que cambió tiene su corrida guardada, las secciones afectadas del README ya no tienen cifras viejas y las pruebas siguen pasando.
```

## Prompt 2. Un comando, pruebas y CI

```text
Fase 2 de alerta-aluviones: que el proyecto se reproduzca con un comando y que las pruebas corran solas en GitHub.

Lee docs/prompts_10_dias.md (Reglas comunes) y cúmplelas, y docs/auditoria_2026-10-17.md (B1 a B6).

1. Dependencias. Crea pyproject.toml (Python >= 3.12) y un archivo de versiones fijas que reproduzca el .venv actual (versiones en la auditoría, B1). Usa uv si ya está instalado; si no, requirements-lock.txt con pip freeze filtrado a lo que el proyecto usa. Declara explícito lo que el código importa directo y hoy llega de rebote: shapely, pyproj, pyogrio, tzdata, Pillow, affine.
2. Configuración única. Completa src/config.py con rutas, CRS, ventanas, umbrales y constantes repetidas, y reemplaza las copias (CRS_METRICO y similares). Ningún valor cambia.
3. Orquestador src/pipeline.py:
   - Lista de pasos en orden, de m1_preparar_dem a m6_visor, con entradas y salidas declaradas.
   - Comandos --listar, --en-seco (qué correría y por qué), --desde X --hasta Y y --solo X.
   - Antes de cada paso comprueba que existan sus entradas; después, que sus salidas existan y sean más nuevas que las entradas.
   - Después de cada paso imprime los conteos clave (unidades, susceptibles, puntos de corte, episodios, temporales, provincias-temporal) y los compara con docs/corridas/referencia.json, que creas con las cifras de las corridas vigentes. Una diferencia es un aviso destacado; un conteo cero aborta.
   - Guarda la salida completa en docs/corridas/ con fecha.
   Pruébalo con --en-seco y con --solo m5_validacion.
4. Pruebas: lleva tests/ a 30 o más, con datos sintéticos: Melton y clasificar, duplicación de punteros en una grilla de 6 x 6 hecha a mano, bocas_de_afluente, cobertura con un ráster de juguete, serie_precipitacion (huecos, recuperación, salto del contador), detectar_episodios, isoterma_cero, razon_critica y Caine fuera de rango, temporales de m5_alerta_sector, segunda estación y niveles de m5_niveles, probabilidad y nivel_de de m6. Marca con @pytest.mark.datos las que necesiten data/ y que se salten si no está.
5. Separa cálculo de impresión en m4_lluvia.main y m5_validacion.main, en funciones que devuelvan tablas. Regla dura: después del cambio, outputs/m4_episodios.csv y outputs/m5_validacion.csv salen idénticos byte a byte (compara hash). Si no, revierte.
6. Calidad: ruff configurado en pyproject (reglas E, F y B, sin exigir largo de línea) con cero avisos F y B; .pre-commit-config.yaml; y .github/workflows/pruebas.yml que en cada push instala con el archivo de versiones fijas en Ubuntu con Python 3.12 y corre ruff y pytest sin las pruebas marcadas datos.
7. Reemplaza los warnings.simplefilter("ignore") generales por filtros del aviso puntual que se quería callar.

Criterio de término: python src/pipeline.py --en-seco describe el pipeline completo, pytest pasa con 30 o más pruebas, ruff no marca F ni B, y las salidas de M4 y M5 son idénticas a las de la fase 1B.
```

## Prompt 3A. Alerta automática y visor público

```text
Fase 3A de alerta-aluviones: preparar la alerta en vivo para que corra sola en GitHub Actions y publicar el visor en GitHub Pages.

Lee docs/prompts_10_dias.md (Reglas comunes) y cúmplelas, docs/auditoria_2026-10-17.md (M7, M8, B7) y las cabeceras de src/m6_alerta_en_vivo.py y src/m6_visor.py.

Datos verificados, no los re-investigues: GitHub Actions es gratis en repositorios públicos con runners estándar; un cron puede retrasarse en horas punta y GitHub desactiva los programados tras 60 días sin actividad en el repo. No sabemos si VIPNET responde desde los servidores de GitHub: eso se prueba primero.

1. .github/workflows/prueba_vipnet.yml, solo manual (workflow_dispatch): un POST al catálogo de estaciones de VIPNET con el payload de m4_lluvia.descargar_catalogo y otro a la serie de una estación; imprime código HTTP, tiempo y cuántas estaciones llegaron. Sin dependencias pesadas.
2. Paquete de operación liviano: src/m6_paquete.py exporta a operacion/ (versionado en git) lo fijo que la alerta necesita y hoy sale de data/: estaciones con normal anual y provincia (CSV), los 10 primeros cruces por provincia con el filtro de m6 (CSV), las estaciones de nieve de referencia y los coeficientes congelados (JSON). Agrega a m6_alerta_en_vivo.py un modo --paquete operacion/ que no lea data/processed ni geoBoundaries. Verificación obligatoria: con --repasar, el modo paquete da 41 de 41, igual que el modo completo.
3. .github/workflows/alerta.yml: cron cada hora en el minuto 17, concurrency para que no se solape, instala solo lo necesario, corre la alerta en modo paquete, escribe visor/datos/vivo.json y outputs/boletines/, y hace commit solo si algo cambió. El almacén data/raw/vivo/ se conserva entre corridas con actions/cache.
4. Avisos por Telegram con los secrets TELEGRAM_TOKEN y TELEGRAM_CHAT_ID (los configuro yo): un mensaje cuando una provincia cambia de nivel respecto del vivo.json anterior y otro si el workflow falla. En el informe dame los pasos exactos para crear el bot con BotFather y obtener el chat id.
5. Visor público: deja de ignorar visor/datos en .gitignore (pesa 5,6 MB) salvo _local.html; copia deck.gl 8.9.35 a visor/vendor/ (o usa integrity SRI si no se puede copiar); haz que app.js cargue vivo.json como escenario "Boletín" si existe, con fecha y hora a la vista; y crea .github/workflows/pages.yml que publique visor/ en GitHub Pages en cada push a main. Agrega en el visor un aviso fijo: herramienta académica, no es una alerta oficial, con enlace a senapred.cl.
6. Documentación: README.md nuevo y corto en inglés (qué es, resultado principal con números verificados, cómo correrlo, límites, enlace al visor y a la documentación en español). El README actual pasa completo a docs/bitacora.md sin perder nada; docs/contexto.md queda igual. Agrega MODEL_CARD.md en inglés (datos, variable, calibración, métricas con su incertidumbre, usos fuera de alcance).
7. No hagas push. Termina con la lista exacta de lo que debo hacer yo en GitHub: hacer público el repo, activar Pages con fuente "GitHub Actions", cargar los secrets y correr prueba_vipnet a mano.

Criterio de término: los tres workflows existen y pasan un chequeo de sintaxis (actionlint si está disponible), el modo paquete reproduce 41 de 41, el visor funciona en local con un vivo.json y el README en inglés existe.
```

## Prompt 3B. Ajustar según la prueba en GitHub

```text
Fase 3B de alerta-aluviones: ajustar la operación según lo que pasó en GitHub.

Lee docs/prompts_10_dias.md (Reglas comunes) y cúmplelas, y docs/progreso.md.

Resultado de prueba_vipnet: [PEGA AQUÍ EL LOG O EL ERROR]
Lo que veo en la pestaña Actions: [PEGA AQUÍ]

- Si VIPNET respondió: revisa la primera corrida real de alerta.yml con el log que te pego, corrige lo que falló y confirma que vivo.json y el visor publicado muestran la hora de Chile (America/Santiago).
- Si no respondió: deja listo el plan B, una tarea programada de Windows que cada hora corre la alerta en modo paquete en mi notebook y sube solo visor/datos/vivo.json y outputs/boletines/. Escribe el script .ps1 (con log de cada corrida y aviso por Telegram si falla) y el comando schtasks para registrarlo; yo lo registro. Deja alerta.yml solo manual, con una nota de por qué.
- En los dos casos: escribe docs/operacion.md con cómo revisar que la alerta está viva, qué hacer si falla y cómo pausarla.
```

## Prompt 4A. Cincuenta años de historia

```text
Fase 4A de alerta-aluviones: probar los niveles contra la historia 1970-2021 (src/m5_historico.py) y validar la interpolación con bloques espaciales.

Lee docs/prompts_10_dias.md (Reglas comunes) y cúmplelas, la cabecera completa de src/m5_historico.py y docs/auditoria_2026-10-17.md (M1, M3, B8).

1. La regla de decisión ya está escrita en la cabecera de m5_historico.py: si el modelo histórico ordena VIPNET 2024-2026 con AUC >= 0,90, se recalibra con historia más VIPNET. No la cambies, ni ninguna regla de etiquetado, después de ver resultados. Si encuentras un error de código, arréglalo con prueba primero y dime si el arreglo puede mover el resultado.
2. Antes de correr: en el modelo con antecedente, el resultado de cal.logistica se usa aunque no converja. Que reporte "no converge" en vez de usar coeficientes inválidos.
3. Corre m5_historico.py (los datos diarios de CR2MET ya están en data/raw/cr2met/diario/) y guarda la corrida con su verificación: registros de DesInventar que entran, temporales, positivos por periodo, AUC y Brier.
4. Aplica la regla tal como está escrita. Si dice recalibrar, NO cambies B0 y B1 de m6. Escribe docs/propuesta_recalibracion.md con los coeficientes nuevos, los cortes, cómo cambiaría cada temporal de 2024-2026 y el repaso de m6 con esos coeficientes (pasándolos como argumento, sin tocar el congelado). Adoptarlo lo decido yo en la fase 5.
5. Interpolación (M1): agrega a m4_interpolacion una validación por bloques espaciales (las estaciones a menos de 10 km entre sí salen juntas) y repórtala al lado de la actual. La regla de adopción no cambia; si el random forest pierde contra la estación cercana con bloques, avísame y no cambies nada sin mi ok.
6. Escribe los resultados en docs/bitacora.md (o en el README si la fase 3 no movió la bitácora), incluido lo que no funcionó.
```

## Prompt 4B. Pronóstico con Open-Meteo

```text
Fase 4B de alerta-aluviones: medir cuántas horas antes habría avisado la alerta si sumara el pronóstico de lluvia.

Lee docs/prompts_10_dias.md (Reglas comunes) y cúmplelas, y src/m6_alerta_en_vivo.py.

Datos verificados: Open-Meteo es gratis para uso no comercial, sin clave, hasta 10.000 llamadas al día, con atribución CC BY 4.0. Su Previous Runs API (https://previous-runs-api.open-meteo.com/v1/forecast) entrega para cada hora el valor que se pronosticó 1 a 7 días antes (sufijo _previous_dayN), con la mayoría de los modelos archivados desde enero de 2024. Antes de escribir código, verifica en su documentación los nombres exactos de los parámetros y qué modelos traen precipitación para Chile.

1. ANTES de bajar ningún dato, escribe docs/preregistro_pronostico.md con la regla de adopción. Propuesta: se adopta como "nivel esperado" solo si en los temporales regionales 2024-2026 adelanta la primera hora de naranja o roja en al menos 12 horas en la mediana, sin agregar ninguna provincia-temporal en falsa alarma respecto de los niveles actuales. Muéstramela y espera mi ok.
2. src/m4_pronostico.py: baja con cache en data/raw/pronostico/ la precipitación horaria pronosticada con 1, 2 y 3 días de anticipación en cada estación de VIPNET de Coquimbo, para las ventanas de outputs/m5_temporales.csv con 3 días de margen previo. Respeta el límite de llamadas, agrupa coordenadas por llamada si la API lo permite y anota el modelo usado.
3. Sesgo: compara lo pronosticado con lo observado por VIPNET en esos temporales, por provincia, y repórtalo. Si corriges, que sea un factor por provincia estimado dejando fuera el temporal evaluado.
4. Backtest: para cada temporal regional y provincia, hora a hora, calcula el nivel con "lluvia caída + lluvia pronosticada para las próximas 24 y 48 h" usando los MISMOS coeficientes congelados, y compáralo con la cronología actual de m6 (--cronologia). Tabla: primera hora de cada nivel con y sin pronóstico, y falsas alarmas nuevas.
5. Aplica la regla del preregistro tal como quedó, guarda la corrida y escribe el resultado en la bitácora, se adopte o no. Si se adopta, NO lo conectes a la alerta en vivo: déjalo detrás de un flag --con-pronostico, documentado; conectarlo se decide en la fase 5.
```

## Prompt 5. Dejar listo para congelar v1.0

```text
Fase 5 de alerta-aluviones: dejar el proyecto listo para congelar la v1.0 y preregistrar la validación del invierno de 2027.

Lee docs/prompts_10_dias.md (Reglas comunes) y cúmplelas, docs/auditoria_2026-10-17.md, docs/progreso.md y los resultados de las fases 4A y 4B en la bitácora.

1. Prepárame una tabla de decisiones pendientes con la evidencia de cada opción: modelo de niveles actual o recalibrado con historia, pronóstico sí o no, troncos sí o no en la lista de cortes. Espera mi decisión antes de tocar coeficientes.
2. Con mis decisiones: actualiza las constantes congeladas de m6 solo si corresponde, corre la verificación completa (pipeline --en-seco, pytest, m6 --repasar) y guarda la corrida de cierre.
3. Archivos de publicación: CITATION.cff y .zenodo.json (autora Camila Alejandra Hernández Cona, palabras clave en inglés y español), LICENSE (pregúntame; sugiere MIT para el código y CC BY 4.0 para los datos derivados, revisando las licencias de origen: OSM ODbL, Copernicus, CR2MET, VIPNET) y docs/fuentes_y_licencias.md.
4. Borrador docs/preregistro_2027.md, en inglés y en español: hipótesis, modelo congelado (coeficientes y commit), variables, unidades de evaluación (provincia-temporal y cortes de ruta), cómo se arma el inventario 2027 (mismo formato y criterio), métricas (AUC, Brier, recall y precisión con su línea base, cortes cubiertos por el 3% superior de la lista contra el azar), criterios de éxito fijados de antemano y qué se reporta si falla. Es el documento que voy a subir a OSF.
5. Revisión independiente: lanza un subagente que no haya visto el trabajo de esta sesión, de solo lectura, para que busque cifras del README, la bitácora y el preregistro que no salgan de una corrida guardada, y errores silenciosos en el código nuevo de las fases 1 a 4. Corrige lo que encuentre o explícame por qué no.
6. Termina con los pasos manuales: tag v1.0, release en GitHub, conectar Zenodo, subir el preregistro a OSF, y la fecha límite (1 de mayo de 2027).
```

## Prompt de retomar (si la sesión se corta)

```text
Retoma alerta-aluviones. Lee docs/prompts_10_dias.md (Reglas comunes) y cúmplelas, y después docs/progreso.md. Dime en 5 líneas en qué fase vamos, qué quedó hecho y cuál es el próximo paso, y espera mi ok para seguir con el prompt de esa fase.
```
