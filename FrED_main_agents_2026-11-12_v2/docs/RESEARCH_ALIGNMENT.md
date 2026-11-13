# FrED: alineación de investigación y primera sesión experimental

Fuente: `Presentation_Summary_Russel (1).pdf`, revisión del 12 de noviembre de
2026. El documento se usa como descripción del rumbo de la investigación.

## Objetivo y estado real

El objetivo es seleccionar consignas y ganancias PID según prioridades,
comparar LLM y control clásico y construir un frente de Pareto de productividad,
error y consumo mediante MOBO. La presentación sitúa primero la línea base
clásica y la implementación independiente del LLM; la integración completa
está programada para abril de 2027.

| Componente | Lo que existe | Trabajo pendiente |
|---|---|---|
| Percepción | Lecturas a través de `FrEDInterface`, conectadas al hardware en el arranque local; validez del diámetro | Sincronización y telemetría de potencia |
| Seguridad | Alerta de temperatura y paro enclavado integrados al hilo de hardware local | Verificación física en la Pi; los límites actuales no son una validación del material |
| Control | Comandos discretos con límites y control deshabilitado por defecto | Aplicación coordinada de consignas y PID, con un solo propietario de los actuadores |
| Razonamiento | `MockLLM`, analizador determinista de instrucciones en inglés | LLM real, propuestas explicadas, prioridades y evaluación experimental |
| Experimentos | Secuencia remota y control clásico en la Pi | Matriz acordada de ensayos y repeticiones |
| Evaluación | CLI para índices de error y trazabilidad por corrida | Productividad y potencia medidas, MOBO 3D y comparación LLM/clásico |

Arquitectura objetivo: prioridades del usuario → propuesta explicada de
consignas/PID → validador → ejecución del control clásico en la Pi → registro
experimental → evaluación y MOBO → nuevas propuestas. El LLM opera en la capa
de supervisión; el PID y los paros conservan su ejecución local. Esto es una
propuesta de implementación derivada del objetivo, no una función ya terminada.

`AgentRuntime` está conectado al bucle de la Pi desde el `main.py` habitual del
programa del dispositivo; ver [arranque local](PI_LOCAL.md). Percepción y seguridad observan el hardware y
una alerta solicita el paro al hilo que posee los actuadores. Las propuestas
de actuación de los agentes permanecen deshabilitadas. Esta integración tiene
pruebas sin hardware; falta validarla físicamente en la Pi. La primera sesión
usa el motor clásico existente para obtener una referencia medible. No se debe
presentar `MockLLM` como un controlador inteligente evaluado.

## Conectar y obtener la primera corrida

Para ejecutar todo desde la Raspberry sin hotspot, seguir [PI_LOCAL.md](PI_LOCAL.md).
Los pasos siguientes corresponden a la alternativa con cámara en la laptop.

Antes de activar el hotspot, completar la [preparación sin internet](OFFLINE_SESSION.md).
Allí se explica cómo conservar la conexión actual durante la preparación y
transferir el código por USB, además de reutilizar el entorno y la calibración
existentes de la Pi.

1. En el escritorio de la Pi, dentro de `fred-device-extcv-pi4v6`, ejecutar
   `bash start_fred.sh`. Si se usará el hotspot, ejecutar primero
   `bash setup_hotspot.sh`. Usar el entorno instalado; reinstalar sólo si falta.
2. En la laptop, conectarse a `FrED_Pi` (clave `fredfiber123`), o usar una red
   compartida y la IP que muestre la Pi. Copiar la versión actual de ambos
   programas antes del ensayo: el código local aún no está desplegado.
3. Antes de abrir la conexión de la aplicación de cámara, ejecutar desde la
   raíz del proyecto:

   ```powershell
   python main.py check-connection --host 192.168.4.1
   ```

   Este comando sólo comprueba los puertos TCP 22 y 5005. No manda órdenes a
   actuadores ni certifica la calibración. El servidor de FrED atiende un cliente;
   no ejecutar el sondeo mientras la aplicación de cámara mantiene la conexión.
