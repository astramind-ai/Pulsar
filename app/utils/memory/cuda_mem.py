import torch
import torch.cuda


def get_free_cuda_memory():
    cuda_device = torch.cuda.current_device()
    free_memory, _ = torch.cuda.mem_get_info(cuda_device)
    return free_memory


def get_used_cuda_memory():
    cuda_device = torch.cuda.current_device()
    free_memory, total_memory = torch.cuda.mem_get_info(cuda_device)
    used_memory = total_memory - free_memory
    return used_memory


def get_total_cuda_memory():
    cuda_device = torch.cuda.current_device()
    _, total_memory = torch.cuda.mem_get_info(cuda_device)
    return total_memory
