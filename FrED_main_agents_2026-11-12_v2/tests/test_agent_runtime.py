import time
import logging

from agent_runtime import AgentRuntime

from communication.schemas import (
    Message,
    MessageType,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


class MockFrEDInterface:

    def __init__(self):
        # Sensor state
        self.temperature = 120.0
        self.diameter = 0.35
        self.spooler_rpm = 0.0

        # Actuator state
        self.fan_duty = 0.0
        self.extrusion_rpm = 0.0
        self.spooler_duty = 0.0

        # Safety state
        self.stop_all_called = False
        self.stop_all_count = 0

    # ==========================================================
    # SENSOR READS
    # ==========================================================

    def get_temperature(self):
        return self.temperature

    def get_diameter(self):
        return self.diameter

    def get_spooler_rpm(self):
        return self.spooler_rpm

    def get_diameter_status(self):
        return {
            "diameter": self.diameter,
            "found": True,
            "age": 0.05,
            "streaming": True,
        }

    # ==========================================================
    # ACTUATOR COMMANDS
    # ==========================================================

    def set_fan_duty(self, duty):
        self.fan_duty = duty

    def set_extrusion_rpm(self, rpm):
        self.extrusion_rpm = rpm

    def set_spooler_duty(self, duty):
        self.spooler_duty = duty

    # ==========================================================
    # STOP COMMANDS
    # ==========================================================

    def stop_heater(self):
        pass

    def stop_extruder(self):
        self.extrusion_rpm = 0.0

    def stop_spooler(self):
        self.spooler_duty = 0.0

    def stop_fan(self):
        self.fan_duty = 0.0

    def stop_all(self):

        self.stop_all_called = True
        self.stop_all_count += 1

        self.extrusion_rpm = 0.0
        self.spooler_duty = 0.0
        self.fan_duty = 0.0


# ==============================================================
# CREATE MOCK HARDWARE
# ==============================================================

fred = MockFrEDInterface()


# ==============================================================
# CREATE COMPLETE AGENT RUNTIME
#
# IMPORTANT:
# Hardware control and reasoning remain disabled.
# ==============================================================

runtime = AgentRuntime(
    fred=fred,
    enable_control=False,
    enable_reasoning=False,
)


runtime.start()


# ==============================================================
# TEST 1
# SAFE SENSOR STATE
# ==============================================================

time.sleep(0.5)

print(
    "\nSTOP during safe state:",
    fred.stop_all_called,
)

assert fred.stop_all_called is False


# ==============================================================
# TEST 2
# NORMAL HARDWARE COMMAND MUST BE BLOCKED
# ==============================================================

fan_command = Message(
    sender="test_client",
    receiver="controller_agent",
    message_type=MessageType.COMMAND,
    payload={
        "command": "set_fan_duty",
        "duty_cycle": 60,
    },
)

runtime.bus.publish(
    fan_command
)

time.sleep(0.3)


print(
    "Fan duty after blocked command:",
    fred.fan_duty,
)

assert fred.fan_duty == 0.0


# ==============================================================
# TEST 3
# SIMULATE REAL SENSOR OVER-TEMPERATURE
#
# Nobody sends an ALERT manually.
# PerceptionAgent must detect the new sensor value.
# SafetyAgent must generate the alert.
# ControllerAgent must execute STOP ALL.
# ==============================================================

print(
    "\nSimulating hardware over-temperature..."
)

fred.temperature = 230.0


time.sleep(0.5)


print(
    "STOP after overheating:",
    fred.stop_all_called,
)

print(
    "STOP ALL count:",
    fred.stop_all_count,
)

print(
    "Emergency stop active:",
    runtime.controller_agent.emergency_stop_active,
)


assert fred.stop_all_called is True

assert runtime.controller_agent.emergency_stop_active is True

# SafetyAgent state latch must prevent repeated STOP ALL calls.
assert fred.stop_all_count == 1


# ==============================================================
# TEST 4
# COMMAND AFTER E-STOP MUST BE REJECTED
# ==============================================================

fan_after_estop = Message(
    sender="test_client",
    receiver="controller_agent",
    message_type=MessageType.COMMAND,
    payload={
        "command": "set_fan_duty",
        "duty_cycle": 80,
    },
)

runtime.bus.publish(
    fan_after_estop
)

time.sleep(0.3)


print(
    "Fan duty after E-STOP command:",
    fred.fan_duty,
)

assert fred.fan_duty == 0.0


# ==============================================================
# SHUTDOWN
# ==============================================================

runtime.stop()


print(
    "\nAgent runtime integration test PASSED"
)