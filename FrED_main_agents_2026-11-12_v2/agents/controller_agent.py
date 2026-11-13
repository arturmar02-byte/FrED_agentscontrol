from agents.base_agent import BaseAgent

from communication.schemas import (
    Message,
    MessageType,
)

from config.settings import (
    MIN_EXTRUSION_RPM,
    MAX_EXTRUSION_RPM,
    MIN_SPOOLER_DUTY,
    MAX_SPOOLER_DUTY,
    MIN_FAN_DUTY,
    MAX_FAN_DUTY,
)


class ControllerAgent(BaseAgent):

    def __init__(
        self,
        fred=None,
        name: str = "controller_agent",
        control_enabled: bool = False,
    ):
        super().__init__(name)

        self.fred = fred

        # Hardware commands are disabled by default.
        # Safety alerts are still allowed to execute stop actions.
        self.control_enabled = control_enabled

        # Latched emergency-stop state.
        self.emergency_stop_active = False

    # ==========================================================
    # MESSAGE PROCESSING
    # ==========================================================

    def process_message(self, message: Message):

        if message.message_type == MessageType.ALERT:
            self._handle_alert(message)
            return

        if message.message_type == MessageType.COMMAND:
            self._handle_command(message)
            return

        self.logger.debug(
            f"Ignored message type: {message.message_type}"
        )

    # ==========================================================
    # SAFETY ALERTS
    # ==========================================================

    def _handle_alert(self, message: Message):

        action = message.payload.get("action")

        self.logger.warning(
            f"SAFETY ALERT received: {message.payload}"
        )

        # ------------------------------------------------------
        # EMERGENCY STOP
        # ------------------------------------------------------

        if action == "stop":

            self.emergency_stop_active = True

            self.logger.warning(
                "EMERGENCY STOP activated"
            )

            if self.fred is not None:
                request_stop = getattr(self.fred, "request_stop", None)
                if callable(request_stop):
                    request_stop(message)
                else:
                    self.fred.stop_all()

                self.logger.warning(
                    "FrED hardware STOP ALL requested"
                )

            return

        # ------------------------------------------------------
        # CLEAR EMERGENCY STATE
        # ------------------------------------------------------

        if action == "clear":

            self.emergency_stop_active = False

            self.logger.info(
                "Emergency stop cleared"
            )

            return

        self.logger.warning(
            f"Unknown safety action: {action}"
        )

    # ==========================================================
    # COMMAND HANDLING
    # ==========================================================

    def _handle_command(self, message: Message):

        command = message.payload.get("command")

        if command is None:

            self.logger.warning(
                f"Command message {message.message_id} "
                "contains no command"
            )

            return

        # ------------------------------------------------------
        # EMERGENCY STOP HAS HIGHEST PRIORITY
        # ------------------------------------------------------

        if self.emergency_stop_active:
            if self.metrics is not None:
                self.metrics.record("command", self.name, status="blocked", command=command,
                                    reason="emergency_stop", correlation_id=message.correlation_id)

            self.logger.warning(
                f"Command rejected while emergency stop "
                f"is active: {command}"
            )

            return

        # ------------------------------------------------------
        # READ-ONLY / SAFE MODE
        # ------------------------------------------------------

        if not self.control_enabled:
            if self.metrics is not None:
                self.metrics.record("command", self.name, status="blocked", command=command,
                                    reason="control_disabled", correlation_id=message.correlation_id)

            self.logger.warning(
                f"Hardware command rejected because "
                f"control mode is disabled: {command}"
            )

            return

        # ------------------------------------------------------
        # EXECUTE VALIDATED COMMAND
        # ------------------------------------------------------

        self._execute_command(
            command,
            message.payload,
        )

    # ==========================================================
    # COMMAND EXECUTION
    # ==========================================================

    def _execute_command(
        self,
        command: str,
        payload: dict,
    ):

        # ======================================================
        # STOP ALL
        # ======================================================

        if command == "stop_all":

            if self.fred is not None:
                self.fred.stop_all()

            self.logger.info(
                "Executing STOP ALL"
            )

        # ======================================================
        # STOP HEATER
        # ======================================================

        elif command == "stop_heater":

            if self.fred is not None:
                self.fred.stop_heater()

            self.logger.info(
                "Executing STOP HEATER"
            )

        # ======================================================
        # STOP EXTRUDER
        # ======================================================

        elif command == "stop_extruder":

            if self.fred is not None:
                self.fred.stop_extruder()

            self.logger.info(
                "Executing STOP EXTRUDER"
            )

        # ======================================================
        # STOP SPOOLER
        # ======================================================

        elif command == "stop_spooler":

            if self.fred is not None:
                self.fred.stop_spooler()

            self.logger.info(
                "Executing STOP SPOOLER"
            )

        # ======================================================
        # EXTRUSION RPM
        # ======================================================

        elif command == "set_extrusion_rpm":

            rpm = payload.get("rpm")

            if rpm is None:

                self.logger.warning(
                    "Missing 'rpm' value"
                )

                return

            if not isinstance(
                rpm,
                (int, float),
            ):

                self.logger.warning(
                    f"Invalid RPM type: {rpm}"
                )

                return

            if not (
                MIN_EXTRUSION_RPM
                <= rpm
                <= MAX_EXTRUSION_RPM
            ):

                self.logger.warning(
                    f"Rejected extrusion RPM: {rpm}. "
                    f"Allowed range: "
                    f"{MIN_EXTRUSION_RPM}-"
                    f"{MAX_EXTRUSION_RPM} RPM"
                )

                return

            if self.fred is not None:
                self.fred.set_extrusion_rpm(rpm)

            self.logger.info(
                f"Extrusion RPM set to {rpm}"
            )

        # ======================================================
        # SPOOLER DUTY
        # ======================================================

        elif command == "set_spooler_duty":

            duty = payload.get(
                "duty_cycle"
            )

            if duty is None:

                self.logger.warning(
                    "Missing 'duty_cycle' value"
                )

                return

            if not isinstance(
                duty,
                (int, float),
            ):

                self.logger.warning(
                    f"Invalid spooler duty type: {duty}"
                )

                return

            if not (
                MIN_SPOOLER_DUTY
                <= duty
                <= MAX_SPOOLER_DUTY
            ):

                self.logger.warning(
                    f"Rejected spooler duty: {duty}. "
                    f"Allowed range: "
                    f"{MIN_SPOOLER_DUTY}-"
                    f"{MAX_SPOOLER_DUTY}%"
                )

                return

            if self.fred is not None:
                self.fred.set_spooler_duty(duty)

            self.logger.info(
                f"Spooler duty set to {duty}%"
            )

        # ======================================================
        # FAN DUTY
        # ======================================================

        elif command == "set_fan_duty":

            duty = payload.get(
                "duty_cycle"
            )

            if duty is None:

                self.logger.warning(
                    "Missing 'duty_cycle' value"
                )

                return

            if not isinstance(
                duty,
                (int, float),
            ):

                self.logger.warning(
                    f"Invalid fan duty type: {duty}"
                )

                return

            if not (
                MIN_FAN_DUTY
                <= duty
                <= MAX_FAN_DUTY
            ):

                self.logger.warning(
                    f"Rejected fan duty: {duty}. "
                    f"Allowed range: "
                    f"{MIN_FAN_DUTY}-"
                    f"{MAX_FAN_DUTY}%"
                )

                return

            if self.fred is not None:
                self.fred.set_fan_duty(duty)

            self.logger.info(
                f"Fan duty set to {duty}%"
            )

        # ======================================================
        # UNKNOWN COMMAND
        # ======================================================

        else:

            self.logger.warning(
                f"Unknown command: {command}"
            )
