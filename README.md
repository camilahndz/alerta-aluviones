# alerta-aluviones

Modelo de riesgo de activación de quebradas para la Región de Coquimbo, Chile.
Predice qué quebradas se activan ante una lluvia dada y qué rutas y zonas urbanas
quedan expuestas. Se valida contra el temporal de julio de 2026, el peor en unos
cuarenta años.

---

## Qué hace

1. **Susceptibilidad**: mapea qué quebradas son propensas a generar flujos de
   detritos, con la razón de Melton calculada sobre el modelo de elevación
   (desnivel, área, pendiente y largo). La geología está en el plan y todavía no
   entra.
2. **Gatillo**: arma la serie de lluvia de 30 minutos de cada quebrada y le
   aplica umbrales intensidad-duración publicados. No calibra uno propio:
   con tres bloques de activaciones documentadas no hay con qué, y ajustar una
   curva sobre tres puntos sería dibujar. Calibrar es trabajo de M5.
3. **Exposición**: cruza las trayectorias de flujo con la red vial y las zonas
   pobladas para identificar cortes de ruta y población en riesgo.
4. **Validación**: compara la predicción contra lo que ocurrió en julio de 2026.

---

## Estructura del repositorio

```
alerta-aluviones/
├── README.md
├── .gitignore
├── requirements.txt
├── data/
│   ├── raw/          # datos originales, NO se modifican ni se suben a git
│   └── processed/    # datos derivados (generados por el código)
├── docs/             # documentación técnica
├── notebooks/        # exploración y pruebas
├── src/              # código ordenado y reutilizable
└── outputs/          # mapas y resultados finales
```

Regla: si se borra todo `data/processed/` y `outputs/`, se debe poder
reconstruirlo corriendo el código sobre `data/raw/`. Los datos pesados no van a
git (ver `.gitignore`).

---

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`rasterio` y `geopandas` dependen de GDAL/PROJ. Si pip falla en Windows, conviene
instalar esas dos con conda o mamba y el resto con pip.

---

## Cómo se corre M1

Cuatro scripts, en este orden:

```bash
python src/m1_preparar_dem.py                                   # baja el DEM, lo une y lo pasa a UTM 19S
python src/m1_terreno.py --umbral-km2 0.15 --area-min-km2 0.4   # rellena, calcula flujo, delinea cuencas
python src/m1_recortar_region.py                                # deja solo las que descargan en Coquimbo
python src/m1_subcuencas.py                                     # agrega las subcuencas de confluencia
python src/m1_troncos.py                                        # agrega los troncos de mas de 50 km2
```

