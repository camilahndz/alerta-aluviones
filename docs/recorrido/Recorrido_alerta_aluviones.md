<!-- Recorrido explicativo de alerta-aluviones — fuente para NotebookLM. Generado el 16 de agosto de 2026. -->


<!-- ===== CAPITULO 00: Índice (Portada y modo de empleo) ===== -->

# Recorrido explicativo de alerta-aluviones

Esta es una guía de lectura del repositorio `alerta-aluviones`, el modelo de
riesgo de activación de quebradas para la Región de Coquimbo. Está escrita para
que puedas abrir el proyecto, entender cada decisión y defenderla ante alguien
que sepa más que tú del tema.

El documento parte desde cero. No asume que sabes qué es un modelo de elevación,
ni qué es un sistema de coordenadas, ni qué es una cuenca, ni qué significa
delinear. Cada término se define en una línea la primera vez que aparece.

## Una nota antes de empezar

Durante buena parte de agosto de 2026 esta portada llevaba una advertencia: las
cifras del README no se podían reproducir corriendo el código en local, porque
salían de un servidor remoto y el DEM que había en el computador cubría menos
territorio. **Eso está resuelto.** El 23 de agosto de 2026 M1 y M2 se volvieron a
correr en local sobre el DEM completo, con la cobertura verificada al 100% antes
de calcular, y la salida quedó guardada en
`docs/corridas/2026-08-23_m1_m2.txt`. Todas las cifras que verás salen de ahí.

Conviene leer el capítulo 12 igual, porque el episodio es de las mejores piezas
del proyecto: un error que no daba error sino un número plausible, cómo se
detectó, y qué se construyó para que no vuelva a pasar. Ya no es una advertencia
sobre lo que el repositorio no puede demostrar; es el registro de un problema
diagnosticado y cerrado.

Lo que sí queda abierto está en ese mismo capítulo, y es de otro tipo: una
limitación de método que la corrida completa dejó a la vista y que M5 tendrá que
resolver.

## Cómo leer esto

Lo más cómodo es abrir Visual Studio Code con la carpeta `alerta-aluviones` como
carpeta de trabajo y tener este documento al lado. Cada vez que aparece una ruta
como `src/m2_susceptibilidad.py` se trata de un archivo real.

Los capítulos van en orden. Los tres primeros no tienen código. Del 04 al 09 se
recorren los módulos en el orden en que se ejecutan, que es también el orden en
que el proyecto fue creciendo. El 10 y el 11 son material de entrevista, el 12 es
el episodio del DEM parcial y el estado honesto del proyecto, y el 13 es el
glosario.

## Índice

| # | Capítulo | De qué trata |
|---|----------|--------------|
| 01 | Qué es el proyecto | El temporal de julio de 2026 y la pregunta que el modelo intenta responder |
| 02 | Conceptos base | DEM, píxel, raster y vector, sistema de coordenadas, cuenca, aluvión |
| 03 | Estructura del repositorio | Las cuatro carpetas de datos y la regla que las gobierna |
| 04 | Conseguir el terreno | `m1_preparar_dem.py`: por qué se descartó un DEM que parecía mejor |
| 05 | De alturas a quebradas | `m1_terreno.py`: relleno, dirección de flujo, acumulación, cuencas |
| 06 | Quedarse con Coquimbo | `m1_recortar_region.py`: por qué se procesa de más y se filtra al final |
| 07 | Qué cuencas pueden generar un aluvión | `m2_susceptibilidad.py`: la razón de Melton y las dos clasificaciones |
| 08 | El parámetro que cambió todo | La historia del `--area-min-km2`, de 1 cuenca a 18 |
| 09 | Dónde el flujo cruza lo que la gente usa | `m3_exposicion.py`: cauces, rutas y puntos de corte |
| 10 | El control de calidad | La comparación contra las áreas oficiales de la DGA |
| 11 | Decisiones y defensa | Cada decisión con su respuesta de 30 segundos |
| 12 | El error que no daba error | El pipeline corrió sobre el 40% del territorio sin avisar: cómo se detectó y qué se construyó |
| 13 | Glosario | Todos los términos, en un solo lugar |

## Qué tamaño tiene esto

| Archivo | Líneas | De qué se encarga |
|---------|--------|-------------------|
| `src/m1_preparar_dem.py` | 323 | Descargar el modelo de elevación, unirlo y reproyectarlo |
| `src/m1_terreno.py` | 651 | Hidrología: de alturas a red de quebradas y cuencas |
| `src/m1_recortar_region.py` | 231 | Filtrar las cuencas que descargan en Coquimbo |
| `src/m2_susceptibilidad.py` | 402 | Clasificar cada cuenca por su capacidad de generar aluviones |
| `src/m3_exposicion.py` | 825 | Cruzar los cauces con rutas y zonas urbanas |
| `src/compat_pysheds.py` | 25 | Un parche de cuatro líneas sin el cual nada corre |

Son unas 2.450 líneas de Python. Es el proyecto más grande de tu portafolio, y
también el que tiene el razonamiento más denso por línea.

<!-- ===== CAPITULO 01: Qué es el proyecto (El problema, sin código) ===== -->

# 01 — Qué es el proyecto

> **Qué vas a entender al terminar este capítulo**
>
> - Qué pasó en Coquimbo en julio de 2026 y por qué el proyecto nace de ahí.
> - Qué pregunta concreta intenta responder el modelo.
> - Las dos mitades del problema, y cuál está construida y cuál no.
> - Qué produce hoy y qué no produce todavía.

## El problema, sin código

En julio de 2026 la Región de Coquimbo tuvo el peor temporal en unos cuarenta
años. Hubo fallecidos, del orden de 99 mil personas quedaron aisladas y se
registraron más de cuarenta cortes de ruta.

Ese aislamiento es la clave del proyecto. La gente no quedó aislada porque le
cayera agua encima, sino porque **las quebradas se activaron y cortaron los
caminos**. Una quebrada seca durante años se convierte, en unas horas de lluvia
intensa, en un torrente de barro y piedras que baja por su cauce y arrasa lo que
cruce por delante. Cuando ese cauce cruza una ruta, la ruta desaparece, y las
localidades que dependían de ella quedan incomunicadas.

Chile tiene mapas de dónde están las quebradas y tiene pronósticos de lluvia. Lo
que no tiene, a escala regional y de acceso libre, es la unión de ambas cosas:
**dado un pronóstico, qué quebradas se van a activar y qué rutas van a quedar
cortadas.** Esa es la pregunta del proyecto.

## Las dos mitades del modelo

Para responderla hacen falta dos cosas distintas, y conviene tenerlas separadas
porque el proyecto está construido sobre esa separación.

La **susceptibilidad** responde *cuáles quebradas son capaces* de generar un
aluvión. Es una propiedad del terreno: depende de qué tan empinada es la cuenca,
cuánto desnivel tiene, qué tamaño, qué material hay en el suelo. No cambia de un
día para otro, así que se calcula una vez.

El **gatillo** responde *cuánta lluvia hace falta* para que una quebrada capaz se
active de verdad. Es un umbral que combina intensidad y duración: no es lo mismo
que caigan 40 milímetros en dos días que en dos horas.

Ninguna de las dos sirve sola. Una quebrada capaz sin lluvia suficiente no pasa
nada, y una lluvia enorme sobre terreno tendido produce inundación de agua limpia
pero no un aluvión. El riesgo aparece en la intersección.

**Hoy el proyecto tiene construida la susceptibilidad y no tiene el gatillo.** Esa
es la distinción más importante de todo el documento y la que hay que tener clara
antes de describir el proyecto a nadie.

## Los seis hitos

El proyecto está organizado en hitos, y cada uno depende del anterior:

| Hito | Qué hace | Estado |
|------|----------|--------|
| **M0** | Andamiaje: repositorio, estructura, README | Cerrado |
| **M1** | Terreno: descargar el DEM, delinear quebradas y cuencas | Cerrado |
| **M2** | Susceptibilidad: clasificar cada cuenca por su peligro | Cerrado |
| **M3** | Exposición: cruzar los cauces con rutas y zonas urbanas | Código escrito, sin corrida validada |
| **M4** | Gatillo de lluvia: el umbral intensidad-duración | No empezado |
| **M5** | Validación: comparar contra julio de 2026 | No empezado |
| **M6** | Entrega: mapa o visor final | No empezado |

M0 a M3 forman la versión mínima mostrable. Con eso el proyecto ya puede decir
*"estas quebradas cortan estas rutas"*, que es una frase con sentido para alguien
que no sabe hidrología. M4 y M5 son lo que convertiría el modelo en algo
predictivo y comprobado.

## Por qué el temporal es la pieza que hace valioso al proyecto

El evento de julio de 2026 cumple dos funciones a la vez, y esa doble función es
lo que distingue este proyecto de un ejercicio de curso.

Es el **origen**: el problema no salió de una lista de ideas sino de algo que
ocurrió, en la región donde vives, con consecuencias documentadas.

Y es el **conjunto de validación**: como se sabe qué rutas se cortaron
realmente, existe una respuesta correcta contra la cual comparar la predicción
del modelo. La mayoría de los proyectos de portafolio no tiene eso. Un modelo que
predice algo sin forma de verificar si acertó es una opinión con matemáticas
encima; uno que se puede contrastar contra un evento real es un modelo.

Eso es M5, y todavía no está hecho. Pero el dato existe y está identificado, que
es lo que permite decir en una entrevista que la validación tiene un plan
concreto y no es una intención.

## Qué NO es el proyecto

Vale la pena cerrar con los límites, porque en una entrevista técnica es donde
apunta la pregunta difícil.

**No es un modelo de propagación.** El código no calcula hasta dónde llega el
material ni con qué espesor; eso requiere resolver la física del flujo y está
explícitamente fuera de alcance. Lo que hace M3 es suponer que el material baja
por el cauce, que es una hipótesis razonable pero es una hipótesis.

**No predice cuándo.** Sin el gatillo de lluvia, el modelo dice qué quebradas son
capaces, no cuáles se van a activar mañana.

**No está validado.** M5 no existe, así que no hay ninguna métrica de acierto.

**Los puntos de corte son candidatos, no predicciones.** Cada uno es un lugar
donde una vía cruza el cauce de una quebrada susceptible. Que ese corte ocurra
depende del gatillo y del volumen movilizado, que el proyecto no estima.

---

## Cómo se lo explicarías a alguien en 60 segundos

En julio de 2026 el peor temporal en cuarenta años dejó a unas 99 mil personas
aisladas en la Región de Coquimbo, no por el agua sino porque las quebradas se
activaron y cortaron más de cuarenta rutas. El modelo responde qué quebradas
pueden generar un aluvión y qué rutas quedan expuestas. Tiene dos mitades: la
susceptibilidad, que es una propiedad del terreno y ya está construida, y el
gatillo de lluvia, que dice cuánta agua hace falta y todavía no. Parto de un
modelo de elevación satelital, deduzco por dónde escurre el agua, delineo las
cuencas, y clasifico cada una con un índice publicado y calibrado contra eventos
reales, no con pesos inventados. Lo que lo hace validable es que el temporal de
julio es a la vez el origen del proyecto y el conjunto de prueba: sé qué rutas se
cortaron de verdad, así que hay una respuesta correcta contra la cual comparar.

<!-- ===== CAPITULO 02: Conceptos base (El vocabulario mínimo) ===== -->

# 02 — Conceptos base

> **Qué vas a entender al terminar este capítulo**
>
> - Qué es un DEM y qué guarda cada píxel.
> - La diferencia entre raster y vector, que organiza todo el proyecto.
> - Qué es un sistema de coordenadas y por qué hay que cambiar de uno a otro.
> - Qué es una cuenca, una quebrada y un flujo de detritos.

## 1. DEM: el terreno como una grilla de números

**DEM** significa *Digital Elevation Model*, o sea modelo digital de elevación. Es
una imagen donde cada píxel, en vez de guardar un color, guarda **la altura del
terreno en ese punto, en metros sobre el nivel del mar**.

Un DEM de 30 metros significa que cada píxel cubre un cuadrado de 30 por 30
metros en el suelo. Toda la Región de Coquimbo, que son unos 40 mil kilómetros
cuadrados, cabe entonces en una grilla de decenas de millones de píxeles.

Lo notable, y lo que hace posible el proyecto entero, es que **de esa única capa
de alturas se puede deducir por dónde escurre el agua**. No hace falta ningún
dato de ríos: el agua baja, y si sabes la altura de cada punto sabes hacia dónde
baja. Los capítulos 05 y 09 son enteramente eso.

## 2. Raster y vector

Hay dos formas de guardar información geográfica, y el proyecto usa las dos.

