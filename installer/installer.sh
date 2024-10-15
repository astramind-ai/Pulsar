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

# Display license terms and require acceptance
function display_license {
    echo -e "\e[1;36mPulsar App Terms and Conditions\e[0m"
    echo -e "\n\e[1;33mAcceptance of Terms\e[0m"
    echo "By downloading, installing, or using this AI application, you agree to be bound by these terms and conditions."

    echo -e "\n\e[1;33mUse of AI Technology\e[0m"
    echo "This app utilizes Large Language Model (LLM) technology for local AI interactions."
    echo "You understand that the AI's responses are generated based on patterns in training data and may not always be accurate or appropriate."

    echo -e "\n\e[1;33mUser Responsibilities\e[0m"
    echo "You agree to use the app responsibly and not for any illegal or harmful purposes."
    echo "You are responsible for the content you input and the actions you take based on the AI's output."

    echo -e "\n\e[1;33mIntellectual Property\e[0m"
    echo "The app, including its software, design, and AI model, is protected by intellectual property laws."
    echo "You may not copy, modify, distribute, sell, or lease any part of our services or included software."

    echo -e "\n\e[1;33mData Usage and Privacy\e[0m"
    echo "While the app processes data locally, certain anonymous usage statistics may be collected."
    echo "Please refer to our Privacy Policy for more information on data handling practices."

    echo -e "\n\e[1;33mDisclaimer of Warranties\e[0m"
    echo 'The app is provided "as is" without any warranties, express or implied.'
    echo "We do not guarantee that the app will be error-free or uninterrupted."

    echo -e "\n\e[1;33mLimitation of Liability\e[0m"
    echo "We shall not be liable for any indirect, incidental, special, consequential, or punitive damages resulting from your use of or inability to use the app."

    echo -e "\n\e[1;33mUpdates and Modifications\e[0m"
    echo "We reserve the right to modify, update, or discontinue the app at any time without notice."

    echo -e "\n\e[1;33mAge Restriction\e[0m"
    echo "You must be at least 13 years old to use this app."
    echo "If you are under 18, you must have parental consent."

    echo -e "\n\e[1;33mGoverning Law\e[0m"
    echo "These terms shall be governed by and construed in accordance with the laws of Italy, without regard to its conflict of law provisions."

    echo -e "\n\e[1;31mTo proceed with the installation, please type 'accept' to agree to the terms and conditions above.\e[0m"
    read -p "Type 'accept' to continue: " user_acceptance
    if [ "$user_acceptance" != "accept" ]; then
        error_exit "You must accept the terms and conditions to proceed."
    fi
}

# Display the license and require acceptance
display_license

# Determine the package manager and distribution
if command -v apt-get &> /dev/null; then
    PKG_MANAGER="apt-get"
    PKG_UPDATE="$PKG_MANAGER update"
    PKG_INSTALL="$PKG_MANAGER install -y"
    DISTRO="debian"
    OS_VERSION=$(lsb_release -cs)
elif command -v dnf &> /dev/null; then
    PKG_MANAGER="dnf"
    PKG_UPDATE="$PKG_MANAGER check-update"
    PKG_INSTALL="$PKG_MANAGER install -y"
    DISTRO="fedora"
    OS_VERSION=$(rpm -E %fedora)
elif command -v yum &> /dev/null; then
    PKG_MANAGER="yum"
    PKG_UPDATE="$PKG_MANAGER check-update"
    PKG_INSTALL="$PKG_MANAGER install -y"
    DISTRO="centos"
    OS_VERSION=$(rpm -E %centos)
elif command -v pacman &> /dev/null; then
    PKG_MANAGER="pacman"
    PKG_UPDATE="$PKG_MANAGER -Sy"
    PKG_INSTALL="$PKG_MANAGER -S --noconfirm"
    DISTRO="arch"
    OS_VERSION=""
else
    error_exit "No supported package manager found. Manual installation required."
fi

# Install lspci if not installed
if ! command -v lspci &> /dev/null; then
    echo -e "\e[1;34mInstalling lspci...\e[0m"
    $PKG_INSTALL pciutils || error_exit "Failed to install pciutils."
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

# Check for GPU using lspci
echo -e "\e[1;36mChecking for GPU...\e[0m"
GPU_VENDOR=""
if lspci | grep -i 'NVIDIA' &> /dev/null; then
    GPU_VENDOR="NVIDIA"
    GPU_INFO=$(lspci | grep -i 'VGA' | grep -i 'NVIDIA')
    echo -e "\e[1;32mNVIDIA GPU detected: $GPU_INFO\e[0m"
