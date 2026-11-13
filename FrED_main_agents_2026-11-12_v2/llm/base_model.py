from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseLLM(ABC):

    @abstractmethod
    def generate(self, prompt: str) -> Dict[str, Any]:
        """
        Generate a structured FrED action.

        Example:
        {
            "command": "set_extrusion_rpm",
            "rpm": 0.6
        }
        """
        pass