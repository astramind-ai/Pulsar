import asyncio
from typing import Optional

from app.utils.log import setup_custom_logger
from app.utils.server.restarter import restart

logger = setup_custom_logger(__name__)


async def continuously_monitor_server_for_errors(time_to_sleep: int = 60):
    from app.core.engine import openai_serving_chat
    while True:
        try:
            if openai_serving_chat:
                await openai_serving_chat.engine_client.check_health()
        except Exception as e:
            logger.error(f"The server is not functioning due to {e}, restarting")
            restart(dont_save_config=True)
        await asyncio.sleep(time_to_sleep)  # Sleep for 60 seconds before next check


class ServerMonitor:
    def __init__(self, check_interval: int = 20):
        self.check_interval = check_interval
        self.monitoring_task: Optional[asyncio.Task] = None

    async def start_monitoring(self):
        if self.monitoring_task is None or self.monitoring_task.done():
            self.monitoring_task = asyncio.create_task(self._run_monitoring())
            logger.info("Server monitoring started")

    async def stop_monitoring(self):
        if self.monitoring_task and not self.monitoring_task.done():
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
            logger.info("Server monitoring stopped")

    async def _run_monitoring(self):
        try:
            await continuously_monitor_server_for_errors(self.check_interval)
        except asyncio.CancelledError:
            logger.info("Monitoring task was cancelled")
        except Exception as e:
            logger.error(f"An unexpected error occurred in the monitoring task: {e}")


async def setup_server_monitoring(check_interval: int = 60):
    monitor = ServerMonitor(check_interval)
    await monitor.start_monitoring()
    return monitor