Un **raster** es una grilla de píxeles, como una foto. Sirve para cosas que
existen en todas partes y varían de forma continua: la altura del terreno, la
temperatura, la cantidad de agua que pasa por cada punto. El formato que usa el
proyecto es **GeoTIFF**, que es una imagen TIFF con la información de a qué
coordenadas del planeta corresponde cada píxel.

Un **vector** es un conjunto de formas geométricas con atributos: puntos, líneas
y polígonos. Sirve para cosas que tienen bordes definidos: el contorno de una
cuenca, el trazado de una ruta, la ubicación de una desembocadura. El formato que
usa el proyecto es **GeoPackage** o **GeoJSON**.

La división del trabajo en este proyecto es limpia. Los cálculos hidrológicos se
hacen sobre rasters, porque el agua escurre píxel a píxel. Los resultados se
guardan como vectores, porque una cuenca es un polígono y una quebrada es una
línea. Las librerías reflejan esa división: `rasterio` para rasters, `geopandas`
para vectores.

## 3. Sistema de coordenadas

Un **sistema de coordenadas de referencia**, abreviado **CRS**, es la regla que
dice cómo se traduce un punto del planeta a un par de números. Hay muchos, y elegir
el correcto no es un detalle administrativo.

El más conocido es **EPSG:4326**, o sea latitud y longitud en grados. Su problema
para este proyecto es que un grado no mide lo mismo en todas partes: un grado de
longitud son unos 111 kilómetros en el ecuador y menos de 100 en Coquimbo. Si
calculas el área de una cuenca en grados, el número no significa nada.

Por eso el proyecto convierte todo a **EPSG:32719**, que es UTM zona 19 Sur, el
sistema métrico que corresponde a esta parte de Chile. La frase que usa el
comentario del código lo resume mejor que cualquier definición: *"lo reproyecta a
UTM 19S, que es donde un metro mide un metro"*.

**Reproyectar** es justamente eso: convertir una capa de un sistema a otro. Es lo
último que hace el primer script, y es lo que permite que todos los cálculos
posteriores hablen en metros y kilómetros cuadrados de verdad.

## 4. Cuenca, quebrada, desembocadura

Una **cuenca** es todo el territorio cuya agua de lluvia termina saliendo por un
mismo punto. Si dibujas la línea que separa dos cuencas —la divisoria de aguas—
la gota que cae de un lado va a un río y la que cae del otro va a otro. La cuenca
es la unidad natural del análisis, porque es la superficie que alimenta a una
quebrada determinada.

Una **quebrada** es un cauce, o sea el fondo del valle por donde el agua se
concentra y escurre. En el norte de Chile la mayoría están secas casi todo el
año, lo que las hace fáciles de subestimar.

La **desembocadura**, que el código llama *salida*, es el punto por donde el agua
abandona la cuenca. En este proyecto es el último píxel con terreno antes del mar
o antes del borde del área analizada, y es un punto importante porque es por ahí
por donde el material sale hacia rutas y poblados.

**Delinear** una cuenca significa determinar exactamente qué píxeles le
pertenecen, o sea dibujar su contorno a partir de las alturas.

## 5. Aluvión y flujo de detritos

Aquí hay una distinción técnica que el proyecto usa constantemente y que conviene
tener precisa, porque los tres casos se ven parecidos desde lejos y tienen
consecuencias muy distintas.

Una **inundación de agua** es agua más o menos limpia desbordándose. Hace daño,
pero es agua.

Una **crecida de detritos** es agua con bastante material arrastrado. Intermedio.

Un **flujo de detritos** es lo que en Chile se llama **aluvión**: barro, piedras y
bloques moviéndose como una masa densa, más parecida a hormigón fluyendo que a
agua. Es lo que destruye puentes y arrasa casas, y es lo que el proyecto quiere
identificar.

Lo que determina cuál de los tres ocurre es **la energía de la cuenca**. Una
cuenca chica y muy empinada le da al agua suficiente energía para arrastrar
material grueso; una cuenca grande y tendida no, por mucha agua que reciba. El
capítulo 07 explica cómo se mide esa capacidad con un solo número.

## 6. Las librerías

| Librería | Para qué |
|----------|----------|
| `rasterio` | Leer y escribir rasters georreferenciados |
| `geopandas` | Trabajar con capas vectoriales como si fueran tablas |
| `pysheds` | La hidrología: relleno, dirección de flujo, acumulación, cuencas |
| `numpy` / `scipy` | Cálculo numérico sobre las grillas |
| `osmnx` | Bajar rutas y zonas urbanas desde OpenStreetMap |
| `matplotlib` | Las figuras de control |

Vale la pena notar que `requirements.txt` no solo lista las librerías sino que
explica un pin de versión:

```
# El pin >=2.0 no es cosmetico: osmnx cambio la API entre 1.x y 2.x. En 2.x el
# bounding box se pasa como bbox=(oeste, sur, este, norte) y las geometrias se
# bajan con features_from_*; en 1.x era geometries_from_* y otro orden.
osmnx>=2.0
```

Un archivo de dependencias que explica *por qué* una versión es obligatoria le
ahorra horas a quien intente correr el proyecto dentro de un año, incluida tú
misma.

---

## Cómo se lo explicarías a alguien en 60 segundos

Un DEM es una grilla donde cada píxel guarda la altura del terreno, y de esa sola
capa se puede deducir por dónde escurre el agua, porque el agua baja. Trabajo con
dos tipos de dato: rasters, que son grillas y sirven para lo que existe en todas
partes como la altura, y vectores, que son formas con atributos y sirven para lo
que tiene bordes, como el contorno de una cuenca. Todo lo reproyecto a UTM 19
Sur, que es el sistema métrico de esta parte de Chile, porque en latitud y
longitud un grado no mide lo mismo en todas partes y las áreas saldrían mal. La
unidad de análisis es la cuenca: todo el territorio cuya agua sale por un mismo
punto. Y lo que busco no es cualquier crecida sino el flujo de detritos, que es
barro y piedras moviéndose como una masa densa, y eso depende de que la cuenca
sea chica y empinada.

<!-- ===== CAPITULO 03: Estructura del repositorio (Las carpetas y su regla) ===== -->

# 03 — Estructura del repositorio

> **Qué vas a entender al terminar este capítulo**
>
> - Qué hay en cada carpeta y por qué esa separación es una garantía.
> - Por qué los scripts se llaman M1, M2 y M3.
> - Qué hace el archivo de cuatro líneas sin el cual nada corre.

## El árbol

```
alerta-aluviones/
├── README.md
├── requirements.txt
├── .gitignore
├── data/
│   ├── raw/          ← datos originales, NO se modifican ni se suben a git
│   └── processed/    ← datos derivados, generados por el código
├── docs/             ← documentación técnica
├── notebooks/        ← exploración y pruebas
├── outputs/          ← mapas y resultados finales
└── src/
    ├── compat_pysheds.py
    ├── m1_preparar_dem.py
    ├── m1_terreno.py
    ├── m1_recortar_region.py
    ├── m2_susceptibilidad.py
    └── m3_exposicion.py
```

## La regla que gobierna las carpetas de datos

El README la enuncia en una frase que vale la pena poder repetir textual:

> *Si se borra todo `data/processed/` y `outputs/`, se debe poder reconstruirlo
> corriendo el código sobre `data/raw/`.*

Esa regla parece una convención de orden y es en realidad una garantía sobre el
proyecto: significa que **ningún resultado depende de un paso manual que nadie
anotó**. Si un resultado se pudiera reconstruir solo recordando que alguien abrió
QGIS y movió algo a mano, el proyecto no sería reproducible y nadie podría
verificarlo, empezando por ti misma dentro de seis meses.

La separación entre `raw` y `processed` es la que hace cumplible esa regla.
`raw` guarda los datos tal como los entrega la fuente, sin tocar: los tiles de
Copernicus, el límite regional descargado. `processed` guarda todo lo que el
código deriva. La carpeta `raw` es sagrada y la carpeta `processed` es
desechable, y esa asimetría es lo que permite borrar y reconstruir con confianza.

Los datos pesados no van a git, que es lo correcto porque un DEM regional son
cientos de megabytes y el historial de Git guarda todas las versiones de todo lo
que se le mete.

## Por qué M1, M2, M3

Los nombres de los scripts no son decorativos: **cada uno corresponde a un hito
del plan del proyecto y consume lo que produjo el anterior**.

```
m1_preparar_dem.py   →  DEM regional en UTM 19S
        ↓
m1_terreno.py        →  red de quebradas + cuencas + dirección y acumulación de flujo
        ↓
m1_recortar_region.py→  las mismas capas, filtradas a Coquimbo
        ↓
m2_susceptibilidad.py→  cada cuenca clasificada por su capacidad de generar aluviones
        ↓
m3_exposicion.py     →  trayectorias, cruces con rutas, puntos de corte priorizados
```

Como cada script escribe archivos en `data/processed/` y el siguiente los lee,
la cadena se puede detener y retomar en cualquier punto. Si quieres cambiar la
clasificación de M2 no tienes que volver a hacer la hidrología, que es la parte
que tarda horas. Es lo que en procesamiento de datos se llama un **pipeline por
etapas con materialización intermedia**, y aquí la ventaja no es teórica: la
diferencia entre volver a correr M2 y volver a correr todo es de minutos contra
una tarde.

Que los tres primeros se llamen todos `m1_` refleja que el hito M1 resultó tener
tres partes separables que se descubrieron sobre la marcha, y separarlas en
archivos distintos en vez de dejar un solo script gigante fue la decisión
correcta.

## El parche de cuatro líneas

`src/compat_pysheds.py` es el archivo más corto del proyecto y merece un
comentario porque explica una situación que se repite mucho en el mundo real:

```python
import numpy as np

if not hasattr(np, "in1d"):
    np.in1d = np.isin
```

El problema es este. La librería `pysheds`, que hace toda la hidrología, todavía
llama a una función de numpy llamada `np.in1d`. Numpy eliminó ese nombre en su
versión 2.0 y lo reemplazó por `np.isin`, que hace exactamente lo mismo. En
consecuencia, con numpy moderno instalado, cualquier llamada a `accumulation()` o
`catchment()` se detiene con un error.

Las cuatro líneas revisan si el nombre viejo existe y, si no, lo crean apuntando
al nuevo. A eso se le llama **monkey patching**: modificar una librería desde
fuera, en tiempo de ejecución, sin tocar su código.

Lo que hace este archivo defendible en vez de sospechoso es la documentación que
lleva encima. Su docstring explica que la única diferencia histórica entre ambas
funciones era la forma del resultado, que **en las nueve llamadas de pysheds la
entrada ya viene aplanada con `.ravel()`**, y que por lo tanto el comportamiento
es idéntico. Y cierra diciendo cuándo se puede borrar: cuando pysheds publique
una versión compatible con numpy 2.

Ese es el estándar. Un parche de este tipo sin justificación es deuda técnica
escondida; con la verificación de por qué es seguro y la condición de retiro, es
una decisión de ingeniería. En una entrevista, poder contar que revisaste las
nueve llamadas antes de parchear vale mucho más que el parche.

---

## Cómo se lo explicarías a alguien en 60 segundos

La regla del repositorio es que si borro todo lo derivado tengo que poder
reconstruirlo corriendo el código sobre los datos originales, y eso garantiza que
ningún resultado dependa de un paso manual que nadie anotó. Los scripts se llaman
por hito y forman una cadena donde cada uno lee lo que dejó el anterior, así que
puedo cambiar la clasificación sin repetir la hidrología, que tarda horas. Y hay
un parche de cuatro líneas porque pysheds llama a una función que numpy eliminó
en la versión 2; antes de escribirlo revisé las nueve llamadas para confirmar que
el reemplazo es equivalente, y dejé anotado cuándo se puede borrar.

<!-- ===== CAPITULO 04: Conseguir el terreno (src/m1_preparar_dem.py) ===== -->

# 04 — Conseguir el terreno

> **Qué vas a entender al terminar este capítulo**
>
> - Por qué se descartó un modelo de elevación que parecía cuatro veces mejor.
> - Cómo se descarga y se une un DEM regional.
> - Por qué el script verifica la cobertura antes de dejar pasar el resultado.

## 1. La decisión del DEM

Esta es la decisión mejor documentada del proyecto y la que más dice sobre
criterio técnico. Está escrita en la cabecera del archivo:

