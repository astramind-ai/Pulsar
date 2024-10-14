# Based on microsoft paper R* algorithm
import re

import asyncio
from asyncio import CancelledError
import time
from typing import List, Dict, Any, AsyncGenerator, Tuple, Optional

from vllm.entrypoints.openai.protocol import ChatCompletionStreamResponse

from app.hijacks.protocols.extended_oai import ExtendedChatCompletionRequest
from app.utils.async_response_wrapper.base import BaseAsyncResponseWrapper
from app.services.logic_booster.mcts import MCTS, Node


class PulsarBoost(BaseAsyncResponseWrapper):
    def __init__(self, api_base_url: str, model_name: str):
        super().__init__(api_base_url, model_name)
        self.mcts = MCTS(api_base_url, model_name)

        self.starting_message += "BOOST-"  # We use this to identify the stream responses
        self.tasks = []

    async def process(self, request: ExtendedChatCompletionRequest, request_id: str) -> AsyncGenerator[str, None]:
        self.logger.info(f"Starting to solve question: {request.messages[-1]['content']}")

        # Create a dictionary of common attributes
        self.general_request = self.mcts.general_request = request.to_standard_request()

        num_rollouts = request.num_rollouts
        max_depth = request.max_depth

        base_messages = request.messages[:-1]
        root = Node(request.messages[-1]['content'])
        created_time = int(time.time())

        yield self._create_stream_response("Starting PulsarBoost process...", request_id, created_time)

        try:
            async for update in self._execute_concurrent_rollouts(root, num_rollouts, max_depth, request_id,
                                                                  created_time, base_messages):
                yield update

            trajectories = self.mcts.get_trajectories(root)

            yield self._create_stream_response(f"Validating {len(trajectories)} trajectories", request_id,
                                               created_time)

            valid_trajectories, verification_updates = await self._verify_trajectories(trajectories, request_id,
                                                                                       created_time, base_messages)

            for update in verification_updates:
                yield update

            if not valid_trajectories:
                yield self._create_stream_response("No valid solutions found.", request_id, created_time)
                return

            yield self._create_stream_response(f"Found {len(valid_trajectories)} valid trajectories",
                                               request_id, created_time)

            best_trajectory = max(valid_trajectories, key=lambda t: self.score_trajectory(t))

            final_content = f"{' '.join(best_trajectory.split('->')[1:]).strip()}"
            yield self._create_stream_response(final_content, request_id, created_time, finish_reason="stop")

        except CancelledError:
            self.logger.info("Main process was cancelled. Cleaning up...")
            self._cancel_all_tasks()
            yield self._create_stream_response("Process was interrupted.", request_id,
                                               created_time, finish_reason="interrupted")
        except Exception as e:
            self.logger.error(f"An error occurred during processing: {str(e)}")
            yield self._create_stream_response(f"An error occurred: {str(e)}", request_id,
                                               created_time, finish_reason="error")
        finally:
            self._cancel_all_tasks()

    def _cancel_all_tasks(self):
        for task in self.tasks:
            if task and not task.done():
                task.cancel()

    async def _execute_concurrent_rollouts(self, root: Node, num_rollouts: int,
                                           max_depth: int, request_id: str,
                                           created_time: int, base_messages: List[Dict[str, str]]) \
            -> AsyncGenerator[Dict[str, Any], None]:

        yield self._create_stream_response(f"Starting {num_rollouts} concurrent rollouts",
                                           request_id, created_time)

        self.tasks = [asyncio.create_task(self._single_rollout(root, max_depth, i, base_messages))
                      for i in range(num_rollouts)]

        try:
            for completed in asyncio.as_completed(self.tasks):
                result = await completed
                yield self._create_stream_response(f"Completed rollout {result['rollout_id']}/{num_rollouts}",
                                                   request_id, created_time)

        except CancelledError:
            self.logger.info("Rollouts were cancelled.")
            raise

    async def _single_rollout(self, root: Node, max_depth: int,
                              rollout_id: int, base_messages: List[Dict[str, str]]) -> Dict[str, Any]:
        start_time = time.time()
        depth = 0
        node = root

        while (not await self.mcts.is_terminal(node.state)) and (depth < max_depth):
            depth += 1
            node = await self.mcts.select(base_messages, node)
            value = await self.mcts.simulate(base_messages, node, max_depth - depth)
            await self.mcts.backpropagate(node, value)

        end_time = time.time()
        return {
            "rollout_id": rollout_id,
            "depth": depth,
            "time": end_time - start_time
        }

    async def _verify_trajectories(self, trajectories: List[str], request_id: str, created_time: int,
                                   base_messages: List[Dict[str, str]]) -> Tuple[List, List[ChatCompletionStreamResponse]]:
        valid_trajectories = list()
        updates = list()

        updates.append(self._create_stream_response(f"Validating {len(trajectories)} trajectories",
                                                    request_id, created_time))

        async def verify_single_trajectory(trajectory: str, trajectory_index: int):
            split_point = max(1, int(len(trajectory) * 0.7))
            messages = base_messages + [{"role": "user",
                                         "content": f"Given the following partial reasoning, complete the solution:"
                                                    f"\n\n{trajectory[:split_point]}\n\nComplete solution:"}]

            is_valid = await self._verify_single_trajectory(messages, trajectory, trajectory_index)
            if is_valid:
                valid_trajectories.append(trajectory)

            return is_valid, trajectory_index

        verification_tasks = [asyncio.create_task(verify_single_trajectory(trajectory, i))
                              for i, trajectory in enumerate(trajectories)]

        try:
            for batch in asyncio.as_completed(verification_tasks):
                is_valid, index = await batch
                updates.append(self._create_stream_response(
                    f"Verified trajectory {index + 1}/{len(trajectories)}: {'Valid' if is_valid else 'Invalid'}",
                    request_id,
                    created_time))

        except CancelledError:
            self.logger.info("Trajectory verification was cancelled.")
            raise

        return valid_trajectories, updates


    async def _verify_single_trajectory(self, messages: List[Dict[str, str]],
                                        original_trajectory: str,
                                        trajectory_index: int) -> bool:
        try:
            request = self._update_chat_request(messages=messages, stream=False)
            async for response in self.api_call(request):
                completion = response['choices'][0]['message']['content']
                is_valid = self.is_consistent(original_trajectory, completion)
                self.logger.debug(f"Trajectory {trajectory_index} validation result: {is_valid}")
                return is_valid
        except Exception as e:
            self.logger.error(f"Error verifying trajectory {trajectory_index}: {str(e)}")
            return False

    def is_consistent(self, original: str, completion: str) -> bool:
        original_answer = self.extract_answer(original)
        completion_answer = self.extract_answer(completion)
        return original_answer == completion_answer

    def score_trajectory(self, trajectory: str) -> float:
        steps = len(trajectory.split("\n"))
        has_answer = 1 if self.extract_answer(trajectory) else 0
        return steps + has_answer * 10

    @staticmethod
    def extract_answer(trajectory: str) -> Optional[str]:
        match = re.search(r"The answer is: (\d+)", trajectory)
        return match.group(1) if match else None




