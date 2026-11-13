# FrED completo en la Raspberry Pi

Esta es la ruta para trabajar sin laptop ni hotspot. Conectar la cámara USB
a la Pi y ejecutar desde su escritorio gráfico, con monitor/teclado o una
sesión de escritorio remoto. No hace falta cambiar la red WiFi.

El `main.py` habitual inicia los agentes, el control, el display de rendimiento
y el proceso de cámara/calibración/experimentos. No se necesita otro lanzador.
Intercambian diámetro, órdenes y resultados mediante TCP en `127.0.0.1`,
puerto 5005 por defecto. El tráfico no sale de la Pi. La cámara trabaja en
otro proceso para que la captura no bloquee directamente el hilo de control;
el rendimiento conjunto debe medirse en la máquina real.

## Preparar y transferir

Desde esta laptop, para crear un ZIP de código sin paquetes de Windows:

```powershell
python tools/prepare_offline.py --pi-local --output artifacts/FrED_pi_local
```

Copiar el ZIP por USB o por la red disponible y extraerlo en una carpeta nueva
de la Pi. Conservar la instalación anterior. El paquete incluye los agentes,
ambas aplicaciones, el lanzador, pruebas y guías. Sus dependencias ARM se
instalan en la Pi, con internet, antes de la primera sesión.

Desde la raíz extraída:

```bash
python3 tools/verify_bundle.py .
bash fred-device-extcv-pi4v6/setup_install.sh
```

El instalador crea `fred-device-extcv-pi4v6/fred-venv` con acceso a paquetes del
sistema. Instala OpenCV, NumPy, matplotlib, Tk, Pillow, openpyxl y PyQt5 desde
`apt`, y las dependencias del hardware desde `pip`. Así OpenCV y NumPy usan
las compilaciones compatibles de la distribución. No instalar los wheels de
Windows en la Pi.

Copiar la calibración real del motor desde la instalación que funciona:

```bash
cp /RUTA/INSTALACION_ACTUAL/calibration.yaml fred-device-extcv-pi4v6/calibration.yaml
```

Sustituir esa ruta por la real. `calibration.example.yaml` es una referencia,
no la calibración validada de la máquina. El ZIP tampoco activa automáticamente
la calibración de cámara de la laptop: sólo incluye `calibration.example.json`.

Si se reutiliza un entorno existente, debe incluir también las dependencias de
cámara y exportación. Ejecutar el diagnóstico con ese mismo intérprete. Si
faltan imports, actualizar mediante el instalador con internet. Los entornos
creados sin `--system-site-packages` no ven las bibliotecas instaladas por apt;
en ese caso usar el entorno nuevo que crea el instalador. Si un NumPy u OpenCV
instalado previamente con pip oculta las versiones de apt y falla la importación,
usar también el entorno nuevo, sin modificar el entorno anterior.

## Arranque local

Desde la raíz del proyecto en el escritorio de la Pi:

```bash
fred-device-extcv-pi4v6/fred-venv/bin/python tools/preflight.py pi-local
cd fred-device-extcv-pi4v6
bash start_fred.sh
```

También se puede ejecutar `python main.py` dentro de esa carpeta con el
entorno correcto activado. Para reutilizar otro entorno ya comprobado:

```bash
cd fred-device-extcv-pi4v6
/RUTA/INSTALACION_ACTUAL/fred-venv/bin/python main.py
```

Se abren tres ventanas:

1. **MIT FrED - Raspberry local**: gráficas, controles clásicos y estado de los
   agentes. El calentador y los motores esperan las órdenes del operador.
2. **FrED - Local camera and experiments**: vista de cámara, detección,
   calibración y pestaña **Experiment (FrED)**. Se conecta automáticamente al
   programa local; no hay que introducir la IP de la Pi ni activar el hotspot.
3. **FrED · Rendimiento de agentes y LLM**: estado, colas, latencias y errores.
   Se puede cerrar de forma independiente y volver a abrir con **Rendimiento
   de agentes y LLM** en los controles de FrED. Ver [las métricas y sus
   definiciones](AGENT_PERFORMANCE.md).

