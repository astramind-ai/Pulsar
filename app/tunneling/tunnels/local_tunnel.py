import asyncio
import asyncio.subprocess

from app.tunneling.tunnels.base_tunnel import BaseTunnel


class CancelledError(Exception):
    pass


class LocalTunnel(BaseTunnel):
    def __init__(self, local_port, name_preferences=None, local_host='localhost'):
        super().__init__()
        self.local_port = local_port
        self.name_preferences = name_preferences
        self.local_host = local_host
        self.process = None
        self.remote_url = None
        self.is_running = False

    async def start_tunnel(self):
        command = ['pylt', 'port', str(self.local_port)]  # TODO : insert puslar local tunnel once open and tested
        if self.name_preferences:
            command.extend(['-s', self.name_preferences])

        try:
            self.logger.info(f"Starting LocalTunnel with command: {' '.join(command)}")
            self.process = await asyncio.subprocess.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            self.is_running = True

            async def read_output(stream, log_prefix):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    line = line.decode().strip()
                    self.logger.debug(f"{log_prefix}: {line}")
                    if line.startswith('Your url is: '):
                        self.remote_url = line.split(': ', 1)[1].strip()
                        return  # Exit the coroutine

            # Create tasks for each read_output coroutine
            tasks = [
                asyncio.create_task(read_output(self.process.stdout, "LocalTunnel stdout")),
                asyncio.create_task(read_output(self.process.stderr, "LocalTunnel stderr"))
            ]

            try:
                # Wait for the first task to complete
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=30)
                # Cancel any pending tasks
                for task in pending:
                    task.cancel()
                # Check if the URL was found
                if self.remote_url:
                    await super().start_tunnel()
                    self.logger.info(
                        f"Tunnel created at {self.remote_url} with local port {self.local_port} using LocalTunnel")
                    return True
                else:
                    self.logger.error("Failed to establish tunnel within timeout period")
                    await self.stop_tunnel()
                    return False
            except asyncio.TimeoutError:
                self.logger.error("Timeout while waiting for the tunnel URL")
                for task in tasks:
                    task.cancel()
                await self.stop_tunnel()
                return False

        except Exception as e:
            self.logger.error(f"Error in Tunnel Execution: {e}")
            self.is_running = False
            return False

        finally:
            if self.process:
                self.process.terminate()
                await self.process.wait()
                self.logger.info("LocalTunnel process terminated")
                self.is_running = False

    async def stop_tunnel(self):
        self.is_running = False
        if self.process:
            self.logger.info("Terminating LocalTunnel process...")
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.logger.warning("LocalTunnel process did not terminate, forcing kill...")
                self.process.kill()
            self.process = None
        self.logger.info("Tunnel stopped.")

    def get_public_url(self):
        return self.remote_url

    def is_tunnel_active(self):
        return self.is_running and self.process and self.process.returncode is None
