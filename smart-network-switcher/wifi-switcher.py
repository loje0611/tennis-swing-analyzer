#!/usr/bin/env python3
import subprocess
import time
import json
import os
import sys

# Constants
LOG_FILE = "/var/log/wifi-switcher.log"
# Config file is expected to be in the same directory as this script
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

def log(message):
    """Writes a message to the console and the log file with a timestamp."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_entry + "\n")
    except PermissionError:
        pass # If running without sudo, we might not be able to write to /var/log

def run_command(command):
    """Runs a shell command and returns (success, output)."""
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def check_internet_connection(host="8.8.8.8", timeout=3):
    """Checks for internet connection by pinging a known host."""
    cmd = f"ping -c 1 -W {timeout} {host}"
    success, _ = run_command(cmd)
    return success

def main():
    log("=== Smart Network Switcher Started ===")
    
    # Check if config exists
    if not os.path.exists(CONFIG_FILE):
        log(f"Error: Config file not found at {CONFIG_FILE}. Please run setup_network.sh first.")
        sys.exit(1)

    # Load Configuration
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            HOME_SSID = config.get("HOME_SSID", "")
            HOME_PASS = config.get("HOME_PASS", "")
    except Exception as e:
        log(f"Error reading config file: {e}")
        sys.exit(1)

    if not HOME_SSID:
        log("Error: HOME_SSID not defined in config.")
        sys.exit(1)

    # Step 1: Scan for Networks
    log("Scanning for available WiFi networks...")
    # Rescan to get fresh results
    run_command("nmcli device wifi rescan")
    time.sleep(3) # Wait for scan results
    
    success, output = run_command("nmcli -t -f SSID device wifi list")
    available_ssids = output.strip().split('\n') if success else []
    
    home_wifi_detected = HOME_SSID in available_ssids
    
    if home_wifi_detected:
        log(f"Home WiFi '{HOME_SSID}' detected.")
        
        # Step 2: Try to connect to Home WiFi
        # First, ensure AP mode is disabled to avoid conflicts
        run_command("nmcli connection down TennisPi_AP")
        
        # Delete existing connection profile to ensure a fresh start
        run_command(f"nmcli connection delete '{HOME_SSID}'")

        log(f"Attempting to connect to '{HOME_SSID}'...")
        
        # Method 1: Automatic connection (nmcli device wifi connect)
        cmd = f"nmcli --wait 30 device wifi connect '{HOME_SSID}' password '{HOME_PASS}'"
        conn_success, conn_msg = run_command(cmd)
        
        if not conn_success and "key-mgmt" in conn_msg:
            log("Auto-connect failed due to missing security info. Trying explicit WPA-PSK profile...")
            # Method 2: Manual Profile Creation (Fallback for WPA-PSK)
            run_command(f"nmcli connection delete '{HOME_SSID}'") # Clean up failed attempt
            run_command(f"nmcli connection add type wifi con-name '{HOME_SSID}' ssid '{HOME_SSID}'")
            run_command(f"nmcli connection modify '{HOME_SSID}' wifi-sec.key-mgmt wpa-psk wifi-sec.psk '{HOME_PASS}'")
            
            # Try to bring up the manually created connection
            cmd = f"nmcli --wait 30 connection up '{HOME_SSID}'"
            conn_success, conn_msg = run_command(cmd)

        # Check result of whichever method was last tried
        
        if conn_success:
            log(f"Successfully connected to '{HOME_SSID}'. Mode: Station.")
            
            # Retrieve and log IP address
            _, ip_info = run_command(f"nmcli -g ip4.address connection show '{HOME_SSID}'")
            if ip_info:
                log(f"Current IP Address: {ip_info.strip()}")
            return # Exit successfully
        else:
            log(f"Failed to connect to '{HOME_SSID}'. Error: {conn_msg.strip()}")
            # Proceed to AP mode
    else:
        log(f"Home WiFi '{HOME_SSID}' not found in range.")

    # Step 3: Switch to AP Mode (if Home WiFi not found or connection failed)
    log("Switching to Hotspot Mode (TennisPi_AP)...")
    
    # Activate AP Profile
    ap_success, ap_msg = run_command("nmcli connection up TennisPi_AP")
    
    if ap_success:
        log("AP Mode Activated successfully.")
        log("SSID: TennisPi_AP | IP: 10.42.0.1 (Default for Shared)")
    else:
        log(f"CRITICAL: Failed to activate AP mode. Error: {ap_msg.strip()}")

if __name__ == "__main__":
    main()