> *Los productos ALOS PALSAR RTC de alta resolución se generan a partir de NED13,
> que solo cubre Estados Unidos, o de SRTM 30 m. Para Chile aplica el segundo
> caso, y la documentación de ASF lo dice explícitamente: esos productos son "up
> sampled from the 30-m version to 12.5 m". O sea, los píxeles miden 12,5 m pero
> el detalle real sigue siendo de 30 m. Interpolar no agrega información: da
> archivos seis veces más pesados con la misma cantidad de terreno adentro.*

Vale la pena desarmar el razonamiento porque es más sutil de lo que parece.

Existían dos candidatos. ALOS PALSAR anunciaba **12,5 metros por píxel** y
Copernicus GLO-30 anuncia **30 metros**. La elección obvia, mirando solo esas dos
cifras, es el primero: cuatro veces más resolución debería significar cuatro
veces más detalle.

La trampa está en la diferencia entre **tamaño de píxel** y **resolución
efectiva**. El tamaño de píxel es cuánto terreno cubre cada celda. La resolución
efectiva es cuánto detalle real hay adentro. Y se pueden separar: si tomas una
imagen de 30 metros y la **remuestreas** —o sea, la agrandas inventando píxeles
intermedios por interpolación— obtienes píxeles de 12,5 metros que no contienen
ninguna información que no estuviera antes. El archivo pesa seis veces más y
muestra lo mismo, un poco más suave.

Eso es exactamente lo que hacen los productos ALOS PALSAR sobre Chile, y la
documentación de la agencia que los distribuye lo dice con esas palabras. La
frase *"interpolar no agrega información"* es el núcleo del argumento.

Copernicus GLO-30, en cambio, entrega 30 metros medidos de verdad, derivados de
TanDEM-X, que es una misión de dos satélites de radar. A igual resolución
efectiva, es mejor dato y pesa seis veces menos.

En una entrevista esto funciona muy bien porque tiene la forma de un criterio:
**rechacé el dato que anunciaba mejor número porque el número anunciado no era el
número real, y lo verifiqué en la documentación de la fuente.** Casi nadie
verifica eso.

## 2. Los tres pasos del script

El módulo hace tres cosas, y cada una tiene su función:

```
1. Descarga los tiles de 1x1 grado que cubren la zona pedida.
2. Los une en un solo raster continuo.
3. Lo reproyecta a UTM 19S, que es donde un metro mide un metro.
```

Un **tile** es un pedazo rectangular en que se reparte un dato global. Copernicus
publica el DEM del mundo en cuadros de un grado de lado, así que cubrir Coquimbo
requiere varios y hay que juntarlos. Al resultado de juntarlos se le llama
**mosaico**.

El área que se pide está en una constante:

```python
BBOX_COQUIMBO = (-72.0, -32.5, -69.7, -29.0)
```

Un **bounding box** es un rectángulo definido por sus bordes: oeste, sur, este y
norte. Este es deliberadamente más grande que la región, y el capítulo 06 explica
por qué.

## 3. Verificar antes de continuar

Hay una función que no calcula nada y que sin embargo es de las más importantes:

```python
def verificar_cobertura(mosaico, limite, minimo):
    """Comprueba que el mosaico cubra la region antes de dejarlo pasar."""
```

Con `COBERTURA_MINIMA = 0.99`, el script exige que el mosaico cubra al menos el
99% de la región antes de seguir.

El problema que previene es de los peores que hay, porque **no se manifiesta como
un error**. Si una descarga falla o si un tile no existe, el mosaico queda con un
hueco. El script siguiente calcularía la hidrología igual, sin quejarse, y
produciría cuencas cortadas en el borde del hueco. Ese error se propagaría por
todo el pipeline y aparecería recién al mirar el mapa final, cuando ya es difícil
saber de dónde vino.

A este tipo de comprobación se le llama **verificación de precondiciones**:
comprobar que las suposiciones de un cálculo se cumplen, antes de calcular. Es
una práctica de ingeniería de datos que rara vez aparece en proyectos de
portafolio, y es especialmente relevante en este proyecto, porque el capítulo 12
cuenta que hoy el DEM local **no** cubre toda la región y esa es exactamente la
condición que esta función existe para detectar.

## 4. La descarga en paralelo

```python
def descargar(bbox, carpeta, hilos):
    """Descarga en paralelo todos los tiles del bbox."""
```

Descargar varios tiles a la vez en lugar de uno tras otro tiene una razón simple:
bajar un archivo por internet consiste sobre todo en esperar. Mientras el
programa espera un tile no está usando el procesador para nada, así que puede
estar esperando varios simultáneamente. A esa forma de paralelismo se le llama
**concurrencia por entrada y salida**, y es donde los hilos rinden de verdad.

La función `descargar_tile` devuelve `(nombre, estado)` en vez de solo el
resultado, y ese detalle permite que al final el script informe cuáles se bajaron,
cuáles ya estaban y cuáles fallaron, en vez de detenerse en el primer problema.

---

## Cómo se lo explicarías a alguien en 60 segundos

El primer script consigue el modelo de elevación. La decisión que hay que
explicar es por qué descarté ALOS PALSAR, que anunciaba 12,5 metros por píxel,
frente a Copernicus de 30: los productos de alta resolución de ALOS sobre Chile
están remuestreados hacia arriba desde una versión de 30 metros, y la
documentación de la agencia lo dice explícitamente. Los píxeles miden 12,5 pero
el detalle real sigue siendo de 30, así que el archivo pesa seis veces más sin
contener nada nuevo. Interpolar no agrega información. El script baja los tiles
en paralelo, los une en un mosaico, verifica que cubra al menos el 99% de la
región antes de dejarlo pasar —porque un hueco no da error, da cuencas cortadas
que solo se notan al final— y lo reproyecta a UTM 19 Sur para que los cálculos
salgan en metros de verdad.

<!-- ===== CAPITULO 05: De alturas a quebradas (src/m1_terreno.py) ===== -->

# 05 — De alturas a quebradas

> **Qué vas a entender al terminar este capítulo**
>
> - Cómo se deduce por dónde escurre el agua a partir de puras alturas.
> - Por qué hay que estropear el DEM a propósito antes de usarlo.
> - Qué es D8 y qué es la acumulación de flujo.
> - Cómo un umbral convierte una grilla de números en una red de quebradas.

Este es el corazón técnico del proyecto: 651 líneas que convierten una grilla de
alturas en un inventario de quebradas y cuencas. El módulo lo resume en cinco
pasos, y este capítulo los sigue en orden.

## 1. Acondicionar: estropear el DEM a propósito

Antes de calcular nada, el DEM hay que arreglarlo, y el docstring de la función
explica exactamente qué se arregla:

```python
def acondicionar(grid, dem):
    """Deja el DEM hidrologicamente coherente: que el agua siempre pueda salir.

    Un DEM crudo tiene defectos que rompen el escurrimiento:

      - Pozos (pits): un pixel mas bajo que sus 8 vecinos. Casi siempre es ruido
        del sensor, no un hoyo real.
      - Depresiones: hondonadas de varios pixeles sin salida, donde el agua
        quedaria estancada y la red de drenaje se cortaria.
      - Planicies (flats): zonas perfectamente horizontales donde no hay un
        "abajo" definido y el algoritmo no sabe hacia donde mandar el agua.
    """
    sin_pozos = grid.fill_pits(dem)
    sin_depresiones = grid.fill_depressions(sin_pozos)
    acondicionado = grid.resolve_flats(sin_depresiones)
    return acondicionado
```

Los tres problemas comparten una consecuencia: **el agua se queda atrapada**. Un
píxel más bajo que sus ocho vecinos es un sumidero del que el agua no puede
salir, así que todo el escurrimiento aguas abajo se corta ahí. Una planicie
perfectamente horizontal no tiene dirección de bajada, así que el algoritmo no
sabe hacia dónde mandar el agua.

La respuesta es rellenar los hoyos y darles una inclinación mínima a las
planicies. Y aquí está la frase que hay que poder decir en una entrevista, porque
es la que demuestra que entiendes lo que estás haciendo:

> *Es una modificación deliberada del DEM: el objetivo no es que sea más fiel a la
> realidad, sino que el agua escurra de principio a fin sin quedarse pegada.*

O sea, el DEM acondicionado es **menos fiel al terreno real** que el original. Se
inventaron alturas que no existen. Y está bien, porque el objetivo del paso no es
representar el terreno sino permitir que un algoritmo de escurrimiento funcione.

Confundir esas dos cosas es el error clásico de quien usa una herramienta sin
entenderla. Distinguirlas explícitamente, y decir que el DEM acondicionado sirve
para calcular flujo y no para medir alturas, es lo que separa el uso de la
herramienta de la comprensión del método.

## 2. Dirección de flujo: la regla D8

```python
def direccion_y_acumulacion(grid, dem_acondicionado):
    """Calcula hacia donde va el agua (D8) y cuanta llega a cada pixel.

    D8 es la regla mas simple y la mas usada: cada pixel manda toda su agua al
    vecino con la mayor pendiente descendente, sin repartir.
    """
    fdir = grid.flowdir(dem_acondicionado, dirmap=DIRMAP)
    acc = grid.accumulation(fdir, dirmap=DIRMAP)
```

**D8** se llama así por *deterministic eight*: cada píxel tiene ocho vecinos —los
cuatro de los lados y los cuatro de las esquinas— y manda **toda** su agua al que
esté más abajo en relación a la distancia. Sin repartir.

El resultado es un raster donde cada celda ya no guarda una altura sino un
**código de dirección**, uno de ocho valores que indica hacia qué vecino drena.
Los códigos están en una constante:

```python
DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)
```

Son potencias de dos, que es la convención estándar en hidrología digital. Se
eligieron así porque permiten combinar direcciones con operaciones de bits, y
porque es lo que esperan las demás herramientas del área.

Vale la pena tener la limitación identificada. D8 es la regla más simple y por eso
la más usada, pero manda toda el agua a un solo vecino, y en laderas anchas el
agua real se reparte en abanico. Existen algoritmos que reparten
proporcionalmente entre varios vecinos y son más realistas en esas zonas. Para
identificar el fondo de las quebradas, que es lo que este proyecto necesita, D8
funciona bien, porque justamente en un cauce el agua sí se concentra en una sola
dirección.

## 3. Acumulación: el número que dibuja las quebradas

Este es el concepto central del capítulo, y el docstring lo dice mejor que
cualquier paráfrasis:

> *La acumulación cuenta, para cada píxel, cuántos píxeles de más arriba terminan
> drenando por ahí. Es el número clave del script: los valores altos dibujan
> exactamente el fondo de las quebradas, porque el agua se concentra en los
> cauces.*

Un píxel en la cima de un cerro tiene acumulación cero o casi: nadie drena hacia
él. Un píxel en el fondo de un valle tiene acumulación enorme, porque recibe el
agua de toda la ladera. Si pintas el raster de acumulación con los valores altos
en oscuro, **aparece dibujado el mapa de la red de drenaje**, sin haberle dado al
programa ningún dato de ríos.

Es probablemente lo más elegante del proyecto: la red hidrográfica emerge de la
sola geometría del terreno.

## 4. El umbral que decide qué es una quebrada

La acumulación es un número continuo, y en algún punto hay que decidir a partir
de qué valor un píxel cuenta como cauce. Esa decisión es el parámetro
`--umbral-km2`, que por defecto vale 0,15.

Significa: un píxel es parte de una quebrada si al menos 0,15 kilómetros
cuadrados de terreno drenan por él. Un valor más bajo densifica la red hacia las
quebradas chicas; uno más alto deja solo los cauces principales.

Que sea un argumento de línea de comandos y no un número escondido en el código
importa, porque es un parámetro con el que hay que experimentar y su valor
correcto depende de la región. El capítulo 08 cuenta lo que pasó cuando el otro
parámetro del script estaba mal elegido.

## 5. Delinear las cuencas

Con la dirección de flujo, delinear una cuenca es conceptualmente simple: eliges
un punto y preguntas qué píxeles terminan drenando hacia él, siguiendo las
flechas hacia atrás. Eso hace `mascara_cuenca`.

Los puntos de partida son las **desembocaduras**, que `puntos_de_salida` encuentra
como los píxeles de alta acumulación por donde el agua abandona el terreno. El
argumento `separacion_px` evita que dos desembocaduras casi pegadas produzcan dos
cuencas casi idénticas.

Hay además una función que revela que esto se enfrentó a datos reales:

```python
def vecinos_aguas_arriba(fdir_arr, acc_arr, fila, col):
    """Devuelve los vecinos que drenan hacia (fila, col), el mas caudaloso primero.

    Se usa como plan B cuando la delineacion falla justo en la boca de la quebrada.
    """
```

