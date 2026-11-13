# Rendimiento de agentes y LLM

El arranque normal de FrED (`bash start_fred.sh` o `python main.py` en la carpeta
del dispositivo) abre automáticamente una ventana independiente de rendimiento.
Se puede cerrar y volver a abrir desde el botón **Rendimiento de agentes y LLM**
de FrED. Su cierre no detiene los agentes ni sus registros.

## Qué muestra

- Estado de cada agente, mensajes pendientes, eventos completados, errores y
  tasa media de eventos por segundo durante la sesión.
- Tiempo de procesamiento y de espera en cola, con media y percentiles.
  Percepción ejecuta muestreos propios: su fila mide lectura y publicación,
  no espera en una cola que no utiliza.
- Identidad del modelo y proveedor configurados. **MockLLM es un simulador
  determinista**: su latencia no representa la de un LLM real.
- Llamadas completadas al modelo, errores, respuestas rechazadas, última latencia,
  media, p50 y p95. La gráfica muestra el p95 reciente del modelo y del
  procesamiento de seguridad, actualizados cada segundo con la ventana visible.
- CPU y memoria residente del proceso de control/agentes/interfaz. El porcentaje
  de CPU se calcula con tiempo de CPU dividido entre tiempo real entre muestras
  y puede superar 100% cuando se usan varios núcleos. La captura corre en otro
  proceso y su uso de CPU/RAM no está incluido. RSS se obtiene en Linux; en
  plataformas sin esa lectura aparece sin valor.
  Estas muestras también se registran aproximadamente cada dos segundos en el
  hilo de escritura, aunque el display esté cerrado. Sin registro a disco,
  no se inicia este muestreo periódico y esos valores aparecen sin valor.
- Ruta de los registros, tamaño de la cola de escritura, eventos perdidos y
  errores de almacenamiento. La instrumentación añade trabajo al proceso y no
  sustituye una medición externa del tiempo real de control.

La entrada **Medir propuesta** envía trabajo al agente de razonamiento en modo
de prueba. La llamada se hace en su hilo y no bloquea directamente la interfaz.
Se muestra la respuesta y se registra su latencia, **sin aplicarla al hardware**.
Con MockLLM se puede probar `set fan to 30 percent`. La aceptación de un nombre
de comando por este simulador no valida los parámetros para una corrida física.

## Definiciones de tiempo

Se utiliza `time.perf_counter_ns()` para duraciones y UTC para trazabilidad.
Las marcas monotónicas de estos eventos pertenecen a un único proceso; no se
deben comparar directamente con marcas de otra máquina o de la cámara.

| Campo | Intervalo medido |
|---|---|
| `processing_ms` | Inicio a final del manejador de un mensaje, o lectura/publicación de percepción. Excluye el registro de su propia métrica. |
| `queue_wait_ms` | Entrada del mensaje en la cola del receptor hasta el inicio de su manejador. |
| `inference_ms` | Justo antes de `model.generate()` hasta su retorno o excepción. Una llamada por API incluiría la espera de esa API. |
| `request_latency_ms` | Creación de la solicitud hasta tener y revisar la respuesta, incluyendo la espera en cola. |
| `trace_latency_ms` | Creación del mensaje que inició la traza hasta terminar el manejador actual. Se propaga entre razonamiento/control y percepción/seguridad/control. |
| `handoff_ms` | Solicitud de paro del agente hasta terminar las llamadas de paro en el hilo de hardware. |
| `observation_to_stop_ms` | Creación de la observación que originó una alerta hasta terminar esas llamadas de paro. No incluye adquisición previa del sensor ni confirma físicamente la detención. |

La media, el máximo y los contadores son acumulados de toda la sesión.
Los percentiles p50/p95 se calculan por interpolación sobre las **últimas 512
muestras de cada métrica**, o las disponibles si son menos. No representan un
percentil de toda la sesión cuando se supera esa ventana. Los eventos crudos
permiten recalcular estadísticas por corrida, fase o periodo.

`time_to_first_token_ms` y `cost_usd` permanecen en `null`: no se ha integrado
streaming ni facturación. `usage` sólo conserva lo que reporte el adaptador del
modelo, si lo reporta. No se estiman tokens a partir de caracteres, ni se
presenta velocidad de tokens o consumo eléctrico sin medición. La primera
comparación con un LLM real exige integrar ese modelo y documentar su
configuración y condiciones de ejecución.

## Archivos y relación con los experimentos

Cada arranque genera un identificador único y una carpeta:

```text
Data/agent_metrics/IDENTIFICADOR_DE_SESION/
  events.jsonl
  events.csv
  summary.json
  timings.csv
```

- **events.jsonl**: eventos UTC/monotónicos, tipo, agente, estado, identificador
  y correlación de mensaje, corrida y fase actuales, duraciones, instrucciones,
  respuestas y errores. Las llamadas al modelo incluyen identidad y la marca
  `simulated`. Los eventos de ciclo de vida identifican la configuración del
  runtime y su inicio/cierre.
- **summary.json**: contadores y agregados por agente/tipo/métrica; incluye el
  tamaño de ventana, estado del registro y la indicación de cierre.
- **events.csv**: una fila por evento, con identificadores, estado, tiempos,
  identidad de modelo y uso reportado. Permite analizar latencias por corrida
  en Excel sin convertir el JSONL. Las instrucciones y respuestas completas
  se conservan en el JSONL.
- **timings.csv**: tabla de agregados exportable, con media, máximo, último valor,
  p50/p95 y número de muestras usadas para el percentil.

Los metadatos del experimento (`*.metadata.json`, recuperados desde la cámara)
incluyen `agent_session_id`; los eventos incluyen `run_id`. Así se puede unir
el comportamiento del sistema de agentes con el CSV de cada experimento.
Los eventos fuera de una corrida pueden tener `run_id: null` y una sesión puede
contener varias corridas. Los tiempos de inferencia no son tiempos de respuesta
del proceso físico ni índices de calidad del filamento.

La escritura se hace en un hilo dedicado, con una cola limitada a 4096 eventos.
Se vacía el buffer y se actualizan los agregados aproximadamente cada dos
segundos y al cerrar normalmente. Si la cola se llena, se descartan eventos de
registro y se cuenta la pérdida; el control no espera al disco. Un cierre
forzado puede perder eventos todavía en memoria. La ventana y los registros
indican los errores de escritura para no interpretar una captura incompleta
como completa. Los resúmenes no reemplazan a los eventos crudos.

Para cambiar las rutas:

```bash
bash start_fred.sh --data-dir /RUTA/DATOS --metrics-dir /RUTA/METRICAS
```

Las pruebas automatizadas separan latencia de cola y modelo usando un modelo
de prueba con retardo, comprueban que el modo de prueba no envía comandos,
registran excepciones/rechazos y verifican percentiles y archivos persistidos.
La validación física y las mediciones representativas de la Pi siguen pendientes.
