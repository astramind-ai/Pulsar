import requests
import subprocess
import os
from packaging import version

from app.utils.definitions import GITHUB_API_URL
from app.utils.log import setup_custom_logger
from app.utils.server.restarter import restart

logger = setup_custom_logger(__name__)

def get_current_version():
    try:
        # Get the latest tag from the local repository
        result = subprocess.check_output(['git', 'describe', '--tags', '--abbrev=0']).decode().strip()
        return result
    except subprocess.CalledProcessError:
        logger.error("Unable to get current version from local repository.")
        return None


def get_latest_release_version():
    try:
        headers = {}
        if 'GITHUB_TOKEN' in os.environ:
            headers['Authorization'] = f"token {os.environ['GITHUB_TOKEN']}"

        response = requests.get(GITHUB_API_URL, headers=headers)
        response.raise_for_status()
        return response.json()["tag_name"]
    except requests.RequestException as e:
        logger.error(f"Unable to retrieve the latest release version: {e}")
        return None


def git_pull():
    try:
        subprocess.check_call(['git', 'pull'])
        logger.info("Git pull executed successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error while executing git pull: {e}")
        return False


def check_and_update():
    current_version = get_current_version()
    if current_version is None:
        logger.error("Unable to determine current version. Exiting.")
        return

    latest_version = get_latest_release_version()
    if latest_version is None:
        return

    logger.info(f"Current version: {current_version}")
    logger.info(f"Latest available version: {latest_version}")

    if version.parse(latest_version) > version.parse(current_version):
        logger.info(f"New version available: {latest_version}")
        if git_pull():
            restart(dont_save_config=True)
    else:
        logger.info("No update available")