4. Abrir `FrEDFiberMeasurewithStreamingv6/fiber_measure.py` mediante su lanzador.
   Calibrar la cámara en **mm**, conectar a la IP de la Pi, puerto **5005**, y
   verificar detección y streaming. La aplicación también permite otras
   unidades, pero los objetivos de este proyecto están definidos en mm.
5. En `Experiment (FrED)`, introducir la configuración previamente comprobada
   para el material: consignas, PID, extrusión, fan y duraciones. Los valores
   iniciales de la interfaz no constituyen una configuración validada. Registrar
   en las notas de la sesión material/lote, operador, propósito y cambios físicos.
6. Ejecutar la corrida y recuperar los datos con `Retrieve Data`. Con las dos
   aplicaciones actualizadas se guardan CSV, Excel si está disponible y
   `*.metadata.json`, con un identificador único en los nombres.
7. Analizar el CSV recuperado:

   ```powershell
   python main.py analyze "ruta\corrida_identificador.csv" --output "ruta\corrida_identificador.metrics.json"
   ```

El siguiente ensayo físico depende de conocer la conexión de la Pi, el material
y los parámetros ya comprobados. No se incluyen consignas experimentales
inventadas ni una secuencia automática de ensayos extremos.

## Qué contienen los resultados

- Parámetros enviados, calibración enviada por la laptop, tiempos UTC de inicio,
  inicio del registro y finalización, periodo de registro, identificador de
  corrida y SHA-256 del CSV. La hora UTC es la del reloj de la Pi: verificar su
  fecha antes de la sesión. Una recuperación durante el spooling puede tener
  finalización aún vacía; el campo `recording_complete` distingue registro
  completo de una captura parcial abortada.
- Diámetro filtrado y crudo; las mediciones sin detección, sin conexión,
  antiguas, no positivas o en unidades distintas de mm quedan vacías y con
  `Diameter valid = 0`. Un heartbeat no renueva la edad de una medición.
- IAE, ISE, ITAE e ITSE por temperatura, diámetro y spooler. Se usa integración
  trapezoidal sobre los tiempos registrados, sin unir intervalos que contienen
  una muestra inválida. También se informa cobertura, MAE/RMSE ponderados por
  tiempo, frecuencia de filas e intervalo máximo entre ellas.
- El análisis de establecimiento exige tolerancia absoluta para el canal y
  `--minimum-dwell` en segundos. Ejemplo de sintaxis: añadir
  `--diameter-tolerance VALOR_EN_MM --minimum-dwell SEGUNDOS` con el criterio
  experimental acordado. El tiempo informado es la primera muestra de la
  ventana final dentro de banda; `null` significa que no se pudo demostrar el
  establecimiento con esos datos. Una muestra inválida interrumpe esa ventana.

Los índices cubren sólo **RECORDING**. El motor actual deja fuera las fases de
calentamiento y estabilización. Una corrida ya estabilizada no mide el tiempo
de establecimiento desde el encendido: para evaluarlo se necesita un ensayo
específico con el escalón y todo el transitorio registrados. Si cambia la
consigna, separar ventanas antes de calcular establecimiento. En lazo abierto,
comprobar que las columnas de referencia representan el objetivo experimental
antes de interpretar índices de seguimiento.

Los PID de temperatura y spooler del código actual actualizan a 10 Hz; exportar
50 filas/s puede repetir lecturas. Eso no demuestra adquisición independiente a
50 Hz. Un CSV antiguo no permite verificar la validez del diámetro; el informe
lo indica expresamente.

La energía, potencia y productividad permanecen como `null`: PWM y RPM
ordenadas no sustituyen mediciones. Falta acordar unidades de productividad y
conectar/calibrar la medición eléctrica. No hay frente de Pareto 3D verificable
hasta disponer de las tres magnitudes.

## Siguientes entregables

1. Línea base clásica repetible y caracterización de actuadores con registros
   completos de respuesta, criterios de evaluación y configuración validada.
2. Interfaz de propuestas LLM: consignas/PID, prioridades, explicación y
   evidencia; validación independiente antes de ejecutar.
3. Medición de productividad y potencia, sincronización y MOBO 3D; comparación
   con la línea base bajo los mismos criterios y condiciones.

Para comprobar el análisis sin dependencias de hardware:
`python -m unittest tests.test_research_workflow -v`.
