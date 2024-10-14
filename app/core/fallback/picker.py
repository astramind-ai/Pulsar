import os
from typing import Any

import yaml

file_path = os.path.join(os.path.dirname(__file__), "fallback.yml")


def pick_a_quantized_fallback(quant_preference) -> Any:
    """
    Pick from a fallback yaml file the name and link for a quantized model
    :return:
    """
    with open(file_path) as file:
        data = yaml.load(file, Loader=yaml.FullLoader)
        # check if the quantized_fallback key exists in the yaml file
        try:
            return data["model"][quant_preference]
        except KeyError:
            return None
