# ============================================================
# FrED safety and operating limits
# ============================================================

# Legacy safety test
MINIMUM_SAFE_DISTANCE = 0.30


# ------------------------------------------------------------
# Extrusion stepper
# ------------------------------------------------------------

MIN_EXTRUSION_RPM = 0.0
MAX_EXTRUSION_RPM = 20.0


# ------------------------------------------------------------
# Spooling DC motor
# ------------------------------------------------------------

MIN_SPOOLER_DUTY = 0.0
MAX_SPOOLER_DUTY = 100.0


# ------------------------------------------------------------
# Cooling fan
# ------------------------------------------------------------

MIN_FAN_DUTY = 0.0
MAX_FAN_DUTY = 100.0


# ------------------------------------------------------------
# Fiber diameter
# ------------------------------------------------------------

MIN_FIBER_DIAMETER = 0.30
MAX_FIBER_DIAMETER = 0.60


# ------------------------------------------------------------
# Temperature
# ------------------------------------------------------------

MIN_TARGET_TEMPERATURE = 65.0
MAX_TARGET_TEMPERATURE = 150.0

# Absolute hardware safety limit
MAX_SAFE_TEMPERATURE = 220.0

# Hysteresis used to reset the internal over-temperature state.
TEMP_SAFETY_HYSTERESIS = 5.0

# ------------------------------------------------------------
# Perception
# ------------------------------------------------------------

PERCEPTION_INTERVAL = 0.1  # seconds (10 Hz)