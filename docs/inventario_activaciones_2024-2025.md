# Inventario de activaciones, inviernos de 2024 y 2025

Este documento acompaña a
[`inventario_activaciones_2024-2025.csv`](inventario_activaciones_2024-2025.csv).
Tiene el mismo formato y el mismo criterio que el de julio de 2026
([`inventario_activaciones_2026-07.md`](inventario_activaciones_2026-07.md)), y
existe para una sola cosa: darle a M5 episodios **sin** activación reportada con
que calibrar.

Con el temporal de 2026 solo, todas las observaciones son positivas. Se puede
medir recall y nada más, y cualquier curva ajustada sobre esas mismas
observaciones queda ajustada contra su propia validación. 2024 y 2025 tuvieron
lluvia real y activaciones mayormente menores. Con ellos se entrena y con 2026
se prueba.

---

## Cómo se armó

Barrido de prensa regional (El Día, Mi Radio, Madero, La Serena Online, Emol,
Meganoticias, Cooperativa) y de balances de SENAPRED citados por la prensa, en
octubre de 2026. Cada fila lleva su URL. **Sin fuente no entra.**

Se buscó en particular, mes por mes, en los períodos con lluvia en VIPNET: junio
y agosto de 2024, mayo, junio, julio-agosto y fines de agosto de 2025, y los
veranos (por si hubo lluvia convectiva en la cordillera). Lo que se encontró
cae en cuatro eventos:

| Evento | Lluvia | Qué reporta la prensa | Filas |
|---|---|---|---|
| 13 de junio de 2024 | Salamanca 106 mm, Illapel 73 mm (INIA, al 14-06) | Activaciones en Punitaqui, Los Vilos, Río Hurtado, Combarbalá, Andacollo, Monte Patria | 101-109 |
| 1 de agosto de 2024 | Punitaqui 90 mm, Los Vilos 70 mm | "Se activaron 41 quebradas", sin nombres | 110 |
| 16 de junio de 2025 | concentrada en Choapa | 14 quebradas en Canela y una lista "de bajo caudal" | 111-135 |
| 31 de julio al 1 de agosto de 2025 | Pichidangui 130,2 mm, El Peral 125,6, Camarico 121,3, Punitaqui 119,2, Coquimbo 101,4 mm en menos de un día | Los Rincones cortó la Ruta 427; "bastantes quebradas activadas" en la región | 136-144 |

**El sistema frontal del 21 y 22 de agosto de 2025 no tiene ninguna fila, y eso
es información.** Dejó más de 40 mm en sectores del Choapa (Quilimarí 41,6 mm,
Tilama 34,5) y la nota que lo registra
([El Día, 22-08-2025](https://www.diarioeldia.cl/noticias/2025/08/22/128169-los-registros-de-lluvia-y-nieve-que-dejo-el-paso-del-sistema-frontal-en-la-region-de-coquimbo))
no reporta ninguna activación. Es el tipo de evento que el proyecto no tenía:
llovió y no se reportó nada.

**En mayo de 2025 y en los veranos no se encontró nada.** Mayo de 2025 solo
tiene pronósticos de menos de 10 mm.

---

## Lo que es distinto respecto del inventario de 2026

### Las filas sin nombre

Once filas no tienen quebrada ni sector. Son fuentes que dicen "se activaron
41 quebradas", "se activó la totalidad de las quebradas" de Combarbalá, o
"bastantes quebradas activadas" en la región, sin nombrar cuáles.

No se pueden ubicar y no entran como positivos. **Pero tampoco se pueden
ignorar**, porque son exactamente lo que destruye un negativo: si el 1 de
agosto de 2025 se activaron muchas quebradas sin nombre, un episodio de ese día
en el que el inventario no tiene nada con nombre **no** es un episodio donde no
pasó nada.

Por eso `m5_calibracion.py` las usa al revés: una fila sin nombre **excluye**
de los negativos todo episodio de su comuna en su fecha, y si no trae comuna,
de toda la región. Dos filas son regionales, la 110 y la 141, así que los dos
eventos grandes, el de agosto de 2024 y el del 1 de agosto de 2025, aportan
positivos con nombre pero ningún negativo.

La columna `sector` de esas filas queda vacía **a propósito**. La 109 habla de
"complicaciones por la quebrada" en Cárcamo, Monte Patria; escribir "Cárcamo" en
`sector` haría que M5 la ubicara en la Quebrada Cárcamo de Illapel.

### Antes de que exista la lluvia

VIPNET tiene dato útil desde el 30 de junio de 2024. Las filas del 13 de junio
de 2024 (101 a 109) caen antes de eso: están en el inventario porque son
activaciones documentadas, pero no hay episodio de lluvia con qué cruzarlas y
no entran a la calibración.

### Fuente que no se pudo leer entera

Las filas 138 a 141 vienen de un post de la Red Geocientífica de Chile en X.
La página pide sesión y no se puede leer directamente; el texto sale del
extracto del buscador y la fecha del número del post (`1951346856056762816`,
1 de agosto de 2025, 18:18 UTC). Van con confianza `baja`.

### La gradación

Se usa la misma escala del inventario de 2026. Tres juicios que conviene
dejar escritos:

* Las 14 de Canela del 16 de junio de 2025 son `activacion_menor` y no
  `activacion`. El balance de SENAPRED dice "activación" sin más, pero la nota
  de Madero del día siguiente agrega "sin provocar situaciones de emergencia ni
  daños a viviendas", y otra nota dice que "se activaron producto del
  escurrimiento de agua". Se eligió la lectura más conservadora.
* Las 125 a 133 vienen de una lista "todas con bajo caudal" sin comuna. Por los
  nombres (Chepiquilla, Maitencillo, El Curque) parecen de Andacollo, pero la
  fuente no lo dice y la comuna no se completó.
* Los Rincones (137) es `activacion` aunque la fuente dice "crecida": el agua
  sobrepasó la calzada, cortó por completo la Ruta 427 y hubo un rescate. Es el
  mismo criterio que puso a Cajón del Romero (2026) en `activacion` por
  "ruta completamente cortada".

---

## Qué NO es este inventario

Un registro de negativos. Ningún documento dice "en tal quebrada no pasó nada".
Lo que hay son eventos con cobertura de prensa donde el reporte nombró algunas
quebradas, y el supuesto de que las demás no hicieron nada que alguien viera.

Ese supuesto es razonable en 2025 —los balances de SENAPRED de junio y agosto
nombran quebradas de Canela, Andacollo y Los Vilos, así que el sistema que
reporta estaba funcionando— pero sigue siendo un supuesto. Por eso
`m5_calibracion.py` llama a sus negativos **presuntos** y reporta la precisión
como **cota inferior**.

## Pendiente

* Hay una nota de El Observatodo que menciona "varias quebradas activadas en
  Andacollo, con caudal mínimo" bajo una alerta vigente "hasta el viernes 22 de
  agosto". El 22 de agosto fue viernes en 2025, lo que la pondría en el frontal
  del 21-22, pero la página devuelve 403 y no se pudo confirmar el año. **No
  entró.** Si se confirma, el frontal del 21-22 de agosto deja de ser un evento
  sin activaciones en Andacollo.
* Las fuentes de agosto de 2024 dicen 41 quebradas y no nombran ninguna. Un
  balance de SENAPRED con la lista convertiría ese evento en el más informativo
  de los dos inviernos.
