import uuid

import aiohttp
from aiohttp import ClientTimeout

from app.utils.log import setup_custom_logger

logger = setup_custom_logger(__name__)


class BaseTunnel:
    def __init__(self):
        self.assigned_url_info = None
        self.local_host = 'localhost'
        self.local_port = None
        self.remote_url = None
        self.name_preferences = 'pulsar'
        self.rand_hex = uuid.uuid4().hex
        self.logger = logger

    async def start_tunnel(self) -> None:
        await self.set_url(self.remote_url)

    @staticmethod
    async def set_url(url: str) -> None:
        from server import set_online_url

        await set_online_url(url)

    async def stop_tunnel(self) -> None:
        pass

    async def verify_tunnel(self):
        if not self.remote_url:
            return False

        headers = {
            'Ngrok-Skip-Browser-Warning': '69420',
            'Bypass-Tunnel-Reminder': 'yup'
        }

        try:
            async with aiohttp.ClientSession(timeout=ClientTimeout(total=10)) as session:
                async with session.get(self.remote_url+"/health", headers=headers) as response:
                    if response.status == 200:
                        return True
                    else:
                        self.logger.error(f"Tunnel verification failed: received {response.status} status code")
                        return False
        except Exception as e:
            self.logger.error(f"Error during tunnel verification: {str(e)}")
            return False
