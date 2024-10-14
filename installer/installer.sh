#!/bin/bash

# Save the original user before elevating privileges
echo "$(whoami)" > /tmp/pulsar_original_user

# Function to display error messages
function error_exit {
    echo -e "\e[31m$1\e[0m" 1>&2
    exit 1
}

# Function to request admin privileges
function request_admin_privileges {
    if command -v pkexec &> /dev/null; then
        echo "Requesting admin privileges via pkexec..."
        pkexec bash "$SCRIPT_PATH" "$@"
    elif command -v gksudo &> /dev/null; then
        echo "Requesting admin privileges via gksudo..."
        gksudo -- bash "$SCRIPT_PATH" "$@"
    elif command -v kdesudo &> /dev/null; then
        echo "Requesting admin privileges via kdesudo..."
        kdesudo -- bash "$SCRIPT_PATH" "$@"
    else
        echo "No graphical privilege elevation command found. Using sudo..."
        sudo bash "$SCRIPT_PATH" "$@"
    fi
}

# Get the absolute path of the script
SCRIPT_PATH=$(readlink -f "$0")

# Check if the script is run as root
if [ "$EUID" -ne 0 ]; then
    echo "This script requires admin privileges."
    request_admin_privileges "$@"
    exit $?
fi

# Read the original user from the temporary file
ORIGINAL_USER=$(cat /tmp/pulsar_original_user)
rm /tmp/pulsar_original_user  # Remove the temporary file

# Function to display colorful banner
function display_banner {
    echo -e "\e[1;34m"
    echo '
    ┌─────────────────────────────────────────────────┐
    │██████╗ ██╗   ██╗██╗     ███████╗ █████╗ ██████╗ │
    │██╔══██╗██║   ██║██║     ██╔════╝██╔══██╗██╔══██╗│
    │██████╔╝██║   ██║██║     ███████╗███████║██████╔╝│
    │██╔═══╝ ██║   ██║██║     ╚════██║██╔══██║██╔══██╗│
    │██║     ╚██████╔╝███████╗███████║██║  ██║██║  ██║│
    │╚═╝      ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝│
    └─────────────────────────────────────────────────┘
              Pulsar AI - Bringing AI to Life
    '
    echo -e "\e[0m"
}

# Display the banner
display_banner

# Determine the package manager and distribution
if command -v apt-get &> /dev/null; then
    PKG_MANAGER="apt-get"
    PKG_UPDATE="$PKG_MANAGER update"
    PKG_INSTALL="$PKG_MANAGER install -y"
    DOCKER_PKG="docker.io docker-compose"
    DISTRO="debian"
elif command -v dnf &> /dev/null; then
    PKG_MANAGER="dnf"
    PKG_UPDATE="$PKG_MANAGER check-update"
    PKG_INSTALL="$PKG_MANAGER install -y"
    DOCKER_PKG="docker docker-compose"
    DISTRO="fedora"
elif command -v yum &> /dev/null; then
    PKG_MANAGER="yum"
    PKG_UPDATE="$PKG_MANAGER check-update"
    PKG_INSTALL="$PKG_MANAGER install -y"
    DOCKER_PKG="docker docker-compose"
    DISTRO="centos"
elif command -v pacman &> /dev/null; then
    PKG_MANAGER="pacman"
    PKG_UPDATE="$PKG_MANAGER -Sy"
    PKG_INSTALL="$PKG_MANAGER -S --noconfirm"
    DOCKER_PKG="docker docker-compose"
    DISTRO="arch"
else
    error_exit "No supported package manager found. Manual installation required."
fi

# Ask user for intended use
echo -e "\e[1;33mWhat is your intended use for Pulsar?\e[0m"
echo "1) Roleplay"
echo "2) Roleplay +18"
echo "3) General use"
read -p "Enter your choice (1-3): " usage_choice

