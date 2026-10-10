# alerta-aluviones

Modelo de riesgo de activación de quebradas para la Región de Coquimbo, Chile.
Predice qué quebradas se activan ante una lluvia dada y qué rutas y zonas urbanas
quedan expuestas. Se valida contra el temporal de julio de 2026, el peor en unos
cuarenta años.

---

## Qué hace

1. **Susceptibilidad**: mapea qué quebradas son propensas a generar flujos de
   detritos, usando el modelo de elevación (pendiente, acumulación de flujo,
   geología).
2. **Gatillo**: calibra el umbral de lluvia (intensidad × duración) sobre el cual
   cada quebrada se activa.
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
python src/m1_limite_region.py                                  # arma el limite regional desde el zip de la BCN
python src/m1_terreno.py --umbral-km2 0.15 --area-min-km2 0.4   # rellena, calcula flujo, delinea cuencas
python src/m1_recortar_region.py                                # deja solo las que descargan en Coquimbo
```

El segundo necesita el zip de división regional de la
[Mapoteca de la BCN](https://www.bcn.cl/siit/mapas_vectoriales), sin
descomprimir, en `data/raw/Regiones.zip`. Produce `limite_coquimbo.gpkg`, que es
el polígono contra el que `src/cobertura.py` comprueba que el DEM cubra la región
antes de calcular nada. Hasta octubre de 2026 ese archivo simplemente estaba en
disco, sin fuente anotada: cuando se perdió `data/raw/` no había forma de
regenerarlo, y la salvaguarda que vigila a los otros cinco scripts era la única
pieza del repositorio que no se podía reconstruir.

Los dos parámetros que vale la pena mover están en el segundo. `--umbral-km2`
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
El tercer script filtra al final y conserva las cuencas completas cuya
desembocadura cae dentro de Coquimbo.

### Resultado de M1

Con los parámetros de arriba se delinean 950 cuencas sobre el área con margen, de
las cuales 444 descargan dentro de la región. Suman 39.523 km² y 134.329 tramos
de quebrada, y cubren el 96% de la superficie regional. El 4% restante drena
hacia Atacama, Valparaíso o Argentina, así que esas cuencas le pertenecen a la
región vecina.

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

De las 444 cuencas de la región, las dos columnas dan esto:

| Clase | `clase` (Wilford completo) | `clase_melton` (solo Melton) |
|---|---|---|
| Flujo de detritos | 21 | 33 |
| Crecida de detritos | 146 | 134 |
| Inundación | 277 | 277 |

La razón de Melton máxima es 1,009 y la pendiente media máxima, 24,9°. Ninguna
cuenca quedó marcada como `borde_truncado`.

Las 21 cuencas críticas miden entre 0,43 y 1,07 km², así que a escala regional
son invisibles. El mapa las marca con un círculo en la desembocadura, que es
además el punto que le importa a M3: por ahí sale el material hacia rutas y
poblados.

La diferencia entre las dos columnas importa, y ahora está medida: **12 cuencas
cambian de clase según el criterio de largo**. Las 12 son las más energéticas de
la región y quedan descartadas solo por ser alargadas, algunas por decenas de
metros sobre el umbral: la primera del ranking, con Melton 1,01, mide 2,84 km de
largo contra un umbral de 2,7. Ese umbral es el parámetro heredado de otra región
y es lo primero que M5 debería recalibrar.

### Un límite estructural de M2, que conviene decir antes que lo pregunten

Las 21 cuencas críticas están todas en la franja costera: sus desembocaduras caen
entre las longitudes −71,71 y −71,29, y ninguna se extiende al este de −71,27. La
región llega hasta −69,81.

No es que el interior no tenga quebradas peligrosas. Es que M1 define una
desembocadura como la última celda con terreno antes del vacío, o sea la costa,
así que toda quebrada del interior es afluente del Elqui, del Limarí o del Choapa
y no recibe cuenca propia. Queda absorbida en una cuenca de diez mil kilómetros
cuadrados cuyo Melton es bajo por construcción, porque el área va en el
denominador.

El reparto lo muestra sin ambigüedad: **4 cuencas concentran el 82,9% de la
superficie drenada** y las cuatro son de clase inundación, mientras que las 380
cuencas que caen dentro del rango donde Melton está calibrado (≤ 10 km²) suman el
1,7%.

O sea que hoy el índice solo *ve* las quebradas que descargan al mar. Para el
temporal de julio de 2026, cuyos cortes de ruta ocurrieron en buena parte en
valles interiores, esta es la limitación de fondo del modelo y no un detalle. La
salida es subdividir las cuencas grandes por sus confluencias en vez de cortarlas
solo en el mar, y es trabajo de M5 con el evento a la vista.

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

De las 444 cuencas de la región, 167 son susceptibles (21 de flujo de detritos y
146 de crecida) y a las 167 se les trazó el cauce principal, con un largo mediano
de 1,80 km. Contra 46.440 tramos de vía, salen **422 puntos de corte**.

| Jerarquía de la vía | Cortes | Peso |
|---|---|---|
| track (huella rural) | 122 | 0,10 |
| residential | 91 | 0,30 |
| unclassified | 79 | 0,30 |
| **motorway** | **73** | **1,00** |
| service | 24 | 0,15 |
| tertiary | 20 | 0,45 |
| living_street | 8 | 0,20 |
| motorway_link | 5 | 0,15 |

Por comuna: Coquimbo 117, La Higuera 94, La Serena 79, Ovalle 49, Canela 42,
Los Vilos 40 y Salamanca 1. Por clase de la cuenca de origen, 351 vienen de
crecida de detritos y 71 de flujo de detritos.

Los 73 cortes sobre la Ruta 5 Norte son el resultado que le da sentido al hito:
es la vía troncal del país cruzando, una por una, las quebradas costeras que M2
marcó como capaces. Diez de esos cortes tienen prioridad 1,00, el máximo posible,
por combinar una cuenca de flujo de detritos con una vía de peso máximo.

Un límite de la tabla de vías: 265 de los 422 cortes caen en vías sin nombre en
OpenStreetMap, casi todas huellas y caminos sin clasificar. El ranking por nombre
solo describe a los 157 restantes.

**El reporte de localidades alcanzadas está subestimado y no debe citarse.** M3
filtra las zonas urbanas a polígonos, y en la Región de Coquimbo las localidades
—La Serena, Coquimbo, Tongoy, Combarbalá, Monte Patria— están mapeadas como
puntos, 1.113 en total, que ese filtro descarta. Lo que hoy se reporta como
localidad sale del nombre de los polígonos de uso de suelo, que son barrios y
sitios. Decidir si una trayectoria que pasa cerca de un punto poblado cuenta como
alcance urbano es una decisión de modelo y queda para M5.

---

## Cómo se corre M4

```bash
python src/m4_lluvia.py              # usa el cache de data/raw/lluvia/
python src/m4_lluvia.py --refrescar  # vuelve a pegarle a VIPNET
python src/m4_umbrales.py            # imprime los umbrales con sus citas
```

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

Las 167 cuencas evaluadas no son las 444 de la región, sino las que M2 declaró
capaces de algo más que agua limpia: 21 de flujo de detritos y 146 de crecida de
detritos. Preguntarle a una cuenca de clase inundación si supera un umbral de
flujos de detritos no significa nada. La mediana de distancia de una cuenca a su
estación es de **15,9 km**, bajo el criterio de 30 km fijado antes de mirar.

**Cuencas que superan cada umbral: 2 de 167 para Caine (1980), 0 de 167 para Ben
David-Novak et al. (2004).** Ninguna supera un umbral y no el otro.

Y esos dos positivos hay que leerlos con cuidado, porque el propio M4 los
desconfía y lo dice en pantalla:

* La cuenca 305 está asignada a **RIO CUNCUMEN ANTES JUNTA CHOAPA**, una de las
  estaciones marcadas como ambiguas: registra 962,0 mm en la ventana contra
  409,5 mm de CUNCUMEN, a 2,2 km.
* La cuenca 805 depende de un episodio de **QUILIMARÍ que dura un solo paso de
  30 minutos**: el contador salta de 1,3 a 15,5 mm y queda plano siete horas a
  cada lado. La lluvia real no da escalones. Y como media hora es la duración
  mínima posible, cualquier paso sobre ~9,7 mm supera Caine por construcción.

**Descontados los dos, ninguna cuenca supera ningún umbral en toda la ventana.**
El resultado de M4 es, en la práctica, negativo.

### El hallazgo principal, que es un resultado negativo

Casi todos los pares cuenca-episodio caen **debajo** de las dos curvas, y no por
poco: sobre los 476 pares, la razón mediana entre la intensidad medida y la que
Caine pide es **0,35**. Es decir que el episodio típico llega a un tercio de lo
que el umbral exige, en una ventana donde hubo activaciones documentadas.

> El control fino contra las siete quebradas con activación documentada
> —`outputs/m4_control_cordura.csv`— **no se regeneró** en la corrida de octubre:
> depende de un inventario de activaciones que no estaba en el código
> recuperable. Es trabajo de M5 y queda declarado como pendiente.

Esto no invalida el pipeline —las series reproducen el control externo al
decimal— pero dice algo sustantivo: **un umbral I-D global no describe este
régimen**. El temporal de julio fue largo y suave, no corto e intenso, y las
quebradas se activaron por acumulación y saturación antes que por intensidad. Es
coherente con Vergara Dal Pont et al. (2018), que para la cuenca media del Elqui
concluye que estos flujos se generan por escorrentía y no por deslizamiento.

La lluvia antecedente apunta en la misma dirección y está medida. **35 episodios
llegan con más de 50 mm acumulados en las 72 horas previas y ninguno de ellos
supera Caine.** Los casos extremos son elocuentes: el episodio del 19 de julio en
RIO CHOAPA EN SALAMANCA arrastra **265,6 mm de lluvia antecedente en 72 horas** y
aun así se queda en 2,3 mm/h de intensidad media; el de CAIMANES, 239,4 mm con
2,1 mm/h. Un suelo con esa cantidad de agua encima no necesita un chaparrón para
soltar material, y **un umbral que solo mira I y D no ve nada de eso**.

Ahí está, medida, la variable que le falta al modelo. Esas columnas ya se
escriben en `m4_episodios.csv` y son el punto de partida de M5.

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
| `data/processed/gatillo.gpkg` | 476 filas, una por cuenca y episodio, con D, I, antecedente 24/72/168 h, distancia y área, y una columna por umbral |
| `outputs/m4_umbral_id.png` | log-log con las curvas y los episodios encima |
| `outputs/m4_episodios.csv` | los 448 episodios, legibles sin abrir un SIG |
| `outputs/m4_control_cordura.csv` | *pendiente*: las 7 quebradas documentadas contra los umbrales. Necesita el inventario de activaciones, que es trabajo de M5 |
---

## Hoja de ruta

- [x] **M0 — Andamiaje**: repo, estructura, README, primer commit.
- [x] **M1 — Terreno**: DEM descargado; cuencas y red de quebradas delineadas.
- [x] **M2 — Susceptibilidad**: mapa de quebradas rankeadas por peligro (razón de Melton).
- [x] **M3 — Exposición**: cruce con red vial y zonas urbanas → 422 puntos de corte.
- [x] **M4 — Gatillo de lluvia**: 448 episodios de 30 min y umbrales publicados aplicados.
- [ ] **M5 — Validación**: comparación contra los tres episodios de 2026 y métricas.
- [ ] **M6 — Entrega**: mapa o visor final y documentación.

M0 a M3 forman la versión mínima mostrable (v0). M4 y M5 son calibración y
validación (v1).

---

## Fuentes de datos

| Dato | Fuente | Acceso |
|---|---|---|
| Modelo de elevación (DEM) | Copernicus GLO-30 (TanDEM-X, 30 m) | Libre, sin registro |
| Precipitación climatológica | CR2MET (CR2) | Libre |
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
verificaciones derivadas anotadas al final. La corrida de referencia de M1, M2 y
M4 es
[`2026-10-10_reconstruccion_m1_m2_m4.txt`](docs/corridas/2026-10-10_reconstruccion_m1_m2_m4.txt),
hecha en local sobre el DEM completo, con la cobertura verificada al 100% de la
superficie regional. La de M3 es
[`2026-10-10_m3_exposicion.txt`](docs/corridas/2026-10-10_m3_exposicion.txt),
sobre el extracto de OSM del 8 de octubre.

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
desajuste de LAMBERT— además de las 107 estaciones de R1, las 167 cuencas
susceptibles y los 15,9 km de distancia mediana. Los conteos no dan idénticos
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
