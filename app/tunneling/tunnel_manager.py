import os

from app.tunneling.tunnels.base_tunnel import BaseTunnel
from app.tunneling.tunnels.local_tunnel import LocalTunnel
from app.tunneling.tunnels.ngrok_tunnel import NgrokTunnel
from app.tunneling.tunnels.serveo_tunnel import ServeoTunnel
from app.tunneling.tunnels.sish_tunnel import SishTunnel
from app.utils.definitions import TUNNEL_TYPES, ALLOWED_TUNNEL_STRINGS
from app.utils.log import setup_custom_logger

logger = setup_custom_logger(__name__)

async def start_tunnel_after_server(server_args) -> None:
    if not os.environ.get("PULSAR_PRIVATE_KEY") or server_args.tunnel_type == "no_tunnel":
        logger.warn("PULSAR_PRIVATE_KEY environment variable not set. Please configure this machine to be connectable from outside." if not os.environ.get("PULSAR_PRIVATE_KEY") else "Using local IP for tunneling. This machine will not be connectable from outside this computer.")
        return
    # List of tunnel types to try, in order of preference
    if server_args.tunnel_type:
        assert server_args.tunnel_type in ALLOWED_TUNNEL_STRINGS, f"Invalid tunnel type: {server_args.tunnel_type}, allowed ones are {ALLOWED_TUNNEL_STRINGS}"

    tunnel_types = TUNNEL_TYPES if not server_args.tunnel_type else [server_args.tunnel_type.lower()]

    if tunnel_types[0] == 'local_ip':
        try:
            logger.info("Using local IP for tunneling., we'll associate your local ip to your machine, so you can access it from the same network without exposing it to the internet.")
            # We get the local network IP to use it as the URL
            local_network_ip = os.popen('ip route get 1 | awk \'{print $7}\'').read().strip()

            await BaseTunnel.set_url(
                f"http://{local_network_ip}:{server_args.port}")
        except Exception:
            logger.error(f"Your private key does not match your public key, you need to launch the UI in local mode, "
                         f"go into settings and then recreate the key pairs, otherwise you will not be able to use the tunneling feature.")
        finally:
            return

    # Servo is disabled since it will cause the request to drop with ERR_HTTP2_PROTOCOL_ERROR
    for tunnel_type in tunnel_types:
        try:
            # Create the appropriate tunnel object based on the type
            match tunnel_type:
                case "serveo": #disabled atm since it's unstable
                    tunnel = ServeoTunnel(server_args.port, 80)
                case "localtunnel" | "lt":
                    tunnel = LocalTunnel(local_port=server_args.port)
                case "sish":
                    tunnel = SishTunnel(local_port=server_args.port)
                case _:
                    tunnel = NgrokTunnel(server_args.port, server_args.ngrok_auth_token)

            # Attempt to start the tunnel
            success = await tunnel.start_tunnel()
            if success:
                # If the tunnel starts successfully, verify it
                verified = await tunnel.verify_tunnel()
                if verified:
                    tunnel.logger.info(f"Tunnel successfully created and verified using {tunnel_type}")
                    return
                else:
                    tunnel.logger.error(f"Tunnel created but not verified with {tunnel_type}, trying next...")
                    await tunnel.stop_tunnel()
            else:
                logger.info(f"Failed to create tunnel with {tunnel_type}, trying next...")

        except Exception as e:
            logger.error(f"Error during creation or verification of tunnel with {tunnel_type}: {str(e)}")

    if server_args.tunnel_type == "local_ip":

        logger.error(f"Failed to create tunnel with specified type: {server_args.tunnel_type}")
    # If all tunnel attempts fail, use the local URL
    logger.warn("All tunnel creation attempts failed. Using local URL.")
    try:
        await BaseTunnel.set_url(
        f"http://{server_args.host or 'localhost'}:{server_args.port}")
    except Exception:
        logger.error(f"Your private key does not match your public key, you need to launch the UI in local mode, "
                     f"go into settings and then recreate the key pairs, otherwise you will not be able to use the tunneling feature.")