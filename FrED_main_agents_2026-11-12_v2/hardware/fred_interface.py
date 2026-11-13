class FrEDInterface:
    """
    Hardware abstraction layer between the agent system and FrED.

    The interface does not create the hardware controllers.
    Existing FrED objects are injected into it.
    """

    def __init__(
        self,
        extruder=None,
        spooler=None,
        fan=None,
        diameter=None,
        database=None,
        gui=None,
    ):
        self.extruder = extruder
        self.spooler = spooler
        self.fan = fan
        self.diameter = diameter
        self.database = database
        self.gui = gui

    # ==========================================================
    # SENSOR READS
    # ==========================================================

    def get_temperature(self):

        if self.database is None:
            return None

        readings = getattr(
            self.database,
            "temperature_readings",
            None,
        )

        if not readings:
            return None

        return readings[-1]

    def get_diameter(self):

        if self.diameter is None:
            return None

        diameter, found, age = self.diameter.get_latest()

        if not found:
            return None

        return diameter

    def get_diameter_status(self):

        if self.diameter is None:
            return {
                "diameter": None,
                "found": False,
                "age": None,
                "streaming": False,
            }

        value, found, age = self.diameter.get_latest()

        return {
            "diameter": value,
            "found": found,
            "age": age,
            "streaming": self.diameter.is_streaming(),
        }

    def get_spooler_rpm(self):

        if self.database is None:
            return None

        readings = getattr(
            self.database,
            "spooler_rpm",
            None,
        )

        if not readings:
            return None

        return readings[-1]

    # ==========================================================
    # EXTRUDER
    # ==========================================================

    def set_extrusion_rpm(self, rpm: float):

        if self.extruder is None:
            raise RuntimeError(
                "Extruder is not connected to FrEDInterface."
            )

        if rpm <= 0:
            self.extruder.stop_stepper()
            return

        self.extruder.set_motor_speed(rpm)

    def stop_extruder(self):

        if self.extruder is not None:
            self.extruder.stop_stepper()

    # ==========================================================
    # HEATER
    # ==========================================================

    def stop_heater(self):

        if self.extruder is not None:
            self.extruder.stop_heater()

    # ==========================================================
    # SPOOLER
    # ==========================================================

    def set_spooler_duty(self, duty_cycle: float):

        if self.spooler is None:
            raise RuntimeError(
                "Spooler is not connected to FrEDInterface."
            )

        duty_cycle = max(
            0.0,
            min(100.0, duty_cycle),
        )

        self.spooler.update_duty_cycle(
            duty_cycle
        )

    def stop_spooler(self):

        if self.spooler is not None:
            self.spooler.stop_motor()

    # ==========================================================
    # FAN
    # ==========================================================

    def set_fan_duty(self, duty_cycle: float):

        if self.fan is None:
            raise RuntimeError(
                "Fan is not connected to FrEDInterface."
            )

        duty_cycle = max(
            0.0,
            min(100.0, duty_cycle),
        )

        self.fan.update_duty_cycle(
            duty_cycle
        )

    def stop_fan(self):

        if self.fan is not None:
            self.fan.update_duty_cycle(0)

    # ==========================================================
    # GLOBAL SAFETY
    # ==========================================================

    def stop_all(self):
        """
        Put FrED into a safe stopped state.

        First disable the original FrED control flags so that
        the hardware loop cannot immediately re-enable outputs.
        Then directly drive every actuator to zero.
        """

        # ------------------------------------------------------
        # Disable original FrED control loops
        # ------------------------------------------------------

        if self.gui is not None:

            self.gui.device_started = False
            self.gui.heater_open_loop_enabled = False

            self.gui.dc_motor_open_loop_enabled = False
            self.gui.dc_motor_close_loop_enabled = False

            self.gui.fan_enabled = False

            # Also request the original hardware loop to stop
            # each subsystem.
            self.gui.heater_stop_requested = True
            self.gui.stepper_stop_requested = True
            self.gui.dc_motor_stop_requested = True

            # Abort a remote experiment if one owns the hardware.
            experiment = getattr(
                self.gui,
                "experiment",
                None,
            )

            if experiment is not None:
                try:
                    if experiment.is_active():
                        experiment.abort()
                except Exception:
                    pass

        # ------------------------------------------------------
        # Direct actuator stop
        # ------------------------------------------------------

        self.stop_heater()
        self.stop_extruder()
        self.stop_spooler()
        self.stop_fan()