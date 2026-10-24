# ADR-001: Modelo de rating ELO para pilotos de F1

- **Estado:** Aceptado
- **Fecha:** 2026-10-22
- **Autor:** <tu nombre>

## Contexto

Queremos un ranking histórico de pilotos de F1 que mida al piloto y no al auto.
Un ELO ingenuo por posición final premia al que maneja el mejor auto. En F1 el único
enfrentamiento con igualdad de máquina es contra el compañero de equipo.

Fuente de datos: Jolpica-F1 (sucesor de Ergast, API compatible). La granularidad
disponible varía según la época:

| Capa | Disponible desde | Fuente |
|---|---|---|
| Resultados de carrera y clasificación | 1950 | Jolpica-F1 |
| Tiempos por vuelta | ~1996 | Jolpica-F1 |
| Sectores, telemetría, stints | ~2018 | FastF1 |

## Decisión

Construimos **dos modelos en paralelo** sobre los mismos duelos y comparamos sus resultados.

### Sistema de rating: Glicko-2 en vez de ELO clásico
Cada piloto tiene tres valores, no uno:
- **Rating (μ):** nivel estimado. Inicial 1500.
- **Desviación (RD):** cuánta incertidumbre hay sobre ese nivel. Inicial 350.
- **Volatilidad (σ):** qué tan errático es el piloto. Inicial 0,06.

El período de rating es el gran premio. La RD crece en cada período sin competir
(hiatos, retiros temporales, temporadas fuera) y baja al acumular duelos.
Una RD alta hace que los primeros resultados muevan mucho el rating, lo que reemplaza
el K provisional del ELO.

Un hiato no baja el nivel estimado del piloto: aumenta la incertidumbre sobre él.
El modelo no asume que empeoró; asume que sabe menos y lo recalibra rápido al volver.

### Modelo A: duelo con el compañero de equipo
- Cada sesión válida genera un duelo por pareja de compañeros: gana quien termina adelante.

### Modelo B: parrilla ajustada por constructor
- Cada sesión genera duelos por pares contra toda la parrilla clasificada.
- El resultado esperado incorpora la diferencia de rating del constructor:
  `E(a,b) = 1 / (1 + 10^(((R_b + C_b) - (R_a + C_a)) / 400))`
- C = rating del constructor por temporada, actualizado con los resultados del equipo.
- Cada duelo pesa `1 / (N - 1)` para que una carrera con N pilotos no pese N veces más.

### Reglas comunes
- **Sesiones:** la clasificación es una dimensión propia, no un ajuste de la carrera.
  Cada modelo (A y B) produce un rating de carrera y un rating de clasificación.
  La qualy mide ritmo puro a una vuelta, donde el piloto lleva el auto al límite;
  la carrera mide gestión, consistencia y lectura de la carrera. Los sprints quedan fuera del MVP.
- **Abandonos:** se clasifica el campo `status` de Jolpica y cada categoría se atribuye a quien corresponde:
  - *Mecánico* (motor, caja, hidráulica, etc.): el piloto no pierde el duelo.
    El abandono penaliza al constructor (rating C del Modelo B e índice de confiabilidad).
  - *Error del piloto* (accidente, trompo): derrota completa del piloto (peso 1).
  - *Colisión*: derrota del piloto con peso reducido (0,5), porque los datos no permiten
    atribuir la culpa. El peso refleja la incertidumbre, no un juicio.
  - *Sin clasificar*: va a una tabla de cuarentena y no entra al cálculo hasta revisarse.
- **Índice de confiabilidad del constructor:** tasa de abandonos mecánicos por temporada.
  Alimenta el rating C y se publica como métrica propia.
- **Alcance del MVP:** temporadas 2000 a la actual. El backfill hasta 1950 se hace después
  de validar el modelo.
- **Validación:** el top 10 de ambos modelos se contrasta con consensos conocidos.
  Las discrepancias grandes entre A y B se investigan; no se corrigen a mano.

## Consecuencias

- (+) Dos modelos permiten comparar una señal pura con una señal con más cobertura.
- (+) La tabla de cuarentena hace explícita la calidad del dato desde la ingesta.
- (−) El Modelo A conecta lento a pilotos que nunca compartieron equipo.
- (−) Clasificar `status` es una decisión manual y discutible; se versiona como tabla de referencia.
- (−) No se puede distinguir una falla mecánica provocada por el piloto (sobreexigencia,
  pasarse de régimen) de una falla del equipo. Se asume falla del equipo.
- (−) Las colisiones penalizan también a la víctima, aunque con peso reducido.

## Alternativas consideradas
- **ELO clásico:** simple y explicable, pero sin noción de incertidumbre. Trata igual a un
  piloto que volvió tras tres años fuera y a uno que corrió todas las carreras.
- **TrueSkill / OpenSkill:** modelan carreras multi-competidor de forma nativa y encajan bien
  con el Modelo B. Se dejan como candidato para una iteración futura del Modelo B.

## Fuera de alcance (ADRs futuros)
- **Actividad en otras categorías:** una tabla de referencia manual (por ejemplo, WEC
  Hypercar, IndyCar, rally raid) que module cuánto crece la RD durante un hiato,
  según la similitud de la categoría con la F1.
- **ADR-002:** rating basado en ritmo (tiempos por vuelta desde ~1996, sectores desde ~2018).
  No se mezcla con el ELO por resultado, porque cambiaría la base de comparación entre épocas.
- Regresión a la media entre temporadas.
- Arquitectura de ingesta y cálculo en GCP (ADR-003).

## Preguntas abiertas
- ¿Cómo tratar las temporadas con equipos de 3 o más autos (años 50–60)?

## Decisión sobre la edad
La edad **no es una entrada** del modelo; se analiza como **salida**.
- La curva de rendimiento por edad cambió entre épocas (medicina, preparación física,
  edad de entrada a la F1). Para ajustarla habría que estimarla desde los mismos datos
  que luego se evalúan, lo que sería circular.
- Glicko-2 ya refleja el declive a través de los resultados, sin suponer cuándo ocurre.
- Análisis posterior: rating vs. edad por década, para ver si el pico se desplazó.
  Ojo con el sesgo de supervivencia: solo los pilotos que siguen rindiendo llegan a correr a los 40.
