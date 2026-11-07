# ADR-005: Causas de abandono desde Wikipedia

- **Estado:** Aceptado (2026-11-07)
- **Fecha:** 2026-11-07
- **Autor:** Joaco Mora
- **Relacionado:** ADR-004 (clasificación de abandonos; este ADR amplía su taxonomía),
  `enrichment/wikipedia_causes.py`, `reference/wikipedia_causa_categoria.csv`,
  `reference/abandonos_revisados.csv`, `reference/wikipedia_overrides.csv`

## Contexto

El control de deriva del ADR-004 mostró que, desde 2023, Jolpica registra casi todos los
abandonos como `Retired`, sin causa:

| Temporada | Abandonos | No atribuibles | % |
|---|---|---|---|
| 2023 | 61 | 53 | 87% |
| 2024 | 51 | 49 | 96% |
| 2025 | 57 | 51 | 89% |
| 2026 | 79 | 79 | 100% |

Todas superan el umbral de baja atribución (30%). En la práctica, el modelo dejaba de
penalizar los errores de los pilotos desde 2023: el sesgo entre épocas que el ADR-004
anticipó como consecuencia.

## Opciones evaluadas

| Opción | Resultado |
|---|---|
| **Wikipedia** (API de MediaWiki) | La tabla de clasificación de cada GP indica la causa de cada abandono. **Elegida** |
| OpenF1 / FastF1 | Cubren la era moderna, pero no dan la causa directa: habría que inferirla |
| Inferencia con reglas | Estimación con error desconocido; útil como complemento futuro |
| Curación manual | No escala; se usa como muestra de validación y para casos dudosos |
| Corregir en el origen (Jolpica) | Deseable, pero sin control ni plazo |
| Sitio oficial de la F1 | Descartado: sus términos de uso prohíben el scraping |

## Experimento

1. **Una carrera** (Australia 2024): Jolpica dice `Retired` para Russell, Hamilton y
   Verstappen; Wikipedia, `Accident`, `Power unit` y `Brakes`. 3 de 3.
2. **Una temporada** (2024): 49 de 49 `Retired` con causa.
3. **2023–2026**, después de las correcciones: 89 carreras, 1.816 resultados,
   **232 de 232 `Retired` con causa (100%)**, con el denominador incluyendo las carreras
   que fallen.

**Hallazgo principal:** 108 de los 232 abandonos (~47%) están relacionados con el piloto
(Collision, Accident, Collision damage, Spun off, Accident damage). Con la regla del
ADR-004, el modelo los ignoraba todos.

## Decisión

### 1. Wikipedia como fuente complementaria, en una capa aparte
Jolpica sigue siendo la fuente principal de los resultados. Wikipedia aporta solo la causa
de los abandonos y **nunca sobrescribe** a Jolpica: el extractor guarda, al lado del dato
de Jolpica, el texto original de Wikipedia, el título del artículo y su `revid` (la versión
exacta leída). Así, cada causa se puede rastrear hasta su texto de origen aunque el artículo
se edite después.

### 2. Llaves de cruce
- **Artículo:** la URL que Jolpica entrega en cada carrera.
- **Piloto:** el número de auto, único dentro de cada carrera; no el nombre.
- **Las rondas siguen la numeración de Jolpica**, que solo cuenta las carreras disputadas.
  Otras fuentes pueden numerar distinto: F1TV conserva la ronda de Imola 2023, cancelada,
  y desde ahí todo queda desplazado en uno. Para cruzar con otras fuentes se usa el nombre
  de la carrera o su fecha, nunca el número de ronda.
- **Excepciones de títulos** (`wikipedia_overrides.csv`): cuando la URL de Jolpica es
  incorrecta. Caso actual: la ronda 7 de 2026 apunta a `2026_Barcelona-Catalunya`, que no
  existe en Wikipedia.

### 3. Clasificación en dos niveles
1. **Regla general por causa** (`wikipedia_causa_categoria.csv`): las 45 causas observadas,
   comparadas sin distinguir mayúsculas ("Collision Damage" = "Collision damage").
2. **Revisión caso a caso** (`abandonos_revisados.csv`): una decisión tomada con evidencia,
   registrada con su fuente y su revisor. **Manda sobre la regla general.**

Orden de precedencia: revisión caso a caso > regla de Wikipedia > tabla de status de
Jolpica (ADR-004).

El segundo nivel existe porque **Wikipedia nombra la pieza que falló, no el origen de la
falla**. En Japón 2023, dos de los tres `Undertray` fueron daños por un choque en cadena,
no fallas mecánicas: aplicar la regla general a ciegas habría penalizado la confiabilidad
de dos equipos por un accidente.

### 4. Ampliación de la taxonomía del ADR-004

| Categoría nueva | Significado | Efecto en el piloto | Efecto en el constructor |
|---|---|---|---|
| `victima` | Abandono por error de **otro** piloto | Sin duelo | — |
| `sancion_tecnica` | Descalificación: el auto no cumplía el reglamento técnico | Sin duelo | Cuenta para la confiabilidad con **peso 0,5** |
| `sancion_deportiva` | Descalificación por infracción deportiva | Según el caso | Según el caso |

