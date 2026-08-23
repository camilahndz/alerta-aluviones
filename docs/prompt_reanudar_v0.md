# Prompt para Claude Code — cerrar M3 (v0) en alerta-aluviones

> Pegar completo como primer mensaje en Claude Code, abierto en
> `D:\Camila\Escritorio\alerta-aluviones`.

---

Trabajas en `alerta-aluviones`, un modelo de riesgo de activación de quebradas
para la Región de Coquimbo. Antes de escribir una sola línea, lee en este orden:
`README.md`, `docs/contexto.md` y `docs/recorrido/Recorrido_alerta_aluviones.md`
(sobre todo los capítulos 08, 10 y 12). El proyecto está muy documentado a
propósito: cada decisión tiene su porqué escrito en el docstring del script. Esa
convención se mantiene.

## Estado verificado hoy (23 de agosto de 2026)

Esto ya está comprobado leyendo los archivos en disco. No lo re-diagnostiques,
solo confírmalo en el paso 0.

- Último commit: `Reescribir readme`, 7 de agosto de 2026. 19 commits en total.
- Los 12 tiles Copernicus están completos en `data/raw/copernicus_dem30/`
  (filas S30–S33 × columnas W070–W072), y `data/processed/dem_utm19s.tif`
  se regeneró el 7 de agosto a las 15:50.
- **Pero `cuencas.gpkg`, `cuencas_coquimbo.gpkg`, `red_quebradas*.gpkg`,
  `susceptibilidad.gpkg` y los tres PNG de `outputs/` se escribieron a las
  14:23–14:24 del mismo día, o sea ANTES del DEM nuevo.** Todo lo vectorial
  que hay en disco salió del DEM truncado.
- Prueba directa: `cuencas_coquimbo.gpkg` se extiende de lat −31,00 a −29,04.
  A la región le falta el tercio sur (llega hasta −32,22).
- Cifras actuales en disco contra las del README:

  | | README (corrida completa, remota) | Disco hoy (DEM truncado) |
  |---|---|---|
  | Cuencas en la región | 434 | 360 |
  | Superficie drenada | 39.487 km² | 16.187 km² |
  | Clase `flujo_detritos` (Wilford) | 18 | 38 |
  | Melton máximo | 1,05 | 1,504 |
  | Pendiente media máxima | 24° | 37,6° |

- `cuencas_coquimbo.gpkg` **no tiene la columna `toca_borde`**, así que la
  corrida en disco es anterior a esa salvaguarda y no excluyó ninguna cuenca de
  borde. Eso explica el Melton inflado: con área truncada, H/√A sube. Es
  exactamente el artefacto que el capítulo 12 anticipa, ahora medido.
- `clase_melton` sí existe en `susceptibilidad.gpkg` (176 inundación /
  132 crecida / 52 flujo), pero sobre el territorio parcial. El desglose sobre
  la región completa sigue pendiente.
- M3 nunca corrió: no existen `puntos_corte.gpkg`, `trayectorias.gpkg`,
  `outputs/m3_puntos_corte.csv` ni `outputs/m3_exposicion.png`.

## Objetivo de esta sesión

**Cerrar M3**, que es lo que cierra la v0 del proyecto. Para poder correrlo hay
que reparar antes M1 y M2, cuyas capas en disco no sirven.

| Paso | Hito |
|---|---|
| 0–1 | Reparar M1 y M2 |
| 2–3 | Transversal (verificación y documentación) |
| 4 | M3, primera corrida real |

M4 (gatillo de lluvia), M5 (validación) y M6 (entrega) quedan fuera de esta
sesión.

## Paso 0 — Verificar antes de tocar nada

Sin modificar archivos, imprime:

1. `rasterio` sobre `data/processed/dem_utm19s.tif`: shape, CRS, bounds en UTM
   y reproyectados a EPSG:4326, y el tamaño en píxeles.
2. Confirma que el bbox del DEM contenga entero el polígono de
   `data/raw/limite_coquimbo.gpkg` (fracción cubierta ≥ 0,99).
3. Una estimación de RAM: `filas × columnas × 8 bytes`, multiplicada por 5 para
   los arreglos vivos de `pysheds`.

**Esto último es el riesgo real de la sesión.** El notebook tiene 12 GB de RAM y
las corridas completas anteriores del README se hicieron en un servidor remoto.
Si la estimación pasa de ~6 GB, para y dime antes de lanzar `m1_terreno.py`:
las opciones son correrlo en el servidor de la UCN o procesar por mitades, y esa
decisión es mía, no tuya.

Si el DEM resulta incompleto, detente ahí y avísame: primero hay que re-generarlo
con `python src/m1_preparar_dem.py`.

## Paso 1 — Re-correr M1 y M2 en local

```bash
python src/m1_terreno.py --umbral-km2 0.15 --area-min-km2 0.4
python src/m1_recortar_region.py
python src/m2_susceptibilidad.py
```