case $usage_choice in
    1) USAGE="roleplay" ;;
    2) USAGE="roleplay_18plus" ;;
    3) USAGE="general" ;;
    *) error_exit "Invalid choice. Exiting." ;;
esac

echo -e "\e[1;32mYou've selected: $USAGE\e[0m"

# Check for GPU and drivers
echo -e "\e[1;36mChecking for GPU...\e[0m"
if command -v nvidia-smi &> /dev/null; then
    GPU_TYPE="NVIDIA"
    GPU_INFO=$(nvidia-smi --query-gpu=gpu_name --format=csv,noheader)
    echo -e "\e[1;32mNVIDIA GPU detected: $GPU_INFO\e[0m"
    DOCKER_IMAGE="marcoastramind/pulsar-nvidia:latest"
    GPU_RUNTIME="nvidia"
    GPU_CONFIG=""
elif command -v rocm-smi &> /dev/null; then
    GPU_TYPE="AMD"
    GPU_INFO=$(rocm-smi --showproduct)
    echo -e "\e[1;32mAMD GPU detected: $GPU_INFO\e[0m"
    DOCKER_IMAGE="marcoastramind/pulsar-amd:latest"
    GPU_RUNTIME="rocm"
    GPU_CONFIG="    devices:
      - /dev/kfd
      - /dev/dri
    group_add:
      - video"
else
    error_exit "No supported GPU detected. Pulsar requires a compatible NVIDIA or AMD GPU."
fi

# Check RAM
TOTAL_RAM=$(free -g | awk '/^Mem:/{print $2}')
if [ $TOTAL_RAM -lt 8 ]; then
    error_exit "Insufficient RAM. Pulsar requires at least 8GB of RAM."
fi

echo -e "\e[1;32mRAM check passed: ${TOTAL_RAM}GB available\e[0m"

echo -e "\e[1;33mWarning: Pulsar will use all available resources by default.\e[0m"
echo -e "\e[1;33mIf you want to run other applications, launch them before starting Pulsar.\e[0m"

# Check if Docker and Docker Compose are installed
if command -v docker &> /dev/null && command -v docker-compose &> /dev/null; then
    echo -e "\e[1;32mDocker and Docker Compose are already installed.\e[0m"
else
    echo -e "\e[1;34mInstalling Docker and Docker Compose...\e[0m"

    # Check for containerd
    if command -v containerd &> /dev/null; then
        echo -e "\e[1;33mcontainerd detected. Skipping Docker installation.\e[0m"
    else
        $PKG_UPDATE || error_exit "Error updating packages."
        $PKG_INSTALL $DOCKER_PKG || error_exit "Error installing Docker and Docker Compose."
    fi

    # Install Docker Compose if not present
    if ! command -v docker-compose &> /dev/null; then
        echo -e "\e[1;34mInstalling Docker Compose...\e[0m"
        curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        chmod +x /usr/local/bin/docker-compose
    fi

    # Add original user to docker group
    if [ -n "$ORIGINAL_USER" ]; then
        usermod -aG docker $ORIGINAL_USER
        echo -e "\e[1;32mUser $ORIGINAL_USER has been added to the docker group. Please restart your PC to apply changes.\e[0m"
    else
        echo "Unable to determine original user. Make sure to run the script without sudo initially."
    fi

    # Start Docker service
    if command -v systemctl &> /dev/null; then
        systemctl start docker || echo "Warning: Unable to start Docker service. You may need to start it manually."
        systemctl enable docker || echo "Warning: Unable to enable Docker to start on boot. You may need to enable it manually."
    elif command -v service &> /dev/null; then
        service docker start || echo "Warning: Unable to start Docker service. You may need to start it manually."
    else
        echo "Warning: Unable to start Docker service. You may need to start it manually."
    fi

    echo -e "\e[1;32mDocker and Docker Compose setup complete.\e[0m"
    echo -e "\e[1;33mPlease log out and log back in to apply group changes, then run this script again.\e[0m"
    exit 0
fi


