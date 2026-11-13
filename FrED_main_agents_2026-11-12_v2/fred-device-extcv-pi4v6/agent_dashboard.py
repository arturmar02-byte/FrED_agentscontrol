"""Independent Qt performance display; reads snapshots, never writes actuators."""
from collections import deque
import json

from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtGui import QDesktopServices, QFont
from PyQt5.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QLineEdit, QPushButton, QPlainTextEdit, QTableWidget,
                             QTableWidgetItem, QHeaderView)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


def number(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


class AgentDashboard(QWidget):
    def __init__(self, runtime_provider, parent=None):
        super().__init__(parent, Qt.Window)
        self.runtime_provider = runtime_provider
        self.setFont(QFont("DejaVu Sans", 10))
        self.setWindowTitle("FrED · Rendimiento de agentes y LLM")
        self.resize(1180, 900)
        self._last_result_id = None
        self._output_dir = None
        self._history = deque(maxlen=120)
        root = QVBoxLayout(self)
        title = QLabel("Agentes y modelo · rendimiento en vivo")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #17465d; padding: 6px 0;")
        root.addWidget(title)
        self.session = QLabel("Esperando inicialización del hardware y los agentes…")
        self.session.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.session)
        self.model = QLabel("Modelo: pendiente")
        self.model.setWordWrap(True)
        self.model.setStyleSheet("background: #fff2d7; color: #714500; padding: 10px; font-weight: bold;")
        root.addWidget(self.model)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(("Agente / estado", "Cola", "Eventos", "Errores",
            "Eventos/s", "Proc. media ms", "Proc. p95 ms", "Espera p95 ms", "Traza p95 ms"))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setMaximumHeight(190)
        root.addWidget(self.table)
        self.llm = QLabel("Sin solicitudes al modelo.")
        self.llm.setWordWrap(True)
        self.llm.setStyleSheet("font-size: 14px; padding: 7px; background: #edf5f8;")
        root.addWidget(self.llm)

        figure = Figure(figsize=(9, 2.0), tight_layout=True)
        self.axes = figure.add_subplot(111)
        self.axes.set_ylabel("Latencia p95 (ms)")
        self.axes.set_xlabel("Tiempo de sesión (s)")
        self.model_line, = self.axes.plot([], [], color="#207b9b", label="Llamada al modelo")
        self.safety_line, = self.axes.plot([], [], color="#c36b2b", label="Procesamiento seguridad")
        self.axes.legend(loc="upper left")
        self.canvas = FigureCanvas(figure)
        root.addWidget(self.canvas, 1)

        box = QGroupBox("Medir una propuesta del modelo · sin aplicar al hardware")
        form = QVBoxLayout(box)
        row = QHBoxLayout()
        self.prompt = QLineEdit()
        self.prompt.setMaxLength(4096)
        self.prompt.setPlaceholderText("MockLLM reconoce inglés: set fan to 30 percent")
        self.submit = QPushButton("Medir propuesta")
        self.submit.clicked.connect(self._request)
        self.prompt.returnPressed.connect(self._request)
        row.addWidget(self.prompt, 1)
        row.addWidget(self.submit)
        form.addLayout(row)
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setMaximumHeight(145)
        self.result.setPlaceholderText("Aquí aparecerán la propuesta, el estado y las métricas de la solicitud.")
        form.addWidget(self.result)
        root.addWidget(box)
        self.resources = QLabel()
        root.addWidget(self.resources)
        self.recording = QLabel()
        self.recording.setWordWrap(True)
        self.recording.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bottom = QHBoxLayout()
        bottom.addWidget(self.recording, 1)
        self.open_logs = QPushButton("Abrir registros")
        self.open_logs.clicked.connect(self._open_logs)
        bottom.addWidget(self.open_logs)
        root.addLayout(bottom)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def _request(self):
        runtime = self.runtime_provider()
        if runtime is None:
            return
        try:
            request_id = runtime.request_reasoning(self.prompt.text(), preview=True)
            self.result.setPlainText(f"Solicitud {request_id}\nEn cola; la propuesta no se aplicará al hardware.")
        except ValueError as exc:
            self.result.setPlainText(str(exc))

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def _open_logs(self):
        if self._output_dir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._output_dir))

    def refresh(self):
        if not self.isVisible():
            return
        runtime = self.runtime_provider()
        self.submit.setEnabled(runtime is not None and runtime.reasoning_agent is not None
                               and runtime.reasoning_agent._running.is_set())
        if runtime is None:
            self.open_logs.setEnabled(False)
            return
        snapshot = runtime.snapshot()
        self.session.setText(f"Sesión {snapshot['session_id']} · {snapshot['elapsed_s']:.0f} s · "
                             f"Paro enclavado: {'SÍ' if snapshot['emergency_stop'] else 'no'}")
        model = snapshot["model"]
        label = (f"{model['name']} · {model['provider']} · "
                 f"{'SIMULADOR: estas latencias no representan un LLM real' if model['simulated'] else 'Modelo configurado'}"
                 if model else "Razonamiento deshabilitado")
        self.model.setText(label + "\nLas solicitudes de esta ventana sólo generan propuestas.")
        groups = snapshot["groups"]
        agents = snapshot["agents"]
        self.table.setRowCount(len(agents))
        for row, agent in enumerate(agents):
            kind = "sample" if agent["name"] == "perception_agent" else "message"
            stats = groups.get(agent["name"], {}).get(kind, {})
            timings = stats.get("timings", {})
            processing = timings.get("processing_ms", {})
            values = (f"{agent['name']} / {agent['state']}", agent["pending"],
                      stats.get("count", 0), stats.get("errors", 0),
                      number(stats.get("rate_hz_session")), number(processing.get("mean_ms")),
                      number(processing.get("p95_ms")),
                      number(timings.get("queue_wait_ms", {}).get("p95_ms")),
                      number(timings.get("trace_latency_ms", {}).get("p95_ms")))
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        llm_stats = groups.get("reasoning_agent", {}).get("llm_call", {})
        inference = llm_stats.get("timings", {}).get("inference_ms", {})
        total = llm_stats.get("timings", {}).get("request_latency_ms", {})
        self.llm.setText(
            f"Modelo: {llm_stats.get('count', 0)} llamadas completadas · {llm_stats.get('errors', 0)} errores · "
            f"{llm_stats.get('rejected', 0)} respuestas rechazadas\n"
            f"Inferencia ms: última {number(inference.get('last_ms'))} · media {number(inference.get('mean_ms'))} · "
            f"p50 {number(inference.get('p50_ms'))} · p95 {number(inference.get('p95_ms'))} · "
            f"Solicitud total p95 {number(total.get('p95_ms'))} ms\n"
            f"p50/p95: últimas {snapshot['percentile_window']} muestras por métrica; media y eventos/s: sesión completa.")
        safety = groups.get("safety_agent", {}).get("message", {}).get("timings", {}).get("processing_ms", {})
        self._history.append((snapshot["elapsed_s"], inference.get("p95_ms"), safety.get("p95_ms")))
        for line, index in ((self.model_line, 1), (self.safety_line, 2)):
            points = [(entry[0], entry[index]) for entry in self._history if entry[index] is not None]
            line.set_data([p[0] for p in points], [p[1] for p in points])
        self.axes.relim()
        self.axes.autoscale_view()
        self.canvas.draw_idle()
        latest = snapshot.get("last_llm_call")
        if latest and latest["message_id"] != self._last_result_id:
            self._last_result_id = latest["message_id"]
            self.result.setPlainText(json.dumps({
                "request_id": latest["message_id"], "estado": latest["status"],
                "propuesta": latest["response"], "error": latest["error"],
                "latencias_ms": latest["durations_ms"], "uso_reportado": latest["usage"],
                "TTFT_ms": latest["time_to_first_token_ms"], "costo_USD": latest["cost_usd"]},
                indent=2, ensure_ascii=False))
        cpu = snapshot["resources"]["cpu_percent"]
        rss = snapshot["resources"]["rss_mib"]
        self.resources.setText(f"Proceso de control y agentes: CPU {number(cpu, 1)} % · RSS {number(rss, 1)} MiB · "
                               "La cámara corre en otro proceso. Tokens, TTFT y costo: sólo si están instrumentados.")
        self._output_dir = snapshot["output_dir"]
        self.open_logs.setEnabled(bool(self._output_dir))
        self.recording.setText(
            f"Registros: {self._output_dir or 'sólo memoria'}\n"
            f"Pendientes de escritura: {snapshot['writer_queue']} · eventos perdidos: {snapshot['dropped_events']}"
            + (f" · ERROR: {snapshot['io_error']}" if snapshot["io_error"] else ""))
