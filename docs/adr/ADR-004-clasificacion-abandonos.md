# ADR-004: Clasificación de abandonos y estados de resultado

- **Estado:** Aceptado (2026-11-04)
- **Fecha:** 2026-11-04
- **Autor:** Joaco Mora
- **Relacionado:** ADR-001 (reglas comunes: abandonos), `reference/status_categoria.csv`

## Contexto

El ADR-001 definió cuatro tratamientos para los abandonos: mecánico, error del piloto,
colisión y sin clasificar. Al analizar los resultados 2000–2026 (~11.000 resultados,
104 valores distintos del campo `status` de Jolpica) aparecieron problemas que esa
regla no cubre:

1. **Notaciones distintas para lo mismo:** `Lapped` y `+1 Lap`, `+2 Laps`…;
   `Puncture` y `Tyre puncture`.
2. **Significados que cambian con el reglamento:** `Stalled` (calar el motor) era
   un error del piloto; con las unidades de potencia híbridas pasa a indicar una
   falla del auto.
3. **Casos sin culpable:** `Debris` (restos de otro auto) es azar, no error de nadie.
4. **Valores genéricos:** `Retired`, `Handling`, `Damage` no indican la causa.
5. **Deriva semántica de `Retired`:** desde 2023 la fuente registra así casi todos
   los abandonos, sin indicar la causa:

   | Temporadas | `Retired` por temporada |
   |---|---|
   | 2005–2021 | 1 a 12 |
   | 2022 | 0 |
   | 2023–2026 | 36 a 71 |

   El formato no cambió y ningún proceso falla: la información se pierde en silencio.

## Decisión

### 1. Una tabla de referencia versionada como única fuente de verdad
La clasificación vive en `reference/status_categoria.csv`, bajo control de versiones.
Ningún componente clasifica abandonos con reglas propias en el código: todos leen esta
tabla. Cada cambio de criterio queda en el historial de Git con autor y fecha.

| Columna | Significado |
|---|---|
| `status` | Valor tal como lo entrega Jolpica |
| `coincidencia` | `exacta`, o `prefijo` (ej.: `+` cubre `+1 Lap`, `+42 Laps`…) |
| `status_normalizado` | Valor unificado para el análisis |
| `desde_temporada` / `hasta_temporada` | Vigencia de la fila, inclusiva; vacío = sin límite |
| `categoria` | Una de las categorías de la sección 2 |
| `tratamiento` | Cómo afecta al duelo |
| `peso_derrota` | Peso de la derrota cuando el tratamiento lo requiere |
| `nota` | Por qué el status está en esa categoría |

### 2. Taxonomía de categorías

| Categoría | Ejemplos | Efecto en el piloto | Efecto en el constructor |
|---|---|---|---|
| `terminado` | Finished, +N Laps, Lapped | Duelo normal por posición | — |
| `error_piloto` | Accident, Spun off | Derrota, peso 1,0 | — |
| `colision` | Collision, Collision damage | Derrota, peso 0,5 (no se sabe quién tuvo la culpa) | — |
| `no_reanudo` | Not restarted | Derrota, peso 0,5 (criterio análogo al reglamento de puntos en carreras incompletas) | — |
| `mecanico` | Engine, Gearbox, Not classified | Sin duelo | Cuenta para el índice de confiabilidad |
| `operacion_equipo` | Wheel nut, Fuel rig, Out of fuel | Sin duelo | Cuenta para el índice de confiabilidad |
| `fortuito` | Debris | Sin duelo | — |
| `no_atribuible` | Retired, Handling, Damage, Puncture | Sin duelo | — |
| `sancion` | Disqualified, Excluded | Sin duelo; se marca para análisis | — |
| `no_compitio` | Did not start, Withdrew, Illness | Sin duelo | Solo `Did not start` cuenta para el índice de confiabilidad (ver sección 9) |

`fortuito` y `no_atribuible` tienen el mismo efecto, pero se mantienen separadas porque
significan cosas distintas: en el primero se sabe que nadie tuvo la culpa; en el segundo,
no se sabe.

### 3. Matriz de duelo entre compañeros

El efecto de cada categoría depende de lo que le pasó al compañero:

| Piloto A | Piloto B | Resultado |
|---|---|---|
| `terminado` | `terminado` | Gana quien terminó adelante |
| `terminado` | `error_piloto`, `colision` o `no_reanudo` | Gana A, con el peso de la categoría de B |
| `terminado` | Cualquier categoría sin duelo | No hay duelo |
| Abandono | Abandono | Prorrateo por vueltas (ver abajo) |

El peso se aplica igual al ganador y al perdedor: un duelo de peso 0,5 da la mitad de
información a ambos.

**Prorrateo cuando ambos abandonan.** Gana quien completó más vueltas, solo si el abandono
de quien completó menos es atribuible al piloto (`error_piloto`, `colision` o `no_reanudo`).
El peso es proporcional a la diferencia de vueltas:

```
peso = peso_categoria_del_perdedor × (vueltas_ganador − vueltas_perdedor) / vueltas_de_la_carrera
```

