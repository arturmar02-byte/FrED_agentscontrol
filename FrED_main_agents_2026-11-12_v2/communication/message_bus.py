from typing import Dict

from communication.schemas import Message


class MessageBus:

    def __init__(self):
        self._agents: Dict[str, object] = {}

    def register(self, agent):
        if agent.name in self._agents:
            raise ValueError(
                f"Agent '{agent.name}' already registered."
            )

        self._agents[agent.name] = agent
        agent.set_message_bus(self)

    def unregister(self, agent_name: str):
        if agent_name in self._agents:
            agent = self._agents.pop(agent_name)
            agent.set_message_bus(None)

    def publish(self, message: Message):

        if message.receiver == "*":
            for agent_name, agent in self._agents.items():
                if agent_name != message.sender:
                    agent.receive(message)
            return

        receiver = self._agents.get(message.receiver)

        if receiver is None:
            raise ValueError(
                f"Receiver '{message.receiver}' is not registered."
            )

        receiver.receive(message)