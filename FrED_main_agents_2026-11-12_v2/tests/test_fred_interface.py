from hardware.fred_interface import FrEDInterface


class MockExtruder:

    def __init__(self):
        self.stepper_rpm = 0.0
        self.heater_stopped = False
        self.stepper_stopped = False

    def set_motor_speed(self, rpm: float):
        self.stepper_rpm = rpm

    def stop_stepper(self):
        self.stepper_rpm = 0.0
        self.stepper_stopped = True

    def stop_heater(self):
        self.heater_stopped = True


class MockSpooler:

    def __init__(self):
        self.duty_cycle = 0.0
        self.stopped = False

    def update_duty_cycle(self, duty_cycle: float):
        self.duty_cycle = duty_cycle

    def stop_motor(self):
        self.duty_cycle = 0.0
        self.stopped = True


class MockFan:

    def __init__(self):
        self.duty_cycle = 0.0

    def update_duty_cycle(self, duty_cycle: float):
        self.duty_cycle = duty_cycle


class MockDiameter:

    def __init__(self):
        self.value = 0.35
        self.found = True
        self.age = 0.1
        self.streaming = True

    def get_latest(self):
        return (
            self.value,
            self.found,
            self.age,
        )

    def is_streaming(self):
        return self.streaming


class MockDatabase:
    temperature_readings = [180.0]
    spooler_rpm = [32.5]


extruder = MockExtruder()
spooler = MockSpooler()
fan = MockFan()
diameter = MockDiameter()

fred = FrEDInterface(
    extruder=extruder,
    spooler=spooler,
    fan=fan,
    diameter=diameter,
    database=MockDatabase,
)


print("\n--- SENSOR TEST ---")

print(
    "Temperature:",
    fred.get_temperature(),
)

print(
    "Diameter:",
    fred.get_diameter(),
)

print(
    "Spooler RPM:",
    fred.get_spooler_rpm(),
)

print(
    "Diameter status:",
    fred.get_diameter_status(),
)


print("\n--- ACTUATOR TEST ---")

fred.set_extrusion_rpm(0.6)

print(
    "Extrusion RPM:",
    extruder.stepper_rpm,
)

fred.set_spooler_duty(40)

print(
    "Spooler duty:",
    spooler.duty_cycle,
)

fred.set_fan_duty(60)

print(
    "Fan duty:",
    fan.duty_cycle,
)


print("\n--- SAFETY STOP TEST ---")

fred.stop_all()

print(
    "Heater stopped:",
    extruder.heater_stopped,
)

print(
    "Stepper stopped:",
    extruder.stepper_stopped,
)

print(
    "Spooler stopped:",
    spooler.stopped,
)

print(
    "Fan duty:",
    fan.duty_cycle,
)


assert fred.get_temperature() == 180.0
assert fred.get_diameter() == 0.35
assert fred.get_spooler_rpm() == 32.5

assert extruder.heater_stopped is True
assert extruder.stepper_stopped is True
assert spooler.stopped is True
assert fan.duty_cycle == 0


print("\nFrEDInterface test PASSED")