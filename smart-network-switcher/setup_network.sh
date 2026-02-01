#!/bin/bash

# setup_network.sh
# Smart Network Switcher Setup Script
# Run as root: sudo ./setup_network.sh

# Ensure running as root
if [ "$EUID" -ne 0 ]; then
  echo "Error: Please run as root (sudo ./setup_network.sh)"
  exit 1
fi

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
CONFIG_FILE="$SCRIPT_DIR/config.json"
SERVICE_TEMPLATE="$SCRIPT_DIR/wifi-switcher.service"
SYSTEMD_SERVICE_PATH="/etc/systemd/system/wifi-switcher.service"

echo "=== Smart Network Switcher Setup ==="

# 1. Input Home WiFi Credentials
echo "Please enter your Home WiFi details (for station mode):"
read -p "SSID (Name): " SSID
read -s -p "Password: " PASS
echo ""

if [ -z "$SSID" ]; then
    echo "Error: SSID cannot be empty."
    exit 1
fi

# Save to config.json
cat > "$CONFIG_FILE" <<EOF
{
  "HOME_SSID": "$SSID",
  "HOME_PASS": "$PASS"
}
EOF
chmod 600 "$CONFIG_FILE"
echo "Configuration saved to $CONFIG_FILE"

# 2. Create Hotspot Profile (TennisPi_AP)
echo "----------------------------------------"
echo "Configuring Hotspot Profile (TennisPi_AP)..."

# Delete existing profile if it exists to ensure clean state
if nmcli connection show "TennisPi_AP" >/dev/null 2>&1; then
    echo "Removing existing TennisPi_AP profile..."
    nmcli connection delete TennisPi_AP
fi

# Create new AP profile
# IP: 10.42.0.1 (default for shared), Password: tennispi0611
echo "Creating new AP profile..."
nmcli connection add type wifi ifname wlan0 con-name TennisPi_AP autoconnect no ssid TennisPi_AP
nmcli connection modify TennisPi_AP 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared ipv4.addresses 10.42.0.1/24
nmcli connection modify TennisPi_AP wifi-sec.key-mgmt wpa-psk wifi-sec.psk tennispi0611

echo "Hotspot profile 'TennisPi_AP' created."

# 3. Install Systemd Service
echo "----------------------------------------"
echo "Installing Systemd Service..."

if [ ! -f "$SERVICE_TEMPLATE" ]; then
    echo "Error: Service template $SERVICE_TEMPLATE not found!"
    exit 1
fi

# Replace placeholder with actual path and write to systemd directory
sed "s|%SCRIPT_PATH%|$SCRIPT_DIR|g" "$SERVICE_TEMPLATE" > "$SYSTEMD_SERVICE_PATH"

echo "Service file installed to $SYSTEMD_SERVICE_PATH"
echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "Enabling wifi-switcher.service..."
systemctl enable wifi-switcher.service

echo "----------------------------------------"
echo "Setup Complete!"
echo "The Smart Network Switcher will run automatically on boot."
echo "To test it now, run: sudo systemctl start wifi-switcher.service"
echo "Check logs with: sudo cat /var/log/wifi-switcher.log"
