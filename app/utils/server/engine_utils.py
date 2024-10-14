import re


def find_max_seq_len(error):
    numers = re.findall(r'\d+', error)
    if len(numers) >= 2:
        return int(numers[1])
    else:
        return None
