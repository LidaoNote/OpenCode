#!/bin/bash

# Exit on any error
set -e

# Define variables
SERVICE_NAME="minichat"
INSTALL_DIR="/opt/miniChat"
PYTHON_VERSION="python3"
USER="minichat"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo "Starting miniChat installation..."

# Check if script is run as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root${NC}"
   exit 1
fi

# Update package lists
echo "Updating package lists..."
apt-get update

# Install required packages
echo "Installing required packages..."
apt-get install -y python3 python3-pip python3-venv nginx

# Create user for running the service
if ! id -u $USER >/dev/null 2>&1; then
    echo "Creating user ${USER}..."
    useradd -m -s /bin/false $USER
fi

# Create installation directory
echo "Creating installation directory ${INSTALL_DIR}..."
mkdir -p $INSTALL_DIR
chown $USER:$USER $INSTALL_DIR

# Copy files to installation directory
echo "Copying application files..."
cp server.py $INSTALL_DIR/
cp index.html $INSTALL_DIR/
chown -R $USER:$USER $INSTALL_DIR

# Create virtual environment and install dependencies
echo "Setting up Python virtual environment..."
su - $USER -s /bin/bash -c "
    cd $INSTALL_DIR
    $PYTHON_VERSION -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install aiohttp aiohttp-jinja2 jinja2
"

# Create systemd service file
echo "Creating systemd service file..."
cat > $SERVICE_FILE << EOF
[Unit]
Description=miniChat WebSocket Chat Service
After=network.target

[Service]
User=$USER
Group=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Set proper permissions for service file
chmod 644 $SERVICE_FILE

# Reload systemd and enable service
echo "Configuring systemd service..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME

# Check service status
echo "Checking service status..."
if systemctl is-active --quiet $SERVICE_NAME; then
    echo -e "${GREEN}miniChat service installed and running successfully!${NC}"
else
    echo -e "${RED}Failed to start miniChat service. Check logs with: journalctl -u ${SERVICE_NAME}.service${NC}"
    exit 1
fi

echo "Installation complete!"
echo "Next steps:"
echo "1. Configure Nginx as reverse proxy (see README.md for configuration)"
echo "2. Access the chat at http://<your-server-ip>:8080"
echo "3. Monitor the service with: systemctl status ${SERVICE_NAME}"
echo "4. View logs with: journalctl -u ${SERVICE_NAME}.service"