`vueltas_de_la_carrera` son las vueltas del ganador del GP. Si ambos completaron las
mismas vueltas, o si quien completó menos abandonó por una causa no atribuible al piloto,
no hay duelo. Ejemplo: en una carrera de 57 vueltas, A choca en la vuelta 5 y B en la 50;
gana B con peso 1,0 × 45 / 57 ≈ 0,79. Las vueltas vienen en el campo `laps` de Jolpica.

### 4. Se conserva el valor crudo y se deriva el normalizado
El loader guarda siempre el `status` original y, al lado, el normalizado y la categoría.
Nunca se pierde lo que dijo la fuente, y una reclasificación futura se aplica sobre los
datos crudos sin volver a descargarlos.

### 5. Vigencia por temporada (dimensión de cambio lento)
Un mismo status puede tener filas distintas según la época. Ejemplo: `Stalled` es
`error_piloto` hasta 2013 y `mecanico` desde 2014. Para un mismo status, los intervalos
de vigencia no pueden solaparse.

Evidencia para el corte de `Stalled` en 2014: el MGU-K, que puede reiniciar el motor,
existe desde 2014, y hay reinicios en pista documentados en 2016 (Sainz, Malasia) y 2017
(Räikkönen, Australia). El reglamento técnico solo regula el arranque con dispositivos
externos en garaje, pit lane y parrilla, y la interpretación sobre la pista es discutida.
El corte se acepta como razonable y no se investiga más: `Stalled` aparece **una sola vez**
entre 2000 y 2026, así que su impacto en el modelo es despreciable.

### 6. Cuarentena: un estado del proceso, no una categoría
- **`no_atribuible`** es una decisión tomada: alguien revisó el status y concluyó que
  la causa no se puede determinar con los datos disponibles.
- **Cuarentena** es lo que ocurre con un status que **no está en la tabla** (o no tiene
  una fila vigente para esa temporada). El resultado se aparta del cálculo, se registra
  en la tabla de cuarentena y genera una alerta hasta que alguien lo clasifique.

Así, la cuarentena funciona como alarma: en régimen normal, debería estar vacía.

### 7. Controles automáticos de calidad
1. **Validez de la tabla** (antes de usarla): cada combinación de categoría, tratamiento
   y peso es una de las permitidas, y no hay vigencias solapadas.
2. **Cobertura:** cada `status` recibido tiene una fila vigente; si no, cuarentena.
3. **Deriva:** proporción de abandonos `no_atribuible` por temporada (sin contar
   `terminado` ni `no_compitio`). **Umbral: 30%.** Sobre ese valor, la temporada se marca
   como de **baja atribución**: sus abandonos aportan poca información y sus resultados se
   reportan con esa advertencia. El 50% se consideró demasiado tarde: a esa altura, la
   mitad de los abandonos ya no informa al modelo.

El prototipo de estos tres controles está en `reference/check_status.py`.

### 8. Implementación del peso en Glicko-2
Glicko-2 no tiene pesos por partida. Se usa la extensión habitual: los términos del duelo
en el cálculo de la varianza (v) y de la mejora (Δ) se multiplican por el peso.
Alternativa descartada: registrar la derrota como resultado 0,25 en vez de 0; eso
cambia el significado del resultado (un "cuarto de victoria") en lugar de su peso.

### 9. Índice de confiabilidad del constructor
Cuentan los resultados con tratamiento `excluir_penaliza_constructor`: `mecanico`,
`operacion_equipo` y `Did not start`. Se incluye `Did not start` por probabilidad: casi
siempre es el auto el que no parte. El error de incluir los pocos casos causados por el
piloto (por ejemplo, un accidente en la vuelta de formación) se acepta hasta tener una
fuente con más detalle.

## Alternativas consideradas
- **Tratar `Retired` como mecánico**, por ser la causa más probable: descartada. Inventa
  una causa, y desde 2023 cargaría casi todos los abandonos a los constructores.
- **Inferir la causa de los abandonos modernos con los mensajes de dirección de carrera**
  (FastF1): prometedora, pero requiere otra fuente y otro proceso. Queda para un ADR futuro.
- **Clasificar en código** (un diccionario en Python): descartada. El criterio de dominio
  quedaría escondido y cada cambio exigiría un deploy.

## Consecuencias
- (+) El criterio queda explícito, versionado y revisable por alguien que no lee código.
- (+) Una reclasificación cambia una fila del CSV, no el código.
- (+) La deriva de la fuente se detecta automáticamente.
- (−) **Sesgo entre épocas:** antes de 2023, los errores de los pilotos penalizan; desde
  2023, la mayoría de los abandonos son `no_atribuible` y no penalizan a nadie. El modelo
  es más indulgente con los pilotos actuales. Mitigación: análisis de sensibilidad que
  compare el ranking con y sin penalización de errores en todo el período.
- (−) El índice de confiabilidad de los constructores también pierde información desde 2023.
- (−) La clasificación depende del criterio de quien la define; la columna `nota` y el
  historial de Git hacen ese criterio auditable.

## Trabajo futuro
- **Fuente con más detalle sobre los abandonos** (prioridad alta si las temporadas desde
  2023 superan el umbral de baja atribución): mensajes de dirección de carrera vía FastF1,
  para atribuir los `Retired` modernos y separar los `Did not start` causados por el piloto.