El quinto, `m1_troncos.py`, se agregó en octubre de 2026 y está explicado en M5,
[Unidades troncales](#unidades-troncales-el-objeto-correcto-y-lo-que-eso-dejó-a-la-vista).
Las cifras de M1 a M3 de esta sección son de antes de los troncos.

El tercero baja el límite regional de geoBoundaries por su cuenta la primera vez
y lo deja en `data/raw/limite_coquimbo.gpkg`, así que ese archivo no hay que
conseguirlo a mano. Es el polígono contra el que `src/cobertura.py` comprueba que
el DEM cubra la región antes de calcular nada.

Los dos parámetros que vale la pena mover están en `m1_terreno.py`. `--umbral-km2`
fija el área drenada mínima para considerar que hay cauce: bajarlo densifica la
red hacia las quebradas chicas. `--area-min-km2` fija bajo qué tamaño se descarta
una cuenca.

Sobre esos valores. La primera pasada usó `--area-min-km2 2.0` y en M2 no
apareció ninguna cuenca capaz de generar flujos de detritos en toda la región, lo
que no tiene sentido para Coquimbo. El filtro estaba botando justamente las
quebradas chicas y empinadas, que son las que producen aluviones. Con 0,4 km²
aparecen 21 cuencas capaces, y la mayor parte del inventario queda dentro del
rango de tamaño donde el índice de Melton está calibrado.

La hidrología se corre sobre un área mayor que la región. Hay quebradas cuyas
cabeceras nacen fuera del límite administrativo, y cortarlas daría áreas falsas.
`m1_recortar_region.py` filtra al final y conserva las cuencas completas cuya
desembocadura cae dentro de Coquimbo.

El cuarto script, `m1_subcuencas.py`, agrega las unidades que faltaban en los
valles interiores. Acepta `--valle-min-km2` para mover qué tan grande tiene que
ser el cauce receptor y `--sensibilidad` para ver cuántas subcuencas salen con
otros valores. Con el defecto de 200 km² salen 3.313 dentro de la región; con 500
bajan a la mitad y con 50 se duplican.

### Resultado de M1

Con los parámetros de arriba se delinean 950 cuencas sobre el área con margen, de
las cuales 444 descargan dentro de la región. Suman 39.523 km² y 134.329 tramos
de quebrada, y cubren el 96% de la superficie regional. El 4% restante drena
hacia Atacama, Valparaíso o Argentina, así que esas cuencas le pertenecen a la
región vecina.

A esas 444 se les suman **3.313 subcuencas de confluencia** que agrega
`m1_subcuencas.py`, y el total de **3.757 unidades** es lo que consume M2. El
porqué está en la sección siguiente: hasta octubre de 2026 el modelo solo veía
las cuencas costeras, y eso dejaba los valles interiores enteros sin evaluar.

La pasada anterior, con `--area-min-km2 2.0`, daba 170 cuencas. La superficie
drenada casi no cambia entre una y otra (39.280 contra 39.523 km², un 0,6%)
porque las que entran son pequeñas; lo que cambia es la resolución del
inventario, y eso es lo que M2 necesita.

Como control de que la delineación reproduce la hidrología real, se comparan las
tres cuencas mayores contra las áreas oficiales de la DGA. Cada una se identifica
por su desembocadura, comparando las coordenadas de salida contra las bocas
conocidas de cada río:

| Cuenca | Delineada | Oficial DGA | Desvío |
|---|---|---|---|
| Choapa | 7.620,4 km² | ~7.650 km² | 0,4% |
| Elqui | 9.408,2 km² | ~9.657 km² | 2,6% |
| Limarí | 11.675,1 km² | ~11.800 km² | 1,1% |

Las tres quedan bajo el 3%, que para una delineación automática de 30 m contra
una medición estatal independiente es un resultado fuerte.

Una versión anterior de este README reportaba el Limarí en 9.309,0 km², un 21% de
desvío, y lo atribuía a una diferencia de criterio: que la DGA agrupara ahí
quebradas costeras hidrológicamente independientes. Sobre el DEM completo esa
hipótesis resulta innecesaria, porque el Limarí se delinea entero y cuadra con la
cifra oficial. Tampoco existe la "cuenca contigua de 1.878 km²" que aquel
razonamiento sumaba: después de Los Choros (4.051,7 km²) la cuenca siguiente mide
742,2 km². El 21% era un artefacto de la corrida, no una diferencia de
definición.

### La unidad de análisis, que es donde estaba el error más caro

Hasta octubre de 2026 M1 cortaba cuencas en un solo lugar: **donde el terreno
termina**, o sea en la costa. Para una quebrada costera eso es correcto. Baja,
cruza la Ruta 5 y descarga al mar, y esa es toda su historia.

Para el interior es un error de unidad. Una quebrada de Vicuña no desemboca en el
mar: desemboca en el río Elqui. Como el único corte estaba en la costa, esa
quebrada quedaba absorbida dentro de la cuenca del Elqui —9.408 km²—. M2 le
calculaba a esa cuenca de río un Melton de cuenca de río, la clasificaba como
`inundación` y la descartaba entera. Con ella se iban todas las quebradas que
contiene.

**El inventario de activaciones de julio de 2026 lo dejó medido:** de 18
activaciones documentadas, 8 ocurrieron en Vicuña, Paihuano, Illapel y Punitaqui,
comunas donde el modelo no tenía **ni una sola unidad que evaluar**. No es que
dijera que ahí no había peligro. No decía nada. Ver
[`docs/inventario_activaciones_2026-07.md`](docs/inventario_activaciones_2026-07.md).

#### La unidad correcta es la confluencia

Un flujo de detritos se deposita donde el cauce sale de su encajonamiento a un
valle abierto: el ápice del abanico aluvial. La cuenca que alimenta ese abanico es
exactamente la unidad sobre la que Wilford et al. (2004) calibraron la razón de
Melton. En el terreno, ese punto es la confluencia con el valle principal.

Así que una unidad se define por **la boca de un afluente**, no por la
desembocadura al mar. Una celda es boca de afluente cuando entra a una
confluencia, no es la rama más caudalosa de esa confluencia, el cauce que la
recibe drena al menos 200 km², y su propia área está entre 0,4 y 50 km² y no pasa
de un cuarto del área del receptor.

El cambio tiene un segundo efecto que importa tanto como cubrir más territorio:
**el índice queda aplicado sobre el objeto para el que fue hecho**. De las 3.757
unidades, 3.334 caen bajo los 10 km² donde Melton está calibrado. Antes eran 380
de 444.

| | solo costeras | con confluencias |
|---|---|---|
| Unidades de análisis | 444 | **3.757** |
| En rango de calibración de Melton | 380 | **3.334** |
| Comunas con unidades | 7 | **14** |

#### Lo que esto costaba y por qué no costó tanto

No hubo que repetir la hidrología. `m1_subcuencas.py` lee `direccion_flujo.tif` y
`acumulacion_flujo.tif` tal como los dejó `m1_terreno.py`: el relleno de
sumideros y la dirección de flujo —que es la parte cara, la que pide 5,4 GB de
RAM sobre 145 millones de píxeles— no se repiten. Cambiar dónde se ponen las
bocas no cambia por dónde corre el agua.

Y delinear 8.000 cuencas una por una, como hace `m1_terreno.py`, habría tomado la
tarde. En vez de eso se etiquetan todas de una pasada con **duplicación de
punteros**: cada celda guarda a dónde drena, las bocas se marcan como punto fijo,
y se eleva el puntero al cuadrado hasta que toda celda apunta a la primera boca
que encuentra aguas abajo. Convergió en 15 pasadas. El paso completo toma 41
segundos.

#### Lo que queda anidado, y por qué no molesta

Con los valores por defecto las subcuencas no se anidan entre sí: una unidad mide
a lo más 50 km² y el valle que la recibe al menos 200, así que los afluentes de un
afluente nunca llegan a valle. Sí quedan anidadas dentro de las cuencas costeras
de río —la subcuenca de Marquesa está dentro de la del Elqui— y eso es correcto.
No duplica nada en la práctica, porque M2 clasifica al Elqui como `inundación` y
lo deja fuera. La columna `origen` permite separarlas de todos modos.

---

## Cómo se corre M2

```bash
python src/m2_susceptibilidad.py
```

Clasifica cada cuenca según su capacidad de generar flujos de detritos con la
razón de Melton, que es el desnivel dividido por la raíz del área y mide cuánta
energía potencial tiene la cuenca por unidad de tamaño:

```
R = desnivel (km) / √área (km²)
```

Los umbrales vienen de
[Wilford et al. (2004)](https://link.springer.com/article/10.1007/s10346-003-0002-0),
calibrados contra eventos reales:

| Razón de Melton | Tipo de evento |
|---|---|
| < 0,30 | Inundación de agua |
| 0,30 a 0,60 | Crecida de detritos |
| ≥ 0,60 y cuenca ≤ 2,7 km de largo | **Flujo de detritos** (aluvión) |

El largo entra en la clasificación porque una cuenca empinada pero alargada
disipa energía en el trayecto y deposita el material antes de la salida.

La capa guarda dos clasificaciones. La razón de Melton se usa igual en todo el
mundo, pero el umbral de largo sale del estudio original en la Columbia Británica
costera, de clima templado lluvioso, y no hay evidencia de que ese valor sirva en
el norte semiárido de Chile. Sobre los datos de Coquimbo el umbral resulta
decisivo: varias de las cuencas más energéticas de la región quedan descartadas
por diferencias de decenas de metros. Elegir un criterio a ciegas escondería esa
sensibilidad, así que la columna `clase` aplica Wilford completo (Melton más
largo) y `clase_melton` aplica solo la razón de Melton. Al comparar contra el
temporal de julio de 2026, M5 va a decir cuál de las dos reproduce mejor lo que
pasó.

Un límite conocido: Melton se calibró en cuencas de 0,1 a 10 km². Las cuencas
grandes (Elqui, Limarí, Choapa) son cuencas de río, no quebradas de aluvión. El
script las clasifica igual, pero las marca con `melton_aplicable = False`.

### Resultado de M2

De las 3.757 unidades de la región, las dos columnas dan esto:

| Clase | `clase` (Wilford completo) | `clase_melton` (solo Melton) |
|---|---|---|
| Flujo de detritos | 959 | 1.414 |
| Crecida de detritos | 1.630 | 1.175 |
| Inundación | 1.168 | 1.168 |

Conviene mirarlo separado por origen, porque ahí se ve que las subcuencas no
desplazaron nada:

| Origen | Flujo | Crecida | Inundación |
|---|---|---|---|
| Costera | 21 | 146 | 277 |
| Confluencia | 938 | 1.484 | 891 |

Las 444 cuencas costeras dan exactamente lo mismo que daban antes de la
extensión. Las 3.313 subcuencas son territorio que el modelo sencillamente no
tenía.

La razón de Melton máxima subió de 1,01 a 2,71, y eso pide una nota. El valor
alto está en cabeceras andinas muy empinadas, de medio kilómetro cuadrado con
1.700 m de desnivel, que antes quedaban diluidas dentro de la cuenca del río. No
es un error de cálculo, pero sí está fuera del rango donde se suelen reportar
valores de Melton. La distribución tranquiliza: la mediana de las susceptibles es
0,65, el percentil 95 llega a 1,54 y solo 20 unidades pasan de 2,0.

La diferencia entre las dos columnas importa, y ahora está medida: **455 unidades
cambian de clase según el criterio de largo**, contra 12 antes. Son las más
energéticas de la región y quedan descartadas solo por ser alargadas. Ese umbral
de 2,7 km es el parámetro heredado de otra región, y con 455 casos dependiendo de
él pasó de ser un detalle a ser lo primero que M5 debería recalibrar.

### El límite estructural que M2 tuvo durante tres meses

Esta sección era una advertencia y pasó a ser el registro de un problema
cerrado. Vale la pena dejarla, porque el episodio explica la mitad de las cifras
de este README.

Entre agosto y octubre de 2026 las 21 cuencas críticas de M2 estaban **todas** en
la franja costera. Sus desembocaduras caían entre las longitudes −71,71 y −71,29,
y ninguna pasaba al este de −71,27. La región llega hasta −69,81.

No era que el interior no tuviera quebradas peligrosas. Era que M1 definía una
desembocadura como la última celda con terreno antes del vacío, o sea la costa,
así que toda quebrada del interior terminaba siendo afluente del Elqui, del
Limarí o del Choapa y no recibía cuenca propia. Quedaba absorbida en una cuenca
de diez mil kilómetros cuadrados cuyo Melton es bajo por construcción, porque el
área va en el denominador.

El reparto lo mostraba sin ambigüedad: 4 cuencas concentraban el 82,9% de la
superficie drenada, las cuatro de clase inundación, mientras que las 380 que
caían dentro del rango de calibración del índice sumaban el 1,7%.

**El inventario de julio de 2026 convirtió la advertencia en una cifra.** Ocho de
las dieciocho activaciones documentadas ocurrieron en Vicuña, Paihuano, Illapel y
Punitaqui, cuatro comunas sin una sola unidad que evaluar. El modelo no estaba
equivocándose ahí: no estaba mirando.

La salida fue subdividir por las confluencias, que es lo que hace
`m1_subcuencas.py`. Hoy hay unidades en 14 comunas en vez de 7, y los valles
interiores tienen cientos cada uno. El efecto sobre el resultado de M4 fue mayor
de lo que nadie esperaba y está contado más abajo.

Queda un residuo honesto: la corrección agrega unidades, no arregla la
clasificación de las cuatro cuencas de río, que siguen saliendo `inundación` y
siguen concentrando la mayor parte de la superficie. Para lo que este modelo hace
da lo mismo, porque las quebradas que contienen ya se evalúan por separado. Pero
si alguna vez se quiere leer la superficie regional por clase, ese número sigue
dominado por cuatro polígonos.

---

## Cómo se corre M3

Dos scripts:

```bash
python src/m3_preparar_osm.py    # baja el extracto de OSM (~765 MB, una sola vez)
python src/m3_exposicion.py      # cruza quebradas con red vial y zonas urbanas
```

El segundo cruza el cauce principal de cada cuenca susceptible con la red vial y
las zonas urbanas, y devuelve los puntos donde una ruta cruza el fondo de una
quebrada capaz de generar flujo.

Desde octubre de 2026 también cruza las cuencas de clase inundación, menos los
ríos, y ordena los puntos sumando el área drenada en el cruce. Las cifras de esta
sección son de antes de ese cambio. El cambio y la prueba que lo motivó están en
M5, [La prueba que haría una
autoridad](#la-prueba-que-haría-una-autoridad-cortes-reales-y-alerta-por-provincia).

El primero baja el extracto de Chile de
[Geofabrik](https://download.geofabrik.de/south-america/chile.html) y lo deja en
`data/raw/osm/chile.gpkg`. **No baja `chile-latest-free.gpkg.zip`**, que es lo
que ofrece la página: ese archivo cambia todos los días, y dos corridas
separadas por un mes correrían sobre mapas distintos sin que nadie se entere. El
script pide un snapshot con fecha en el nombre y la anota en
`data/raw/osm/PROCEDENCIA.txt`, que es la fecha que después se cita.

Esa distinción es el motivo por el que M3 dejó de consultar Overpass, y no
conviene perderla por la puerta de al lado. Overpass además limita a dos
consultas simultáneas por IP y M3 necesita del orden de cuarenta y ocho, así que
la descarga se cae a mitad de camino. El script todavía sabe usarlo si el
extracto no está, pero no es el camino recomendado.

### Resultado de M3

De las 3.757 unidades de la región, 2.589 son susceptibles (959 de flujo de
detritos y 1.630 de crecida) y a las 2.589 se les trazó el cauce principal, con un
largo mediano de 1,70 km. Contra 47.839 tramos de vía, salen **3.669 puntos de
corte**.

| Jerarquía de la vía | Cortes | Peso |
|---|---|---|
| unclassified | 858 | 0,30 |
| track (huella rural) | 778 | 0,10 |
| residential | 625 | 0,30 |
| tertiary | 621 | 0,45 |
| secondary | 275 | 0,80 |
| service | 210 | 0,15 |
| primary | 135 | 0,93 |
| **motorway** | **94** | **1,00** |
| living_street | 60 | 0,20 |
| enlaces (link) | 13 | 0,15 |

El salto de 422 a 3.669 viene de las subcuencas y no de un cambio de criterio. De
hecho **los 422 cortes antiguos se reproducen exactamente**: los 3.247 nuevos
vienen todos de unidades de confluencia. Y los cortes por cuenca bajaron de 2,5 a
1,4, que es lo esperable, porque una quebrada interior cruza menos caminos que una
costera.

Ese mismo cambio hizo saltar una alarma del propio script, que avisaba sobre los
2.000 cortes. El tope estaba calibrado para 167 cuencas y ahora mide el tamaño del
inventario en vez de la densidad, así que se cambió por un control de cortes por
cuenca. La alarma vieja habría gritado en cada corrida sin que hubiera nada malo.

Por comuna, el reparto cambió por completo:

| Comuna | Antes | Ahora |
|---|---|---|
| Monte Patria | 0 | 748 |
| Vicuña | 0 | 667 |
| Salamanca | 1 | 434 |
| Illapel | 0 | 295 |
| La Serena | 79 | 241 |
| La Higuera | 94 | 206 |
| Río Hurtado | 0 | 202 |
| Paihuano | 0 | 160 |
| Coquimbo | 117 | 142 |
| Combarbalá | 0 | 141 |
| Canela | 42 | 139 |
| Ovalle | 49 | 137 |
| Los Vilos | 40 | 116 |
| Punitaqui | 0 | 41 |

De 7 comunas a 14. Las seis que estaban en cero son justamente los valles
interiores, y Monte Patria y Vicuña pasaron a encabezar la lista.

Los 94 cortes sobre la Ruta 5 Norte son el resultado que le da sentido al hito: es
la vía troncal del país cruzando, una por una, las quebradas costeras que M2 marcó
como capaces. Diez de esos cortes tienen prioridad 1,00, el máximo posible, por
combinar una cuenca de flujo de detritos con una vía de peso máximo. Detrás
aparece el Camino Internacional Gabriela Mistral con 173 cortes, que es la ruta
del valle del Elqui y antes no figuraba en ninguna parte.

Un límite de la tabla de vías: 1.919 de los 3.669 cortes caen en vías sin nombre
en OpenStreetMap, casi todas huellas y caminos sin clasificar. El ranking por
nombre solo describe a los 1.750 restantes.

**El reporte de localidades alcanzadas está subestimado y no debe citarse.** Son
24 con nombre y 130 trayectorias entrando en zona urbana, contra 3 y 10 antes,
pero el mecanismo que las subestima no cambió. M3 filtra las zonas urbanas a
polígonos, y en la Región de Coquimbo las localidades —La Serena, Coquimbo,
Tongoy, Combarbalá, Monte Patria— están mapeadas como puntos, que ese filtro
descarta. Lo que hoy se reporta como
localidad sale del nombre de los polígonos de uso de suelo, que son barrios y
sitios. Decidir si una trayectoria que pasa cerca de un punto poblado cuenta como
alcance urbano es una decisión de modelo y queda para M5.

---

## Cómo se corre M4

```bash
python src/m4_lluvia.py              # usa el cache de data/raw/lluvia/<inicio>_<fin>/
python src/m4_lluvia.py --refrescar  # vuelve a pegarle a VIPNET
python src/m4_umbrales.py            # imprime los umbrales con sus citas
```

Desde octubre de 2026 la ventana cubre tres inviernos, del 1 de junio de 2024 al
23 de agosto de 2026, y la lluvia de cada cuenca ya no es la de su estación más
cercana. Lo que cambió y por qué está en
[Tres inviernos y la lluvia de la cuenca](#tres-inviernos-y-la-lluvia-de-la-cuenca),
al final de esta sección. Lo que sigue documenta la corrida de un invierno, que
es la línea base contra la que se comprobó que el cambio no movió nada de 2026.

M2 dijo qué quebradas *pueden* generar un flujo. M4 responde la otra mitad:
*cuándo*. Se expresa como un umbral intensidad-duración (I-D), una curva
`I = α · D^(−β)` que baja hacia la derecha porque un chaparrón corto tiene que
ser violento para gatillar, mientras que una lluvia larga puede ser suave y
lograrlo por saturación.

**M4 no ajusta un umbral propio.** Una curva I-D se calibra con decenas de pares
(episodio, activó / no activó). En la ventana de este proyecto hay tres bloques
con activaciones documentadas. Una curva ajustada sobre tres puntos pasa por los
tres y no predice nada. Lo que M4 hace es construir el pipeline de lluvia
sub-diaria y aplicarle umbrales publicados, guardando una columna por umbral sin
elegir ganador —el mismo criterio con que M2 guarda dos clasificaciones—.

### De dónde sale la lluvia

De **VIPNET**, el Visualizador Hidrométrico Nacional de la DGA
(`vipnet.mop.gob.cl`), que expone una API REST pública sin registro, sin token y
sin captcha, con **paso de 30 minutos**.

El camino obvio no sirve: DGASAT (`snia.mop.gob.cl/dgasat`) entrega los mismos
valores horarios, pero sus botones "Ver Tabla" y "Ver Gráfico" están detrás de un
reCAPTCHA v2 de Google. No es automatizable y no se intenta rodear.

Tampoco se usa CR2MET ni ningún producto diario: la intensidad es sub-diaria, y
150 mm en cuatro días y 150 mm en seis horas son el mismo número diario y
fenómenos distintos. GPM IMERG quedó fuera porque no hizo falta —la mediana de
distancia cuenca-estación es 16 km, bajo el criterio de 30 km que se había
fijado— y porque su Final Run no cubre 2026.

> El inventario completo de fuentes que respaldaba esta decisión
> (`docs/corridas/2026-08-23_m4_paso0_inventario.txt`) **se perdió** junto con el
> resto de `data/raw/` en septiembre de 2026 y no se ha reconstruido. Lo que
> queda documentado es la conclusión, no el barrido que la sostuvo.

### Las decisiones que hay que poder defender

**Se trabaja con el acumulado, no con la suma de incrementos.** VIPNET entrega
`instantaneo` (el incremento del paso) y `acumulado` (el contador corrido).
Parecen redundantes y no lo son: en CUNCUMEN (04703003-K) la suma de incrementos
da 208,0 mm y el acumulado sube 409,5 mm sobre la misma ventana. La diferencia
está donde la serie tiene huecos: el contador siguió avanzando y no quedó
registro. Sumar incrementos sub-cuenta justo en las estaciones que peor
transmiten.

**Sin dato no es cero milímetros.** La serie se arma sobre una grilla regular de
30 minutos y cada paso queda con un valor o con NaN, nunca con un cero de
relleno. Un hueco largo corta el registro en vez de simular un período seco,
porque un período seco falso parte un episodio en dos y le baja la duración a los
dos pedazos. Es el mismo error del cuadro vacío contra la consulta fallida que
arruinó tres corridas de M3, por el otro extremo.

Con dos salvedades que la reconstrucción de octubre tuvo que agregar, porque sin
ellas estaciones enteras se evaporaban sin que nada fallara. La primera: **la red
no transmite en punto.** Hay estaciones que reportan a los :59, otras a los :22.
Casar por marca de tiempo exacta las deja en cero registros, y el resto del
pipeline no distingue eso de una estación muda. Se redondea al slot más cercano.
La segunda: **hay estaciones horarias**, no de 30 minutos, y los slots que ellas
no usan no son huecos de transmisión. Se mide la cadencia propia de cada una y se
tolera hasta el doble antes de llamar hueco a un silencio.

**Los máximos imposibles de 30 minutos son nieve, no sensores rotos.** Glaciar
Tapado, a 4.065 m, registró 233,8 mm en media hora. En julio a esa altura no
llueve: nieva, y el pluviómetro suelta el equivalente de golpe cuando se derrite.
El corte no se pone a ojo: con la temperatura de la misma red se ajusta día a día
una recta de temperatura contra altitud y se despeja dónde cruza los 0 grados.
Esa es la **isoterma 0 observada**, y durante el temporal de julio dio 2.643 m.
El ajuste solo se acepta con 8 estaciones o más, gradiente entre 2 y 10 °C/km y
R² sobre 0,70; si no, ese día queda sin isoterma y se dice: de los 84 días de la
ventana, solo 22 lo consiguen.

**Y el paso en que una estación vuelve de un corte no es un pico de lluvia.**
Trae el alza del contador de todo el corte junta, así que su valor sirve para
sumar y miente para cualquier cuenta de intensidad. HURTADO salía con 373,1 mm en
media hora —746 mm/h, dos órdenes de magnitud sobre Caine— hasta que esos pasos
se marcaron aparte. Ahora R4 los excluye del máximo de 30 minutos y R3 descarta
el episodio que los contenga.

### Selección de estaciones

Las reglas se escribieron **antes** de mirar los datos, se aplican en orden, y el
reporte dice qué estación cayó por cuál:

| Regla | Unidad | Criterio | Cayeron |
|---|---|---|---|
| R1 | estación | está en Coquimbo y declara parámetro de precipitación | 107 entran |
| R2 | estación | cobertura de la ventana ≥ 50% | 1 |
| R3 | episodio | sin hueco de transmisión adentro | 58 episodios |
| R4 | estación | incremento máximo de 30 min ≤ 20 mm | 4 |
| R5 | episodio | la estación bajo la isoterma 0 observada | 7 episodios |

Quedan **102 estaciones de 107**.

**R3 cambió de granularidad después de mirar los datos, y eso queda escrito.** La
primera versión era por estación —descartar si el desajuste entre suma y
acumulado pasaba de 0,10— y botaba 24 de las 107, entre ellas LAMBERT, que es la
estación más cercana a 7 de las 21 cuencas críticas. Al ir a ver por qué fallaban
apareció que el desajuste no estaba repartido sino concentrado en un solo hueco
por estación: en LAMBERT, 25,2 mm de un desajuste total de 25,2 mm caben en un
único hueco de 94 horas el 24 de julio. El mecanismo que la regla vigilaba es el
correcto, pero el daño está localizado en el tiempo, así que la regla pasó a
aplicarse por episodio con el mismo criterio. El efecto sobre el resultado se
reporta en las dos versiones: **es idéntico**, así que la discusión es sobre el
método y no sobre el número.

**15 estaciones quedan marcadas como ambiguas** y ninguna se descarta. Son pares
vecinos que se contradicen sin que ninguna regla pueda decidir cuál está mala:
LAS BURRAS con 343,5 mm contra RIO ILLAPEL EN LAS BURRAS con 1,1 mm a 200 metros;
EL MAITEN con 1,9 mm contra RIO MOSTAZAL EN CUESTECITA a 3,8 km; RIO CUNCUMEN
ANTES JUNTA CHOAPA con 962,0 mm contra CUNCUMEN con 409,5 mm a 2,2 km.
Elegir cuál sobrevive mirando cuál cuadra mejor sería elegir el resultado.

El corte que las marca —vecinas a menos de 5 km que difieren en más del doble—
es **la constante más débil de M4 y conviene decirlo**. No sale de un criterio
independiente sino de que los tres pares de arriba queden dentro, y el tercero es
el que manda: 962 contra 409,5 es un factor de 2,35, así que cualquier umbral más
exigente lo dejaba pasar. La justificación física existe pero es blanda: dos
pluviómetros a 2 km no pueden ver una diferencia de más del doble en un temporal
frontal que cubre cientos de kilómetros.

### Episodios

Un episodio es un bloque de lluvia separado del siguiente por un período seco. El
corte es de **12 horas**, centro del rango de 6 a 24 h que la literatura usa en
clima árido. No hay valor canónico: es un juicio, y por eso se corre la
sensibilidad con los dos extremos.

| Corte seco | Episodios | D mediana | Episodios que superan Caine |
|---|---|---|---|
| 6 h | 592 | 7,5 h | 33 |
| **12 h** | **455** | **9,0 h** | **26** |
| 24 h | 359 | 10,0 h | 20 |

Hay un segundo parámetro de juicio que el trabajo original no dejó escrito y que
manda tanto como el primero: **qué cuenta como paso seco**. Con cero exacto, una
sola basculada perdida en doce horas impide el corte y pega dos temporales en
uno. Medido sobre la ventana del 17 al 22 de julio, la duración mediana pasa de
53 a 113 horas, y la duración es justamente lo que entra al umbral.

Se fijó en **0,2 mm**, que es la resolución de la cubeta basculante de la red: un
paso con menos que eso no es lluvia medida, es la cubeta todavía sin volcar.

| Paso seco | Episodios | D mediana | Episodios que superan Caine |
|---|---|---|---|
| cero exacto | 455 | 11,5 h | 22 |
| < 0,1 mm | 467 | 11,5 h | 23 |
| **< 0,2 mm** | **455** | **9,0 h** | **26** |
| < 0,5 mm | 424 | 7,2 h | 29 |

**Los dos parámetros mandan sobre el resultado, no solo sobre el conteo**, y hay
que decirlo igual que se dijo del umbral de largo de Wilford en M2.

### Resultado de M4

448 episodios en 94 estaciones, con paso de 30 minutos, entre el 1 de junio y el
23 de agosto de 2026. La ventana termina el 23 y no el 31 de agosto porque los
últimos días todavía no existen; no se rellenan con ceros.

Control externo: **La Serena (Escuela Agrícola) acumula 150,9 mm en julio de
2026**, contra los más de 150 mm en cuatro días que reportó la prensa sobre el
récord de 125 mm de julio de 1987. El acumulado del sensor sube de 2,6 a 153,5 mm
y las dos cuentas cuadran al decimal.

Los tres bloques documentados, vistos por la red:

| Ventana | Episodios | Lluvia mediana | D mediana | I media mediana |
|---|---|---|---|---|
| 17 al 22 de julio | 78 | 130,9 mm | 57,8 h | 2,19 mm/h |
| 31 de julio | 72 | 23,9 mm | 8,2 h | 2,48 mm/h |
| 14 al 16 de agosto | 82 | 6,2 mm | 11,8 h | 0,67 mm/h |

El episodio mayor de la ventana son 412,6 mm en 117,5 h en ANDACOLLO.

Las 2.589 cuencas evaluadas no son las 3.757 de la región, sino las que M2 declaró
capaces de algo más que agua limpia: 959 de flujo de detritos y 1.630 de crecida.
Preguntarle a una cuenca de clase inundación si supera un umbral de flujos de
detritos no significa nada. La mediana de distancia de una cuenca a su estación es
de **6,5 km**, bastante bajo el criterio de 30 km fijado antes de mirar, y 150
cuencas quedan por sobre ese criterio y marcadas en la capa.

**Cuencas que superan cada umbral: 668 de 2.589 para Caine (1980), 0 de 2.589
para Ben David-Novak et al. (2004).** De las 668, el propio M4 no le encuentra
objeción a 577.

### El hallazgo principal, que durante tres meses fue el contrario

Hasta octubre de 2026 esta sección decía que el resultado de M4 era negativo:
ninguna cuenca superaba ningún umbral, pese a que hubo activaciones documentadas.
Era falso, y la causa no estaba en M4.

Las 167 cuencas de entonces eran todas costeras, así que se emparejaban con
estaciones costeras, que acumularon entre 150 y 200 mm en julio. Donde de verdad
llovió fue en el interior: Combarbalá midió 285,5 mm, y las estaciones de Choapa y
Limarí van por ahí. Ahí no había ninguna cuenca que evaluar, de modo que esos
episodios no se cruzaban con nada. **El resultado negativo era una consecuencia
de la unidad de análisis, no un hecho sobre el clima.**

Con las subcuencas de confluencia, 668 cuencas superan Caine. Las estaciones que
las sostienen lo dicen solas: Río Choapa en Cuncumén (116 cuencas), Río Hurtado en
San Agustín (62), Huintil (40), Cogotí (39), Salamanca (38), Caimanes (38), El
Tomé (37), Coirón (34). Todas interiores. Todas invisibles para el modelo
anterior.

#### Lo que sigue siendo cierto

La conclusión de fondo no se invierte, se afina. El 94% de los pares sigue cayendo
**debajo** de las dos curvas, y la razón mediana entre la intensidad medida y la
que Caine pide **bajó** de 0,35 a 0,19 al sumar las cuencas interiores. El
episodio típico llega a un quinto de lo que el umbral exige.

Así que sigue siendo verdad que el temporal fue largo y suave antes que corto e
intenso, y que la mayoría de las quebradas se activaron por acumulación y
saturación. Es coherente con Vergara Dal Pont et al. (2018), que para la cuenca
media del Elqui concluye que estos flujos se generan por escorrentía y no por
deslizamiento. Lo que era falso es la frase "ninguna cuenca lo superó". Sí lo
superaron, en los valles interiores, que es donde el inventario registra ocho de
las dieciocho activaciones.

#### Por qué el vuelco no es un artefacto

Lo revisé buscando que lo fuera:

* **666 de las 668 positivas son subcuencas nuevas.** Las dos costeras son las
  mismas de la corrida anterior. Nada se movió de lugar, apareció territorio.
* **No es un corrimiento general.** Los 668 son una cola del 6% de los 11.591
  pares, y la razón mediana bajó en vez de subir.
* **No es nieve.** El 60% de las positivas tiene altitud media bajo 1.500 m y solo
  el 17% queda sobre la isoterma 0 de julio.
* **No es el artefacto de media hora.** La duración mediana de los episodios
  positivos es de 115 horas. Queda un solo episodio de un paso, el de Quilimarí.
* **Ben David-Novak sigue en cero**, que es lo esperable: su umbral pide
  intensidad convectiva y esta lluvia no la tuvo.

#### La lluvia antecedente sigue siendo la variable que falta

Hay 35 episodios que llegan con más de 50 mm acumulados en las 72 horas previas.
El del 19 de julio en Río Choapa en Salamanca arrastra **265,6 mm de lluvia
antecedente** y aun así se queda en 2,3 mm/h de intensidad media; el de Caimanes,
239,4 mm con 2,1 mm/h. Un suelo con esa cantidad de agua encima no necesita un
chaparrón para soltar material, y un umbral que solo mira I y D no ve nada de eso.

Esas columnas ya se escriben en `m4_episodios.csv` y son el punto de partida de
M5.

> El control fino contra las quebradas con activación documentada
> —`outputs/m4_control_cordura.csv`— todavía no se escribe. Ahora sí existe el
> inventario para hacerlo, en
> [`docs/inventario_activaciones_2026-07.csv`](docs/inventario_activaciones_2026-07.csv),
> pero cruzarlo con las cuencas requiere geolocalizar cada quebrada por nombre.
> Es M5.

### Umbrales aplicados, con la cita completa

| Umbral | Forma | Validez | Cita |
|---|---|---|---|
| Caine (1980) | `I = 14,82 · D^(−0,39)` | 10 min a 10 días | Caine, N. (1980). *Geografiska Annaler A*, 62(1-2), 23-27. |
| Ben David-Novak et al. (2004) | `I ≥ 30 mm/h durante D ≥ 1 h` | clima hiperárido | Ben David-Novak, H., Morin, E., & Enzel, Y. (2004). *GSA Bulletin*, 116(5-6), 718-728. doi:10.1130/B25403.2 |

El segundo se aplica sobre la intensidad máxima en 60 minutos, no sobre la media,
porque así está enunciado, y viene con una advertencia de transferencia escrita en
el código: fue calibrado sobre tormentas convectivas de desierto, y Coquimbo
recibe lluvia frontal de invierno. Su silencio es información, no una falla.

**Guzzetti et al. (2008) no entró.** Es el umbral global de referencia después de
Caine, pero el artículo está detrás de pago y sus coeficientes no se pudieron
verificar en ninguna fuente abierta. Escribir de memoria un número bajo el nombre
de un autor real es exactamente el error que el capítulo 12 del recorrido
documenta. Queda como el primer pendiente de M4: son dos números en
`src/m4_umbrales.py`, y el archivo ya tiene escrito el hueco y el motivo.

### Salidas

| Archivo | Contenido |
|---|---|
| `data/processed/gatillo.gpkg` | 11.591 filas, una por cuenca y episodio, con D, I, antecedente 24/72/168 h, distancia y área, y una columna por umbral |
| `outputs/m4_umbral_id.png` | log-log con las curvas y los episodios encima |
| `outputs/m4_episodios.csv` | los 448 episodios, legibles sin abrir un SIG |
| `outputs/m4_control_cordura.csv` | *pendiente*: las quebradas documentadas contra los umbrales. El inventario ya existe en `docs/`; falta geolocalizarlo. Es M5 |
| `outputs/m4_interpolacion_validacion.csv` | la validación dejando una estación fuera, par por par |

### Tres inviernos y la lluvia de la cuenca

Corrida: [`2026-10-10_m4_tres_inviernos.txt`](docs/corridas/2026-10-10_m4_tres_inviernos.txt).

**Por qué tres inviernos.** Con el temporal de 2026 solo, todas las observaciones
son positivas: hay activaciones y no hay ningún episodio donde lloviera y no
pasara nada. VIPNET tiene dato útil desde el 30 de junio de 2024, y 2025 tuvo
lluvia real —La Serena 122,2 mm de junio a agosto, contra 175,8 en 2026— con
activaciones mayormente menores. Eso es lo que permite calibrar en M5.

Extender la ventana obligó a cuatro cambios, y ninguno es de forma:

* **La hora.** El desfase fijo de 4 horas era válido solo en invierno; la ventana
  nueva cruza seis cambios de hora. Ahora se usa `zoneinfo` con
  `America/Santiago` y la grilla vive en tiempo absoluto: el día que se adelanta
  la hora tiene 46 pasos y el que se atrasa, 50. Sobre la ventana vieja el cambio
  reproduce la corrida anterior al número.
* **El cache.** Era una carpeta plana, y cambiar la ventana leía en silencio la
  serie vieja. Ahora hay una subcarpeta por ventana.
* **Los saltos del contador.** Con tres años, R4 pasó de botar 4 estaciones a
  botar 13, y casi ninguna por nieve: el 9 y 10 de abril de 2026 cinco estaciones
  registran a la vez cientos de milímetros en un paso entre ceros (Huintil 739,
  Cogotí Embalse 660, Cuncumén 598). En tres inviernos, el paso de 30 minutos más
  grande que no está aislado es de 16 mm; los aislados se separan solos en una
  familia de 22 a 81 mm y otra de 163 a 739. Un paso aislado de más de 100 mm se
  anula, como ya se anulaba el salto hacia abajo.
* **R2 y R4 por estación e invierno.** Por estación, una falla de abril botaba a
  Cuncumén también para julio, y Río Mostazal en Cuestecita —99% de cobertura en
  2026— caía por no existir en 2024. Es el mismo cambio de granularidad que ya
  tuvo R3, también hecho después de mirar los datos, y la corrida reporta las dos
  versiones: por estación quedaban 88 de 107; por invierno son válidas 98, 101 y
  101.

Resultado: **1.188 episodios en 104 estaciones**, 98 eventos regionales.

| | 2024 | 2025 | 2026 |
|---|---|---|---|
| Episodios | 223 | 503 | 462 |
| Superan Caine (episodio) | 3 | 7 | 26 |
| Superan Caine (ventana crítica) | 10 | 17 | 41 |

**La lluvia de la cuenca.** El diagnóstico ya había medido que la estación más
cercana es casi ruido: dejando una estación fuera, le gana apenas a la media
regional en error absoluto y le pierde en R². Ahora la cantidad de lluvia de cada
cuenca la predice un random forest sobre latitud, longitud, altitud y distancia a
la costa, más dos rasgos del evento —su media regional y la latitud donde se
concentró—. Predice **por evento regional**, no el total del invierno, porque el
umbral se aplica a episodios. La cuenca conserva el reloj de su estación cercana
(cuándo empezó, cuánto duró) y la cantidad se escala por el cociente entre la
predicción y lo medido. Los pares sobre la isoterma 0 quedan fuera del
entrenamiento, para que el bosque no aprenda como física la nieve que la cubeta
no mide. Todo está en `src/m4_interpolacion.py`.

La regla era adoptarlo solo si le ganaba a la estación cercana dejando
estaciones fuera. Le gana:

| Método | MAE | RMSE | R² | R² dentro del evento |
|---|---|---|---|---|
| media regional | 39,5 mm | 65,5 | 0,62 | −0,02 |
| estación cercana | 36,8 mm | 76,9 | 0,48 | −0,41 |
| **random forest** | **29,9 mm** | **59,1** | **0,69** | **0,17** |
| gradient boosting | 30,7 mm | 58,1 | 0,70 | 0,19 |

La última columna dice cuánto gana de verdad: 0,17 de R² repartiendo la lluvia
dentro de un evento es poco, y el bosque gana sobre todo porque la estación
cercana es **peor** que la media regional. Además se entrena con solo 5 eventos
regionales; los 93 restantes son demasiado chicos y quedan con factor 1. Sobre el
total del invierno de 2026, que es como se hizo el diagnóstico, el orden se
repite: media regional 125,8 mm de MAE, estación cercana 158,2, bosque 107,7.

La interpolación no cambia el recall de M5 leyendo el episodio entero, y lo sube
en la ventana crítica de 40% a 72%. Pero también marca más cuencas (de 856 a
1.000 en 2026), así que sin negativos no se sabía si eso era mejora. La
calibración de M5 lo contesta, y la respuesta es que no.

---

## Cómo se corre M5

```bash
python src/m5_validacion.py
python src/m5_validacion.py --solo-fuertes   # solo aluvión y activación
```

Cruza las activaciones documentadas del temporal de julio contra lo que el modelo
predijo. El inventario está en
[`docs/inventario_activaciones_2026-07.csv`](docs/inventario_activaciones_2026-07.csv),
con 18 entradas de prensa y comunicados de SENAPRED y Carabineros, cada una con su
URL.

Las entradas traen nombres, no coordenadas, así que se ubican en el extracto de
OpenStreetMap que M3 ya usa. Catorce calzan directo entre los cauces con nombre,
donde las quebradas aparecen como "Quebrada X"; las otras cuatro necesitan un
alias, y los cuatro están escritos en el código con su motivo.

### Lo que M5 puede medir y lo que no

Una matriz de confusión necesita saber, para cada cuenca, si se activó o no. Este
inventario es de prensa: registra activaciones **que alguien reportó**. Una
quebrada que bajó con fuerza en un cerro sin camino figura igual que una que no se
movió. Hay positivos observados y **no hay negativos observados**.

Entonces se puede estimar el recall —de las activaciones documentadas, cuántas
marcó el modelo— y nada más. La precisión no es estimable: el modelo marca 668
cuencas y el inventario tiene 18 entradas, así que las 650 que no figuran no son
falsos positivos, son lugares donde nadie fue a mirar. Reportar una precisión
contra ese inventario sería inventar 2.571 verdaderos negativos.

Por eso este hito no entrega AUC ni F1. Un número que no se puede defender es peor
que no tenerlo.

### Resultado de M5

| | Todas las entradas | Solo evidencia fuerte |
|---|---|---|
| Entradas | 18 | 9 |
| Sin cobertura del modelo | 3 | 3 |
| Evaluadas y no predichas | 11 | 5 |
| Predichas | 4 | 1 |
| **Recall sobre las evaluadas** | **27%** | **17%** |

Las tres sin cobertura —Cruz de Caña, Tambillos y Cajón del Romero— no son errores
de predicción. Caen en cuencas costeras de entre 195 y 538 km², y
`m1_subcuencas.py` solo delinea una subcuenca cuando el cauce receptor drena al
menos 200 km². El modelo nunca evaluó ese lugar.

Bajando `--valle-min-km2` a 25 aparecen unidades ahí. **No se hizo**, y el motivo
es de método: bajar un parámetro hasta que cubra los casos de su propia validación
es ajustar contra el conjunto de prueba. Queda como lo primero que debería revisar
una iteración siguiente, con datos distintos de los que lo detectaron.

### Las fallas son el hallazgo

Un recall de 17% suena a fracaso y no lo es, porque lo interesante no es cuántas
falló sino **por cuánto**. Las tres quebradas con más unidades cerca:

| Quebrada | Comuna | Lluvia | Duración | I media | Razón vs Caine | |
|---|---|---|---|---|---|---|
| El Rincón | Los Vilos | 238,6 mm | 52,5 h | 4,54 mm/h | **1,44** | acierto |
| Marquesa | Vicuña | 198,7 mm | 112,0 h | 3,27 mm/h | **0,75** | falla |
| Tres Cruces | Paihuano | 159,4 mm | 111,5 h | 2,34 mm/h | **0,67** | falla |

El Choapa recibió casi la misma agua que el Elqui **en la mitad del tiempo**. No
es que el modelo midiera mal el valle del Elqui: el Elqui no alcanzó la intensidad
que Caine pide, y las quebradas se activaron igual.

De las 11 entradas evaluadas y no predichas, **10 caen entre 0,55 y 0,80 de lo que
Caine exige**, con mediana 0,75. Y el recall salta donde están:

| Caine × k | Recall |
|---|---|
| 1,0 | 4/15 (27%) |
| 0,9 | 4/15 (27%) |
| 0,8 | 4/15 (27%) |
| **0,7** | **12/15 (80%)** |
| 0,6 | 13/15 (87%) |
| 0,5 | 14/15 (93%) |

O sea que el umbral global de Caine queda del orden de **un 30% alto** para la
Región de Coquimbo. Es la medición que M4 venía pidiendo desde su resultado
negativo, ahora con un número.

**Ese escalamiento no se adopta.** Elegir el k que maximiza el recall sobre este
mismo inventario es ajustar el modelo contra su propia validación, y el número que
saliera después no mediría nada. Además las entradas no son independientes: varias
comparten la estación más cercana y por eso repiten exactamente la misma razón
—0,747 aparece cuatro veces—, así que los 15 casos valen bastante menos de 15
observaciones.

Para calibrar en serio hace falta un inventario con episodios **sin** activación
documentada. Eso se armó en octubre de 2026 y está en la sección siguiente.

### Calibración con negativos: entrenar en 2024-2025, probar en 2026

```bash
python src/m5_calibracion.py                    # positivos: aluvión, activación y activación menor
python src/m5_calibracion.py --positivos fuerte # solo aluvión y activación
```

Corrida: [`2026-10-10_m5_tres_inviernos.txt`](docs/corridas/2026-10-10_m5_tres_inviernos.txt).

**El inventario nuevo.**
[`docs/inventario_activaciones_2024-2025.csv`](docs/inventario_activaciones_2024-2025.csv)
tiene 44 entradas de cuatro eventos, con el mismo formato y criterio que el de
2026, y su documento explica cada juicio. Las filas sin nombre ("se activaron 41
quebradas") no son positivos, pero **excluyen** su comuna y su fecha de los
negativos. El inventario de 2026 sumó El Porotal, que **no es de julio sino del
15 de agosto**, y las demás quebradas de las mismas fuentes: pasó de 18 a 33. La
entrada 9, el aluvión del Islón, ya tiene quebrada: Santa Gracia.

**La unidad es la estación y el episodio**, no la cuenca: un umbral I-D es un
umbral de lluvia, y las cuencas de una estación comparten el reloj de su lluvia.
Un episodio es positivo si una activación documentada cae a menos de 3 km de una
cuenca de su zona, en su fecha ±1 día. Los negativos son **presuntos**: un
episodio sin activación reportada. Por eso la precisión es una **cota
inferior**.

**La precisión de Caine publicado, que antes no se podía calcular:**

| Invierno 2026 | Recall | Precisión (cota inf.) | Falsos positivos | AUC |
|---|---|---|---|---|
| Caine publicado | 3% | 4,5% | 6% | 0,47 |
| Caine, ventana crítica | 15% | 13% | 10% | 0,49 |
| Ajustada sobre 2024-2025 | 48% | 9% | 45% | 0,49 |

La curva ajustada por máxima verosimilitud es más empinada que Caine,
`I = 28,9 · D^(−0,60)` a probabilidad 0,5 (β entre 0,23 y 0,83), y en el punto
de operación elegido en el entrenamiento queda bastante más baja. **Baja el
umbral pero no discrimina mejor**: el AUC es el mismo. Cambia falsos negativos
por falsos positivos a lo largo de la misma ordenación. Es el diagnóstico previo
—mover el umbral no arregla el ranking—, ahora medido con negativos y sobre un
invierno que el ajuste no vio.

**Y el AUC de 0,47 esconde dos temporales distintos:**

| Evento de 2026 | Positivos | Lluvia mediana | AUC Caine | Recall ajustada |
|---|---|---|---|---|
| 16 de julio | 13 | 59,2 mm | 0,77 | 92% |
| 13 de agosto | 20 | 4,6 mm | 0,27 | 20% |

Dentro del temporal de julio el I-D sí ordena. En agosto las zonas activadas
recibieron 4,6 mm de mediana y se activaron donde **menos** llovió: El Día lo
atribuyó al "derretimiento acelerado de la nieve acumulada" sobre suelos ya
saturados. Ningún umbral de lluvia puede ver eso.

**Lo que no se puede concluir.** Hay 12 positivos de entrenamiento y salen de
dos eventos, así que el intervalo de β es optimista aunque ya es ancho. Con
evidencia fuerte quedan 6 positivos de un solo evento, y esa variante no se usa.
La regresión con Melton, antecedente de 72 h y altitud pide 50 positivos y hay
12: no se ajustó.

### El piloto satelital

`python src/m5_satelite_piloto.py` compara Sentinel-2 antes y después sobre
cuatro quebradas con activación documentada. Usa los datos abiertos de AWS, que
no piden cuenta, en vez de Copernicus Data Space o Earth Engine, que sí la piden.
De julio a septiembre domina el reverdecimiento después de la lluvia. Septiembre
de 2025 contra septiembre de 2026 limpia las sombras y deja una señal real —más
suelo desnudo a lo largo de los cauces—, pero en **toda** la red de drenaje y no
solo en la quebrada reportada. Lo que el satélite ve con claridad es por dónde
corrió agua con energía. Separar un flujo de detritos de una crecida pide un
clasificador entrenado, y para entrenarlo hacen falta las etiquetas que se
querían producir.

### Negativos desde satélite: no se lograron, y el porqué es el hallazgo

```bash
python src/m5_satelite_cauces.py    # las 2.589 unidades, septiembre contra septiembre (~30 min)
python src/m5_satelite_troncos.py   # el mismo detector sobre los troncos reportados
```

Corrida: [`2026-10-10_m5_satelite.txt`](docs/corridas/2026-10-10_m5_satelite.txt).

El objetivo era reemplazar los negativos presuntos de la calibración por
negativos **observados**: cauces que Sentinel-2 ve sin cambio entre un
septiembre y el siguiente. La métrica es cuánto suelo desnudo ganó el cauce
principal de cada unidad frente a sus propias laderas. El umbral sale de líneas
paralelas a 200 m del cauce, que no son cauces, y no de las etiquetas. Todo eso
se fijó antes de correr, junto con la prueba: las quebradas reportadas tienen
que cambiar más que las demás.

**La prueba falló.** En 2026 las unidades cerca de las quebradas reportadas
cambiaron **menos** que el resto (AUC 0,37). Esos negativos no se usan.

**El porqué es más importante que los negativos.** Sobre el *tronco* de las
mismas quebradas, el detector ve las activaciones de 2026 con claridad: 66% de
los tramos con cambio y AUC 0,89 contra sus nulos. Santa Gracia cambió en el
82% de sus tramos, Marquesa en el 72%. Lo que fallaba era el objeto:

| | Área drenada |
|---|---|
| Santa Gracia (aluvión del Islón) | 1.073 km² |
| Marquesa | 736 km² |
| El Arrayán | 562 km² |
| San Carlos | 259 km² |
| **Mediana de las 23 reportadas** | **113 km²** |
| Tope de una unidad de M1 | 50 km² |

**15 de las 23 quebradas reportadas son más grandes que cualquier unidad del
modelo.** M1 las ve solo a través de afluentes chicos que pasan cerca, y el
satélite dice que esos afluentes mayormente no hicieron nada. Es el mismo error
que M1 tuvo hasta octubre —la unidad no coincide con el fenómeno—, ahora de
escala en vez de ubicación. Y es la explicación más directa de por qué el
modelo rankea mal: el umbral se aplica a la lluvia de unidades que no son las
que se activaron.

Dos resultados más, que acotan lo que el satélite puede dar:

* **2025 no dejó huella.** Los troncos reportados en 2025 no cambiaron (AUC
  0,18). Calza con que fueron activaciones menores: agua, no sedimento.
* **Tampoco hay negativos a escala de tronco.** De 60 quebradas que nadie
  reportó en las mismas comunas, el 46% de los tramos cambió en 2026, contra
  66% de las reportadas. O la prensa reportó solo una parte de lo que bajó, o el
  reverdecimiento del lecho frente a las laderas pesa más de lo que el método
  descuenta. Estos datos no separan una cosa de la otra.

### Unidades troncales: el objeto correcto, y lo que eso dejó a la vista

```bash
python src/m1_troncos.py        # después de m1_subcuencas.py; ~3 GB de RAM por un par de minutos
python src/m2_susceptibilidad.py
python src/m3_exposicion.py
python src/m4_lluvia.py
python src/m5_troncos.py        # la evaluación; lee imágenes de AWS, ~15 min
```

Corrida: [`2026-10-10_troncos.txt`](docs/corridas/2026-10-10_troncos.txt).

**Qué es un tronco.** Un afluente que entra a un valle con las mismas reglas de
`m1_subcuencas.py`, pero de más de 50 km², que es donde terminaban las unidades.
Se excluyen los que OpenStreetMap llama "Río": un río tiene caudal permanente y
su peligro es el desborde, otro fenómeno. La regla se tomó de afuera a propósito.
Elegir un tope de tamaño mirando el área de las quebradas reportadas habría sido
ajustar contra la validación. Salen **93 troncos**, de 51 a 1.371 km² (mediana
92), con su área completa aguas arriba. Melton no está calibrado a esa escala,
así que no se filtran: M2 los marca como `tronco` y se evalúan todos.

Para la lluvia, M4 usa el promedio del random forest sobre una grilla de ~25
puntos por tronco (lluvia areal), no el valor de un punto.

**Agregarlos no movió nada de lo existente**, y está comprobado. M2 sin troncos
reproduce la clasificación de siempre, M5 `--sin-troncos` reproduce el recall
anterior y la calibración reproduce su salida línea por línea. Para lograrlo
hubo que corregir dos errores previos que no daban error. M2 medía todas las
cuencas en una sola capa de etiquetas, y donde se superponían ganaba la última:
la primera corrida con troncos le cambió la clase a cientos de unidades chicas.
Y M3 le ponía peso cero a una clase sin peso de prioridad.

**El tronco es el objeto correcto.** De los 8 troncos que la prensa reportó en
2026, el satélite ve 5 activos, 3 dudosos y ninguno inactivo. Y en exposición
agregan 1.177 cortes de ruta, 145 en la Ruta 5, la Ruta 43 o rutas primarias:
es donde bajó el agua en 2026.

**Pero la lluvia no distingue entre troncos:**

| Prueba (2026) | AUC Caine | AUC ventana crítica |
|---|---|---|
| Troncos activos (45) contra inactivos (21), según el satélite | 0,49 | 0,54 |
| Unidades chicas con cambio contra sin cambio, según el satélite | 0,59 | 0,58 |
| Troncos reportados por la prensa (motivó el cambio, no valida) | 0,38 | 0,40 |

Dentro de un mismo temporal, la lluvia que el modelo le asigna a cada tronco no
separa los que bajaron de los que no. 2025 no sirve para separar: el satélite ve
un tronco activo de 89, y la prensa reporta tres.

**El cuello de botella se movió.** Ya no son la unidad ni el umbral: es la
lluvia de entrada. Con pluviómetros, incluso interpolados (R² dentro del evento
de 0,17), el modelo no resuelve cuánto llovió en una cuenca frente a la vecina.

Para gestión, eso se traduce en dos usos distintos:

* **Sirve** para decir *cuándo* un temporal es peligroso a escala regional, y
  para decir *dónde* están los cortes de ruta que conviene vigilar cuando llega,
  ahora incluidos los troncos.
* **No sirve**, con la red de pluviómetros actual, para priorizar entre
  quebradas *dentro* de un mismo temporal. Para eso hace falta precipitación con
  resolución espacial: radar, o satélite corregido contra estaciones.

### La prueba que haría una autoridad: cortes reales y alerta por provincia

```bash
python src/m3_exposicion.py       # con la clase inundacion y el area en el orden
python src/m5_cortes.py           # los cortes de ruta reales contra la lista de M3
python src/m5_alerta_sector.py    # la alerta por provincia y por temporal
```

Corridas: [`2026-10-11_m3_exposicion.txt`](docs/corridas/2026-10-11_m3_exposicion.txt),
[`2026-10-11_m5_cortes.txt`](docs/corridas/2026-10-11_m5_cortes.txt) y
[`2026-10-11_m5_alerta_sector.txt`](docs/corridas/2026-10-11_m5_alerta_sector.txt).

Todo lo anterior de M5 evalúa quebrada por quebrada. Una autoridad no decide así:
vigila tramos de ruta y declara alertas por provincia y por temporal. Estas dos
pruebas miden el modelo en esos términos.

#### Los cortes de ruta reales contra el mapa de exposición

Los inventarios traen 11 cortes o daños de ruta con la vía nombrada. Cada uno se
ubica con el cauce o el caserío de OSM que lleva su nombre. Hay acierto si M3
tiene un candidato sobre esa ruta a menos de 1 km del punto (1,5 km si se ubicó
por caserío). La línea base pone la misma ventana en 2.000 puntos al azar de la
misma ruta. Sin ella el acierto no dice nada: hay rutas con un candidato por
kilómetro.

| Lista de M3 | Cortes con candidato | Al azar | 3% de arriba de la lista | Al azar |
|---|---|---|---|---|
| Hasta octubre (clases susceptibles, orden por clase y vía) | 7 de 11 | 5,3 | 2 | 2,5 |
| Más la clase inundación | 9 de 11 | 6,6 | 2 | 2,5 |
| Más el área drenada en el orden (la actual) | 9 de 11 | 6,6 | **4** | **1,0** |

**La lista de antes sabía qué rutas cruzan quebradas, no en qué punto**
(P = 0,14 contra el azar), y su orden no ayudaba. Los cuatro cortes sin candidato
caían en cuencas de clase inundación, que M3 no miraba. La prensa ahí describe
agua, no barro: "aumento de caudal" en la D-427, una crecida que "sobrepasó la
calzada" en la misma ruta un año antes, un socavón en la D-697. M2 acertaba el
proceso; M3 se equivocaba de pregunta. Para una vía no importa si la corta un
flujo de detritos o una crecida de agua.

De ahí los dos cambios. Las cuencas de inundación entran con peso 0,30, sin los
ríos (Elqui, Limarí, Choapa y otros doce, con la regla de los troncos). La
prioridad pasa a tener tres tercios: clase, vía y área drenada en el cruce, en
logaritmo entre 0,15 y 1.000 km². El área se agregó porque con dos términos los
candidatos de una misma ruta empataban. **El 3% de arriba de la lista pasa a
cubrir 4 cortes contra 1,0 al azar (P = 0,006).** La lista crece de 4.846 a 9.424
puntos y los 4.846 de antes no cambian.

La fórmula se fijó antes de evaluarla, pero los once cortes son los mismos que
mostraron el problema. **Esto no es validación independiente**: la
independiente es el invierno de 2027, contra la lista congelada de esta corrida.

#### La alerta por provincia y por temporal

Los temporales se arman con los episodios de M4 de 5 mm o más que quedan a menos
de 24 h. Salen 34 en tres inviernos, 15 de ellos regionales (5 estaciones o más
sobre 5 mm). Una provincia es positiva en un temporal si alguna fuente reporta
una activación en una de sus comunas. A esa escala el negativo pesa bastante más
que por quebrada: es difícil que una provincia entera tenga activaciones y nadie
lo reporte.

Caine publicado, sin ajustar nada, en los temporales regionales:

| Nivel | Recall | Precisión | Falsas alarmas | AUC Caine | AUC lluvia máxima |
|---|---|---|---|---|---|
| Región, por temporal (*cuándo*) | 0,67 | 0,80 | 1 de 9 | 0,91 | 0,94 |
| Provincia, por temporal (*dónde*) | 0,25 | 0,43 | 4 de 29 | 0,78 | 0,86 |

**El *cuándo* funciona.** De los 6 temporales con activaciones, Caine avisa en 4.
No ve el del 16-06-2025 (activaciones menores en Canela con 51 mm) ni el bloque de
deshielo de agosto de 2026.

**El *dónde* por provincia no, y el patrón es uno solo.** En Elqui, Caine no se
activa en ningún temporal, ni siquiera en el de julio de 2026, con el aluvión de
Santa Gracia. Un umbral global, puesto sobre un gradiente que va del desierto al
semiárido, queda alto justo en la provincia más seca. Y la lluvia máxima del
temporal, sin umbral, ordena las provincias mejor que la razón contra Caine.

De ahí salen los dos pasos siguientes:

* un indicador de deshielo, para el bloque de agosto que ningún umbral de lluvia
  ve;
* niveles de alerta por provincia que miren la lluvia relativa al clima de cada
  zona, calibrados con 2024-2025 y probados en 2026 con esta misma tabla.

#### El deshielo: el bloque que ningún umbral de lluvia ve

```bash
python src/m4_deshielo.py         # antes de m5_alerta_sector.py
```

Corrida: [`2026-10-11_m4_deshielo.txt`](docs/corridas/2026-10-11_m4_deshielo.txt).

Del 11 al 18 de agosto de 2026 se activaron veinte zonas con una lluvia mediana
de 4,6 mm. La prensa lo atribuyó al "derretimiento acelerado de la nieve
acumulada", con lluvia en altura. M4 no tenía ninguna variable que viera eso. El
indicador nuevo usa dos redes de VIPNET que no se usaban para esto:

* **La nieve.** La mediana de la altura de nieve en las cuatro estaciones con
  registro completo (Cerro Olivares, Glaciar Tapado, Quebrada Larga y El Soldado,
  de 3.293 a 4.065 m). Su máximo fue de 40 cm en 2024, 23 cm en 2025 y
  **157 cm en 2026**, después del temporal de julio.
* **La isoterma 0**, extrapolada desde las estaciones sobre 3.000 m. La de M4
  ajusta una recta sobre toda la red y fuera de los días de temporal la rompe la
  inversión térmica de la costa: no tiene ningún día entre el 4 y el 22 de agosto
  de 2026. Las estaciones altas quedan sobre la inversión.

**La condición de deshielo** se cumple cuando hay 50 cm de nieve o más y la
isoterma está sobre la línea de nieve, que es la isoterma más baja de los días
en que nevó durante el último mes. En la práctica es nieve acumulada recibiendo
lluvia o derritiéndose. En 2024 y 2025 no aparece nunca. En 2026 queda activa del
22 de julio al 23 de agosto, y la tienen los temporales del 30 de julio, del 4 de
agosto y del 11 al 18.

Sumada a la alerta ("Caine o deshielo"), en los temporales regionales:

| Nivel | Caine | Caine o deshielo |
|---|---|---|
| Por temporal (región) | recall 0,67, precisión 0,80 | recall 0,83, precisión 0,83 |
| Por provincia | recall 0,25, precisión 0,43 | recall 0,67, precisión 0,67 |

La tasa de falsas alarmas no cambia. **Es experimental, y se dice por qué.** Hay
un solo evento de deshielo documentado. Los 50 cm describen que 2026 fue
distinto, no son un umbral calibrado: cualquier corte entre 41 y 110 cm da lo
mismo en estos tres inviernos. De los cinco aciertos que se agregan por
provincia, tres son el bloque de agosto que motivó el indicador. El siguiente
invierno con mucha nieve dirá si sirve.

#### Niveles de alerta por provincia

```bash
python src/m4_climatologia.py     # una vez: la normal 1991-2020 de CR2MET, ~20 min
python src/m5_niveles.py          # después de m5_alerta_sector.py
```

Corridas: [`2026-10-11_m4_climatologia.txt`](docs/corridas/2026-10-11_m4_climatologia.txt)
y [`2026-10-11_m5_niveles.txt`](docs/corridas/2026-10-11_m5_niveles.txt).

Una autoridad no emite "supera Caine": emite amarilla, naranja o roja por
provincia. El modelo nuevo usa una sola variable: **la lluvia del temporal en la
estación más mojada de la provincia, como fracción de lo que llueve ahí en un año
normal.** La normal es la de CR2MET 1991-2020: 91 mm en La Serena, 211 en
Illapel. No se bajan los 2,5 GB del producto, solo los 360 meses de la normal,
leídos por rangos dentro del zip. La probabilidad sale de una logística sobre esa
variable. Los niveles se fijaron antes de ajustar: 0,25, 0,50 y 0,75 de
probabilidad.

| Prueba | Lluvia / normal | Lluvia en mm | Caine publicado |
|---|---|---|---|
| Entrenado en 2024-2025, probado en 2026 (AUC) | **1,00** | 0,95 | 0,68 |
| Un temporal fuera a la vez, tres inviernos (AUC) | **0,95** | 0,94 | 0,88 |
| Ídem, solo temporales regionales | 0,87 | 0,87 | 0,78 |
| Ídem, solo Elqui | 0,94 | 0,92 | 0,91 |

En 2026, sin haberlo visto, las 9 provincias-temporal que quedaron sin nivel no
tuvieron activaciones, y las 4 en naranja o roja tuvieron todas.

**Los niveles para operar**, ajustados con los tres inviernos, se leen así: en
alguna estación de la provincia, el temporal deja

| Nivel | Lluvia del temporal | Probabilidad de activaciones en la provincia |
|---|---|---|
| Amarilla | 21% de la normal anual | 1 de cada 4 |
| Naranja | 27% | 1 de cada 2 |
| Roja | 35% | 3 de cada 4 |

Tres cosas que conviene decir con la misma claridad que las cifras:

* **Normalizar por el clima aporta poco dentro de Coquimbo.** Con milímetros
  absolutos, la validación cruzada da casi lo mismo. La mejora viene de contar la
  lluvia del temporal entero por provincia y poner el corte a esa escala: en
  Elqui, Caine ordenaba bien (AUC 0,91), pero su corte global nunca se alcanzaba.
  Se usa la fracción igual por el argumento físico, y porque es la única forma
  de llevar los niveles a un clima más seco. **Atacama es la prueba**, con normales
  de 19 mm en Copiapó.
* **El bloque de deshielo de agosto de 2026 queda en naranja o roja sin el
  indicador de deshielo.** Medido como temporal entero, llovió entre el 30 y el
  42% de la normal. Los 4,6 mm de mediana que lo hacían parecer seco eran por
  cuenca y por episodio.
* **Lo que falla es un par de temporales.** El 11 de junio de 2025 llovió entre
  el 26 y el 33% de la normal y no hubo reportes (falsa alarma). El 16 de junio
  llovió entre el 21 y el 23% y sí hubo activaciones (falla). Es la firma de la
  lluvia antecedente: el segundo cayó sobre el suelo que mojó el primero. Con 12
  positivos no se puede agregar una segunda variable sin sobreajustar.

---

## M6: la alerta en vivo

```bash
python src/m6_alerta_en_vivo.py                                # ahora, contra VIPNET
python src/m6_alerta_en_vivo.py --momento "2026-07-18 12:00"   # como si fuera ese momento
python src/m6_alerta_en_vivo.py --repasar                      # el final de cada temporal, contra M5
python src/m6_alerta_en_vivo.py --cronologia "2026-07-15 12:00" "2026-07-18 00:00" 3
```

Corrida: [`2026-10-11_m6_alerta_en_vivo.txt`](docs/corridas/2026-10-11_m6_alerta_en_vivo.txt).

Es la primera parte de M6, y la que convierte el modelo en algo que se usa. Baja
de VIPNET la lluvia, la temperatura y la nieve de la región y arma el temporal en
curso. Con eso emite un boletín por provincia, que escribe en
`outputs/alerta_en_vivo.json` (lo que leerá el visor) y en
`outputs/boletines/boletin_AAAA-MM-DD_HHMM.md`. El boletín trae:

* el nivel, la probabilidad y la lluvia del temporal en la estación más mojada;
* **cuántos milímetros faltan para el nivel siguiente** y en qué estación;
* el aviso de deshielo;
* los tramos de ruta a vigilar en las provincias con alerta: el primer cruce de
  cada quebrada con cada vía, de la lista de M3;
* las estaciones que están transmitiendo. Con menos de 3 en una provincia, el
  boletín dice "datos insuficientes" en vez de "sin alerta".

**Usa exactamente las mismas reglas que la calibración.** Las funciones de M4 y
M5 se reutilizan sin reescribir, y el modelo está congelado en el código, con la
fecha de su calibración. Así, el invierno de 2027 se va a evaluar contra una regla
que no se movió. La comprobación: corrida al final de cada temporal regional de
tres inviernos, **da el mismo nivel que M5 en 41 de 41 provincias-temporal.**

**Cuándo habría avisado**, hora a hora, en el temporal de julio de 2026:

| Hora | Elqui | Limarí | Choapa |
|---|---|---|---|
| 16-07, 21:00 | amarilla | amarilla | — |
| 17-07, 00:00 | naranja | naranja | amarilla |
| 17-07, 03:00 | naranja | **roja** | naranja |
| 17-07, 06:00 | naranja | roja | **roja** |
| 17-07, 09:00 | **roja** | roja | roja |

Las primeras activaciones reportadas son del 17 de julio, con fecha y sin hora,
así que la anticipación exacta no se puede medir. El aluvión de Santa Gracia, en
Elqui, fue el 20: la provincia llevaba casi tres días en roja. En el bloque de
deshielo de agosto, Limarí estaba en naranja desde la medianoche del 13 y en
roja desde la del 15, el día de las activaciones. Elqui llegó a naranja el 15 al
mediodía, y Choapa solo a amarilla, el 16. El aviso de deshielo estuvo activo
todo el bloque.

**Probada en vivo el 11 de octubre de 2026.** La primera corrida contra la API
encontró un temporal real en curso desde el 5 de octubre: la DMC había emitido
la alerta AA174/2026 por lluvias para el 6 y el 7. El boletín de las 14:30 dio
Choapa en naranja (94 mm en Río Cuncumén, 30% de su normal) y Limarí en amarilla,
con el aviso de deshielo activo: había 148 cm de nieve en altura y la isoterma
estaba a 3.545 m. Que llueva en Los Vilos y en Quilimarí, al nivel del mar,
descarta que sea nieve derretida dentro de los pluviómetros altos.

**Cómo dejarla corriendo sola.** En Windows, una tarea programada cada hora. La
primera corrida baja 40 días de 230 series (unos 7 MB); las siguientes bajan
solo lo que falta, con 24 horas de solape porque VIPNET a veces completa datos
tarde. El almacén queda en `data/raw/vivo/`.

**Lo que todavía no hace:** mirar hacia adelante. Avisa con la lluvia que ya
cayó: en julio, la alerta subió durante la noche del 16, horas antes del día de
las primeras activaciones reportadas. Para avisar con uno a tres días hay que
sumar el pronóstico, que es el paso siguiente.

### El visor: Vigía de quebradas

```bash
python src/m6_visor.py      # prepara visor/datos/: relieve, capas y repasos (~25 min)
```

El visor es la parte del proyecto pensada para alguien que no va a leer este
README. Es un mapa en relieve de la región, mirado desde el mar hacia la
cordillera, con cada provincia pintada del color de su nivel. Se pueden repasar
temporales reales hora a hora, y las activaciones que reportó la prensa aparecen
en el mapa el día en que ocurrieron. El panel explica cada momento en palabras
simples: qué nivel tiene cada provincia, cuánta lluvia lleva y cuánta falta para
el nivel siguiente, qué tramos de ruta vigilar y qué quebradas se activaron. Un
botón explica cómo funciona, qué tan confiable es y qué no hace.

Trae cinco escenarios. Los cuatro repasos se eligieron para contar tanto lo que
el modelo hace como lo que no:

* **Hoy**: el boletín en vivo del momento en que se generaron los datos.
* **Julio de 2026**: el peor temporal en cuarenta años.
* **Agosto de 2026**: el bloque de deshielo.
* **Fines de julio de 2025**: otro acierto, en otro invierno.
* **Junio de 2025**: donde falló, con una falsa alarma el 11 y una falla el 16.

Cada hora del repaso es lo que la alerta en vivo (`m6_alerta_en_vivo.evaluar`)
habría dicho a esa hora, no lo que se supo después.

**Por qué el mapa base sale del DEM del proyecto.** El visor se publica como una
página que no puede pedir nada a servidores ajenos, ni siquiera teselas de
OpenStreetMap. El relieve se arma entonces con Copernicus GLO-30, que además es
el terreno sobre el que se calcularon las cuencas, en tres imágenes de la misma
grilla:

* la altura en terrain-RGB;
* un sombreado con tonos de tierra;
* el número de provincia de cada píxel, para teñirla del color de su nivel.

La malla 3D se arma en el navegador, con el relieve exagerado tres veces en
altura. Está hecho con deck.gl, sin servidor, y en un teléfono usa la mitad de
resolución.

**Una verificación que vale la pena contar.** La primera versión mostraba Los
Vilos sobre el mar: la textura estaba invertida de norte a sur, y con las tres
provincias en rojo no se notaba. Se vio al mirar un paso con niveles distintos
por provincia.

Para verlo en local:

```bash
python -m http.server 8765 --directory visor
```

Se abre en `http://localhost:8765/_local.html`, una envoltura que genera
`m6_visor.py`: `index.html` no trae `<!doctype>` porque el servicio donde se
publica la agrega. Para publicarlo se sube `index.html` con `app.js` y
`datos/`.

---

## Hoja de ruta

- [x] **M0 — Andamiaje**: repo, estructura, README, primer commit.
- [x] **M1 — Terreno**: DEM descargado; cuencas y red de quebradas delineadas.
- [x] **M2 — Susceptibilidad**: mapa de quebradas rankeadas por peligro (razón de Melton).
- [x] **M3 — Exposición**: cruce con red vial y zonas urbanas → 3.669 puntos de corte en 14 comunas.
- [x] **M4 — Gatillo de lluvia**: tres inviernos, 1.188 episodios de 30 min; lluvia de cada cuenca interpolada con random forest.
- [x] **M5 — Validación y calibración**: 33 activaciones de 2026 y 44 de 2024-2025. Con negativos, Caine publicado tiene precisión de 4,5% (cota inferior) y calibrar baja el umbral sin mejorar el AUC.
- [x] **M1 — Unidades troncales**: 93 quebradas de más de 50 km² como segunda clase de unidad. El satélite confirma que son el objeto que se activa; la lluvia de pluviómetros no las distingue entre sí.
- [x] **M3/M5 — La prueba de una autoridad**: 11 cortes de ruta reales contra la lista de exposición, y la alerta por provincia y temporal. Con la clase inundación y el área drenada, el 3% de arriba de la lista cubre 4 cortes contra 1,0 al azar. Caine dice bien *cuándo* (precisión 0,80 por temporal) y mal *dónde* (en Elqui no se activa nunca).
- [x] **Indicador de deshielo (experimental)**: nieve de VIPNET e isoterma 0 desde las estaciones altas. Ve el bloque de agosto de 2026 y no se activa nunca en 2024 ni 2025; con un solo evento, no está validado.
- [x] **Niveles de alerta por provincia**: lluvia del temporal como fracción de la normal de CR2MET; amarilla 21%, naranja 27%, roja 35%. Probados en 2026 sin un error de orden; en validación cruzada, AUC 0,95 contra 0,88 de Caine.
- [x] **M6 — Alerta en vivo**: boletín por provincia con datos de VIPNET, mismas reglas que la calibración (41 de 41 niveles iguales al repasar tres inviernos). Probada contra el temporal real del 6 de octubre de 2026.
- [ ] **Pronóstico**: la lluvia esperada para los próximos 1 a 3 días, para que la alerta sea anticipada y no solo en curso.
- [ ] **Atacama como prueba independiente**: los niveles de Coquimbo aplicados a otra región, con su propio inventario de prensa. VIPNET tiene 68 estaciones allí y el temporal de julio de 2026 activó quebradas en Huasco y Copiapó.
- [ ] **Lluvia antecedente**: la segunda variable de los niveles, cuando haya positivos para ajustarla.
- [ ] **Lluvia con resolución espacial**: radar o satélite corregido contra estaciones. Es hoy el límite del modelo.
- [x] **M6 — Visor**: Vigía de quebradas, un mapa en relieve con las provincias del color de su nivel, repaso de cuatro temporales reales hora a hora, fichas y una explicación para cualquier persona.

M0 a M3 forman la versión mínima mostrable (v0). M4 y M5 son calibración y
validación (v1).

---

## Fuentes de datos

| Dato | Fuente | Acceso |
|---|---|---|
| Modelo de elevación (DEM) | Copernicus GLO-30 (TanDEM-X, 30 m) | Libre, sin registro |
| Precipitación climatológica | CR2MET v2.5 (CR2), normal 1991-2020, en uso desde octubre de 2026 | Libre, sin registro (Zenodo) |
| Lluvia, temperatura y nieve sub-diarias | VIPNET (MOP), API REST | Libre, sin registro |
| Precipitación evento jul-2026 | Estaciones DGA/DMC + GPM IMERG | Libre |
| Geología / peligro | SERNAGEOMIN | Libre |
| Red vial y urbana | OpenStreetMap, extracto de Chile de Geofabrik | Libre, sin registro |
| Validación satelital | Sentinel-1 / Sentinel-2 (Copernicus) | Libre (registro) |

Sobre el DEM: la primera versión de este README apuntaba a ALOS PALSAR de
"12,5 m". Ese producto se descartó. Los RTC de alta resolución se generan desde
NED13, que solo cubre Estados Unidos, o desde SRTM de 30 m, y para Chile aplica
el segundo caso. La documentación de ASF dice que esos productos vienen
remuestreados hacia arriba desde la versión de 30 m, o sea que los píxeles miden
12,5 m pero el detalle real sigue siendo de 30 m. Copernicus GLO-30 entrega 30 m
reales derivados de TanDEM-X: a igual resolución efectiva es mejor dato y pesa
seis veces menos.

---

## Stack

Python (rasterio, geopandas, scikit-learn), GRASS GIS o pysheds para hidrología,
QGIS para visualización y Google Earth Engine para lo satelital.

---

## Reproducibilidad

Toda cifra de este README sale de una corrida guardada en
[`docs/corridas/`](docs/corridas/), con la salida de consola completa y las
verificaciones derivadas anotadas al final.

La corrida de referencia es
[`2026-10-10_subcuencas_confluencia.txt`](docs/corridas/2026-10-10_subcuencas_confluencia.txt),
que cubre M1 extendido, M2, M3 y M4 sobre las 3.757 unidades, con la cobertura
del DEM verificada al 100% de la superficie regional y el extracto de OSM del 8
de octubre. M4 y M5 sobre tres inviernos están en
[`2026-10-10_m4_tres_inviernos.txt`](docs/corridas/2026-10-10_m4_tres_inviernos.txt)
y [`2026-10-10_m5_tres_inviernos.txt`](docs/corridas/2026-10-10_m5_tres_inviernos.txt).

Quedan guardadas también las dos corridas previas del mismo día, sobre las 444
cuencas costeras: [`2026-10-10_reconstruccion_m1_m2_m4.txt`](docs/corridas/2026-10-10_reconstruccion_m1_m2_m4.txt)
y [`2026-10-10_m3_exposicion.txt`](docs/corridas/2026-10-10_m3_exposicion.txt).
No son material histórico sin uso: son la línea base contra la que se comprueba
que las subcuencas no movieron nada de lo que ya existía.

Esto existe porque durante un tiempo no fue así. Entre el 7 y el 23 de agosto de
2026 el repositorio reportaba cifras de una corrida remota que no se podían
reproducir en local, sobre un DEM al que le faltaba el tercio sur de la región.
El capítulo 12 del recorrido cuenta el episodio completo. La regla que quedó: si
un número no salió de una corrida guardada en `docs/corridas/`, no entra a este
README.

### La segunda vez que la regla sirvió

El 19 de septiembre de 2026 se perdió el disco de trabajo. Lo que estaba
commiteado volvió de GitHub; lo que no, no volvió. Se perdieron `data/raw/`
completo y **el código de M4, que nunca se había commiteado**. Sobrevivió solo
esta sección del README, que lo documentaba.

M4 se reescribió desde esa documentación y la corrida del 10 de octubre
reproduce al decimal sus cifras de control —La Serena 150,9 mm en julio, los
409,5 mm de CUNCUMEN por acumulado contra 208,0 por incrementos, los 25,2 mm de
desajuste de LAMBERT— además de las 107 estaciones de R1 y las 167 cuencas
susceptibles que entonces tenia el modelo. Los conteos no dan idénticos
porque VIPNET rellenó huecos entre agosto y octubre; está medido y anotado en la
corrida.

De paso aparecieron tres errores que el código perdido tenía y esta versión no:
estaciones que desaparecían por no transmitir en punto, pasos de recuperación
contados como picos de intensidad, y la falta del filtro de cuencas susceptibles.

La lección es más barata de escribir que de aprender: **documentar sirvió para
reconstruir el código, pero no reemplaza al commit**.

---

## Documentación adicional

[`docs/contexto.md`](docs/contexto.md) reúne el alcance del proyecto, las dos
mitades del modelo (susceptibilidad y gatillo), los criterios con que se
eligieron las fuentes de datos, las convenciones del repositorio y los puntos
donde este tipo de modelo suele fallar.
