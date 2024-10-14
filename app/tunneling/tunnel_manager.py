import os

from app.tunneling.tunnels.base_tunnel import BaseTunnel
from app.tunneling.tunnels.local_tunnel import LocalTunnel
from app.tunneling.tunnels.ngrok_tunnel import NgrokTunnel
from app.tunneling.tunnels.serveo_tunnel import ServeoTunnel
from app.utils.definitions import TUNNEL_TYPES
from app.utils.log import setup_custom_logger

logger = setup_custom_logger(__name__)

async def start_tunnel_after_server(server_args) -> None:
    if not os.environ.get("PULSAR_PRIVATE_KEY"):
        logger.warn("PULSAR_PRIVATE_KEY environment variable not set. Please configure this machine to be connectable from outside.")
        return
    # List of tunnel types to try, in order of preference
    tunnel_types = TUNNEL_TYPES if not server_args.tunnel_type else [server_args.tunnel_type]
    # Servo is disabled since it will cause the request to drop with ERR_HTTP2_PROTOCOL_ERROR
    for tunnel_type in tunnel_types:
        try:
            # Create the appropriate tunnel object based on the type
            match tunnel_type:
                case "serveo":
                    tunnel = ServeoTunnel(server_args.port, 80)
                case "localtunnel" | "lt":
                    tunnel = LocalTunnel(local_port=server_args.port)
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

    # If all tunnel attempts fail, use the local URL
    logger.warn("All tunnel creation attempts failed. Using local URL.")
    try:
        await BaseTunnel.set_url(
        f"http://{server_args.host or 'localhost'}:{server_args.port}")
    except Exception:
        logger.error(f"Your private key does not match your public key, you need to launch the UI in local mode, "
                     f"go into settings and then recreate the key pairs, otherwise you will not be able to use the tunneling feature.")