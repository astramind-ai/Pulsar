import asyncio
import asyncio.subprocess
import os
from pathlib import Path
from app.tunneling.tunnels.base_tunnel import BaseTunnel

class SishTunnel(BaseTunnel):
    def __init__(self, local_port, remote_host='tunnel.pulsar.astramind.ai', local_host='localhost'):
        super().__init__()
        self.local_port = local_port
        self.local_host = local_host
        self.remote_host = remote_host
        self.process = None
        self.remote_url = None
        self.is_running = False
        self.ssh_key_path = Path.home() / ".ssh" / "id_rsa"


    async def start_tunnel(self):

        command = [
            'ssh',
            '-R', f'80:{self.local_host}:{self.local_port}',
            '-p', '2222',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'ExitOnForwardFailure=yes',
            self.remote_host
        ]

        try:
            self.logger.info(f"Starting SSH tunnel with command: {' '.join(command)}")
            self.process = await asyncio.subprocess.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            self.is_running = True

            asyncio.create_task(self._read_output())

            try:
                await asyncio.wait_for(self._wait_for_tunnel(), timeout=30)
            except asyncio.TimeoutError:
                self.logger.error("Failed to establish tunnel within timeout period")
                await self.stop_tunnel()
                return False

            await super().start_tunnel()
            return True

        except Exception as e:
            self.logger.error(f"Error in Tunnel Execution: {e}")
            self.is_running = False
            return False

    async def _read_output(self):
        async def read_stream(stream, log_prefix):
            while True:
                line = await stream.readline()
                if not line:
                    break
                line = line.decode().strip()
                self.logger.debug(f"{log_prefix}: {line}")
                if "HTTPS" in line:
                    self.remote_url = line.split()[-1]
                    self.logger.info(
                        f"Tunnel created at {self.remote_url} with local port {self.local_port} using AstraMind's sish tunneling service")

        await asyncio.gather(
            read_stream(self.process.stdout, "SSH stdout"),
            read_stream(self.process.stderr, "SSH stderr")
        )

        exit_code = await self.process.wait()
        self.logger.info(f"SSH process exited with code {exit_code}")
        self.is_running = False

    async def _wait_for_tunnel(self):
        while not self.remote_url:
            if not self.is_running:
                raise Exception("SSH process terminated before tunnel was established")
            await asyncio.sleep(0.1)

    async def stop_tunnel(self):
        self.is_running = False
        if self.process:
            self.logger.info("Terminating SSH process...")
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.logger.warning("SSH process did not terminate, forcing kill...")
                self.process.kill()
            self.process = None
        self.logger.info("Tunnel stopped.")

    def get_public_url(self):
        return self.remote_url

    def is_tunnel_active(self):
        return self.is_running and self.process and self.process.returncode is None