elif lspci | grep -i 'AMD/ATI' &> /dev/null; then
    GPU_VENDOR="AMD"
    GPU_INFO=$(lspci | grep -i 'VGA' | grep -i 'AMD\|ATI')
    echo -e "\e[1;32mAMD GPU detected: $GPU_INFO\e[0m"
else
    error_exit "No supported GPU detected. Pulsar requires an NVIDIA or AMD GPU."
fi

# Check for GPU drivers
if [ "$GPU_VENDOR" == "NVIDIA" ]; then
    if command -v nvidia-smi &> /dev/null; then
        echo -e "\e[1;32mNVIDIA drivers are installed.\e[0m"
    else
        error_exit "\e[1;33mNVIDIA drivers are not installed. Please install them and verify the installation with nvidia-smi\e[0m"
    fi
elif [ "$GPU_VENDOR" == "AMD" ]; then
    if command -v rocm-smi &> /dev/null; then
        echo -e "\e[1;32mAMD ROCm drivers are installed.\e[0m"
    else
        error_exit "\e[1;33mAMD ROCm drivers are not installed. Please install them and verify the installation with rocm-smi\e[0m"
    fi
fi

# Set Docker image and GPU config based on GPU vendor
if [ "$GPU_VENDOR" == "NVIDIA" ]; then
    DOCKER_IMAGE="marcoastramind/pulsar-nvidia:latest"
    GPU_RUNTIME="nvidia"
    GPU_CONFIG=""
elif [ "$GPU_VENDOR" == "AMD" ]; then
    DOCKER_IMAGE="marcoastramind/pulsar-amd:latest"
    GPU_RUNTIME="rocm"
    GPU_CONFIG="    devices:
      - /dev/kfd
      - /dev/dri
    group_add:
      - video"
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

    # Install prerequisites
    if [ "$DISTRO" == "debian" ]; then
        apt-get update || error_exit "Error updating packages."
        apt-get install -y apt-transport-https ca-certificates curl gnupg-agent software-properties-common || error_exit "Error installing prerequisites."
        curl -fsSL https://download.docker.com/linux/$(. /etc/os-release; echo "$ID")/gpg | apt-key add - || error_exit "Error adding Docker GPG key."
        add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/$(. /etc/os-release; echo "$ID") $(lsb_release -cs) stable" || error_exit "Error adding Docker repository."
        apt-get update || error_exit "Error updating packages."
        apt-get install -y docker-ce docker-ce-cli containerd.io || error_exit "Error installing Docker."
    elif [ "$DISTRO" == "fedora" ] || [ "$DISTRO" == "centos" ]; then
        $PKG_INSTALL yum-utils device-mapper-persistent-data lvm2 || error_exit "Error installing prerequisites."
        yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo || error_exit "Error adding Docker repository."
        $PKG_INSTALL docker-ce docker-ce-cli containerd.io || error_exit "Error installing Docker."
    elif [ "$DISTRO" == "arch" ]; then
        $PKG_INSTALL docker || error_exit "Error installing Docker."
    else
        error_exit "Unsupported distribution for automatic Docker installation."
    fi

    # Start Docker service
    systemctl enable docker || error_exit "Error enabling Docker service."
    systemctl start docker || error_exit "Error starting Docker service."

    # Install Docker Compose
    COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep -Po '"tag_name": "\K.*\d')
    curl -L "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose || error_exit "Error downloading Docker Compose."
    chmod +x /usr/local/bin/docker-compose

    # Verify installation
    docker --version || error_exit "Docker installation failed."
    docker-compose --version || error_exit "Docker Compose installation failed."

    # Add original user to docker group
    if [ -n "$ORIGINAL_USER" ]; then
        usermod -aG docker $ORIGINAL_USER
        echo -e "\e[1;32mUser $ORIGINAL_USER has been added to the docker group.\e[0m"
    else
        echo "Unable to determine original user. Make sure to run the script without sudo initially."
    fi

    echo -e "\e[1;33mPlease log out and log back in to apply group changes, then run this script again.\e[0m"
    exit 0
fi