# Create Pulsar directory structure
ORIGINAL_HOME="/home/${ORIGINAL_USER}"
PULSAR_DIR="${ORIGINAL_HOME}/pulsar"
mkdir -p "${PULSAR_DIR}/configs"
mkdir -p "${PULSAR_DIR}/db_revison/alembic_"
mkdir -p "${PULSAR_DIR}/static"

# Create Docker Compose file
cat << EOF > "${PULSAR_DIR}/docker-compose.yml"
version: '3'
services:
  postgres:
    network_mode: host
    image: postgres:latest
    environment:
      POSTGRES_DB: pulsar
      POSTGRES_USER: \${PULSAR_DB_USER}
      POSTGRES_PASSWORD: \${PULSAR_DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init-db.sql:/docker-entrypoint-initdb.d/init-db.sql
    healthcheck:
      test: [ "CMD-SHELL", "pg_isready -U astramind -d pulsar" ]
      interval: 10s
      timeout: 5s
      retries: 5

  pulsar:
    image: ${DOCKER_IMAGE}
    network_mode: host
    volumes:
      - ./configs:/home/user/Pulsar/configs:rw
      - ./static:/home/user/Pulsar/static/item_images:rw
      - ./.env:/home/user/Pulsar/.env:rw
      - ${ORIGINAL_HOME}/.cache/huggingface:/home/user/.cache/huggingface:rw
      - ./db_revison:/home/user/Pulsar/app/db/migration/alembic_/versions:rw
    depends_on:
      postgres:
        condition: service_healthy
    deploy:
      resources:
        reservations:
          devices:
            - driver: ${GPU_RUNTIME}
              count: all
              capabilities: [gpu]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:40000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
${GPU_CONFIG}

volumes:
  pgdata:
EOF

# Create init-db.sql file
cat << EOF > "${PULSAR_DIR}/init-db.sql"
-- Create user if not exists
DO
\$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'astramind') THEN
    CREATE USER astramind WITH PASSWORD '${PULSAR_DB_PASSWORD}';
  END IF;
END
\$\$;

-- Create database if not exists
DO
\$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'pulsar') THEN
    CREATE DATABASE pulsar;
  END IF;
END
\$\$;

-- Grant privileges on the database
GRANT ALL PRIVILEGES ON DATABASE pulsar TO astramind;
EOF

# Create .env file
ENV_FILE="${PULSAR_DIR}/.env"

if [ ! -f "$ENV_FILE" ]; then
    cat << EOF > "$ENV_FILE"
PULSAR_DB_PASSWORD=$(openssl rand -base64 32)
PULSAR_DB_USER=astramind
PULSAR_DB_NAME=localhost:5432/pulsar
PULSAR_HF_TOKEN=
PULSAR_SHOULD_SEND_PRIVATE_TOKEN=false
PULSAR_NGROK_TOKEN=
EOF
    echo -e "\e[1;32mCreated new .env file at $ENV_FILE\e[0m"
else
    echo -e "\e[1;33mExisting .env file found at $ENV_FILE. Keeping existing values.\e[0m"
fi

case $USAGE in
    "roleplay")
        echo "PRIMARY_USE=roleplay" >> "$ENV_FILE"
        echo "IS_ADULT_CONTENT=false" >> "$ENV_FILE"
        ;;
    "roleplay_18plus")
        echo "PRIMARY_USE=roleplay" >> "$ENV_FILE"
        echo "IS_ADULT_CONTENT=true" >> "$ENV_FILE"
        ;;
    "general")
        echo "PRIMARY_USE=general" >> "$ENV_FILE"
        echo "IS_ADULT_CONTENT=false" >> "$ENV_FILE"
        ;;
esac

# Change ownership of the Pulsar directory to the original user
chown -R $ORIGINAL_USER:$ORIGINAL_USER "$PULSAR_DIR"

