#!/usr/bin/env bash
# Install the fuel-level poller as a systemd service on the Raspberry Pi.
# Run on the Pi from the project folder:  sudo bash deploy/install.sh
set -euo pipefail

SERVICE=fuel-level
RUN_USER="${SUDO_USER:-$(whoami)}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "run with sudo: sudo bash $0" >&2
  exit 1
fi

echo "user:    $RUN_USER"
echo "project: $PROJECT_DIR"

# Serial port access for the service user.
usermod -aG dialout "$RUN_USER"

# pyserial for the system python used by the unit.
if ! python3 -c "import serial" 2>/dev/null; then
  apt-get install -y python3-serial || pip3 install --break-system-packages pyserial
fi

# Unit file with the real user and path substituted in.
sed -e "s|^User=.*|User=$RUN_USER|" \
    -e "s|/home/backup/fuel-level|$PROJECT_DIR|g" \
    "$PROJECT_DIR/deploy/$SERVICE.service" > "/etc/systemd/system/$SERVICE.service"

# Env file only if none exists yet, so edits survive reinstalls.
if [[ ! -f /etc/default/$SERVICE ]]; then
  cp "$PROJECT_DIR/deploy/$SERVICE.env.example" "/etc/default/$SERVICE"
fi

systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"
sleep 2
systemctl --no-pager --lines=5 status "$SERVICE" || true

cat <<MSG

Installed. Useful commands:
  journalctl -u $SERVICE -f          # live log
  sudo systemctl restart $SERVICE    # after editing code or /etc/default/$SERVICE
  sudo systemctl stop $SERVICE       # stop until next reboot
  sudo systemctl disable $SERVICE    # stop auto-start at boot
MSG