- `victima` se distingue de `fortuito` (ADR-004): en `fortuito` nadie tuvo la culpa; en
  `victima` sí, y fue otro piloto.
- El peso 0,5 de `sancion_tecnica` refleja que el auto corrió la carrera completa (no fue una
  falla de confiabilidad en sentido estricto), pero el equipo lo preparó fuera del
  reglamento. Es un parámetro a calibrar con el análisis de sensibilidad.
- Las descalificaciones deportivas se clasifican según su origen. Ejemplo: Hülkenberg,
  Brasil 2024, recibió ayuda externa después de un trompo propio → `error_piloto`.

**Pesos del índice de confiabilidad del constructor:**

| Origen | Peso |
|---|---|
| `mecanico`, `operacion_equipo`, `Did not start` | 1,0 |
| `sancion_tecnica` | 0,5 |

### 5. Duelo entre compañeros ambos descalificados
**No hay duelo.** Criterio: *un duelo cuenta si ninguno de los dos tuvo una ventaja que el
otro no tuvo*. Con descalificaciones técnicas eso no se puede verificar. Ejemplo: China
2025, Leclerc (auto bajo el peso mínimo) terminó delante de Hamilton (tabla del fondo
gastada): ambos tuvieron ventajas ilegales distintas y de magnitud desconocida. Además,
hay un solo caso en cuatro temporadas.

### 6. Decisiones sobre causas puntuales
- **Heatstroke → `fortuito`:** condición física por calor extremo, análoga a enfermarse
  (Sargeant, Qatar 2023). Los trajes refrigerantes son recientes en la categoría.
- **Safety switch → `mecanico`** por regla general; con evidencia de causa externa, se
  revisa caso a caso (Hülkenberg, Barcelona 2026: una piedra golpeó el interruptor →
  `fortuito`).

### 7. Controles de calidad del extractor
- **Tabla correcta:** se busca la tabla bajo la sección "Race", porque la del sprint tiene
  las mismas columnas.
- **Notas al pie:** los superíndices se eliminan antes de leer el texto (causaban
  encabezados como "Lapsa" y causas como "Collision1").
- **Cobertura con denominador honesto:** los `Retired` de carreras que no se pudieron
  procesar cuentan en el total.
- **Consistencia de vueltas entre fuentes:** se cuentan aparte las descalificaciones, porque
  Jolpica les registra 0 vueltas y Wikipedia las que realmente dieron. Las 5 diferencias de
  2023–2026 resultaron ser descalificaciones.
- **Cuarentena:** una causa sin regla no se clasifica; se aparta y genera alerta.

### 8. Licencia y uso responsable
- El contenido de Wikipedia tiene licencia **CC BY-SA 4.0**: requiere atribución, y lo
  derivado se comparte con la misma licencia. La tabla de causas extraída se publica bajo
  CC BY-SA 4.0, citando a Wikipedia como fuente.
- El extractor se identifica con un User-Agent descriptivo, espera 1 segundo entre
  llamadas y guarda una caché para no repetir descargas.

## Muestra de validación
10 casos revisados a mano con evidencia (resúmenes oficiales de formula1.com y repeticiones
de F1TV), en `abandonos_revisados.csv`:
- **5 abandonos con causa de Wikipedia.** En 2 la revisión confirmó la regla general
  (Pérez, Canadá 2024; Sargeant, Qatar 2023). En 3 la causa era correcta pero nombraba la
  pieza dañada y no el origen, y la categoría cambió (Bottas y Albon, Japón 2023:
  `Undertray` → `victima`; Hülkenberg, Barcelona 2026: `Safety switch` → `fortuito`).
- **5 descalificaciones**, que Jolpica registra como `Disqualified` sin indicar el tipo:
  4 técnicas y 1 deportiva originada en un error del piloto.
- Una primera revisión con la transmisión se corrigió con la cámara a bordo (Japón 2023):
  la evidencia se registra porque no toda tiene la misma calidad.

## Consecuencias
- (+) Se recupera la causa del 100% de los abandonos modernos, y con ella ~47% de abandonos
  atribuibles al piloto que el modelo ignoraba.
- (+) Cada clasificación es trazable: texto original, versión del artículo, regla o revisión,
  evidencia y revisor.
- (−) Dependencia de una fuente editada por la comunidad. Mitigación: `revid`, controles de
  consistencia con Jolpica y revisión caso a caso.
- (−) Las revisiones dependen del criterio del revisor, que puede discrepar de los
  comisarios. Se registra explícitamente que es criterio del revisor.
- (−) **El modelo atribuye abandonos, no culpas.** Un piloto que provoca un choque y sigue en
  carrera no recibe penalización (Ocon, Japón 2023). Corregirlo requiere otra fuente.

## Trabajo futuro
- Reportar a Jolpica la URL incorrecta de la ronda 7 de 2026.
- Integrar las tablas en el cálculo del rating y medir el ranking antes y después.
- Evaluar los documentos oficiales de los comisarios (FIA) para atribuir culpas en incidentes.
- Medir la cobertura de Wikipedia en épocas anteriores, si se necesitara.