# HuggingFace token setup
echo -e "\e[1;33mPulsar requires a HuggingFace token for full functionality.\e[0m"
echo -e "\e[1;33mPlease create an account at https://huggingface.co/ and generate a token at https://huggingface.co/settings/tokens\e[0m"
read -p "Enter your HuggingFace token (leave blank to skip): " hf_token

if [ -n "$hf_token" ]; then
    sed -i "s/^PULSAR_HF_TOKEN=.*/PULSAR_HF_TOKEN=$hf_token/" "$ENV_FILE"
    echo -e "\e[1;32mHuggingFace token has been set.\e[0m"

    read -p "Do you want to allow sending your token to our platform for access to private/gated models? (y/n): " send_token
    if [[ $send_token =~ ^[Yy]$ ]]; then
        sed -i "s/^PULSAR_SHOULD_SEND_PRIVATE_TOKEN=.*/PULSAR_SHOULD_SEND_PRIVATE_TOKEN=true/" "$ENV_FILE"
        echo -e "\e[1;32mToken sharing enabled for private/gated model access.\e[0m"
    else
        sed -i "s/^PULSAR_SHOULD_SEND_PRIVATE_TOKEN=.*/PULSAR_SHOULD_SEND_PRIVATE_TOKEN=false/" "$ENV_FILE"
        echo -e "\e[1;33mToken sharing disabled. You won't be able to access private/gated models.\e[0m"
    fi
else
    echo -e "\e[1;33mNo HuggingFace token set. Some features may be limited.\e[0m"
fi

# Ngrok token setup
echo -e "\e[1;33mPulsar can use Ngrok for tunneling as a fallback option.\e[0m"
echo -e "\e[1;33mIf you want to set up Ngrok, please create an account and get your authtoken at https://dashboard.ngrok.com/get-started/your-authtoken\e[0m"
read -p "Enter your Ngrok authtoken (leave blank to skip): " ngrok_token

if [ -n "$ngrok_token" ]; then
    sed -i "s/^PULSAR_NGROK_TOKEN=.*/PULSAR_NGROK_TOKEN=$ngrok_token/" "$ENV_FILE"
    echo -e "\e[1;32mNgrok authtoken has been set.\e[0m"
else
    echo -e "\e[1;33mNo Ngrok authtoken set. Ngrok tunneling will not be available.\e[0m"
fi

# Create desktop entry
DESKTOP_ENTRY="/usr/share/applications/pulsar.desktop"
ICON_PATH="${PULSAR_DIR}/pulsar_icon.png"

# Download Pulsar icon
wget -O $ICON_PATH "https://github.com/user-attachments/assets/0ea3636b-53b3-4d8b-9749-8a5c42921cf5"

cat << EOF > $DESKTOP_ENTRY
[Desktop Entry]
Name=Pulsar
Exec=bash -c "cd ${PULSAR_DIR} && docker-compose up -d"
Icon=$ICON_PATH
Type=Application
Categories=Utility;
EOF

chmod +x $DESKTOP_ENTRY

# Set up auto-update for Docker images
UPDATE_SCRIPT="${PULSAR_DIR}/update_pulsar.sh"

cat << EOF > $UPDATE_SCRIPT
#!/bin/bash
cd ${PULSAR_DIR}
docker-compose pull
docker-compose up -d
EOF

chmod +x $UPDATE_SCRIPT

# Add a weekly cron job for updates
(crontab -l 2>/dev/null; echo "0 0 * * 0 $UPDATE_SCRIPT") | crontab -

echo -e "\e[1;32mPulsar installation and setup complete!\e[0m"
echo -e "\e[1;32mYou can now launch Pulsar from your application menu or run 'docker-compose up -d' in ${PULSAR_DIR}\e[0m"
echo -e "\e[1;32mPulsar will auto-update weekly.\e[0m"

# Start Pulsar
echo -e "\e[1;34mStarting Pulsar...\e[0m"
cd ${PULSAR_DIR} && docker-compose up -d

echo -e "\e[1;32mPulsar is now running!\e[0m"