Ese *plan B* es un detalle honesto: a veces la delineación falla exactamente en el
píxel de la desembocadura, por efectos de borde, y entonces se retrocede un paso
hacia el vecino que trae más agua y se intenta desde ahí. Nadie escribe una
función así diseñando; se escribe cuando el mapa sale con huecos y hay que
averiguar por qué.

## 6. La figura de control

El script termina generando un mapa:

```python
def figura_control(dem, acc, red, cuencas, grid, ruta_png):
    """Mapa rapido para revisar a ojo que el resultado tenga sentido."""
```

En análisis geoespacial esto no es un adorno. Un error de coordenadas o una
delineación mal hecha producen números perfectamente plausibles en una tabla y un
mapa evidentemente absurdo: cuencas en el mar, la red de drenaje corriendo cerro
arriba, la región desplazada cien kilómetros. **El ojo detecta en un segundo
errores que ninguna verificación numérica atraparía.**

Que exista una figura de control en cada uno de los cuatro scripts es una
práctica de trabajo, y en una entrevista se puede nombrar como tal: el pipeline
produce una imagen revisable en cada etapa, no solo al final.

---

## Cómo se lo explicarías a alguien en 60 segundos

Este script deduce por dónde escurre el agua a partir de puras alturas. Primero
acondiciona el DEM rellenando pozos y depresiones e inclinando las planicies, y
eso lo vuelve deliberadamente menos fiel al terreno real: el objetivo no es
representar bien el paisaje sino que el agua pueda escurrir de principio a fin
sin quedar atrapada. Después aplica D8, que hace que cada píxel mande toda su
agua al vecino más bajo, y con eso calcula la acumulación: cuántos píxeles de más
arriba drenan por cada punto. Ese número es el que dibuja las quebradas, porque el
agua se concentra en los cauces; la red hidrográfica emerge de la pura geometría,
sin darle ningún dato de ríos. Un umbral de área drenada decide qué cuenta como
cauce, y desde cada desembocadura se sigue el flujo hacia atrás para delinear la
cuenca completa.

<!-- ===== CAPITULO 06: Quedarse con Coquimbo (src/m1_recortar_region.py) ===== -->

# 06 — Quedarse con Coquimbo

> **Qué vas a entender al terminar este capítulo**
>
> - Por qué se procesa más territorio del necesario y se filtra al final.
> - Cuál es el criterio para decir que una cuenca es de Coquimbo.

Este script es el más corto de los cuatro y contiene una de las decisiones más
fáciles de defender del proyecto.

## 1. El agua no respeta los límites políticos

El docstring lo dice directo:

> *La hidrología se corre sobre un área más grande que la región, con medio grado
> de margen por lado. No es desprolijidad: hay quebradas cuyas cabeceras nacen
> fuera del límite administrativo, y si cortáramos el DEM justo en la frontera
> esas cuencas quedarían mochas y sus áreas saldrían mal. El agua no respeta los
> límites políticos.*

El razonamiento es este. Una cuenca es una unidad natural definida por el
terreno, y la frontera de una región es una línea administrativa dibujada por
personas. Las dos no coinciden. Hay quebradas que descargan en Coquimbo pero
cuyas cabeceras están en Atacama o en Argentina.

Si el DEM se cortara justo en el límite regional, esas cuencas aparecerían
truncadas: el algoritmo delinearía solo la parte que quedó dentro y calcularía un
área menor que la real. Y como el área entra directamente en el índice del
capítulo 07 —dividida bajo una raíz cuadrada—, un área subestimada produce un
índice sobreestimado, o sea que esas cuencas se clasificarían como más peligrosas
de lo que son.

O sea que un recorte hecho en el momento equivocado **no produce un dato faltante
sino un dato incorrecto**, que es bastante peor, porque un dato faltante se nota y
un dato incorrecto se usa.

Por eso el `BBOX_COQUIMBO` del capítulo 04 es medio grado más grande que la
región por cada lado, se calcula la hidrología completa sobre esa área con
margen, y recién al final se filtra.

## 2. El criterio de pertenencia

```
Una cuenca es de Coquimbo si su desembocadura cae dentro de la región.
```

O sea, si el agua descarga acá. La cuenca conserva su geometría completa aunque
sus cabeceras estén en otra región, porque hidrológicamente esa quebrada es una
sola y su área drenada es la que es.

Es un criterio nítido y binario, y esa nitidez es su virtud. Las alternativas son
peores: quedarse con las cuencas totalmente contenidas en la región descartaría
justo las transfronterizas, y quedarse con las que intersectan produciría cuencas
que le pertenecen a Atacama.

El criterio elegido, además, corresponde a la pregunta del proyecto. Lo que
importa es dónde sale el material, porque ahí es donde están las rutas que se
cortan.

Del filtro salen dos números que conviene tener juntos: de las 950 cuencas
delineadas sobre el área con margen, 444 descargan dentro de la región. El 4% de
la superficie regional que queda fuera drena hacia Atacama, Valparaíso o
Argentina, así que esas cuencas le pertenecen a la región vecina.

Hay una tercera cifra que este filtro produce y que sirve de control: de las 950
cuencas, 214 alcanzan el borde del rectángulo del DEM y por lo tanto están
truncadas. Ninguna de esas 214 sobrevive al filtro, porque todas drenan hacia
Argentina por el borde este. O sea que el recorte regional, además de responder
la pregunta del proyecto, deja fuera por su cuenta a todas las cuencas cuya área
sería falsa.

## 3. El límite regional se descarga

```python
URL_REGIONES = "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/CHL/ADM1/..."
```

El límite no está guardado como un archivo dentro del repositorio: se descarga de
geoBoundaries, un proyecto que publica límites administrativos de todos los
países. Y el detalle que importa es que **la URL incluye un identificador de
commit fijo**, ese `9469f09`.

Si apuntara a la rama principal, el archivo podría cambiar en cualquier momento y
la misma corrida daría resultados distintos en fechas distintas, sin que nadie se
enterara. Fijar la versión hace que el dato sea siempre el mismo. A eso se le
llama **anclar una dependencia de datos**, y es la misma idea que fijar la versión
de una librería, aplicada a los datos en vez del código.

Es un detalle chico y es exactamente el tipo de cosa que un revisor con
experiencia nota, porque revela que entiendes que los datos externos también son
dependencias.

---

## Cómo se lo explicarías a alguien en 60 segundos

Corro la hidrología sobre un área medio grado más grande que la región y filtro
al final, porque hay quebradas que descargan en Coquimbo pero nacen en Atacama o
en Argentina, y cortar el DEM en la frontera las dejaría truncadas con un área
menor que la real. Eso no daría un dato faltante sino un dato incorrecto: el área
entra bajo una raíz cuadrada en el índice de peligro, así que subestimarla haría
que esas cuencas parecieran más peligrosas de lo que son. El criterio de
pertenencia es que la desembocadura caiga dentro de la región, o sea que el agua
descargue acá, y la cuenca conserva su geometría completa. El límite lo bajo de
geoBoundaries con la URL anclada a un commit fijo, para que el dato no cambie
bajo mis pies entre dos corridas.

<!-- ===== CAPITULO 07: Qué cuencas pueden generar un aluvión (src/m2_susceptibilidad.py) ===== -->

# 07 — Qué cuencas pueden generar un aluvión

> **Qué vas a entender al terminar este capítulo**
>
> - Por qué el proyecto no inventó una fórmula con pesos.
> - Qué es la razón de Melton y qué mide exactamente.
> - Por qué se guardan dos clasificaciones en vez de elegir una.
> - Qué límite tiene el índice y cómo el código lo marca.

Este es el capítulo con el razonamiento más fuerte del proyecto, y el que más
conviene tener preparado para una entrevista.

## 1. Por qué no inventar pesos

El docstring del módulo empieza con una tentación y su rechazo:

> *Lo fácil sería armar una fórmula tipo "pendiente × 0,4 + desnivel × 0,3 + ..."
> y elegir los números a ojo. El problema es que nadie puede decir si esos pesos
> son correctos, ni siquiera una misma.*

Ese párrafo es la mejor frase del repositorio. Describe con precisión el error más
común en proyectos de modelamiento de riesgo: construir un índice ponderado con
coeficientes elegidos por intuición, presentarlo con decimales y mapas de colores,
y que el resultado se vea científico sin serlo.

El problema de fondo es que **una fórmula con pesos inventados no se puede
falsear**. Si alguien pregunta por qué la pendiente pesa 0,4 y no 0,35, no hay
respuesta posible, y por lo tanto tampoco hay forma de que el modelo esté
equivocado, lo cual suena bien y es exactamente lo contrario de lo que uno quiere.

La alternativa que elige el proyecto es usar un índice publicado, con umbrales
calibrados contra eventos reales y sin parámetros libres.

## 2. La razón de Melton

```
R = desnivel (km) / √área (km²)
```

El desnivel es la diferencia entre el punto más alto y la salida de la cuenca. El
área es la superficie de la cuenca. Como el desnivel va en kilómetros y el área en
kilómetros cuadrados, la raíz deja las unidades canceladas y el resultado es un
número puro, sin unidad.

Lo que mide, según el docstring, es **cuánta energía potencial tiene la cuenca por
unidad de tamaño**. La intuición física es directa: una cuenca chica con mucho
desnivel concentra la caída del agua en poco espacio, así que el agua llega abajo
con mucha energía y arrastra piedras. Una cuenca grande con el mismo desnivel
reparte esa caída en mucha superficie, el agua llega más tranquila y solo produce
inundación.

Que la fórmula sea **una sola cuenta, sin parámetros libres**, es su virtud
principal. No hay nada que ajustar, así que no hay nada que sesgar.

## 3. Los umbrales de Wilford

Los tres cortes no los eligió el proyecto: vienen de Wilford et al. (2004),
publicado en la revista *Landslides*, calibrados contra eventos reales.

| Razón de Melton | Tipo de evento |
|---|---|
| < 0,30 | Inundación de agua |
| 0,30 a 0,60 | Crecida de detritos |
| ≥ 0,60 y cuenca ≤ 2,7 km de largo | **Flujo de detritos** (aluvión) |
| ≥ 0,60 y cuenca más larga | Crecida de detritos |

El largo entra en la clasificación por una razón física que el código explica:
*"una cuenca empinada pero alargada disipa energía en el trayecto: el material se
va depositando antes de llegar a la salida"*. O sea que no basta con tener energía;
hay que tenerla cerca de la salida.

El largo se mide de una forma concreta:

```python
def largo_cuenca_km(cuencas):
    """Largo de la cuenca: distancia en linea recta de la salida al punto mas lejano.

    Es la definicion que usa Wilford para su clasificacion. Se mide contra el
    borde de la cuenca, que es donde estan las cabeceras.
    """
```

Ese comentario —*"es la definición que usa Wilford"*— es importante. Hay varias
formas razonables de medir el largo de una cuenca, y elegir una distinta de la
del estudio original invalidaría los umbrales, porque estarían calibrados sobre
otra magnitud. Usar la misma definición es lo que hace que los números publicados
sigan aplicando.

## 4. Las dos clasificaciones

Aquí está la decisión más madura del proyecto:

```python
def clasificar(melton, largo_km):
    """Aplica dos clasificaciones, y devuelve ambas.

    La razon de Melton es robusta y se usa igual en todo el mundo. El criterio de
    largo maximo, en cambio, sale del estudio original de Wilford en la Columbia
    Britanica costera -bosque templado lluvioso- y no hay evidencia de que el
    mismo valor sirva en el norte semiarido de Chile.

    Sobre los datos de Coquimbo ese umbral resulta decisivo: varias de las cuencas
    mas energeticas de la region quedan descartadas por diferencias de decenas de
    metros. Elegir un criterio a ciegas seria esconder esa sensibilidad.
    """
    wilford = np.full(len(melton), "inundacion", dtype=object)
    wilford[melton >= MELTON_CRECIDA] = "crecida_detritos"
    wilford[(melton >= MELTON_FLUJO) & (largo_km <= LARGO_MAX_FLUJO_KM)] = "flujo_detritos"

    solo_melton = np.full(len(melton), "inundacion", dtype=object)
    solo_melton[melton >= MELTON_CRECIDA] = "crecida_detritos"
    solo_melton[melton >= MELTON_FLUJO] = "flujo_detritos"

    return wilford, solo_melton
```

El problema es concreto. La razón de Melton es geometría pura y no depende del
clima ni de la vegetación, así que se puede trasladar entre regiones con
confianza. El umbral de 2,7 kilómetros de largo, en cambio, sale de un estudio
hecho en la Columbia Británica costera, que es bosque templado lluvioso, y
Coquimbo es semiárido. La forma en que la vegetación y la humedad afectan al
transporte de material es completamente distinta, así que no hay razón para
suponer que el mismo número aplique.

