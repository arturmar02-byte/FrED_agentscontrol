from agents.base_agent import BaseAgent

from communication.schemas import (
    Message,
    MessageType,
    MessagePriority,
)

from config.settings import (
    MAX_SAFE_TEMPERATURE,
    TEMP_SAFETY_HYSTERESIS,
)


class SafetyAgent(BaseAgent):

    def __init__(
        self,
        name: str = "safety_agent",
    ):
        super().__init__(name)

        # Internal safety state.
        self._over_temperature_active = False

    def process_message(self, message: Message):

        if message.message_type != MessageType.OBSERVATION:
            return

        temperature = message.payload.get("temperature")

        if temperature is not None:
            self._check_temperature(
                temperature,
                message,
            )

    def _check_temperature(
        self,
        temperature,
        source_message: Message,
    ):

        if not isinstance(
            temperature,
            (int, float),
        ):
            self.logger.warning(
                f"Invalid temperature value: {temperature}"
            )
            return

        self.logger.info(
            f"Temperature observation: "
            f"{temperature:.2f} °C"
        )

        # ======================================================
        # ENTER OVER-TEMPERATURE STATE
        # ======================================================

        if (
            temperature >= MAX_SAFE_TEMPERATURE
            and not self._over_temperature_active
        ):

            self._over_temperature_active = True

            self.logger.critical(
                f"OVER-TEMPERATURE detected: "
                f"{temperature:.2f} °C"
            )

            alert = Message(
                sender=self.name,
                receiver="controller_agent",
                message_type=MessageType.ALERT,
                payload={
                    "event": "over_temperature",
                    "temperature": temperature,
                    "limit": MAX_SAFE_TEMPERATURE,
                    "action": "stop",
                },
                priority=MessagePriority.CRITICAL.value,
                correlation_id=source_message.message_id,
                trace_started_ns=source_message.trace_started_ns,
            )

            self.send(alert)

            return

        # ======================================================
        # RECOVER INTERNAL SAFETY STATE
        # ======================================================

        recovery_threshold = (
            MAX_SAFE_TEMPERATURE
            - TEMP_SAFETY_HYSTERESIS
        )

        if (
            self._over_temperature_active
            and temperature <= recovery_threshold
        ):

            self._over_temperature_active = False

            self.logger.info(
                f"Temperature returned below safety "
                f"recovery threshold: "
                f"{temperature:.2f} °C"
            )
