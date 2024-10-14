import struct
from typing import Any, Dict, List, Optional, Tuple

from app.utils.definitions import INITIAL_CHUNK_SIZE, GGUF_MAGIC


def read_u32(data: bytes, offset: int) -> Tuple[int, int]:
    return struct.unpack("<I", data[offset:offset + 4])[0], offset + 4


def read_u64(data: bytes, offset: int) -> Tuple[int, int]:
    return struct.unpack("<Q", data[offset:offset + 8])[0], offset + 8


def read_string(data: bytes, offset: int) -> Tuple[str, int]:
    length, offset = read_u64(data, offset)
    return data[offset:offset + length].decode('utf-8'), offset + length


def read_value(data: bytes, offset: int, data_type: int) -> Tuple[Any, int]:
    if data_type == 0:  # UINT8
        return data[offset], offset + 1
    elif data_type == 1:  # INT8
        return struct.unpack("b", data[offset:offset + 1])[0], offset + 1
    elif data_type == 2:  # UINT16
        return struct.unpack("<H", data[offset:offset + 2])[0], offset + 2
    elif data_type == 3:  # INT16
        return struct.unpack("<h", data[offset:offset + 2])[0], offset + 2
    elif data_type == 4:  # UINT32
        return read_u32(data, offset)
    elif data_type == 5:  # INT32
        return struct.unpack("<i", data[offset:offset + 4])[0], offset + 4
    elif data_type == 6:  # FLOAT32
        return struct.unpack("<f", data[offset:offset + 4])[0], offset + 4
    elif data_type == 7:  # BOOL
        return bool(data[offset]), offset + 1
    elif data_type == 8:  # STRING
        return read_string(data, offset)
    elif data_type == 9:  # ARRAY
        array_type, offset = read_u32(data, offset)
        array_length, offset = read_u64(data, offset)
        array = []
        for _ in range(array_length):
            value, offset = read_value(data, offset, array_type)
            array.append(value)
        return array, offset
    elif data_type == 10:  # UINT64
        return read_u64(data, offset)
    elif data_type == 11:  # INT64
        return struct.unpack("<q", data[offset:offset + 8])[0], offset + 8
    elif data_type == 12:  # FLOAT64
        return struct.unpack("<d", data[offset:offset + 8])[0], offset + 8
    else:
        raise ValueError(f"Unknown data type: {data_type}")


def extract_gguf_info_local(file_path: str, params: Optional[List[str]] = None) -> Dict[str, Any]:
    chunk_size = INITIAL_CHUNK_SIZE

    with open(file_path, 'rb') as file:
        data = file.read(chunk_size)

        if data[:4] != GGUF_MAGIC:
            raise ValueError("Not a valid GGUF file")

        offset = 4
        version, offset = read_u32(data, offset)

        tensor_count, offset = read_u64(data, offset)
        metadata_kv_count, offset = read_u64(data, offset)

        info = {
            "version": version,
            "tensor_count": tensor_count,
            "metadata_kv_count": metadata_kv_count,
            "metadata": {},
            "tensor_infos": []
        }

        params_found = set()
        for _ in range(metadata_kv_count):
            try:
                key, offset = read_string(data, offset)
                value_type, offset = read_u32(data, offset)
                value, offset = read_value(data, offset, value_type)
            except UnicodeError as e:
                print(f"Error reading metadata: {e}")
                value = None
            info["metadata"][key] = value

            if params and key in params:
                params_found.add(key)

        for _ in range(tensor_count):
            try:
                name, offset = read_string(data, offset)
                n_dims, offset = read_u32(data, offset)
                shape = []
                for _ in range(n_dims):
                    dim, offset = read_u64(data, offset)
                    shape.append(dim)
                dtype, offset = read_u32(data, offset)
                offset_tensor, offset = read_u64(data, offset)

                tensor_info = {
                    "name": name,
                    "shape": shape,
                    "dtype": dtype,
                    "offset": offset_tensor
                }
                info["tensor_infos"].append(tensor_info)

            except UnicodeError as e:
                print(f"Error reading metadata: {e}")
                name = None

            if params and name in params:
                params_found.add(name)

        if params:
            filtered_info = {"metadata": {}, "tensor_infos": []}
            for key, value in info["metadata"].items():
                if key in params:
                    filtered_info["metadata"][key] = value
            for tensor in info["tensor_infos"]:
                if tensor["name"] in params:
                    filtered_info["tensor_infos"].append(tensor)
            return filtered_info

        return info