Y sobre estos datos el umbral **es decisivo**: varias de las cuencas más
energéticas de la región quedan a un lado o al otro por diferencias de decenas de
metros. O sea que la elección de ese parámetro heredado cambia sustancialmente la
respuesta.

Frente a eso hay tres caminos. Aplicar Wilford completo y no mencionarlo esconde
la sensibilidad. Aplicar solo Melton y no mencionarlo la esconde igual, en la
otra dirección. **Calcular ambas, guardar ambas y dejar que la validación decida**
es el camino que elige el proyecto, y es el correcto.

La frase del docstring —*"elegir un criterio a ciegas sería esconder esa
sensibilidad"*— es material de entrevista directo, porque muestra que identificaste
un parámetro heredado de otro contexto, mediste cuánto importa, y decidiste no
resolverlo por decreto sino diferirlo hasta tener con qué compararlo. Eso es
exactamente lo que hace alguien que ha trabajado con modelos.

## 5. El límite del índice, marcado en el dato

```python
AREA_VALIDA_KM2 = 10.0
```

Melton se calibró sobre cuencas de 0,1 a 10 kilómetros cuadrados. Las cuencas
grandes —Elqui, Limarí, Choapa— son cuencas de río, no quebradas de aluvión, y
aplicarles el índice no significa lo mismo.

Lo que hace el script es notable: **las clasifica igual, pero las marca con
`melton_aplicable = False`**.

Las dos alternativas eran peores. Excluirlas dejaría huecos sin explicación en el
mapa, y alguien podría interpretar la ausencia como bajo riesgo. Clasificarlas sin
marcar dejaría números que se leerían como si significaran lo mismo que los demás.

Marcarlas conserva el dato y transmite la advertencia junto a él. Es un principio
general que vale la pena poder enunciar: **la incertidumbre viaja mejor pegada al
dato que en una nota al pie**.

## 6. Los resultados

De las 444 cuencas de la región, con las dos clasificaciones a la vista:

| Clase | `clase` (Wilford) | `clase_melton` (solo Melton) |
|-------|-------------------|------------------------------|
| Flujo de detritos (aluvión) | 21 | 33 |
| Crecida de detritos | 146 | 134 |
| Inundación | 277 | 277 |

La razón de Melton máxima es 1,009 y la pendiente media máxima 24,9°. Las 21
cuencas críticas miden entre 0,43 y 1,07 km², o sea que a escala regional son
prácticamente invisibles: por eso el mapa las marca con un círculo en la
desembocadura, que es además el punto que le importa a M3.

La comparación entre las dos columnas es la que el capítulo planteaba como
interesante y ahora está medida: **12 cuencas cambian de clase según el criterio
de largo**, todas en el mismo sentido —Wilford las baja de flujo a crecida— y
todas por poco. La primera del ranking, con Melton 1,01, mide 2,84 km de largo
contra un umbral de 2,7: la descarta un 5% de exceso sobre un parámetro traído de
la Columbia Británica. Doce cuencas de 444 no suena a mucho hasta que se nota que
son doce de las veintiuna más energéticas de la región.

## 7. Lo que la corrida completa dejó a la vista

Hay un resultado de esta clasificación que no se ve en la tabla y que conviene
mirar de frente: **las 21 cuencas críticas están todas en la franja costera**. Sus
desembocaduras caen entre las longitudes −71,71 y −71,29, y ninguna se extiende al
este de −71,27. La región llega hasta −69,81.

No es que el interior de Coquimbo no tenga quebradas peligrosas; el temporal de
julio de 2026 demostró lo contrario. Es que ninguna quebrada interior existe como
cuenca en este inventario. Recordando el capítulo 05: una desembocadura es la
última celda con terreno antes del vacío, o sea la costa. Toda quebrada del
interior desemboca en otro cauce, no en el vacío, así que no genera un punto de
salida y queda absorbida dentro del Elqui, del Limarí o del Choapa.

Y ahí el índice la vuelve invisible por construcción. Melton es H/√A: una quebrada
de 2 km² con 800 m de desnivel, medida dentro de una cuenca de 11.675 km², aporta
su desnivel al numerador de una raíz de área gigante. El número que sale describe
al Limarí, no a la quebrada.

El reparto lo dice sin ambigüedad: **4 cuencas concentran el 82,9% de la superficie
drenada**, las cuatro de clase inundación, mientras que las 380 cuencas que caen
dentro del rango donde Melton está calibrado (≤ 10 km²) suman el 1,7%.

Esto no invalida nada de lo anterior. El índice es el correcto, los umbrales son
los publicados y la clasificación de las 444 unidades es la que corresponde a esas
444 unidades. Lo que está mal elegido es **a qué objetos se aplica**: la unidad de
análisis la fija un criterio geométrico —dónde termina el terreno— y no el
fenómeno que se quiere describir.

La salida es subdividir las cuencas grandes por sus confluencias, de modo que cada
quebrada tributaria sea su propia unidad. Es trabajo de M5, con el evento de julio
a la vista para saber a qué escala conviene cortar.

---

## Cómo se lo explicarías a alguien en 60 segundos

Podría haber armado una fórmula ponderada con pesos elegidos a ojo, pero nadie
puede decir si esos pesos son correctos, ni siquiera yo, y un modelo que no se
puede falsear no sirve. Usé la razón de Melton, que es desnivel dividido por raíz
del área y mide la energía potencial de la cuenca por unidad de tamaño, con los
umbrales de Wilford calibrados contra eventos reales. Es una sola cuenta sin
parámetros libres. Guardo dos clasificaciones a propósito: Melton es geometría y
se traslada bien entre regiones, pero el umbral de largo sale de un estudio en la
Columbia Británica lluviosa y Coquimbo es semiárido, y sobre estos datos ese
umbral resulta decisivo, con cuencas que quedan dentro o fuera por decenas de
metros. Elegir uno a ciegas escondería esa sensibilidad, así que calculo las dos y
la validación contra el temporal de julio dirá cuál reproduce mejor lo que pasó. Y
las cuencas grandes quedan marcadas como fuera del rango donde el índice está
calibrado, en vez de excluirlas.

<!-- ===== CAPITULO 08: El parámetro que cambió todo (La mejor anécdota técnica) ===== -->

# 08 — El parámetro que cambió todo

> **Qué vas a entender al terminar este capítulo**
>
> - Cómo un parámetro mal elegido produjo un resultado absurdo.
> - Cómo se diagnosticó la causa.
> - Por qué la corrección se puede verificar con un número.

Este capítulo es corto y es el que más conviene tener memorizado. Tiene la
estructura exacta de lo que un entrevistador quiere escuchar: un resultado
absurdo, una hipótesis sobre la causa, una corrección, y una verificación.

## 1. El resultado absurdo

La primera pasada de M1 se corrió con `--area-min-km2 2.0`, o sea descartando toda
cuenca menor a 2 kilómetros cuadrados. Con esa configuración se delinearon 170
cuencas en la región.

Al correr M2 sobre ese inventario, **no apareció ninguna cuenca capaz de generar
flujos de detritos en toda la Región de Coquimbo**. (Cuando esta historia se
escribió por primera vez el conteo era de una sola cuenca, sobre el DEM parcial;
al rehacerla sobre el DEM completo el resultado absurdo resultó ser todavía más
absurdo.)

Ese resultado no es plausible y hay que poder decir por qué, porque el valor de
esta historia está en haberlo notado. Coquimbo es una región con historial
documentado de aluviones, con un temporal reciente que aisló a decenas de miles
de personas cortando rutas por activación de quebradas. Un modelo que dice que
hay una sola quebrada capaz en toda la región está contradiciendo un hecho
conocido.

El punto general: **el modelo no da error cuando está mal, da un número**. La
única defensa es tener suficiente conocimiento del terreno como para reconocer
cuándo un número es imposible.

## 2. El diagnóstico

La hipótesis fue que el filtro estaba eliminando exactamente el objeto de estudio,
y sale del capítulo 07. Un flujo de detritos requiere razón de Melton alta, o sea
mucho desnivel dividido por raíz del área. Como el área está en el denominador,
**las cuencas chicas son las que pueden tener Melton alto**. Una cuenca grande
necesitaría un desnivel imposible para alcanzar el mismo índice.

O sea que las cuencas capaces de generar aluviones son, casi por definición,
cuencas chicas y empinadas. Y el filtro de 2 km² estaba botando justamente esas.

El README lo dice en una frase: *"El filtro estaba botando justamente las
quebradas chicas y empinadas, que son las que producen aluviones."*

Hay una segunda parte del diagnóstico que refuerza la corrección. Melton está
calibrado para cuencas de 0,1 a 10 km², así que un filtro en 2 km² dejaba fuera
buena parte del rango donde el índice tiene validez. Con 0,4 km², la mayor parte
del inventario queda dentro de ese rango.

## 3. La corrección y su verificación

Bajar el parámetro de 2,0 a 0,4 km² produjo esto:

| Métrica | Con 2,0 km² | Con 0,4 km² | Cambio |
|---------|-------------|-------------|--------|
| Cuencas que descargan en la región | 170 | 444 | ×2,6 |
| Cuencas de flujo de detritos | 0 | 21 | — |
| Superficie drenada total | 39.280 km² | 39.523 km² | +0,6% |

Estas cifras se pueden comprobar sin re-correr la hidrología, que tarda media
hora. El filtro por área se aplica al final de `delinear_cuencas()`, después de
delinear todas las cuencas, así que quedarse con las mayores a 2,0 km² de la
corrida de 0,4 da exactamente el mismo inventario que habría producido una
corrida con 2,0. El anexo E de `docs/corridas/2026-08-23_m1_m2.txt` lo hace.

La tercera fila es la que convierte esto en una verificación en vez de un
resultado sin más. Si la superficie total hubiera crecido mucho, significaría que
el cambio estaba incorporando territorio nuevo, y no habría forma de saber si las
cuencas nuevas eran reales o artefactos del algoritmo. Como la superficie
prácticamente no se movió, **el territorio es el mismo y lo que cambió es la
resolución con que está descrito**: las mismas cuencas grandes de antes, ahora
subdivididas en sus quebradas componentes. El +0,6% se midió dos veces —la
corrida remota de agosto y la local del 23— en máquinas distintas, y dio el mismo
número las dos veces.

El README lo dice así: *"la superficie drenada casi no cambia porque las que entran
son pequeñas; lo que cambia es la resolución del inventario, y eso es lo que M2
necesita"*.

## 4. Por qué esto funciona en una entrevista

La estructura completa es la que se busca en un candidato:

1. **Un resultado que no cuadraba** con lo que se sabe del terreno, notado en vez
   de aceptado.
2. **Una hipótesis derivada del método**, no adivinada: como el área está en el
   denominador del índice, las cuencas capaces son chicas, y el filtro las estaba
   botando.
3. **Una corrección con su justificación adicional**: 0,4 km² además deja el
   inventario dentro del rango donde Melton está calibrado.
4. **Una verificación independiente**: la superficie casi constante prueba que lo
   que cambió fue la resolución y no el territorio.
5. **La decisión documentada** en el README, donde alguien más puede revisarla.

Y hay una lección general que se puede enunciar en una frase, que es lo que suele
quedar: **un parámetro de filtrado elegido antes de conocer la escala del
fenómeno puede eliminar el fenómeno**.

---

## Cómo se lo explicarías a alguien en 60 segundos

La primera corrida con área mínima de 2 km² dio una sola cuenca capaz de generar
aluviones en toda la región, y eso no puede ser: Coquimbo tiene historial de
aluviones y un temporal reciente que cortó cuarenta rutas por activación de
quebradas. La hipótesis salió del propio índice: como el área va en el
denominador, las cuencas capaces son chicas y empinadas, así que el filtro estaba
botando exactamente lo que buscaba. Bajé el umbral a 0,4, que además deja el
inventario dentro del rango donde Melton está calibrado, y las cuencas capaces
pasaron de 0 a 21. Lo que confirma que el cambio es correcto es que la superficie
drenada total casi no se movió, de 39.280 a 39.523 km²: el territorio es el mismo,
lo que cambió es la resolución del inventario.

<!-- ===== CAPITULO 09: Dónde el flujo cruza lo que la gente usa (src/m3_exposicion.py) ===== -->

# 09 — Dónde el flujo cruza lo que la gente usa

> **Qué vas a entender al terminar este capítulo**
>
> - Por qué la trayectoria se traza hacia arriba y no hacia abajo.
> - Por qué el proyecto se negó a poner un parámetro de alcance.
> - Cómo se priorizan los cortes y por qué la prioridad no es el peligro.

