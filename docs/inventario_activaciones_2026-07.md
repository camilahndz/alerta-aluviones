# Inventario de activaciones, temporal de julio de 2026

Este documento acompaña a
[`inventario_activaciones_2026-07.csv`](inventario_activaciones_2026-07.csv) y
explica de dónde sale, qué se puede y qué no se puede hacer con él.

Es la verdad de terreno contra la que M5 va a medir el modelo. Sin esto no hay
matriz de confusión, no hay precisión ni recall, y M4 se queda en una tabla de
episodios sin veredicto.

---

## Por qué está en `docs/` y no en `data/raw/`

Porque `data/raw/` no va a git, y este archivo **no se puede regenerar corriendo
código**. El DEM se vuelve a bajar, el extracto de OSM se vuelve a bajar, las
series de VIPNET se vuelven a pedir. Esto no: son horas de leer prensa y
comunicados, y si se pierde hay que rehacerlo a mano.

La regla del repositorio dice que `data/raw/` son datos originales intocables que
no se suben. La regla detrás de la regla es que lo que se sube es lo que no se
puede reconstruir. En septiembre de 2026 ese matiz costó el código de M4 entero.

---

## Cómo se armó

Barrido de prensa regional y comunicados de SENAPRED y Carabineros entre el 17 y
el 31 de julio de 2026. Cada fila lleva su URL. Criterio de entrada: que una
fuente nombre una quebrada o un sector concreto, con fecha.

**No hay informe oficial consolidado.** Se buscó un balance final de SENAPRED o
SERNAGEOMIN con las activaciones georreferenciadas y no existe en abierto. Lo que
hay son notas del día. Esa es la limitación de fondo de este inventario y
conviene tenerla a la vista antes de leer cualquier métrica que salga de él.

## Qué significa cada columna de evidencia

| Valor | Qué dijo la fuente |
|---|---|
| `aluvion` | la fuente usa la palabra aluvión |
| `activacion` | la fuente dice que la quebrada se activó |
| `activacion_menor` | "bajada moderada de agua", "flujo bajo", "flujo menor" |
| `escurrimiento` | "escurrimiento superficial": agua corriendo, no flujo de detritos |
| `alerta_preventiva` | la autoridad advierte **riesgo** de activación, no activación ocurrida |

**Esa gradación no es cosmética y define el resultado de M5.** Si se cuenta como
positivo todo lo que la prensa menciona, el inventario tiene 18 entradas. Si se
cuenta solo lo que es defendiblemente un flujo de detritos —`aluvion` y
`activacion`— quedan 8. La métrica cambia por más del doble según dónde se ponga
la línea, y la línea es un juicio, no un dato.

M5 tiene que reportar las dos, igual que M2 reporta sus dos clasificaciones y M4
sus dos umbrales.

## Tres problemas que el inventario no resuelve

**La prensa no es un inventario geotécnico.** Un medio reporta donde hay gente y
cámaras. Una quebrada que bajó con fuerza en un cerro sin camino no sale en
ninguna parte, y en esta tabla figura como no activada. Eso sesga los falsos
positivos del modelo hacia arriba: el modelo puede estar acertando donde nadie
miró.

**"Evitar" no es "evacuar".** Las fuentes del 31 de julio se contradicen entre
sí: unas dicen que SENAPRED pidió evitar un sector y otras que ordenó evacuarlo.
La columna `accion_autoridad` registra lo que dijo la fuente citada, sin intentar
resolver la contradicción.

**Dos fuentes asignan comunas distintas.** Carabineros ubica Santa Gracia y Los
Loros en Vicuña; SENAPRED ubica Santa Gracia en La Serena. Lo mismo con Cutum y
Cajón del Romero, que Carabineros lista bajo Coquimbo y SENAPRED bajo La Serena.
Queda anotado en la columna `nota` de cada fila. Resolverlo requiere coordenadas,
no más lectura.

---

## El hallazgo que condiciona M5

**Casi la mitad de las activaciones documentadas ocurrió en territorio que el
modelo no puede evaluar.**

Las 167 cuencas susceptibles de M2 se reparten en siete comunas, medidas por los
puntos de corte de M3:

| Comuna | Puntos de corte |
|---|---|
| Coquimbo | 117 |
| La Higuera | 94 |
| La Serena | 79 |
| Ovalle | 49 |
| Canela | 42 |
| Los Vilos | 40 |
| Salamanca | 1 |

Ahora, las comunas donde el inventario registra activaciones:

| Comuna | Entradas del inventario | ¿La cubre el modelo? |
|---|---|---|
| Coquimbo | 4 | sí |
| La Serena | 5 | sí |
| Vicuña | 3 | **no** |
| Paihuano | 2 | **no** |
| Los Vilos | 1 | sí |
| Illapel | 1 | **no** |
| Punitaqui | 1 | **no** |
| Salamanca | 1 | apenas: 1 punto de corte |

**Vicuña, Paihuano, Illapel y Punitaqui no aparecen.** No porque el modelo diga
que ahí no hay peligro, sino porque **ahí no tiene cuencas que evaluar**.

La causa está documentada desde antes y ahora queda medida contra eventos
reales. M1 delinea cuencas cortando donde el terreno termina, o sea en la costa.
Las quebradas del valle del Elqui —Marquesa, Las Cañas, Tres Cruces, Los Loros,
San Carlos— desembocan en el río Elqui, no en el mar, así que quedan absorbidas
dentro de la cuenca del Elqui y nunca se evalúan por separado. Lo mismo pasa con
Cárcamo y Batuco dentro del Choapa, y con Punitaqui dentro del Limarí.

Cuatro cuencas concentran el 83% de la superficie drenada y las cuatro son de
clase `inundacion`, así que M2 las descarta enteras y con ellas todas las
quebradas que contienen.

### Qué hacer con eso

Son dos caminos y la decisión es de método, no de código:

**Restringir el alcance.** Declarar que el modelo cubre las quebradas costeras de
Coquimbo y evaluar M5 solo sobre las 10 entradas de comunas cubiertas. Es
honesto, es inmediato, y reduce la pregunta a una que el modelo sí puede
responder.

**Arreglar la unidad de análisis.** Cambiar M1 para que delinee subcuencas en los
afluentes de los ríos grandes, no solo en la costa. Es la solución de fondo,
vuelve evaluables las 18 entradas, y es bastante más que un ajuste de parámetro:
hay que repensar dónde se cortan las cuencas.

Lo que **no** se puede hacer es correr M5 sobre las 18 entradas sin decir nada.
Ocho de ellas están en territorio donde el modelo nunca dijo nada, y contarlas
como falsos negativos sería medir algo que el modelo no intentó.

---

## Pendiente antes de usarlo

El inventario tiene nombres, no coordenadas. Para la matriz de confusión hay que
amarrar cada fila a un `id_cuenca` de `cuencas_coquimbo.gpkg`, y eso requiere
geolocalizar cada quebrada. Dos sin resolver:

* La entrada 9, el aluvión de El Islón del 20 de julio, es el único evento que
  una fuente llama aluvión y no tiene quebrada identificada. Vale la pena
  averiguar cuál lo generó: es el caso más claro de todo el inventario.
* Varias quebradas comparten nombre con otras del país. "Los Loros" aparece dos
  veces en el mismo reporte de Carabineros, bajo dos comunas distintas.
