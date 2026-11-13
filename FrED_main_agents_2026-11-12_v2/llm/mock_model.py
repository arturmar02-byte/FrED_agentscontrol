import re

from llm.base_model import BaseLLM


class MockLLM(BaseLLM):
    is_simulated = True
    model_name = "MockLLM"
    provider = "local_deterministic_mock"

    def generate(self, prompt: str) -> dict:

        prompt_lower = prompt.lower()

        # --------------------------------------------------
        # Emergency / global stop
        # --------------------------------------------------

        if "stop all" in prompt_lower:
            return {
                "command": "stop_all"
            }

        # --------------------------------------------------
        # Extruder
        # --------------------------------------------------

        if "extrusion" in prompt_lower or "extruder" in prompt_lower:

            rpm = self._extract_number(prompt_lower)

            if rpm is not None:
                return {
                    "command": "set_extrusion_rpm",
                    "rpm": rpm,
                }

        # --------------------------------------------------
        # Spooler
        # --------------------------------------------------

        if "spooler" in prompt_lower:

            duty = self._extract_number(prompt_lower)

            if duty is not None:
                return {
                    "command": "set_spooler_duty",
                    "duty_cycle": duty,
                }

        # --------------------------------------------------
        # Fan
        # --------------------------------------------------

        if "fan" in prompt_lower:

            duty = self._extract_number(prompt_lower)

            if duty is not None:
                return {
                    "command": "set_fan_duty",
                    "duty_cycle": duty,
                }

        # --------------------------------------------------
        # Individual stop commands
        # --------------------------------------------------

        if "stop heater" in prompt_lower:
            return {
                "command": "stop_heater"
            }

        if "stop extruder" in prompt_lower:
            return {
                "command": "stop_extruder"
            }

        if "stop spooler" in prompt_lower:
            return {
                "command": "stop_spooler"
            }

        # --------------------------------------------------
        # Unknown
        # --------------------------------------------------

        return {
            "command": "unknown"
        }

    @staticmethod
    def _extract_number(text: str):

        match = re.search(
            r"[-+]?\d*\.?\d+",
            text,
        )

        if match is None:
            return None

        return float(match.group())
