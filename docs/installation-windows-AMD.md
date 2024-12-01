[![](https://dcbadge.limes.pink/api/server/https://discord.gg/BEMVTmcPEs)](https://discord.gg/https://discord.gg/BEMVTmcPEs)

# Pulsar AI Setup Guide for Windows (AMD GPUs)

This guide will help you set up Pulsar AI on Windows with AMD GPUs. We'll use some automated scripts to simplify the process.

## Prerequisites

- Windows 10 64-bit: Pro, Enterprise, or Education (Build 16299 or later)
- A compatible AMD GPU (with ROCm 6.1+ support)
- At least 8GB of RAM (16GB or more recommended)
- At least 50GB of free disk space
- Internet connection
- Hyper-V and Containers Windows features enabled

# Pulsar AI Installation Guide for Windows (AMD GPUs)

## Prerequisites
- Windows 10/11 64-bit (Build 16299 or later)
- Compatible AMD GPU with ROCm 6.1+ support
- At least 8GB RAM (16GB recommended)
- At least 50GB free disk space
- Internet connection

## Installation Steps

### 1. Install Windows Subsystem for Linux (WSL)
1. Open PowerShell as Administrator and run:
   ```powershell
   wsl --install
   ```
2. Restart your computer when prompted
3. After restart, open Microsoft Store and install Ubuntu 22.04 LTS  [Guide](https://learn.microsoft.com/en-us/windows/wsl/install)
   > **Important**: Specifically use Ubuntu 22.04, as newer versions may cause compatibility issues

### 2. Install ROCm Drivers in WSL
1. Open Ubuntu 22.04 from the Start menu
2. Run the following commands:
   ```bash
   sudo apt update
   wget https://repo.radeon.com/amdgpu-install/6.1.3/ubuntu/jammy/amdgpu-install_6.1.60103-1_all.deb
   sudo apt install ./amdgpu-install_6.1.60103-1_all.deb
   sudo amdgpu-install -y --usecase=wsl,rocm --no-dkms
   ```
3. Verify the ROCm installation:
   ```bash
   rocm-smi
   ```

### 3. Install Docker Desktop
1. Download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. During installation, ensure the "Use WSL 2 instead of Hyper-V" option is selected
3. After installation, open Docker Desktop
4. Go to Settings > Resources > WSL Integration
5. Enable integration with Ubuntu-22.04
6. Click "Apply & Restart"

### 4. Follow Linux Installation Steps
Now that WSL and Docker are set up, you can follow the Linux installation method [linux-installer](https://github.com/astramind-ai/Pulsar/blob/main/docs/installation-linux.md):

1. Open Ubuntu 22.04
2. Download the Pulsar AI installer script:
   ```bash
   wget https://raw.githubusercontent.com/astramind-ai/Pulsar/refs/heads/main/installer/installer.sh
   chmod +x installer.sh
   ./installer.sh
   ```
3. Follow the installer prompts to complete the setup

4. Once installation is complete, you can access Pulsar AI at `http://localhost:40000` through your Windows web browser.

## Alternative: Beta UI Installation
If you prefer a more automated approach, you can use the beta Windows installer:

1. Download the [Pulsar Windows Installer (beta)](https://github.com/astramind-ai/Pulsar/releases/download/v0.2.1/WindowsPulsarServerInstaller.exe)
2. Run the installer and follow the prompts
3. Once complete, you'll find Pulsar Server and Pulsar UI desktop applications
4. Launch Pulsar Server first, then launch Pulsar UI

## Troubleshooting
If you encounter issues:
1. Restart your computer
2. Verify GPU drivers are properly installed
3. Check Docker Desktop is running and WSL integration is enabled
4. For additional help, visit:
   - [Pulsar AI GitHub Issues](https://github.com/astramind-ai/Pulsar/issues)
   - [Discord Community](https://discord.gg/BEMVTmcPEs)