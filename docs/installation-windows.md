[![](https://dcbadge.limes.pink/api/server/https://discord.gg/BEMVTmcPEs)](https://discord.gg/https://discord.gg/BEMVTmcPEs)

# Simplified Pulsar AI Setup Guide for Windows (NVIDIA and AMD)

This guide will help you set up Pulsar AI on Windows with either NVIDIA or AMD GPUs. We'll use some automated scripts to simplify the process.

## Prerequisites

- Windows 10 64-bit: Pro, Enterprise, or Education (Build 16299 or later)
- A compatible NVIDIA GPU (with CUDA 12.1+ support) or AMD GPU (with ROCm 6.1+ support)
- At least 8GB of RAM (16GB or more recommended)
- At least 50GB of free disk space
- Internet connection
- Hyper-V and Containers Windows features enabled

## 1. GPU Driver Installation

### For NVIDIA GPUs:
1. Visit the [NVIDIA Driver Downloads](https://developer.nvidia.com/cuda-12-1-0-download-archive) page.
2. Select your GPU model and download the latest driver.
3. Run the installer and follow the on-screen instructions.
4. Restart your computer after installation.

### For AMD GPUs:
1. Visit the [AMD Drivers and Support](https://rocm.docs.amd.com/projects/install-on-windows/en/docs-6.1.0/) page.
2. Select your GPU model and download the latest driver.
3. Run the installer and follow the on-screen instructions.
4. Restart your computer after installation.

## 2. Installing Docker Desktop

1. Download [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop).
2. Run the installer and follow the on-screen instructions.
3. During installation, ensure "Use WSL 2 instead of Hyper-V" is selected if prompted.
4. After installation, restart your computer.
5. Start Docker Desktop and wait for it to finish starting up.

## 3. Setting Up Pulsar Server

We'll use a PowerShell script to automate most of the setup process. 

1. Open PowerShell as an administrator.

2. Copy and paste the following script into your PowerShell window:

```powershell
# Function to detect GPU type
function Detect-GPUType {
    $gpuInfo = Get-WmiObject Win32_VideoController | Where-Object { $_.AdapterCompatibility -match "NVIDIA|Advanced Micro Devices" }
    if ($gpuInfo.AdapterCompatibility -match "NVIDIA") {
        return "nvidia"
    } elseif ($gpuInfo.AdapterCompatibility -match "Advanced Micro Devices") {
        return "amd"
    } else {
        Write-Host "No compatible NVIDIA or AMD GPU detected. Exiting."
        exit 1
    }
}

# Detect GPU type
$gpuType = Detect-GPUType

# Set environment variables based on GPU type
$env:DOCKER_IMAGE = if ($gpuType -eq "nvidia") { "marcoastramind/pulsar-nvidia" } else { "marcoastramind/pulsar-amd" }
$env:GPU_RUNTIME = $gpuType

# Create necessary directories
$pulsarDir = "$env:USERPROFILE\pulsar"
$hfCacheDir = "$env:USERPROFILE\.cache\huggingface"
$dirs = @(
    "$pulsarDir\configs",
    "$pulsarDir\static",
    "$pulsarDir\db_revision",
    $hfCacheDir
)
foreach ($dir in $dirs) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "Created directory: $dir"
    } else {
        Write-Host "Directory already exists: $dir"
    }
}
Set-Location -Path $pulsarDir

# Create .env file
$envFile = "$pulsarDir\.env"
if (!(Test-Path $envFile)) {
    $securePassword = Read-Host "Enter a secure password for the database" -AsSecureString
    $password = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword))
    $primaryUse = Read-Host "Enter your expected use type (1:general, 2:roleplay, 3:roleplay 18+)"
    $hfToken = Read-Host "Enter your HuggingFace token (press Enter to skip)"
    $shouldSendTokenOnline = Read-Host "Allow sending your read token to your online profile? This is mandatory for adding private and gated models/loras (y/n)"
    $ngrokToken = Read-Host "Enter your Ngrok token (press Enter to skip)"
    $isAdultContent = if ($primaryUse -eq "3") { "true" } else { "false" }
    $shouldSendOnline = if ($shouldSendTokenOnline -ieq "y") {"true"} else {"false"}
    $primaryUseText = switch ($primaryUse) {
        "1" { "general" }
        "2" { "roleplay" }
        "3" { "roleplay" }
        default { "general" }
    }

    $envContent = @"
PULSAR_DB_PASSWORD=$password
PULSAR_HF_TOKEN=$hfToken
PULSAR_SHOULD_SEND_PRIVATE_TOKEN=$shouldSendOnline
PULSAR_NGROK_TOKEN=$ngrokToken
PULSAR_DB_USER=astramind
POSTGRES_DB_NAME=pulsar
PULSAR_DB_NAME=postgres:5432/pulsar
PRIMARY_USE=$primaryUseText
IS_ADULT_CONTENT=$isAdultContent
DOCKER_IMAGE=$env:DOCKER_IMAGE
GPU_RUNTIME=$env:GPU_RUNTIME
GPU_DEVICES=
GPU_GROUPS=
"@
    $envContent | Out-File -FilePath $envFile -Encoding utf8
    Write-Host "Created .env file: $envFile"
} else {
    Write-Host ".env file already exists: $envFile"
}

# Create docker-compose.yml file
$composeFile = "$pulsarDir\docker-compose.yml"
$composeContent = @"
version: '3'
services:
  postgres:
    ports:
      - "5432:5432"
    image: postgres:latest
    environment:
      POSTGRES_DB: `${PULSAR_DB_NAME}
      POSTGRES_USER: `${PULSAR_DB_USER}
      POSTGRES_PASSWORD: `${PULSAR_DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init-db.sql:/docker-entrypoint-initdb.d/init-db.sql
    healthcheck:
      test: [ "CMD-SHELL", "pg_isready -U astramind -d pulsar" ]
      interval: 10s
      timeout: 5s
      retries: 5
  pulsar:
    ports:
      - "40000:40000"
    image: `${DOCKER_IMAGE}
    volumes:
      - `${USERPROFILE}\pulsar\configs:/home/user/Pulsar/configs:rw
      - `${USERPROFILE}\pulsar\static:/home/user/Pulsar/static/item_images:rw
      - `${USERPROFILE}\pulsar\.env:/home/user/Pulsar/.env:rw
      - `${USERPROFILE}\.cache\huggingface:/home/user/.cache/huggingface:rw
      - `${USERPROFILE}\pulsar\db_revision:/home/user/Pulsar/app/db/migration/alembic_/versions:rw
    depends_on:
      postgres:
        condition: service_healthy
    deploy:
      resources:
        reservations:
          devices:
            - driver: `${GPU_RUNTIME}
              count: all
              capabilities: [gpu]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:40000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s          
"@

if ($gpuType -eq "amd") {
    $composeContent += @"

    devices:
      - /dev/kfd
      - /dev/dri
    group_add:
      - video
"@
}

$composeContent += @"

volumes:
  pgdata:
"@

$composeContent | Out-File -FilePath $composeFile -Encoding utf8
Write-Host "Created docker-compose.yml file: $composeFile"

# Create init-db.sql file
$initDbFile = "$pulsarDir\init-db.sql"
$initDbContent = @"
-- Create user if not exists
DO
$$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'astramind') THEN
    CREATE USER astramind WITH PASSWORD '`${PULSAR_DB_PASSWORD}';
  END IF;
END
$$;
-- Create database if not exists
SELECT 'CREATE DATABASE pulsar'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'pulsar');
-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE pulsar TO astramind;
"@
$initDbContent | Out-File -FilePath $initDbFile -Encoding utf8
Write-Host "Created init-db.sql file: $initDbFile"

Write-Host "Setup complete. To start Pulsar AI, run 'docker-compose up -d' in the $pulsarDir directory."
```

3. The script will prompt you for a database password, HuggingFace token, and Ngrok token. Enter these when prompted.

4. After the script completes, it will have created all necessary files and directories.

## 5. Installing Pulsar UI 

Install [this](https://github.com/astramind-ai/PulsarUIReleases/releases/download/v0.1.0/Pulsar.Setup.0.1.0.exe) and folow the instruction to complete the installation

## 4. Running Pulsar AI

1. Ensure Docker Desktop is running and GPU support is enabled:
   - Open Docker Desktop
   - Go to Settings > General
   - Make sure "Use GPU for compute" is checked (for NVIDIA GPUs)

2. In PowerShell, navigate to the Pulsar directory:
   ```powershell
   cd $env:USERPROFILE\pulsar
   ```

3. Start Pulsar AI:
   ```powershell
   docker-compose up -d
   ```

4. Check the logs to ensure everything is running correctly:
   ```powershell
   docker-compose logs -f
   ```
   
5. Start the Pulsar UI ans finish the setup to bind your account to your server, or just use it locally.


## Troubleshooting

- If you encounter issues with GPU access, ensure your GPU drivers are correctly installed and that Docker has the necessary permissions.
- For AMD GPUs, make sure the ROCm for Windows package is properly installed and configured.
- If the containers fail to start, check the Docker logs for error messages:
  ```powershell
  docker-compose logs
  ```
- Ensure all environment variables in the `.env` file are correctly set.
- If you're having network issues, try restarting Docker Desktop.

For additional support, visit the [Pulsar AI GitHub repository](https://github.com/astramind-ai/Pulsar/issues) or join our [Discord community](https://discord.gg/BEMVTmcPEs).
