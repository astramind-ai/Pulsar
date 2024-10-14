import ngrok

from app.tunneling.tunnels.base_tunnel import BaseTunnel


class NgrokTunnel(BaseTunnel):
    def __init__(self, local_port, auth_token=None, region=None):
        super().__init__()
        self.local_port = local_port
        self.auth_token = auth_token
        self.region = region
        self.tunnel = None
        self.remote_url = None
        self.is_running = False

    async def start_tunnel(self):
        try:
            self.logger.info(f"Starting ngrok tunnel for port {self.local_port}")

            listener = await ngrok.forward(self.local_port, authtoken=self.auth_token, region=self.region)
            self.remote_url = listener.url()
            self.tunnel = listener
            self.is_running = True

            self.logger.info(f"Tunnel created at {self.remote_url}")
            await super().start_tunnel()
            return True
        except Exception as e:
            self.logger.error(f"Error in Tunnel Execution: {e}")
            self.is_running = False
            return False

    async def stop_tunnel(self):
        if self.tunnel:
            self.logger.info("Closing ngrok tunnel...")
            await self.tunnel.close()
            self.tunnel = None
        self.is_running = False
        self.logger.info("Tunnel stopped.")

    def get_public_url(self):
        return self.remote_url

    def is_tunnel_active(self):
        return self.is_running and self.tunnel is not None
