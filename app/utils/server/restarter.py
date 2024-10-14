import os
import sys
from time import sleep


def restart(server_conf=None, dont_save_config: bool = False):
    if server_conf and dont_save_config==False:
        server_conf.save_to_yaml()
    sleep(0.3)
    arguments = [sys.argv[0]]
    arguments.extend(['--use_config_file', "True", '--server_config_file', 'last.yml'])
    os.execv(sys.executable, ['python3'] + arguments)