# Create Pulsar directory structure
ORIGINAL_HOME=$(eval echo "~$ORIGINAL_USER")
PULSAR_DIR="${ORIGINAL_HOME}/pulsar"
mkdir -p "${PULSAR_DIR}/configs"
mkdir -p "${PULSAR_DIR}/db_revision/alembic_"
mkdir -p "${PULSAR_DIR}/static"

# Create Docker Compose file
cat << EOF > "${PULSAR_DIR}/docker-compose.yml"
version: '3.7'
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
      test: [ "CMD-SHELL", "pg_isready -U \${PULSAR_DB_USER} -d pulsar" ]
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
      - ./db_revision:/home/user/Pulsar/app/db/migration/alembic_/versions:rw
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
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '\${PULSAR_DB_USER}') THEN
    CREATE USER \${PULSAR_DB_USER} WITH PASSWORD '\${PULSAR_DB_PASSWORD}';
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
GRANT ALL PRIVILEGES ON DATABASE pulsar TO \${PULSAR_DB_USER};
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
echo -e "\e[1;33m\nPulsar requires a HuggingFace token for full functionality.\e[0m"
echo -e "\e[1;36mWhy do I need a HuggingFace token?\e[0m"
echo -e "\e[1;37mThe HuggingFace token allows Pulsar to download and use language models from HuggingFace's model repository. Without it, some features may be limited.\e[0m"
echo -e "\e[1;36mHow to get a HuggingFace token?\e[0m"
echo -e "\e[1;37mPlease create an account at \e[4mhttps://huggingface.co/\e[0m\e[1;37m and generate a token at \e[4mhttps://huggingface.co/settings/tokens\e[0m\n"

read -p "Enter your HuggingFace token (leave blank to skip): " hf_token

if [ -n "$hf_token" ]; then
    sed -i "s/^PULSAR_HF_TOKEN=.*/PULSAR_HF_TOKEN=$hf_token/" "$ENV_FILE"
    echo -e "\e[1;32mHuggingFace token has been set.\e[0m"

    echo -e "\e[1;36m\nWhy should I allow sending my HuggingFace token to Pulsar?\e[0m"
    echo -e "\e[1;37mAllowing Pulsar to send your HuggingFace token enables uploading of private or gated models that require authentication. This ensures can get the most out of the upload and create functionalities.\e[0m"
    echo -e "\e[1;37mIf you choose not to send the token you will still be able to access gated and private models from your server, you wouldn't be able to upload them since we need to check the model config to ensure compatibility\e[0m"
    read -p "Do you want to allow sending your token to our platform for access to private/gated models? (y/n): " send_token
    if [[ $send_token =~ ^[Yy]$ ]]; then
        sed -i "s/^PULSAR_SHOULD_SEND_PRIVATE_TOKEN=.*/PULSAR_SHOULD_SEND_PRIVATE_TOKEN=true/" "$ENV_FILE"
        echo -e "\e[1;32mToken sharing enabled for private/gated model access.\e[0m"
    else
        sed -i "s/^PULSAR_SHOULD_SEND_PRIVATE_TOKEN=.*/PULSAR_SHOULD_SEND_PRIVATE_TOKEN=false/" "$ENV_FILE"
        echo -e "\e[1;33mToken sharing disabled. You won't be able to upload private/gated models.\e[0m"
    fi
else
    echo -e "\e[1;33mNo HuggingFace token set. Some features may be limited.\e[0m"
fi

# Ngrok token setup
echo -e "\e[1;33m\nPulsar can use Ngrok for tunneling as a fallback option.\e[0m"
echo -e "\e[1;36mWhy do I need an Ngrok token?\e[0m"
echo -e "\e[1;37mNgrok allows Pulsar to securely expose a local server to the internet. This is useful if you want to access Pulsar remotely or share it with others.\e[0m"
echo -e "\e[1;36mHow to get an Ngrok token?\e[0m"
echo -e "\e[1;37mPlease create an account and get your authtoken at \e[4mhttps://dashboard.ngrok.com/get-started/your-authtoken\e[0m\n"

read -p "Enter your Ngrok authtoken (leave blank to skip): " ngrok_token

if [ -n "$ngrok_token" ]; then
    sed -i "s/^PULSAR_NGROK_TOKEN=.*/PULSAR_NGROK_TOKEN=$ngrok_token/" "$ENV_FILE"
    echo -e "\e[1;32mNgrok authtoken has been set.\e[0m"
else
    echo -e "\e[1;33mNo Ngrok authtoken set. Ngrok tunneling will not be available.\e[0m"
