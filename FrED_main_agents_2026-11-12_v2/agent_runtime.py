import logging

from communication.message_bus import MessageBus

from agents.perception_agent import PerceptionAgent
from agents.safety_agent import SafetyAgent
from agents.controller_agent import ControllerAgent
from agents.reasoning_agent import ReasoningAgent

from llm.mock_model import MockLLM
from research.agent_metrics import AgentMetrics
from communication.schemas import Message, MessageType


class AgentRuntime:
    """
    Coordinates all FrED agents.

    The runtime receives an already initialized FrEDInterface
    and builds the multi-agent system around it.
    """

    def __init__(
        self,
        fred,
        enable_control: bool = False,
        enable_reasoning: bool = False,
        metrics_dir=None,
        model=None,
        context=None,
    ):

        self.logger = logging.getLogger(
            "agent_runtime"
        )

        self.fred = fred

        self.enable_control = enable_control
        self.enable_reasoning = enable_reasoning
        self.metrics = AgentMetrics(metrics_dir, context=context)

        # ------------------------------------------------------
        # Message infrastructure
        # ------------------------------------------------------

        self.bus = MessageBus()

        # ------------------------------------------------------
        # Core agents
        # ------------------------------------------------------

        self.perception_agent = PerceptionAgent(
            fred=self.fred
        )

        self.safety_agent = SafetyAgent()

        self.controller_agent = ControllerAgent(
            fred=self.fred,
            control_enabled=self.enable_control,
        )

        # ------------------------------------------------------
        # Optional reasoning layer
        # ------------------------------------------------------

        self.reasoning_agent = None

        if self.enable_reasoning:

            model = model if model is not None else MockLLM()

            self.reasoning_agent = ReasoningAgent(
                model=model
            )

        # ------------------------------------------------------
        # Register agents
        # ------------------------------------------------------

        self.bus.register(
            self.perception_agent
        )

        self.bus.register(
            self.safety_agent
        )

        self.bus.register(
            self.controller_agent
        )

        if self.reasoning_agent is not None:
            self.bus.register(
                self.reasoning_agent
            )
        self.agents = [self.perception_agent, self.safety_agent, self.controller_agent]
        if self.reasoning_agent is not None:
            self.agents.append(self.reasoning_agent)
        for agent in self.agents:
            agent.metrics = self.metrics

    def request_reasoning(self, prompt, preview=True):
        if self.reasoning_agent is None or not self.reasoning_agent._running.is_set():
            raise ValueError("Reasoning agent is not running.")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4096:
            raise ValueError("Enter an instruction with 1 to 4096 characters.")
        if self.reasoning_agent.inbox.qsize() >= 8:
            raise ValueError("Reasoning queue is full. Wait for pending requests.")
        message = Message(sender="performance_display", receiver=self.reasoning_agent.name,
                          message_type=MessageType.REQUEST,
                          payload={"prompt": prompt.strip(), "preview": bool(preview)})
        self.bus.publish(message)
        self.metrics.record("request_submitted", "reasoning_agent", message_id=message.message_id,
                            prompt=prompt.strip(), preview=bool(preview))
        return message.message_id

    def snapshot(self):
        result = self.metrics.snapshot()
        result["agents"] = [{"name": agent.name, "state": agent.state.value,
                             "alive": agent._thread is not None and agent._thread.is_alive(),
                             "pending": agent.inbox.qsize()} for agent in self.agents]
        model = self.reasoning_agent.model if self.reasoning_agent else None
        result["model"] = ({"name": getattr(model, "model_name", type(model).__name__),
                            "provider": getattr(model, "provider", type(model).__name__),
                            "simulated": bool(getattr(model, "is_simulated", False))} if model else None)
        result["control_enabled"] = self.enable_control
        result["emergency_stop"] = self.controller_agent.emergency_stop_active
        return result

    # ==========================================================
    # START
    # ==========================================================

    def start(self):
        self.metrics.record("lifecycle", "runtime", event="start",
                            model=self.snapshot()["model"], control_enabled=self.enable_control)

        self.logger.info(
            "Starting FrED agent runtime"
        )

        self.controller_agent.start()
        self.safety_agent.start()
        self.perception_agent.start()

        if self.reasoning_agent is not None:
            self.reasoning_agent.start()

        self.logger.info(
            "FrED agent runtime started"
        )

        if not self.enable_control:
            self.logger.warning(
                "Hardware control is DISABLED "
                "(read-only test mode)"
            )

    # ==========================================================
    # STOP
    # ==========================================================

    def stop(self):

        self.logger.info(
            "Stopping FrED agent runtime"
        )

        self.perception_agent.stop()
        self.safety_agent.stop()

        if self.reasoning_agent is not None:
            self.reasoning_agent.stop()

        self.controller_agent.stop()
        self.metrics.record("lifecycle", "runtime", event="stop",
                            pending_messages={agent.name: agent.inbox.qsize() for agent in self.agents})
        for agent in self.agents:
            if agent._thread is not None and agent._thread.is_alive():
                self.metrics.record("shutdown", agent.name, status="error",
                                    error="Agent thread still running after shutdown timeout.")
        self.metrics.close()

        self.logger.info(
            "FrED agent runtime stopped"
        )
