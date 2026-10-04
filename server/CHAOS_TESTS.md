# Pruebas caóticas de `booking-goals`

Resumen de las dos baterías de pruebas aleatorias y de casos extremos que se lanzaron contra `main()` para buscar fallos al mezclar el formato antiguo y el nuevo de `booking-goals`.

Todas las peticiones a aimharder estaban simuladas (mocks). Cada resultado se comparó con un cálculo independiente escrito a partir de las reglas del README. Se comprobaba qué error salía, cuántos logins se hacían y qué clases se reservaban.

## Reglas probadas

| Caso | Comportamiento esperado |
|---|---|
| Formato antiguo (`"0"`–`"6"`, una clase como objeto) **y** `days-in-advance` | Camino original: reserva solo el día hoy + N |
| Cualquier otro caso | Camino nuevo: valida la configuración antes del login y reserva la semana en curso (de lunes a domingo); `days-in-advance` se ignora |
| `timezone` | Decide qué día es "hoy" (`UTC` por defecto) |

## Batería 1: antes de añadir la validación

### Combinaciones aleatorias (3.000 casos)

| Dimensión | Valores |
|---|---|
| Días | De 0 a 7 días distintos por caso |
| Clave del día | Número (`"3"`) o nombre (`"thursday"`), elegido al azar |
| Mismo día dos veces | 15 % de probabilidad de repetirlo con la otra forma (`"0"` y `"monday"`) |
| Clases por día | De 1 a 3, como objeto suelto o como lista |
| `days-in-advance` | `None`, -1, 0, 1, 2, 3, 6, 7, 13 |
| Fecha y hora | Cualquier día a lo largo de 400 días, a cualquier hora |

**Resultado:** 0 fallos.

### Casos extremos (24) y fallos encontrados

| Fallo | Ejemplo | Estado |
|---|---|---|
| Se calcula "hoy" en UTC: al ejecutarlo el lunes a las 00:30 en España toma la semana anterior | Domingo 22:30 UTC | Arreglado con la variable `timezone` |
| Un número de día fuera de rango se acepta sin avisar | `"7"` reserva el lunes de la semana siguiente | Arreglado: se rechaza |
| Un error de configuración para el bot a mitad de la ejecución | `"Monday"`, `"lunes"`, `null`, falta `name`, hora `1700` como número | Arreglado: se rechaza antes del login |
| La búsqueda de clases es demasiado permisiva | `"name": ""` reserva cualquier clase; `"time": "60"` coincide con la duración | Arreglado en el camino nuevo (hora HHMM y nombre no vacío) |

## Batería 2: camino antiguo frente a camino nuevo

### Combinaciones aleatorias (6.000 casos)

| Dimensión | Valores |
|---|---|
| Tipo de configuración | Antigua (1.496), nueva (1.542), mezclada (1.452), rota (1.510) |
| Configuración rota | Claves `"Monday"`, `"7"`, `"lunes"`, `"-1"`, `"01"`, `" 0"`; clases con hora `1700` o `"17:00"`, `name` vacío o ausente, sin `time`, texto suelto, `null` |
| `days-in-advance` | `None`, -1, 0, 1, 2, 3, 6, 7, 13 |
| `timezone` | `UTC`, `Europe/Madrid`, `America/New_York`, `Pacific/Kiritimati` (+14), `Pacific/Pago_Pago` (-11) |
| Fecha y hora | Cualquier día a lo largo de 800 días; dos de cada tres casos cerca de medianoche |
| Clases | 25 % ya reservadas (`bookState: 1`); 5 % de días sin clases |

**Resultado:** 0 fallos.

### Casos extremos (17)

| Caso | Resultado |
|---|---|
| Antiguo + `days-in-advance`, falta `name` | No reserva nada y no avisa (comportamiento original) |
| Antiguo + `days-in-advance`, `"name": ""` | Reserva cualquier clase de esa hora (comportamiento original) |
| Antiguo + `days-in-advance`, hora como número | El bot se para con `TypeError` (comportamiento original) |
| Antiguo + `days-in-advance`, la clase no existe | El bot se para con `NoBookingGoal` (comportamiento original) |
| Antiguo + `days-in-advance`, box cerrado | El bot se para con `BoxClosed` (comportamiento original) |
| Antiguo + `days-in-advance`, clave `"7"` | Va por el camino nuevo y se rechaza sin login |
| Antiguo + `days-in-advance`, `{}` | No reserva nada y no hace login |
| Nuevo, `{}` o un día con `[]` | Hace login sin necesidad |
| Mezcla `"0"` + `"monday"` con `days-in-advance` | Camino nuevo; reserva las dos clases del lunes |
| `timezone` inválida (`Mars/Phobos`) | El bot se para antes del login, con un traceback de Python |
| Madrid pasada la medianoche (antiguo + `days-in-advance`) | Toma el lunes correcto |
| `Pacific/Kiritimati`, domingo 10:30 UTC | Ya es lunes: reserva la semana que empieza ese lunes |
| Cambio de hora de marzo en Madrid | Fecha correcta |
| `days-in-advance=700` | Fecha correcta |
| Clave `"0"` repetida en el JSON | Se queda con la última (como en el original) |

### Línea de comandos (7 casos, con `argparse` como en el `Makefile`)

| Caso | Resultado |
|---|---|
| Formato antiguo + `--days-in-advance=0` | Reserva el día correcto |
| Formato nuevo con `--proxy=` y `--timezone=` vacíos | Usa los valores por defecto |
| Formato nuevo + `--timezone=Europe/Madrid` | Correcto |
| `--days-in-advance=` vacío | `argparse` sale con código 2 (el `Makefile` no lo pasa si está vacío) |
| `--days-in-advance=x` | `argparse` sale con código 2 |
| `--booking-goals` que no es JSON | `argparse` sale con código 2 |
| `--booking-goals=[1,2]` | `InvalidBookingGoals` sin login |

## Pendiente

- Los fallos que quedan en el camino antiguo (`name` ausente o vacío, la clase no existe, box cerrado) **no se arreglan**: por decisión, ese camino se comporta exactamente como el original.
- Mostrar un mensaje claro cuando la `timezone` no existe, en lugar del traceback.
- No hacer login cuando no hay ninguna clase que reservar.
