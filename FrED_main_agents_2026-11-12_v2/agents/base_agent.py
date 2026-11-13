from abc import ABC, abstractmethod
from queue import PriorityQueue, Empty
from threading import Thread, Event
from typing import Optional
import logging
import itertools
import time

from communication.schemas import Message, AgentState


class BaseAgent(ABC):

    def __init__(self, name: str):
        self.name = name
        self.inbox = PriorityQueue()
        self.metrics = None
        self._sequence = itertools.count()

        self._running = Event()
        self._stopping = Event()
        self._thread: Optional[Thread] = None

        self.message_bus = None
        self.state = AgentState.INITIALIZED

        self.logger = logging.getLogger(self.name)

    def set_message_bus(self, message_bus):
        self.message_bus = message_bus

    def send(self, message: Message):
        if self.message_bus is None:
            raise RuntimeError(
                f"Agent '{self.name}' is not connected to a MessageBus."
            )

        self.logger.debug(
            f"Sending message {message.message_id} "
            f"to '{message.receiver}'"
        )

        self.message_bus.publish(message)

    def receive(self, message: Message):
        self.logger.debug(
            f"Received message {message.message_id} "
            f"from '{message.sender}'"
        )

        self.inbox.put(
            (
                -message.priority,
                next(self._sequence),
                time.perf_counter_ns(),
                message,
            )
        )

    def start(self):
        if self._running.is_set():
            return

        self.state = AgentState.RUNNING
        self._stopping.clear()
        self._running.set()

        self.logger.info("Agent started")

        self._thread = Thread(
            target=self._run,
            daemon=True,
            name=f"{self.name}-thread",
        )

        self._thread.start()

    def stop(self):
        self._stopping.set()
        self._running.clear()

        if self._thread is not None:
            self._thread.join(timeout=2)

        self.state = (AgentState.ERROR if self._thread is not None and self._thread.is_alive()
                      else AgentState.STOPPED)
        self.logger.info("Agent stopped")

    def _run(self):
        while self._running.is_set():
            try:
                _, _, queued_ns, message = self.inbox.get(timeout=0.5)
                started_ns = time.perf_counter_ns()
                error = None

                try:
                    self.process_message(message)

                except Exception as exc:
                    error = str(exc)
                    self.state = AgentState.ERROR

                    self.logger.exception(
                        f"Error processing message "
                        f"{message.message_id}"
                    )

                finally:
                    if self.metrics is not None:
                        finished_ns = time.perf_counter_ns()
                        self.metrics.record("message", self.name, status="error" if error else "ok",
                            durations={"processing_ms": (finished_ns - started_ns) / 1e6,
                                       "queue_wait_ms": (started_ns - queued_ns) / 1e6,
                                       "trace_latency_ms": (finished_ns - message.trace_started_ns) / 1e6},
                            message_id=message.message_id, correlation_id=message.correlation_id,
                            message_type=message.message_type.value, error=error)
                    self.inbox.task_done()

            except Empty:
                continue

    @abstractmethod
    def process_message(self, message: Message):
        pass
