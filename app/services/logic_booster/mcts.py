import asyncio
import json
import re
from typing import List, Dict, Optional

import numpy as np

from app.utils.async_response_wrapper.base import BaseAsyncResponseWrapper
from app.utils.log import setup_custom_logger


class Node:
    def __init__(self, state: str, action: Optional[str] = None, parent: Optional['Node'] = None):
        self.state = state
        self.action = action
        self.parent = parent
        self.children: List[Node] = []
        self.visits = 0
        self.value = 0.0


class MCTS(BaseAsyncResponseWrapper):
    def __init__(self, api_base_url: str, model_name: str, c: float = 1.414):
        super().__init__(api_base_url, model_name)
        self.c = c
        self.logger = setup_custom_logger(f"{__name__}.MCTS")
        self.stats = {
            "nodes_explored": 0,
            "actions_taken": 0,
            "simulations_run": 0,
            "total_depth_reached": 0
        }

    async def select(self, messages: List[Dict[str, str]], node: Node) -> Node:
        self.logger.debug(f"Selecting node: {node.state[:50]}...")
        self.stats["nodes_explored"] += 1

        while node.children:
            unvisited = [child for child in node.children if child.visits == 0]
            if unvisited:
                return np.random.choice(unvisited)

            if not all(child.visits > 0 for child in node.children):
                return await self.expand(messages, node)

            node = max(node.children,
                       key=lambda n: n.value / n.visits + self.c * np.sqrt(np.log(node.visits) / n.visits))
            if len(node.state) > 750:
                node.state = await self.summarize(messages, node.state)
        return await self.expand(messages, node)

    async def expand(self, messages: List[Dict[str, str]], node: Node) -> Node:
        actions = await self.get_dynamic_actions(messages, node.state)
        new_states = await asyncio.gather(*[self.apply_action(messages, node.state, action) for action in actions])

        for action, new_state in zip(actions, new_states):
            if new_state not in [child.state for child in node.children]:
                new_node = Node(new_state, action, node)
                node.children.append(new_node)
                self.stats["actions_taken"] += 1
                return new_node

        return node

    async def simulate(self, messages: List[Dict[str, str]], node: Node, remaining_depth: int) -> float:
        state = node.state
        total_value = 0
        depth = 0

        while not await self.is_terminal(state) and depth < remaining_depth:
            actions = await self.get_dynamic_actions(messages, state)
            action_values = await self.evaluate_actions(messages, state, actions)
            action = self.select_action_for_simulation(actions, action_values)
            state = await self.apply_action(messages, state, action)
            total_value += await self.evaluate_state(messages, state)
            depth += 1

        self.stats["simulations_run"] += 1
        self.stats["total_depth_reached"] += depth
        return total_value / (depth + 1)

    async def summarize(self, messages: List[Dict[str, str]], state: str) -> str:
        new_messages = messages.copy()
        new_messages.append({"role": "user",
                             "content": f"Briefly summarize this state. No matter what it should not exceed "
                                        f"400 characters:\n\n{state}\n\nSummary:"})

        summary_schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "maxLength": 400}
            },
            "required": ["summary"]
        }

        request = self._update_chat_request(messages=new_messages, stream=False,
                                            guided_json=summary_schema)
        try:
            async for response in self.api_call(request):
                summary = response['choices'][0]['message']['content']
                return json.loads(summary)['summary'][:450]
        except Exception as e:
            self.logger.error(f"Error {e} during summarization")
            return state[:450]

    async def backpropagate(self, node: Node, value: float):
        self.logger.debug(f"Backpropagating value {value}")
        while node:
            node.visits += 1
            node.value += value
            node = node.parent

    async def apply_action(self, messages: List[Dict[str, str]], state: str, action: str) -> str:
        self.logger.debug(f"Applying action {action}")
        new_messages = messages.copy()
        new_messages.append({"role": "user",
                             "content": f"Given the current reasoning state:"
                                        f"\n'{state}'\n\nPerform the following action: {action}"})

        request = self._update_chat_request(messages=new_messages, stream=False)
        try:
            async for response in self.api_call(request):
                new_state = response['choices'][0]['message']['content']
                self.logger.debug(f"New state after action {action}: {new_state[:100]}...")
                return new_state
        except Exception as e:
            self.logger.error(f"Error applying action {action}: {str(e)}")
            raise

    @staticmethod
    async def is_terminal(state: str) -> bool:
        return bool(re.search(r"(The answer is:|Final result:) \S+", state, re.IGNORECASE))

    async def evaluate_state(self, messages: List[Dict[str, str]], state: str) -> float:
        new_messages = messages.copy()
        new_messages.append({"role": "user",
                             "content": f"Evaluate the following state in terms of coherence, detail, and correctness. "
                                        f"Provide a score between 0 and 1:\n\n{state}\n\nScore:"})
        evaluation_schema = {
            "type": "object",
            "properties": {
                "score": {"type": "number", "minimum": 0, "maximum": 1}
            },
            "required": ["score"]
        }
        request = self._update_chat_request(messages=new_messages, stream=False, guided_json=evaluation_schema,
                                            max_tokens=100)
        try:
            async for response in self.api_call(request):
                evaluation_result = response['choices'][0]['message']['content']
                score = float(json.loads(evaluation_result)['score'])
                return max(0, min(1, float(score)))
        except Exception as e:
            self.logger.error(f"Error evaluating state: {str(e)}")
            return 0.5

    async def get_dynamic_actions(self, messages: List[Dict[str, str]], state: str) -> List[str]:
        new_messages = messages.copy()
        new_messages.append({"role": "user",
                             "content": f"Given the current state:\n{state}\n\n"
                                        f"Suggest 5 possible actions to progress the reasoning. "
                                        f"Format the response as a JSON list of strings."})
        actions_schema = {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 5
                }
            },
            "required": ["actions"]
        }
        request = self._update_chat_request(messages=new_messages, stream=False,
                                            guided_json=actions_schema)
        try:
            async for response in self.api_call(request):
                actions_json = response['choices'][0]['message']['content']
                actions = json.loads(actions_json)['actions']
                return actions[:5]
        except Exception as e:
            self.logger.error(f"Error getting dynamic actions: {str(e)}")
            return ["Elaborate", "Summarize", "Question", "Answer", "Critique"]

    async def evaluate_actions(self, messages: List[Dict[str, str]], state: str, actions: List[str]) -> List[float]:
        new_messages = messages.copy()
        new_messages.append({"role": "user",
                             "content": f"Given the current state:\n{state}\n\n"
                                        f"Evaluate the potential of each action on a scale of 0 to 1:"
                                        f"\n{json.dumps(actions)}\n\n"
                                        f"Provide the evaluations as a JSON list of floats."})

        evaluations_schema = {
            "type": "object",
            "properties": {
                "evaluations": {
                    "type": "array",
                    "items": {"type": "number", "minimum": 0, "maximum": 1},
                    "minItems": 1,
                    "maxItems": 5
                }
            },
            "required": ["evaluations"]
        }
        request = self._update_chat_request(messages=new_messages, stream=False,
                                            guided_json=evaluations_schema, max_tokens=100)
        try:
            async for response in self.api_call(request):
                evaluations_json = response['choices'][0]['message']['content']
                evaluations = json.loads(evaluations_json)['evaluations']
                return [max(0, min(1, float(e))) for e in evaluations]
        except Exception as e:
            self.logger.error(f"Error evaluating actions: {str(e)}")
            return [0.5] * len(actions)

    @staticmethod
    def select_action_for_simulation(actions: List[str], action_values: List[float]) -> str:
        if len(actions) != len(action_values):
            min_length = min(len(actions), len(action_values))
            actions = actions[:min_length]
            action_values = action_values[:min_length]

        total = sum(action_values)
        if total == 0:
            return np.random.choice(actions)
        probs = [v / total for v in action_values]
        return np.random.choice(actions, p=probs)

    @staticmethod
    def get_trajectories(root: Node) -> List[str]:
        trajectories = []
        stack = [(root, "")]
        while stack:
            node, path = stack.pop()
            if not node.children:  # Leaf node
                trajectories.append(path + node.state)
            else:
                for child in node.children:
                    stack.append((child, f"{path}{node.state} -> {child.action}: "))
        return trajectories