M1 dijo dónde están las quebradas y M2 dijo cuáles pueden generar un flujo. M3
responde la pregunta que le importa a alguien que no sabe hidrología: **qué rutas
se cortan y qué localidades quedan en el camino**. Son 825 líneas, el archivo más
largo del proyecto.

## 1. Lo que este script NO es

El docstring dedica una sección entera a eso, y conviene leerla antes que nada:

> *No es un modelo de propagación (runout). Un runout de verdad resuelve la
> reología del flujo —viscosidad, fricción, volumen movilizado— y devuelve hasta
> dónde llega el material y con qué espesor. Eso es Nivel 3 (RAMMS, FLO-2D) y
> está explícitamente fuera de alcance.*
>
> *Lo que hace este script es un **proxy geométrico**: supone que el material baja
> por el cauce principal de la cuenca, que es por donde va el agua. Es una
> hipótesis razonable —los flujos de detritos son encauzados hasta que llegan al
> abanico— pero es una hipótesis, no un cálculo.*

Un **proxy** es un sustituto medible de algo que no se puede medir directamente.
Aquí, en vez de calcular la física del flujo, se usa la geometría del cauce como
aproximación de por dónde va a bajar el material.

La consecuencia se enuncia explícitamente: cada punto de corte es un
**candidato**, no una predicción. Es un lugar donde una vía cruza el cauce de una
quebrada susceptible, y que ese corte ocurra depende del gatillo de lluvia y del
volumen movilizado, que el proyecto no estima.

Declarar el alcance con esta precisión, y nombrar las herramientas que sí harían
el cálculo completo, es lo que impide que el resultado se lea como algo que no es.

## 2. La trayectoria se traza hacia arriba

```python
def cauce_principal(fdir, acc, fila, col, transform, min_celdas):
    """Traza el cauce principal caminando aguas ARRIBA desde la desembocadura.

    Por que aguas arriba y no aguas abajo: la desembocadura es, por definicion,
    el ultimo punto con terreno antes del mar o del borde. Aguas abajo de ahi no
    queda nada que recorrer. La trayectoria del flujo es el camino que baja desde
    la cabecera hasta esa boca, y se reconstruye al reves.
    """
```

Suena al revés y no lo es, y el docstring anticipa esa confusión, que es
exactamente lo que hay que hacer cuando una decisión parece contraintuitiva.

El método es: parado en una celda, mirar cuál de sus ocho vecinos drena hacia
ella, y avanzar al que trae más agua. Repitiendo eso desde la boca se recorre la
rama principal hasta la cabecera, dejando fuera los afluentes chicos, porque en
cada bifurcación se sigue siempre el brazo con más acumulación.

Hay dos detalles del código que merecen mención. El conjunto `visitadas` está
comentado como *"protección contra ciclos en zonas planas rellenadas"*: en las
planicies que el capítulo 05 inclinó artificialmente pueden aparecer
configuraciones donde el recorrido volvería sobre sus pasos, y sin esa protección
el bucle no terminaría nunca. Y el corte por `min_celdas` detiene el trazado
cuando el cauce ya no concentra agua, porque *"por encima de ese punto hay ladera,
no quebrada"*.

Al final la línea se invierte para quedar en sentido cabecera → boca, que es el
sentido en que viaja el flujo. Es un detalle de presentación con una razón: quien
abra la capa en un programa de mapas ve la geometría orientada como el fenómeno.

## 3. La negativa a inventar un alcance

Esta es la decisión más íntegra del archivo:

> *Exponer un "alcance de runout" en kilómetros habría sido inventar un número: el
> alcance real depende del volumen movilizado, que este proyecto no estima. En vez
> de eso el único parámetro espacial es el ancho del corredor alrededor del cauce
> (45 m por defecto), y su justificación es puramente geométrica: el cauce se
> trazó sobre una grilla de 30 m, así que su posición tiene una incertidumbre del
> orden de píxel y medio.*
>
> *Es tolerancia de posición, no distancia de propagación. Si alguien lo lee como
> lo segundo, está leyendo mal el modelo.*

Vale la pena notar cuánto se resiste aquí. Habría sido facilísimo poner un
parámetro llamado `alcance_km = 2.0`, y el resultado se vería más completo y más
impresionante. El proyecto se niega porque ese número no tendría fundamento.

El parámetro que sí existe tiene una justificación aritmética verificable: 45
metros son un píxel y medio de una grilla de 30 metros. Es la tolerancia
necesaria para que el desajuste entre dónde el DEM cree que está el cauce y dónde
OpenStreetMap cree que está la ruta no haga perder cruces reales.

Y la última frase —*"si alguien lo lee como lo segundo, está leyendo mal el
modelo"*— es una advertencia contra el malentendido más probable, escrita en el
lugar donde alguien la va a leer.

## 4. La priorización

```python
def priorizar(puntos):
    """Ordena los cortes combinando peligro de la cuenca con importancia de la via.

    El criterio: ordenar solo por susceptibilidad respondería "que quebrada es mas
    peligrosa", que es la pregunta de M2 y ya esta contestada. La pregunta de M3
    es otra: **cual de estos cortes tiene peores consecuencias**. Y ahi una cuenca
    de clase media que corta la Ruta 5 pesa mas que una de clase alta que corta
    una huella, porque la troncal aisla a mucha mas gente.

    prioridad = 0,5 x peligro_de_la_cuenca + 0,5 x importancia_de_la_via

    Ninguno de los pesos esta calibrado: son juicios explicitos, puestos arriba
    como constantes para poder discutirlos y moverlos.
    """
```

El razonamiento distingue dos preguntas que se confunden con facilidad. *Qué
quebrada es más peligrosa* es una propiedad del terreno y la contestó M2. *Qué
corte tiene peores consecuencias* depende también de qué hay al otro lado, y esa
es la pregunta de M3. Una quebrada mediana que corta la Ruta 5 deja aislada a
mucha más gente que una quebrada muy peligrosa que corta un camino de tierra sin
casas.

Los pesos están en constantes al principio del archivo:

```python
PESO_VIA = {"motorway": 1.0, "trunk": 1.0, "primary": 0.85, "secondary": 0.6,
            "tertiary": 0.45, "unclassified": 0.3, ...}
PESO_CLASE = {"flujo_detritos": 1.0, "crecida_detritos": 0.55}
```

Y aquí conviene notar la coherencia con el capítulo 07, porque es lo que hace
defendible esta decisión. En M2 el proyecto **se negó** a inventar pesos, y aquí
los inventa. La diferencia está en la frase del docstring: *"ninguno de los pesos
está calibrado: son juicios explícitos, puestos arriba como constantes para poder
discutirlos y moverlos"*.

O sea: en M2 existía un índice publicado y calibrado, así que inventar habría sido
peor que usar lo que ya estaba validado. Aquí no existe ninguna calibración
publicada sobre qué importancia relativa tiene una ruta troncal frente a una
secundaria, porque eso depende de decisiones sociales y no de física. Ante eso hay
dos opciones: no priorizar nada, o poner un juicio y declararlo como juicio. El
proyecto elige la segunda y lo dice.

Esa distinción —usar lo calibrado cuando existe, declarar el juicio cuando no— es
el argumento que hay que tener listo si alguien pregunta por la aparente
contradicción.

## 5. Los otros detalles

`descargar_osm` baja las rutas y las zonas urbanas de OpenStreetMap **con caché en
disco**, porque el área es grande y bajarla en cada corrida sería lento y
descortés con un servicio gratuito. Además parte el área en cuadros, porque una
consulta demasiado grande falla.

`verificar_solape` comprueba que las trayectorias y las vías ocupen el mismo
pedazo de mundo antes de cruzarlas. Es la misma familia de verificación que la
cobertura del capítulo 04: si dos capas están en sistemas de coordenadas
distintos, la intersección da cero cruces sin ningún error, y cero cruces se ve
igual que "no hay cortes".

`_fusionar_cercanos` colapsa puntos de la misma cuenca y la misma vía que caen casi
encima. Sin eso, una ruta que serpentea junto a un cauce produciría veinte cruces
donde en la práctica hay uno.

`alcance_urbano` marca aparte qué trayectorias entran en zona poblada y en cuál,
que es la otra mitad de la pregunta: no solo qué rutas se cortan sino qué
localidades quedan en el camino.

---

## Cómo se lo explicarías a alguien en 60 segundos

M3 cruza los cauces de las quebradas susceptibles con la red vial de
OpenStreetMap y devuelve puntos de corte candidatos. Trazo la trayectoria
caminando aguas arriba desde la desembocadura, porque aguas abajo de la boca no
queda terreno; en cada paso avanzo al vecino que trae más agua y así sigo la rama
principal. Deliberadamente no hay parámetro de alcance: el alcance real depende
del volumen movilizado, que no estimo, así que ponerlo sería inventar un número. El
único parámetro espacial es un corredor de 45 metros, que es píxel y medio de una
grilla de 30 y absorbe el desajuste entre el DEM y el trazado de las rutas: es
tolerancia de posición, no distancia de propagación. Y priorizo combinando peligro
de la cuenca con importancia de la vía, porque la pregunta de M3 no es qué
quebrada es más peligrosa sino qué corte tiene peores consecuencias; esos pesos no
están calibrados y los dejo declarados como juicios en constantes al principio del
archivo.

<!-- ===== CAPITULO 10: El control de calidad (La comparación contra la DGA) ===== -->

# 10 — El control de calidad

> **Qué vas a entender al terminar este capítulo**
>
> - Por qué comparar contra un tercero es lo que distingue este proyecto.
> - Qué dio la comparación y cómo se interpreta la discrepancia.

## 1. Por qué esto importa más que el resto

Un proyecto de portafolio típico produce un resultado y lo muestra. Nadie puede
saber si está bien, porque no hay nada contra qué compararlo, y en la práctica el
lector tiene que confiar.

Este proyecto hace algo distinto: toma las tres cuencas mayores que delineó y
compara sus áreas contra **las áreas oficiales de la Dirección General de Aguas**,
que es el organismo del Estado chileno que las publica.

| Cuenca | Delineada | Oficial DGA | Desvío |
|---|---|---|---|
| Choapa | 7.620,4 km² | ~7.650 km² | 0,4% |
| Elqui | 9.408,2 km² | ~9.657 km² | 2,6% |
| Limarí | 11.675,1 km² | ~11.800 km² | 1,1% |

Es un resultado fuerte. Un desvío de 0,4% sobre una cuenca de 7.600 km² significa
que el algoritmo reprodujo con precisión una hidrología que un organismo estatal
midió por su cuenta, y las tres quedan bajo el 3%. **Es una verificación externa e
independiente**, y es lo que permite decir que el método funciona sin pedirle a
nadie que confíe.

En una entrevista esto se puede plantear en una frase: *un externo puede intentar
refutar mi resultado con datos oficiales, y aun así cuadra.*

## 2. La discrepancia del Limarí, y cómo terminó

Esta tabla tuvo durante un tiempo una tercera fila incómoda: el Limarí daba
9.309,0 km² contra 11.800 oficiales, un 21% de desvío. Vale la pena contar cómo
se trató y cómo terminó, porque las dos mitades enseñan cosas distintas.

El README de entonces proponía una explicación y la sometía a una prueba
aritmética:

> *La diferencia del Limarí probablemente sea de definición y no un error. La DGA
> agrupa en esa cuenca varias quebradas costeras que hidrológicamente son
> independientes; sumando la cuenca contigua (1.878 km²) se llega a 11.187 km²,
> cerca del valor oficial. Queda por confirmar cuando estén los nombres a la
> vista.*

La estructura de ese párrafo era la correcta. Hay una **hipótesis** —es una
diferencia de criterio, no un error de cálculo—, una **verificación numérica**
—sumando la cuenca contigua se llega a 11.187 contra 11.800 oficiales—, y una
**condición de cierre** explícita: hay que confirmarlo cuando se puedan ver los
nombres.

Y esa condición de cierre es la que salvó el análisis, porque **la hipótesis era
falsa**. Al re-correr M1 sobre el DEM completo, el Limarí sale entero: 11.675,1
km², un 1,1% de la cifra oficial. Tampoco existe la cuenca contigua de 1.878 km²
que aquel razonamiento sumaba; después de Los Choros (4.051,7 km²), la cuenca
siguiente mide 742,2 km². El 21% no era una diferencia de criterio con la DGA:
era la corrida que partía el Limarí en dos.

La lección es más útil que la que habría dejado un acierto. Una hipótesis
razonable, verificada aritméticamente y que da un número cercano al esperado,
puede aun así ser falsa: 9.309 + 1.878 = 11.187 se acercaba a 11.800 por
coincidencia, no porque el mecanismo propuesto fuera el real. Lo que impidió que
eso quedara escrito como verdad fue haber puesto *queda por confirmar* en vez de
declararlo resuelto. Es la diferencia entre una explicación y una explicación
provisoria, y solo se nota cuando la explicación resulta equivocada.