fi

# Create desktop entry
DESKTOP_ENTRY="/usr/share/applications/pulsar_server.desktop"
ICON_PATH="${PULSAR_DIR}/pulsar_icon.png"

# Download Pulsar icon
wget -O $ICON_PATH "https://raw.githubusercontent.com/astramind-ai/Pulsar/main/assets/pulsar_server_icon.png" || echo -e "\e[1;33mWarning: Unable to download Pulsar icon.\e[0m"

# Create a wrapper script for starting Pulsar
START_SCRIPT="${PULSAR_DIR}/start_pulsar.sh"
cat << EOF > "$START_SCRIPT"
#!/bin/bash
cd "${PULSAR_DIR}"
docker-compose pull
docker-compose up
exec bash
EOF
chmod +x "$START_SCRIPT"
chown $ORIGINAL_USER:$ORIGINAL_USER "$START_SCRIPT"

# Modify the desktop entry to use the wrapper script and Terminal=true
cat << EOF > $DESKTOP_ENTRY
[Desktop Entry]
Name=Pulsar Server
Exec=${START_SCRIPT}
Icon=$ICON_PATH
Type=Application
Categories=Utility;
Terminal=true
EOF

chmod +x $DESKTOP_ENTRY

# Download the latest Pulsar UI AppImage
echo -e "\e[1;34mDownloading the latest Pulsar UI AppImage...\e[0m"
LATEST_RELEASE_URL="https://api.github.com/repos/astramind-ai/PulsarUIReleases/releases/latest"
LATEST_APPIMAGE_URL=$(curl -s $LATEST_RELEASE_URL | grep "browser_download_url.*AppImage" | cut -d '"' -f 4)

if [ -z "$LATEST_APPIMAGE_URL" ]; then
    echo -e "\e[1;31mError: Unable to find the latest Pulsar UI AppImage.\e[0m"
else
    UI_APPIMAGE_PATH="${PULSAR_DIR}/PulsarUI.AppImage"
    wget -O "$UI_APPIMAGE_PATH" "$LATEST_APPIMAGE_URL" || echo -e "\e[1;33mWarning: Unable to download Pulsar UI AppImage.\e[0m"
    chmod +x "$UI_APPIMAGE_PATH"
    chown $ORIGINAL_USER:$ORIGINAL_USER "$UI_APPIMAGE_PATH"

    # Download Pulsar UI icon
    UI_ICON_PATH="${PULSAR_DIR}/pulsar_ui_icon.png"
    wget -O "$UI_ICON_PATH" "https://raw.githubusercontent.com/astramind-ai/Pulsar/main/assets/pulsar_UI_icon.png" || echo -e "\e[1;33mWarning: Unable to download Pulsar UI icon.\e[0m"
    chown $ORIGINAL_USER:$ORIGINAL_USER "$UI_ICON_PATH"

    # Create desktop entry for Pulsar UI
    UI_DESKTOP_ENTRY="/usr/share/applications/pulsar_ui.desktop"
    cat << EOF > $UI_DESKTOP_ENTRY
[Desktop Entry]
Name=Pulsar UI
Exec=${UI_APPIMAGE_PATH}
Icon=$UI_ICON_PATH
Type=Application
Categories=Utility;
Terminal=false
EOF

    chmod +x $UI_DESKTOP_ENTRY
    echo -e "\e[1;32mPulsar UI installed and desktop entry created.\e[0m"
fi

# Set up auto-update for Docker images
UPDATE_SCRIPT="${PULSAR_DIR}/update_pulsar.sh"

cat << EOF > $UPDATE_SCRIPT
#!/bin/bash
cd ${PULSAR_DIR}
docker-compose pull
docker-compose up -d
EOF

chmod +x $UPDATE_SCRIPT
chown $ORIGINAL_USER:$ORIGINAL_USER "$UPDATE_SCRIPT"

# Add a weekly cron job for updates
(crontab -l -u $ORIGINAL_USER 2>/dev/null; echo "0 0 * * 0 $UPDATE_SCRIPT") | crontab -u $ORIGINAL_USER -

echo -e "\e[1;32m\nPulsar installation and setup complete!\e[0m"
echo -e "\e[1;32mYou can now launch Pulsar Server and Pulsar UI from your application menu\e[0m"
echo -e "\e[1;32mPulsar will auto-update weekly.\e[0m"