La captura usa V4L2 en Linux. Está preparada para la cámara USB que ya usa
OpenCV; una cámara CSI que requiera Picamera2 necesita otro adaptador de captura.
Si la cámara no es el índice 0:

```bash
bash start_fred.sh --camera 1 --fps 15
```

También se admiten `--width`, `--height`, `--calibration RUTA.json` y
`--data-dir RUTA`. Sin dimensiones explícitas se conserva la resolución que
negocie la cámara. La frecuencia de procesamiento está limitada por defecto a
20 Hz; la alcanzada depende de la captura, el tamaño de imagen y la carga de
la Pi. Mantener el tamaño de captura y recalibrar si cambia la resolución,
el lente, el enfoque, la distancia o el montaje. Comprobar la escala con una
referencia física y guardar la calibración en **mm** antes del ensayo.

## Corrida y resultados

Introducir en **Experiment (FrED)** las consignas, PID y duraciones ya probados
para el material y la máquina. Los valores iniciales de la interfaz no son
una receta experimental validada. Ejecutar la secuencia y usar **Retrieve Data**
antes de cerrar las ventanas para guardar CSV, Excel y metadatos. La carpeta
predeterminada es `Data` en la raíz del proyecto. Las capturas aún no recuperadas
se conservan sólo en memoria y se pierden al cerrar el control.

El análisis se ejecuta en la misma Pi:

```bash
fred-device-extcv-pi4v6/fred-venv/bin/python main.py analyze Data/MI_CORRIDA.csv --output Data/MI_CORRIDA.metrics.json
```

Cerrar la ventana principal de FrED o la cámara, o pulsar Ctrl+C en su terminal,
solicita el cierre del conjunto. El control detiene calentador, stepper, spooler
y fan, detiene los agentes, termina sus registros y libera GPIO. Después
finaliza la cámara. Cerrar únicamente el display de rendimiento lo oculta y
conserva el registro de métricas en segundo plano. No abrir en paralelo una
instalación anterior de FrED: ambas intentarían controlar los mismos pines.
El `main.py` nuevo impide abrir dos instancias suyas; no puede detectar todos
los programas externos de GPIO.

La ruta externa anterior se conserva con `bash start_fred.sh --external-camera`.
`start_pi_local.sh` queda como alias compatible; no es necesario usarlo.

## Agentes y alcance actual

Los cuatro agentes se inician después de inicializar el hardware:

- Percepción consulta temperatura, RPM y diámetro válido. No presenta una
  lectura de diámetro antigua o sin calibración en mm como válida.
- Seguridad evalúa la temperatura con el límite configurado en
  `config/settings.py`. Ese límite debe revisarse para el material y la máquina.
- Control recibe las alertas y solicita un paro enclavado. La escritura a GPIO
  se realiza en el hilo de hardware. Un paro del agente aborta el experimento,
  bloquea nuevos experimentos y los controles de arranque. Resolver su causa
  antes de reiniciar FrED; enfriar el sensor no reanuda automáticamente la máquina.
- Razonamiento utiliza **MockLLM**, un simulador determinista. Su hilo se inicia,
  pero todavía no hay un LLM real ni generación autónoma de consignas/PID. Las
  propuestas de actuación de los agentes permanecen deshabilitadas. Las órdenes
  del operador y los experimentos usan los controladores clásicos existentes.
  El display permite enviar instrucciones de prueba y medirlas; sus propuestas
  se muestran y registran sin enviar órdenes de actuación.

Tras instalar las dependencias, esta ruta no necesita internet. Integrar un LLM
por API requeriría conectividad; ejecutar un modelo real local es otro trabajo.
Las limitaciones de adquisición, productividad y potencia están documentadas
en [RESEARCH_ALIGNMENT.md](RESEARCH_ALIGNMENT.md).

## Verificación pendiente en la Pi

Las pruebas sin hardware cubren transporte local, agentes y paro, fallo de
inicialización, cierre, exportación y empaquetado. Antes de una corrida física
hay que comprobar en la Pi la captura y calibración, la lectura de sensores,
los botones STOP y el cierre de ambas ventanas, y medir la frecuencia real de
captura/control/registro. No se han validado aquí GPIO, SPI ni el rendimiento
de OpenCV en la Raspberry.