Conviene saber contar las dos partes. La primera muestra que ante un número que
no cuadra se investiga en vez de justificar. La segunda, que una explicación se
sostiene abierta hasta poder cerrarla, y que cuando el dato mejora se corrige lo
escrito en vez de defenderlo.

## 3. Por qué esto es la mejor pieza del proyecto

La **práctica** que este capítulo describe es lo que hay que conservar: cuando
produzcas un resultado, busca un tercero que haya medido lo mismo por su cuenta y
compárate contra él. Y nótese que fue esa práctica, y no una revisión del código,
la que dejó al descubierto que una corrida estaba partiendo el Limarí en dos.
Comparar contra un externo no solo valida: también encuentra errores que desde
adentro no se ven.

Casi ningún proyecto de portafolio lo hace, en parte porque da miedo: si el
resultado no cuadra, se nota. Precisamente por eso, cuando cuadra, vale mucho.

---

## Cómo se lo explicarías a alguien en 60 segundos

Comparé las áreas de las tres cuencas mayores que delineé contra las que publica
la Dirección General de Aguas, que las midió por su cuenta. Choapa dio 0,4% de
desvío, Elqui 2,6% y Limarí 1,1%, o sea que el método reproduce una hidrología
medida por un organismo estatal. El Limarí daba 21% y lo investigué en vez de dejarlo
pasar: mi hipótesis fue que la DGA agrupaba ahí quebradas costeras
hidrológicamente independientes, y sumando la cuenca contigua llegaba a 11.187
km² contra 11.800 oficiales. La dejé anotada como probable, pendiente de
confirmar. Y resultó equivocada: al re-correr sobre el DEM completo el Limarí
sale entero, 11.675 km², 1,1% de desvío. El 21% era mi corrida partiendo la
cuenca en dos, no un criterio distinto de la DGA. Lo que me salvó fue no haber
declarado resuelta una explicación que solo estaba verificada por coincidencia.
Lo importante del ejercicio es que un externo puede intentar refutar mi resultado
con datos oficiales.

<!-- ===== CAPITULO 11: Decisiones y defensa (Preparación para entrevista) ===== -->

# 11 — Decisiones y defensa

## Tabla de decisiones

| Decisión | Alternativa descartada | Por qué |
|----------|----------------------|---------|
| Copernicus GLO-30 | ALOS PALSAR "12,5 m" | Los productos ALOS sobre Chile están remuestreados desde 30 m; interpolar no agrega información |
| Reproyectar a UTM 19S | Trabajar en latitud/longitud | En grados las áreas no significan nada; en UTM un metro mide un metro |
| Acondicionar el DEM | Usarlo crudo | Sin rellenar hoyos el agua queda atrapada y la red de drenaje se corta |
| D8 | Algoritmos de flujo repartido | Es el estándar y basta para identificar cauces, donde el agua sí se concentra |
| Procesar con margen y filtrar al final | Cortar el DEM en el límite regional | Cortar da cuencas truncadas con área subestimada, o sea un dato incorrecto, no faltante |
| Cuenca de Coquimbo = desembocadura en Coquimbo | Cuencas contenidas, o cuencas que intersectan | Criterio nítido y alineado con la pregunta: importa dónde sale el material |
| Razón de Melton | Fórmula ponderada con pesos propios | Un índice publicado y calibrado se puede falsear; unos pesos a ojo, no |
| Guardar dos clasificaciones | Elegir una | El umbral de largo viene de otra región y resulta decisivo; elegir a ciegas escondería la sensibilidad |
| Marcar cuencas grandes en vez de excluirlas | Sacarlas del resultado | Un hueco sin explicación se lee como bajo riesgo; la advertencia viaja mejor pegada al dato |
| `--area-min-km2 0.4` | 2,0 | Con 2,0 no aparecía ninguna cuenca capaz en toda la región: el filtro botaba el objeto de estudio |
| Sin parámetro de alcance | `alcance_km = 2.0` | El alcance depende del volumen movilizado, que el proyecto no estima |
| Corredor de 45 m | Un radio elegido a ojo | Es píxel y medio de una grilla de 30 m: tolerancia de posición con justificación aritmética |
| Pesos declarados en M3 | No priorizar, o presentarlos como calibrados | No existe calibración publicada; el juicio se declara como juicio en constantes visibles |
| URL de límites anclada a un commit | Apuntar a la rama principal | Un dato externo que cambia hace que la misma corrida dé resultados distintos |
| Parche de numpy documentado | Fijar numpy < 2, o parchear sin explicar | Se verificaron las nueve llamadas y quedó escrita la condición de retiro |
| Figura de control en cada script | Solo tablas | Un error de coordenadas da números plausibles y un mapa evidentemente absurdo |
| Verificar cobertura en un módulo compartido | Una copia por script, o confiar en el que arma el DEM | La comprobación protegía la escritura del DEM y el problema estaba en su lectura; ver capítulo 12 |

## Preguntas probables

**¿Por qué no usaste machine learning?**

Porque no hay con qué entrenarlo. Un modelo supervisado necesita ejemplos
etiquetados —quebradas que se activaron y quebradas que no— y ese inventario no
existe para Coquimbo en forma sistemática. Además, con pocos eventos el modelo
memorizaría en vez de generalizar. La razón de Melton está calibrada contra
eventos reales publicados y no requiere entrenamiento. Si M5 produce un inventario
de activaciones de julio de 2026, ahí sí habría con qué entrenar o al menos
recalibrar los umbrales, y sería el paso natural.

**¿Qué tan confiable es esto?**

No está validado, y hay que decirlo así. M5 es exactamente el hito que produciría
una métrica de acierto y no está hecho. Lo que sí hay es una verificación
intermedia: las áreas de las tres cuencas mayores cuadran con las oficiales de la
DGA con desvíos bajo el 3%, lo que dice que la delineación reproduce la
hidrología real. Eso valida el terreno, no la predicción de riesgo.

Y hay una limitación que conviene decir antes de que la pregunten: la unidad de
análisis son cuencas que desembocan en el mar, así que las quebradas interiores
quedan absorbidas dentro del Elqui, del Limarí y del Choapa y el índice no las ve.
Las 21 cuencas críticas están todas en la costa. No es que el interior sea seguro;
es que hoy no está siendo evaluado. Está en el capítulo 07 con las cifras.

**¿De dónde salen los umbrales?**

De Wilford et al. (2004), publicado en *Landslides*, calibrado contra eventos
reales. No los elegí yo, y esa es la razón de haberlos usado. El único que
cuestiono es el de largo máximo, porque viene de la Columbia Británica costera y
Coquimbo es semiárido; por eso guardo las dos clasificaciones y dejo que la
validación decida.

**¿Qué harías con más tiempo?**

Cerrar M3 con una corrida completa y revisada, y después M5, porque sin validación
el modelo es una hipótesis bien construida. En paralelo, rehacer M1 y M2 en local
para que las cifras del README sean reproducibles, que hoy no lo son.

**¿Esto sirve para algo o es un ejercicio?**

Sirve como capa de priorización, que es distinto de un sistema de alerta. Alguien
que tenga que decidir dónde poner sensores de lluvia, o qué rutas revisar primero
después de un temporal, tiene aquí una lista ordenada de puntos donde una vía cruza
el cauce de una quebrada susceptible. No dice cuándo va a pasar ni con qué
probabilidad, y eso hay que decirlo antes de que lo pregunten.

<!-- ===== CAPITULO 12: Estado real y cifras (Lo que hay que decir antes) ===== -->

# 12 — El error que no daba error

> **Qué vas a entender al terminar este capítulo**
>
> - Cómo el pipeline completo corrió sobre el 40% del territorio sin quejarse.
> - Por qué la comprobación que existía para detectarlo no lo detectó.
> - Qué cambió cuando se volvió a correr sobre el territorio completo.
> - Qué sigue abierto, que no es lo mismo que lo que estaba roto.

Este capítulo era, hasta el 23 de agosto de 2026, una advertencia sobre cifras que
el repositorio no podía demostrar. Ya no lo es: M1 y M2 se re-corrieron en local
sobre el DEM completo y las cifras son reproducibles. Lo que queda es el registro
del episodio, que vale más que la advertencia.

## 1. Qué pasó

El 7 de agosto de 2026, entre las 14:19 y las 14:24, el pipeline completo corrió
sobre un DEM que cubría de latitud −29 a −31, o sea al que le faltaba el tercio
sur de la Región de Coquimbo. Escribió sus capas, dibujó sus tres mapas y terminó
sin un solo mensaje de error.

Las cifras que produjo:

| | Corrida buena | DEM truncado |
|---|---|---|
| Cuencas en la región | 444 | 360 |
| Superficie drenada | 39.523 km² | 16.187 km² |
| Melton máximo | 1,009 | 1,504 |
| Cuencas de flujo de detritos | 21 | 38 |
| Pendiente media máxima | 24,9° | 37,6° |

Ninguna de las de la derecha se ve mal. Son 360 cuencas, un número plausible; un
Melton máximo de 1,5, alto pero posible; 38 quebradas capaces de generar aluviones
en una región que tiene historial de aluviones. Un mapa con 360 polígonos se ve
igual de convincente que uno con 444 si no se sabe qué forma tiene la región.

**Un modelo mal alimentado no da error: da un número.** Esa es la frase que hay
que llevarse del capítulo.

## 2. El efecto de segundo orden, que es peor

Faltaba territorio, sí. Pero hay algo más dañino que el faltante, y está en la
tercera y cuarta fila de esa tabla.

Las cuencas que el borde del recorte parte por la mitad quedan con el área
truncada. Como la razón de Melton es H/√A, achicar A **infla** el índice. Medido:
el Melton máximo pasó de 1,009 a 1,504, y las cuencas clasificadas como flujo de
detritos, de 21 a 38.

O sea que el recorte no solo omitía territorio: **fabricaba cuencas críticas que
no existen**. Un modelo de riesgo que inventa peligro donde no lo hay es peor que
uno que lo omite, porque el error viaja en la dirección de la alarma y nadie
cuestiona una alarma.

## 3. Por qué no lo detuvo la comprobación que existía

El capítulo 04 describe `verificar_cobertura`, una función que compara el polígono
regional contra el rectángulo del DEM y aborta si la cobertura baja del 99%. La
pregunta obvia es cómo un DEM al que le faltaba el 60% pasó por ahí.

La respuesta tiene dos partes, y la primera es sencilla: **no existía todavía**.
`verificar_cobertura` entró al repositorio en el commit `84ca780`, el 7 de agosto
a las 19:37. Las capas parciales se escribieron ese mismo día a las 14:24, cinco
horas antes. La función no falló en su único trabajo: nació después del accidente,
como reacción a él, junto con la marca `toca_borde` y el bbox de 12 tiles.

La segunda parte es la interesante, porque es la que seguía rota. La función vivía
dentro de `m1_preparar_dem.py`, que es el script que **arma** el DEM. Ahí solo
protege el momento de la creación. Pero `m1_terreno.py`, `m1_recortar_region.py` y
`m2_susceptibilidad.py` no arman nada: leen `data/processed/dem_utm19s.tif` tal
como esté en disco. Un DEM parcial que quedó ahí de una prueba con `--bbox` chico,
de una descarga interrumpida o de una copia entra a los tres sin que nadie lo
mire.

Dicho de una forma que se puede enunciar en una entrevista: **la comprobación
protegía la escritura, y el problema estaba en la lectura**. Que es exactamente el
escenario que la había motivado, un archivo viejo que sobrevive en disco.

Había además una tercera grieta, más chica: existía una segunda copia de la
función dentro de `m3_exposicion.py`, con un umbral distinto (0,95 contra 0,99).
Dos copias de la misma comprobación con dos criterios distintos son una sola
comprobación con un criterio indefinido.

## 4. Lo que se construyó

`src/cobertura.py`: una sola copia de la función, llamada al inicio de los cinco
scripts que leen un DEM —los cuatro del pipeline más M3—, antes de gastar un
minuto de cálculo. El docstring del módulo lleva escrito el caso de agosto de 2026
con sus cifras, para que el próximo que lo lea sepa por qué está ahí y no lo borre
por parecer redundante.

También lleva escrito su propio límite, que conviene conocer: compara contra el
**rectángulo** de coordenadas del ráster, no contra sus píxeles con dato. Un DEM
cuyo rectángulo cubra la región pero venga vacío por dentro pasaría la prueba. Se
acepta porque el caso real que motivó todo esto sí se detecta, y porque leer 145
millones de píxeles para verificar costaría más que el cálculo que protege.

