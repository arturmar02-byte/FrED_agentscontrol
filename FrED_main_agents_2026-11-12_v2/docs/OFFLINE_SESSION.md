# Sesión FrED sin internet

Para la nueva ruta con cámara y agentes en la Raspberry, sin laptop ni hotspot,
seguir [PI_LOCAL.md](PI_LOCAL.md). Esta guía conserva la alternativa de cámara
externa con la laptop.

El cambio a `FrED_Pi` se hace al final de la preparación. La laptop permanece
en `Tec` mientras se descarga, prueba y copia todo. El control clásico, la
cámara, la exportación y el análisis funcionan localmente; no requieren un LLM
ni servicios externos para esta primera sesión.

## Preparación con internet

### Laptop

Desde la raíz del proyecto:

```powershell
python tools/preflight.py laptop
python -m unittest tests.test_research_workflow -v
python tools/prepare_offline.py
```

El último comando genera una carpeta y un ZIP en `artifacts`. Incluye código,
guías, herramientas de diagnóstico, calibración de cámara almacenada y los
wheels de las versiones instaladas de OpenCV, NumPy, Pillow, openpyxl y sus
dependencias para **esta versión de Python en Windows**. No incluye Python;
usa el intérprete de esta laptop, cuya ruta queda guardada en el instalador.

En la carpeta generada, ejecutar `INSTALL_LAPTOP_OFFLINE.bat`. Crea un entorno
aislado `laptop-venv` e instala únicamente desde `wheelhouse-laptop` mediante
`--no-index`. Así comprobamos la instalación offline antes de cambiar la red.
Después usar `RUN_LAPTOP.bat` para abrir la aplicación con ese mismo entorno.
La carpeta es ejecutable; el ZIP se usa para transferir el código a la Pi.

`python tools/verify_bundle.py RUTA_DE_LA_CARPETA_GENERADA` compara los archivos
con el manifiesto SHA-256. Hacerlo antes de introducir modificaciones de sesión.

### Raspberry Pi

**La instalación de dependencias de la Pi debe quedar comprobada antes de
activar el hotspot.** Los wheels de Windows no sirven para la Raspberry. El
paquete no contiene los paquetes `apt` ni los wheels ARM necesarios para una
instalación desde cero.

Si FrED ya funcionaba, reutilizar su `fred-venv` y su `calibration.yaml`.
Si falta ese entorno, ejecutar `bash setup_install.sh` desde la aplicación
existente mientras **la Pi todavía tiene internet**, antes de activar el hotspot.
También puede disponer de internet por Ethernet. Si no conocemos el sistema y
la arquitectura de la Pi, no podemos garantizar una instalación nueva offline.

Para transferir el paquete sin cambiar todavía el WiFi de la laptop, copiar
el ZIP a una memoria USB y llevarla a la Pi, o transferirlo por una conexión
ya disponible en una red compartida. Extraer en **una carpeta nueva**, sin
reemplazar la instalación que ya funciona. Puede hacerse con el explorador de
archivos del escritorio de la Pi.

Dentro de la carpeta nueva extraída, copiar la calibración real de la Pi:

```bash
cp /RUTA/INSTALACION_ACTUAL/calibration.yaml fred-device-extcv-pi4v6/calibration.yaml
```

`/RUTA/INSTALACION_ACTUAL` debe sustituirse por la carpeta real donde funciona
FrED. El paquete incluye `calibration.example.yaml` únicamente como referencia;
no elige automáticamente esa calibración para la máquina.

Comprobar dependencias y configuración con el Python del entorno que funciona:

```bash
/RUTA/INSTALACION_ACTUAL/fred-venv/bin/python tools/preflight.py pi
```

Este diagnóstico no inicia la interfaz, la cámara ni los actuadores. Comprueba
imports, plataforma ARM/Linux, presencia de `nmcli`, archivo de calibración y
dispositivos SPI. No sustituye la comprobación física de sensores ni valida PID.
Si informa un faltante, resolverlo con internet antes de continuar. Verificar
también la fecha/hora que muestra el escritorio de la Pi.

## Datos que debemos fijar antes del ensayo

La primera sesión será una **línea base del control clásico actual**. Aún deben
anotarse material/lote, temperatura, extrusión, spooler, PID, fan y duraciones
que se hayan probado en esa máquina. También el propósito del ensayo y las
condiciones de calibración. Las consignas iniciales de la interfaz no son una
configuración experimental aprobada.

La calibración de cámara incluida es una copia de la que existe en esta laptop.
Comprobarla físicamente si cambió el lente, enfoque, distancia o montaje.

## Cambio de red y ejecución local

Sólo después de completar la preparación:

1. En la Pi, desde la carpeta del código nuevo, activar el hotspot:

   ```bash
   cd fred-device-extcv-pi4v6
   bash setup_hotspot.sh
   cd ..
   ```

2. En el escritorio de la Pi, iniciar el programa nuevo con el entorno existente:

   ```bash
   bash tools/run_pi_offline.sh /RUTA/INSTALACION_ACTUAL/fred-venv
   ```

3. En la laptop, conectarse a `FrED_Pi`, clave `fredfiber123`. La IP esperada
   de la Pi es `192.168.4.1`, puerto `5005`; comprobar la IP en su pantalla.
4. Antes de conectar la aplicación de cámara, comprobar el enlace desde la
   carpeta generada:

   ```powershell
   laptop-venv\Scripts\python.exe main.py check-connection --host 192.168.4.1
   ```

   Es un sondeo TCP, no una orden de arranque. No ejecutarlo durante el
   streaming: el servidor de FrED atiende un cliente.
5. Abrir `RUN_LAPTOP.bat`, revisar calibración en mm, conectar el streaming y
   verificar la detección del filamento. Introducir los parámetros acordados
   en `Experiment (FrED)` y ejecutar la corrida.
6. Al terminar, pulsar `Retrieve Data`: se guardan CSV, Excel y metadatos con
   identificador de corrida. Si el experimento se aborta durante el registro,
   recuperar también la captura parcial, identificada como incompleta.
7. Evaluar el CSV localmente:

   ```powershell
   laptop-venv\Scripts\python.exe main.py analyze "RUTA\corrida.csv" --output "RUTA\corrida.metrics.json"
   ```

Sin una medición eléctrica y una definición de productividad, esos objetivos
quedan pendientes. Los índices calculados cubren sólo la ventana de registro;
ver [alineación de investigación](RESEARCH_ALIGNMENT.md) para sus límites.

## Recuperación sin internet

| Situación | Acción local |
|---|---|
| No aparece `FrED_Pi` | En la Pi, ejecutar `bash setup_hotspot.sh status` y revisar el resultado. |
| Puerto 5005 inaccesible | Confirmar que el programa de la Pi está abierto y leer su IP en pantalla. |
| Sin diámetro válido | Verificar conexión, streaming, detección y calibración en mm. |
| Error de paquetes en laptop | Ejecutar de nuevo `INSTALL_LAPTOP_OFFLINE.bat`; usa la caché local. |
| Error de paquetes en Pi | Detener la preparación offline y restaurar internet en la Pi para instalar lo faltante. |
| Necesidad de detener una corrida | Usar `Abort` en la laptop o los botones STOP de la Pi. |
| Necesidad de volver a internet | En la Pi, `bash setup_hotspot.sh down`; en la laptop, reconectarse a `Tec`. |

Al finalizar, conservar CSV, metadatos y reportes; no actualizar el paquete ni
reinstalar dependencias durante una corrida.
