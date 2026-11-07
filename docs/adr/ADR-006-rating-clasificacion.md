# ADR-006: Rating de clasificación: fuentes y parrilla como sustituto

- **Estado:** Propuesto
- **Fecha:** 2026-11-07
- **Autor:** Joaco Mora
- **Relacionado:** ADR-001 (la clasificación como dimensión propia del rating)

## Contexto

El ADR-001 decidió que cada modelo produce un rating de carrera y uno de clasificación.
La clasificación mide el ritmo a una vuelta, donde el piloto lleva el auto al límite.

El problema es la cobertura. Jolpica entrega la clasificación en un archivo propio
(`qualifying.json`), pero no para todas las épocas:

| Período | Clasificación en Jolpica |
|---|---|
| 1950–1993 | No existe |
| 1994–2002 | Parcial: entre 1 y 17 rondas por temporada (1995 completa) |
| 2003–2026 | Completa |

En cambio, cada resultado de carrera (`results.json`) incluye desde 1950 el campo `grid`:
la posición de largada. La parrilla se arma con el resultado de la clasificación, pero las
sanciones (por ejemplo, 10 puestos por cambiar el motor) y algunos formatos especiales la
modifican: un piloto puede hacer la pole y largar undécimo.

**Pregunta:** ¿la parrilla puede sustituir a la clasificación donde esta no existe?

## Evidencia

**Métrica.** El Modelo A solo necesita el **orden entre compañeros**, no la posición
absoluta: si una sanción ajena retrasa a ambos pilotos de un equipo, el duelo no cambia.
Se mide entonces, por temporada, el porcentaje de duelos entre compañeros en que la parrilla
y la clasificación dan el mismo ganador. Se calcula en las temporadas donde existen ambos
datos (1994–2026).

| Época | Concordancia | Lectura |
|---|---|---|
| 1994–2003 | ~100% (1 diferencia en ~930 duelos) | Sin sanciones de parrilla, la parrilla **es** la clasificación |
| 2004–2011 | 96–99% | Aparecen las sanciones por cambio de motor y de caja de cambios |
| 2012–2026 | 92–99% | Valles en 2012 (92,3%), 2014 (93,1%), 2021 (92,3%) y 2022 (93,8%) |

**Detalle de 2021** (16 duelos invertidos de 208):
- **9 en fines de semana con sprint** (Gran Bretaña, Italia y São Paulo): en 2021 y 2022, el
  resultado del sprint armaba la parrilla de la carrera, así que la parrilla del domingo no
  reflejaba la clasificación.
- **7 por sanciones de parrilla** (Estiria, Austria, Turquía, EE.UU. y México).

**Largadas desde pits:** aparecen con `grid` = 0. Entre 0 y 11 duelos por temporada.

## Decisión

### 1. Prioridad de fuentes, por carrera
1. **Clasificación de Jolpica** (`qualifying.json`), cuando existe.
2. **Clasificación desde Wikipedia**, para completar los huecos de 1994–2002 (trabajo futuro,
   con el mismo enfoque del ADR-005).
3. **Parrilla de largada (`grid`)** como sustituto, donde no hay ninguna de las anteriores
   (en la práctica, 1950–1993).

Desde 2003, el rating de clasificación nunca usa la parrilla: es justo la época en que las
sanciones y los formatos especiales la distorsionan.

### 2. Trazabilidad de la fuente
Cada duelo de clasificación registra de dónde salió el orden: `clasificacion`, `wikipedia`
o `parrilla`. Permite analizar el rating por fuente y medir la sensibilidad del resultado.

### 3. Casos especiales
- **Largada desde pits** (`grid` = 0) sin clasificación real: no hay duelo. No se sabe cómo
  habría clasificado.
- **Piloto ausente de la clasificación:** no hay duelo.
- Se aplica la misma lógica de duelos entre compañeros del Modelo A (ADR-001).

### 4. Enriquecimiento sí, imputación no
Los huecos se completan solo con **datos observados de otra fuente** (enriquecimiento).
No se estiman posiciones que no existen en ninguna fuente (imputación). Si en el futuro se
imputara algo, se marcaría siempre como estimado y nunca se mezclaría en silencio con el dato
observado.

### 5. Control continuo
La métrica de concordancia se recalcula cada vez que se reprocesan los datos. Es la evidencia
de este ADR y, a la vez, un control: si los datos cambian, la validación también.

## Alternativas consideradas
- **Solo la clasificación real:** precisa, pero deja fuera 44 temporadas (1950–1993) y gran
  parte de 1994–2002.
- **Solo la parrilla, en toda la historia:** simple, pero en la era moderna habría asignado
  mal el ganador de hasta un 8% de los duelos.
- **Estimar la clasificación faltante:** descartada (sección 4).

## Consecuencias
- (+) Rating de clasificación para toda la historia de la F1.
- (+) La regla está respaldada con evidencia medida, no solo con conocimiento del dominio.
- (+) Cada duelo es trazable a su fuente.
- (−) **Extrapolación:** la validación cubre 1994–2003 y se extiende a 1950–1993. Es
  razonable (las sanciones eran aún más raras), pero esas décadas tenían rarezas propias, como
  parrillas armadas con la suma de tiempos de dos sesiones. Queda como riesgo conocido.
- (−) Las 500 Millas de Indianápolis (1950–1960) contaban para el campeonato con su propio
  formato de clasificación; su tratamiento queda para un ADR propio.

## Trabajo futuro
- Extraer la clasificación de Wikipedia para los huecos de 1994–2002, y validar su
  concordancia con las rondas que sí tiene Jolpica.
- Historia para el backlog: la evolución de las sanciones de parrilla, contada con la
  concordancia por temporada.
