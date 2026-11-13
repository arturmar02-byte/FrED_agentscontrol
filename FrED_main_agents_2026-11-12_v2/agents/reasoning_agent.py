from agents.base_agent import BaseAgent

from communication.schemas import (
    Message,
    MessageType,
    MessagePriority,
)

from llm.base_model import BaseLLM
import time


class ReasoningAgent(BaseAgent):

    ALLOWED_COMMANDS = {
        "set_extrusion_rpm",
        "set_spooler_duty",
        "set_fan_duty",
        "stop_heater",
        "stop_extruder",
        "stop_spooler",
        "stop_all",
    }

    def __init__(
        self,
        model: BaseLLM,
        name: str = "reasoning_agent",
    ):
        super().__init__(name)

        self.model = model

    def process_message(self, message: Message):

        if message.message_type != MessageType.REQUEST:
            return

        prompt = message.payload.get("prompt")

        if not prompt:
            self.logger.warning(
                f"Request {message.message_id} contains no prompt"
            )
            return

        self.logger.info(
            f"Processing reasoning request: {prompt}"
        )

        started_ns = time.perf_counter_ns()
        response = None
        error = None
        status = "ok"
        finished_ns = None
        try:
            response = self.model.generate(prompt)
            finished_ns = time.perf_counter_ns()
            command = response.get("command") if isinstance(response, dict) else None
            if command not in self.ALLOWED_COMMANDS:
                status = "rejected"
                self.logger.warning(f"Rejected model response: {response}")
                return
            # Dashboard requests only evaluate latency and proposals.
            if message.payload.get("preview", False):
                return
            if not self._stopping.is_set():
                self.send(Message(
                    sender=self.name, receiver="controller_agent",
                    message_type=MessageType.COMMAND, payload=response,
                    priority=MessagePriority.NORMAL.value,
                    correlation_id=message.message_id,
                    trace_started_ns=message.trace_started_ns))
        except Exception as exc:
            status, error = "error", str(exc)
            raise
        finally:
            if self.metrics is not None:
                self.metrics.record("llm_call", self.name, status=status,
                    durations={"inference_ms": ((finished_ns or time.perf_counter_ns()) - started_ns) / 1e6,
                               "request_latency_ms": (time.perf_counter_ns() - message.created_monotonic_ns) / 1e6},
                    message_id=message.message_id, correlation_id=message.correlation_id,
                    model=getattr(self.model, "model_name", type(self.model).__name__),
                    provider=getattr(self.model, "provider", type(self.model).__name__),
                    simulated=bool(getattr(self.model, "is_simulated", False)),
                    preview=bool(message.payload.get("preview", False)),
                    prompt=prompt, response=response, error=error,
                    # No streaming or provider billing instrumentation is installed.
                    time_to_first_token_ms=None, cost_usd=None,
                    usage=response.get("usage") if isinstance(response, dict) else None)
        