Y la regla de proceso que acompaña al código: cada corrida de referencia queda
guardada en `docs/corridas/`, con la salida de consola completa. Si un número no
salió de ahí, no entra al README.

## 5. Qué cambió al re-correr

La corrida del 23 de agosto de 2026 (`docs/corridas/2026-08-23_m1_m2.txt`) tomó 36
minutos de hidrología sobre 145 millones de píxeles, en un notebook de 12 GB.

Lo esperable se confirmó: 444 cuencas contra las 434 que reportaba la corrida
remota, 39.523 km² contra 39.487, 134.329 tramos contra 134.306. Diferencias del
orden del 0,1%, atribuibles al ajuste del bbox de 20 a 12 tiles.

Lo no esperable fue el Limarí. El capítulo 10 cuenta esa historia completa: la
cuenca sale entera, 11.675,1 km² contra ~11.800 oficiales, y el 21% de desvío que
el proyecto había explicado como diferencia de criterio con la DGA resulta ser una
corrida que partía la cuenca en dos. La explicación era falsa, y el mecanismo que
impidió que quedara escrita como verdad fue haberla dejado marcada como *queda por
confirmar*.

Y se cerró el pendiente que este capítulo dejaba abierto: el desglose de
`clase_melton` sobre la región completa. Son 33 / 134 / 277 contra los 21 / 146 /
277 de Wilford, y **12 cuencas cambian de clase según el criterio de largo**.

## 6. El estado por hito

| Hito | Estado real |
|------|-------------|
| M0 — Andamiaje | Cerrado |
| M1 — Terreno | Cerrado y reproducible en local |
| M2 — Susceptibilidad | Cerrado y reproducible en local |
| M3 — Exposición | Cerrado y reproducible en local: 422 puntos de corte |
| M4 — Gatillo de lluvia | No empezado |
| M5 — Validación | No empezado |
| M6 — Entrega | No empezado |

## 7. Lo que queda abierto

Conviene separar esto de lo anterior. Lo de arriba estaba **roto** y se arregló.
Lo que sigue son limitaciones conocidas, que es otra cosa.

**La unidad de análisis no coincide con el fenómeno.** Es la más importante y la
dejó a la vista la corrida completa. Las 21 cuencas críticas están todas en la
franja costera, porque M1 solo corta una cuenca donde el terreno termina, o sea en
el mar, y toda quebrada interior queda absorbida dentro del Elqui, del Limarí o
del Choapa. Cuatro cuencas concentran el 82,9% de la superficie drenada y las
cuatro son de clase inundación. El índice funciona; lo que está mal elegido es a
qué objetos se aplica. El capítulo 07 lo trata con las cifras. Es trabajo de M5.

**`toca_borde` sub-detecta.** De las 950 cuencas delineadas sobre el área con
margen, 214 alcanzan el borde del ráster pero solo 2 quedan marcadas. La causa está
medida: al reproyectar a UTM queda una franja de una celda sin dato en los bordes
este, oeste y sur del rectángulo, así que la comprobación —que mira la primera y
última fila y columna— nunca encuentra terreno ahí. Por el norte no hay franja y
por eso ahí sí detecta las 2. No contamina nada hoy, porque las 214 drenan hacia
Argentina y el recorte regional las elimina igual, pero es una salvaguarda que
está dando un falso negativo y hay que arreglarla antes de confiar en ella.

**El reporte de localidades alcanzadas de M3 subestima.** M3 filtra las zonas
urbanas a polígonos, y en esta región las localidades están mapeadas como puntos
—1.113 en el extracto, incluidas La Serena, Coquimbo y Tongoy— que ese filtro
descarta. Lo que hoy reporta como localidad sale del nombre de los polígonos de
uso de suelo, o sea barrios y sitios. Los 422 puntos de corte no están afectados;
lo que no se puede citar es la frase "tantas localidades alcanzadas". Decidir si
una trayectoria que pasa a cierta distancia de un punto poblado cuenta como
alcance urbano es una decisión de modelo, y es de M5.

**El repositorio está en una cuenta antigua.** El remoto apunta a `k1000lala` y
está privado; hay que migrarlo a `camilahndz` antes de enlazarlo en un portafolio.

**No hay pruebas automatizadas.** El proyecto se apoya en figuras de control, que
son buenas para detectar errores groseros y no sirven para detectar una regresión
sutil. Funciones como `largo_cuenca_km` o `clasificar` son puras y fáciles de
probar, y un puñado de pruebas cubriría los casos de frontera de los umbrales.

**Sin gatillo no hay predicción.** Es la limitación de fondo y ya está en el
capítulo 01: el modelo dice qué quebradas son capaces, no cuáles se activan
mañana.

## 8. Lo que está bien y no conviene minimizar

El problema de las cifras era de ejecución y no de método, y esa distinción hay que
hacerla porque es real: al correr el mismo código sobre el territorio completo, los
números salieron y cuadraron.

El razonamiento del proyecto es de un nivel poco común: rechazar un DEM que
anunciaba mejor resolución tras verificar la documentación de la fuente, negarse a
inventar pesos donde existe un índice calibrado, guardar dos clasificaciones en vez
de esconder la sensibilidad de un parámetro heredado, negarse a exponer un alcance
de propagación que no se puede fundamentar, y declarar como juicio lo que es
juicio. Cada una de esas decisiones está escrita en el código, con su alternativa y
su motivo.

El diagnóstico del `--area-min-km2` es una historia técnica completa y verificable.
El control contra la DGA es una verificación externa que casi ningún proyecto de
portafolio tiene, y que además encontró un error que desde adentro no se veía. Y el
hábito de dejar el porqué escrito en el docstring es lo que hizo posible que este
documento se escribiera leyendo el código.

---

## Cómo se lo explicarías a alguien en 60 segundos

Corrí el pipeline completo sobre un DEM al que le faltaba el tercio sur de la
región y no me avisó nada: terminó bien, escribió sus capas y dibujó sus mapas.
Las cifras se veían plausibles —360 cuencas, 16.000 km²— y solo comparándolas
contra la corrida buena se notaba que faltaba el 60% del territorio. Lo peor no era
el faltante sino que las cuencas cortadas por el borde quedaban con el área
truncada, y como Melton es desnivel sobre raíz de área, eso infla el índice: el
máximo pasó de 1,0 a 1,5 y las cuencas críticas de 21 a 38. O sea que el recorte
fabricaba peligro que no existe. Cuando fui a ver por qué la comprobación de
cobertura no lo había detenido, encontré dos cosas: que se había escrito después
del incidente, y que vivía dentro del script que arma el DEM, o sea que protegía la
escritura cuando el problema estaba en la lectura. La saqué a un módulo compartido
y ahora la llaman los cinco scripts que leen un DEM. La lección: un modelo mal
alimentado no da error, da un número, y la única defensa es comprobar la entrada
antes de calcular.

<!-- ===== CAPITULO 13: Glosario (Todos los términos) ===== -->

# 13 — Glosario

## Datos geoespaciales

**DEM** — *Digital Elevation Model*. Grilla donde cada píxel guarda la altura del
terreno en metros.

**Raster** — Dato geográfico en forma de grilla de píxeles. Sirve para lo que
existe en todas partes y varía de forma continua.

**Vector** — Dato geográfico en forma de puntos, líneas o polígonos con atributos.
Sirve para lo que tiene bordes definidos.

**GeoTIFF** — Formato de raster que incluye a qué coordenadas corresponde cada
píxel.

**GeoPackage / GeoJSON** — Formatos de capa vectorial.

**CRS** — *Coordinate Reference System*. La regla que traduce un punto del planeta
a un par de números.

**EPSG:4326** — Latitud y longitud en grados. Un grado no mide lo mismo en todas
partes.

**EPSG:32719** — UTM zona 19 Sur, el sistema métrico de esta parte de Chile. Donde
un metro mide un metro.

**Reproyectar** — Convertir una capa de un sistema de coordenadas a otro.

**Tile** — Pedazo rectangular en que se reparte un dato global. Copernicus publica
el DEM en cuadros de 1×1 grado.

**Mosaico** — El raster continuo que resulta de unir varios tiles.

**Bounding box** — Rectángulo definido por sus bordes oeste, sur, este y norte.

**Remuestrear** — Cambiar el tamaño de píxel de un raster. Hacia arriba, inventa
píxeles por interpolación sin agregar información.

**Resolución efectiva** — Cuánto detalle real contiene un dato, que puede ser
distinto del tamaño de píxel.

## Hidrología

**Cuenca** — Todo el territorio cuya agua termina saliendo por un mismo punto.

**Quebrada** — Cauce, el fondo del valle por donde el agua se concentra.

**Desembocadura / salida** — El punto por donde el agua abandona la cuenca.

**Delinear** — Determinar qué píxeles pertenecen a una cuenca a partir de las
alturas.

**Divisoria de aguas** — La línea que separa dos cuencas.

**Acondicionar** — Rellenar pozos y depresiones e inclinar planicies para que el
agua pueda escurrir. Vuelve el DEM menos fiel al terreno a propósito.

**Pozo** (*pit*) — Un píxel más bajo que sus ocho vecinos. Casi siempre ruido del
sensor.

**Depresión** — Hondonada de varios píxeles sin salida.

**Planicie** (*flat*) — Zona horizontal sin dirección de bajada definida.

**D8** — Regla de escurrimiento donde cada píxel manda toda su agua al vecino con
mayor pendiente descendente.

**Dirección de flujo** — Raster donde cada celda guarda hacia qué vecino drena.

**Acumulación de flujo** — Cuántos píxeles de más arriba drenan por cada punto.
Los valores altos dibujan las quebradas.

**Umbral de área drenada** — El valor de acumulación a partir del cual un píxel
cuenta como cauce. Aquí `--umbral-km2`.

## Riesgo y clasificación

**Inundación de agua** — Agua más o menos limpia desbordándose.

**Crecida de detritos** — Agua con bastante material arrastrado.

**Flujo de detritos / aluvión** — Barro, piedras y bloques moviéndose como una
masa densa. Lo que el proyecto quiere identificar.

**Susceptibilidad** — Qué quebradas son capaces de generar un flujo. Propiedad del
terreno.

**Gatillo** — Cuánta lluvia hace falta para activar una quebrada capaz. No
construido.

**Razón de Melton** — Desnivel dividido por raíz del área. Mide la energía
potencial de la cuenca por unidad de tamaño. Adimensional.

**Wilford et al. (2004)** — El estudio de donde salen los umbrales, publicado en
*Landslides*, calibrado contra eventos reales.

**Runout** — Modelo de propagación que calcula hasta dónde llega el material.
Fuera de alcance de este proyecto.

**Proxy** — Sustituto medible de algo que no se puede medir directamente. Aquí, la
geometría del cauce en lugar de la física del flujo.

**Corredor** — Ancho alrededor del cauce, 45 m. Tolerancia de posición, no
distancia de propagación.

**Punto de corte** — Lugar donde una vía cruza el cauce de una quebrada
susceptible. Es un candidato, no una predicción.

## Instituciones y fuentes

**DGA** — Dirección General de Aguas. Publica las áreas oficiales de las cuencas
de Chile.

**SERNAGEOMIN** — Servicio Nacional de Geología y Minería.

**Copernicus GLO-30** — El DEM elegido. 30 m reales, derivados de TanDEM-X.

**TanDEM-X** — Misión de dos satélites de radar de la que deriva el DEM.

**ALOS PALSAR** — El DEM descartado. Sus productos de "12,5 m" sobre Chile están
remuestreados desde 30 m.

**OpenStreetMap** — De donde salen la red vial y las zonas urbanas.

**geoBoundaries** — De donde sale el límite regional, con la URL anclada a un
commit fijo.

## Software y práctica

**pysheds** — La librería que hace la hidrología.

**rasterio** / **geopandas** — Rasters y vectores respectivamente.

**osmnx** — Descarga de OpenStreetMap. Pin `>=2.0` porque la API cambió.

**Monkey patching** — Modificar una librería desde fuera en tiempo de ejecución.
Lo que hace `compat_pysheds.py`.

**Verificación de precondiciones** — Comprobar que las suposiciones de un cálculo
se cumplen antes de calcular. Aquí, la cobertura del DEM.

**Pipeline por etapas** — Cadena donde cada script escribe archivos que el
siguiente lee, y que se puede retomar en cualquier punto.

**Figura de control** — Mapa generado para revisar a ojo que el resultado tenga
sentido. El ojo detecta errores que ninguna verificación numérica atraparía.