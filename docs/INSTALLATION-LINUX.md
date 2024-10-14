[![](https://dcbadge.limes.pink/api/server/https://discord.gg/BEMVTmcPEs)](https://discord.gg/https://discord.gg/BEMVTmcPEs)

# Pulsar AI: Detailed Installation Guide

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Docker Compose Installation (Recommended)](#docker-compose-installation-recommended)
3. [Manual Installation](#manual-installation)
   - [3.1 GPU Drivers](#31-gpu-drivers)
   - [3.2 Python Environment](#32-python-environment)
   - [3.3 PostgreSQL](#33-postgresql)
   - [3.4 Pulsar AI](#34-pulsar-ai)
4. [Configuration](#configuration)
5. [Troubleshooting](#troubleshooting)

## 1. Prerequisites

Before installing Pulsar AI, ensure your system meets the following requirements:

- A compatible NVIDIA GPU (with CUDA 12.1+) or AMD GPU (with ROCm 6.1+)
- Ubuntu 20.04 or later (other Linux distributions may work but are not officially supported)
- At least 8GB of RAM (16GB or more recommended)
- At least 50GB of free disk space
- Internet connection for downloading dependencies and models

## 2. Docker Compose Installation (Recommended)

This method is the easiest and most consistent way to install Pulsar AI.

1. Install Docker and Docker Compose:
   ```bash
   sudo apt-get update
   sudo apt-get install docker.io docker-compose
   ```

2. Add your user to the docker group:
   ```bash
   sudo usermod -aG docker $USER
   ```
   Log out and log back in for this change to take effect.

3. Download the Pulsar AI installer script:
   ```bash
   wget https://raw.githubusercontent.com/astramind-ai/Pulsar/refs/heads/main/installer/installer.sh
   ```

4. Make the script executable:
   ```bash
   chmod +x installer.sh
   ```

5. Run the installer script:
   ```bash
   ./installer.sh
   ```

6. Follow the prompts in the installer. It will:
   - Check for a compatible GPU
   - Install Docker and Docker Compose if needed
   - Set up the necessary Docker Compose configuration
   - Create and configure the .env file
   - Start the Pulsar AI services

7. Once the installation is complete, Pulsar AI should be accessible at `http://localhost:40000`.

## 3. Manual Installation

This guide will walk you through the process of setting up Pulsar AI manually, including cloning the GitHub repository, setting up dependencies, configuring PostgreSQL, and more.

### Prerequisites

- A Linux system (Ubuntu 20.04 or later recommended)
- Git installed
- Conda or Miniconda installed
- NVIDIA GPU with CUDA support or AMD GPU with ROCm support

### 3.1: Clone the GitHub Repository

1. Open a terminal and clone the repository:

```bash
git clone https://github.com/astramind-ai/pulsar.git ~/pulsar
cd ~/pulsar
```

### 3.2 GPU Drivers

#### For NVIDIA GPUs:
1. Follow the official NVIDIA CUDA 12.1+ installation guide: [CUDA Installation Guide](https://developer.nvidia.com/cuda-12-1-0-download-archive)

4. Verify the installation:
   ```bash
   nvidia-smi
   ```

#### For AMD GPUs:
1. Follow the official ROCm 6.1+ installation guide: [ROCm Installation Guide](https://rocm.docs.amd.com/projects/install-on-linux/en/docs-6.1.2/tutorial/install-overview.html)

2. Verify the installation:
   ```bash
   rocm-smi
   ```

### 3.3 Python Environment

1. Install Miniconda:
   ```bash
   wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
   bash Miniconda3-latest-Linux-x86_64.sh
   ```
   Follow the prompts to complete the installation.

2. Create a new conda environment:
   ```bash
   conda create -n pulsar python=3.10
   conda activate pulsar
   ```

## 3.4: Set Up the Conda Environment

1. Create a new Conda environment:

```bash
conda create -n pulsar python=3.10
conda activate pulsar
```

2. Install PyTorch with GPU support:

For NVIDIA GPUs:
```bash
conda install pytorch torchvision torchaudio pytorch-cuda=12.1 -c pytorch -c nvidia
```

For AMD GPUs:
```bash
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.1
```

3. Install other dependencies:

```bash
pip install -r requirements.txt
```

## Step 3: Set Up PostgreSQL

1. Install PostgreSQL:

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
```

2. Start the PostgreSQL service:

```bash
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

3. Create a new PostgreSQL user and database:

```bash
sudo -u postgres psql
```

In the PostgreSQL prompt, run:

```sql
CREATE USER astramind WITH PASSWORD 'your_password_here';
CREATE DATABASE pulsar;
GRANT ALL PRIVILEGES ON DATABASE pulsar TO astramind;
\q
```

## Step 4: Configure Pulsar

1. Create a `.env` file in the pulsar directory:

```bash
touch ~/pulsar/.env
```

2. Open the `.env` file in a text editor and add the following content:

```
PULSAR_DB_PASSWORD=your_password_here
PULSAR_HF_TOKEN=your_huggingface_token_here
PULSAR_SHOULD_SEND_PRIVATE_TOKEN=false
PULSAR_NGROK_TOKEN=your_ngrok_token_here
PULSAR_DB_USER=astramind
PULSAR_DB_NAME=localhost:5432/pulsar
PRIMARY_USE=general
IS_ADULT_CONTENT=false
```

Replace your_secure_password with the password you set for the PostgreSQL user in Step 3.

Now, let's discuss the importance of each of these settings:

- PULSAR_HF_TOKEN (HuggingFace Token):
   This token is crucial for accessing HuggingFace's model repository. Without it, you won't be able to download and use many of the AI models that power Pulsar's functionality. To get your token:

   Go to HuggingFace and create an account if you don't have one.
   Navigate to your profile settings and find the "Access Tokens" section.
   Create a new token and copy it into your .env file.

   Setting this token allows Pulsar to access a wide range of powerful AI models, significantly enhancing its capabilities.
- PULSAR_SHOULD_SEND_PRIVATE_TOKEN:
   Setting this to true is highly recommended. It allows Pulsar to use your HuggingFace token to access private or gated models. This can unlock advanced features and improve Pulsar's performance. While you can set it to false for privacy reasons, doing so may limit Pulsar's functionality.
- PULSAR_NGROK_TOKEN (Ngrok Token):
   Ngrok is a tool that creates secure tunnels to localhost, allowing you to expose Pulsar to the internet securely. This is particularly useful if you want to access Pulsar remotely or collaborate with others. To get your Ngrok token:

   Sign up for an account at Ngrok.
   In your dashboard, you'll find your authtoken. Copy this into your .env file.

   While not strictly necessary for local use, setting up Ngrok can greatly enhance Pulsar's accessibility and usefulness.

## Step 5: Set Up the Database

1. Run the database migrations:

```bash
alembic upgrade head
```

## Step 6: Start Pulsar

1. Start the Pulsar server:

```bash
python main.py
```


## Step 7: Create a Desktop Entry (Optional)

1. Create a desktop entry file:

```bash
sudo nano /usr/share/applications/pulsar.desktop
```

2. Add the following content:

```
[Desktop Entry]
Name=Pulsar
Exec=bash -c "cd ~/pulsar && conda activate pulsar && python main.py"
Icon=~/pulsar/pulsar_icon.png
Type=Application
Categories=Utility;
```

3. Download the Pulsar icon:

```bash
wget -O ~/pulsar/pulsar_icon.png "https://github.com/user-attachments/assets/0ea3636b-53b3-4d8b-9749-8a5c42921cf5"
```

## Conclusion

You have now manually set up Pulsar AI on your system. You can start Pulsar by running `python main.py` in the Pulsar directory, or by using the desktop entry if you created one. Remember to activate the Conda environment (`conda activate pulsar`) before running Pulsar.

For any updates or changes to Pulsar, it will automatically pull the latest changes from the GitHub repository. You can also contribute to the project by submitting pull requests or opening issues on the GitHub page.