Guarda la salida completa de consola de cada uno en
`docs/corridas/2026-08-23_m1_m2.txt`. Esa es la corrida de referencia: si mañana
alguien pide reproducir un número del README, se apunta ahí.

Después de correr, revisa y repórtame:

- Cuántas cuencas quedaron con `toca_borde = True` y cuántas M2 marcó como
  `borde_truncado`. Si son más de un puñado, el margen del bbox al norte
  (0,07° ≈ 8 km) se está quedando corto y hay que decirlo.
- Las áreas de Choapa, Elqui y Limarí contra las oficiales de la DGA
  (~7.650 / ~9.657 / ~11.800 km²), igual que la tabla del capítulo 10.
- El desglose de `clase` y `clase_melton` sobre la región completa, y cuántas
  cuencas discrepan entre ambos criterios. Ese conteo es el pendiente explícito
  que el capítulo 12 deja abierto.

Abre los tres PNG de `outputs/` y describe qué se ve: si las quebradas no caen
en el fondo de los valles, o si los bordes de cuenca cruzan por la mitad de una
ladera, algo se rompió y no seguimos a M3.

## Paso 2 — Tapar el agujero de cobertura

El capítulo 12 pregunta por qué `verificar_cobertura` no detuvo la corrida
parcial. Averígualo con el código a la vista y arréglalo.

Pista de por dónde empezar, no conclusión: `verificar_cobertura` solo existe en
`m1_preparar_dem.py` (y una copia en `m3_exposicion.py`). `m1_terreno.py`,
`m1_recortar_region.py` y `m2_susceptibilidad.py` leen `dem_utm19s.tif` sin
comprobar nada. Un DEM parcial que ya está en `data/processed/` entra a esos tres
scripts sin que nadie se queje.

Extrae la función a un módulo compartido (`src/cobertura.py` o similar) y llámala
al inicio de los tres scripts que hoy no la tienen, abortando bajo el mínimo.
Documenta en el docstring **por qué** existe, con el caso real de agosto de 2026
como motivo. No dupliques la función en cuatro archivos.

## Paso 3 — Sincronizar la documentación

Con las cifras nuevas a la vista, actualiza:

- `README.md`: secciones "Resultado de M1" y "Resultado de M2", y la tabla DGA.
- `docs/contexto.md`: la tabla de estado por hito.
- `docs/recorrido/Recorrido_alerta_aluviones.md`: el capítulo 12 completo y la
  advertencia de la portada. Si las cifras ya son reproducibles, el capítulo 12
  deja de ser una advertencia y pasa a ser el registro de un problema resuelto:
  reescríbelo así, conservando la historia de cómo se detectó. No borres el
  episodio, es de las mejores piezas del documento.

Regla: si una cifra no salió de la corrida guardada en `docs/corridas/`, no entra.
Nada de arrastrar números del README viejo.

## Paso 4 — Correr M3 completo

```bash
python src/m3_exposicion.py
```

Sin `--permitir-cobertura-parcial`. Si aborta por cobertura, algo del paso 1
quedó mal y hay que volver, no forzar la bandera.

Repórtame: cuántos puntos de corte salieron, el desglose por jerarquía de vía,
las 12 vías más afectadas y las localidades alcanzadas. Abre
`outputs/m3_exposicion.png` y dime si el mapa tiene sentido: los cortes deberían
caer donde una ruta cruza el fondo de una quebrada, no dispersos por laderas.

Si salen más de 2.000 puntos, o menos de 10, no es un hallazgo, es un síntoma:
para y diagnostica antes de escribir nada en la documentación.

## Git: no tocar

**No hagas `git add`, ni `git commit`, ni `git push`, ni `git checkout`, ni
`git stash`, ni nada que mueva el historial o el índice.** Los commits los hago
yo. `git status`, `git log` y `git diff` los puedes usar para mirar.

Al terminar cada paso, dime qué archivos quedaron modificados y propóneme el
mensaje de commit que usarías, en español y en el estilo del repo. Yo decido si
lo uso.

`data/processed/` y `outputs/` no van a git; eso ya está en `.gitignore` y no se
toca. Los `.txt` de `docs/corridas/` sí deberían ir, avísame para incluirlos.

## Qué no hacer

- No cambies `MELTON_CRECIDA`, `MELTON_FLUJO`, `LARGO_MAX_FLUJO_KM`, ni los pesos
  de M3. Recalibrar es trabajo de M5, con el evento de julio de 2026 en la mano.
- No empieces M4 ni M5. Esta sesión cierra v0 y nada más.
- No agregues dependencias nuevas sin decírmelo primero.
- No inventes un parámetro de alcance de runout. El proyecto se negó a hacerlo a
  propósito y esa negativa está documentada.
- No commitees ni hagas push. Ver la sección anterior.
- Si un número no cuadra, dilo. No lo suavices ni lo justifiques sin comprobarlo.

## Cómo quiero el reporte final

Cinco líneas por paso, con los números medidos, y una lista de lo que quedó
abierto. Si algo falló, primero eso.
