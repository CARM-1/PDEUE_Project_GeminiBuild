#!/usr/bin/env bash
set -euo pipefail

echo "=== Initializing PDEUE 72-Hour Cloud Paper Soak Runner ==="

sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git htop jq curl

TARGET_DIR="/opt/pdeue"
if [ ! -d "$TARGET_DIR" ]; then
    sudo git clone https://github.com/CARM-1/PDEUE_Project_GeminiBuild.git "$TARGET_DIR"
fi

cd "$TARGET_DIR"
sudo git checkout main
sudo git pull origin main

sudo python3 -m venv "$TARGET_DIR/venv"
sudo "$TARGET_DIR/venv/bin/pip" install --upgrade pip
sudo "$TARGET_DIR/venv/bin/pip" install pytest fastapi uvicorn httpx jsonschema prometheus_client

sudo tee /etc/systemd/system/pdeue-paper-soak.service > /dev/null <<EOF
[Unit]
Description=PDEUE 72-Hour Autonomous Cloud Paper Soak Runner
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$TARGET_DIR
ExecStart=$TARGET_DIR/venv/bin/python3 $TARGET_DIR/backend/scripts/paper_soak_runner.py
Restart=on-failure
RestartSec=5s
StandardOutput=append:$TARGET_DIR/soak_runner.log
StandardError=append:$TARGET_DIR/soak_runner_error.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable pdeue-paper-soak.service
sudo systemctl start pdeue-paper-soak.service

echo "=== PDEUE Soak Runner Service Active ==="
sudo systemctl status pdeue-paper-soak.service --no-pager
