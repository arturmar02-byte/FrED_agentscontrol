import time

from agents.base_agent import BaseAgent

from communication.schemas import (
    Message,
    MessageType,
    MessagePriority,
)

from config.settings import PERCEPTION_INTERVAL


class PerceptionAgent(BaseAgent):

    def __init__(
        self,
        fred,
        name: str = "perception_agent",
    ):
        super().__init__(name)

        self.fred = fred

    def _run(self):
        """
        Periodically read the current FrED state and publish
        observations to the safety layer.
        """

        while self._running.is_set():
            started_ns = time.perf_counter_ns()
            error = None
            try:
                observation = self._read_fred_state()

                message = Message(
                    sender=self.name,
                    receiver="safety_agent",
                    message_type=MessageType.OBSERVATION,
                    payload=observation,
                    priority=MessagePriority.HIGH.value,
                )

                self.send(message)

            except Exception as exc:
                error = str(exc)
                self.logger.exception(
                    "Error while reading FrED state"
                )

            if self.metrics is not None:
                self.metrics.record("sample", self.name, status="error" if error else "ok",
                                    durations={"processing_ms": (time.perf_counter_ns() - started_ns) / 1e6},
                                    error=error)
            # Reading is a separate operation from queue processing; report it as such.
            time.sleep(PERCEPTION_INTERVAL)

    def _read_fred_state(self) -> dict:

        temperature = self.fred.get_temperature()
        diameter = self.fred.get_diameter()
        spooler_rpm = self.fred.get_spooler_rpm()

        diameter_status = (
            self.fred.get_diameter_status()
        )

        observation = {
            "temperature": temperature,
            "diameter": diameter,
            "spooler_rpm": spooler_rpm,
            "diameter_streaming": diameter_status.get(
                "streaming",
                False,
            ),
            "diameter_age": diameter_status.get(
                "age"
            ),
        }

        self.logger.debug(
            f"FrED observation: {observation}"
        )

        return observation

    def process_message(self, message: Message):
        """
        PerceptionAgent currently works autonomously and does
        not require incoming messages.
        """
        pass
