#!/bin/bash
set -euo pipefail

dnf install -y nginx python3 python3-pip

install -d -m 0755 /opt/cloud-appointment
install -d -m 0755 /etc/cloud-appointment

for attempt in {1..12}; do
  if aws s3api get-object \
    --bucket "${application_bucket}" \
    --key "${application_key}" \
    --version-id "${application_version}" \
    /tmp/cloud-appointment-app.zip; then
    break
  fi

  if [[ "$${attempt}" -eq 12 ]]; then
    exit 1
  fi

  sleep 10
done

python3 -m zipfile -e /tmp/cloud-appointment-app.zip /opt/cloud-appointment
python3 -m venv /opt/cloud-appointment/.venv
/opt/cloud-appointment/.venv/bin/pip install --no-cache-dir -r /opt/cloud-appointment/requirements.txt

curl -fsS \
  https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem \
  -o /etc/cloud-appointment/rds-global-bundle.pem
chmod 0644 /etc/cloud-appointment/rds-global-bundle.pem

TOKEN=$(curl -fsS -X PUT \
  "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

INSTANCE_ID=$(curl -fsS \
  -H "X-aws-ec2-metadata-token: $${TOKEN}" \
  http://169.254.169.254/latest/meta-data/instance-id)

AZ=$(curl -fsS \
  -H "X-aws-ec2-metadata-token: $${TOKEN}" \
  http://169.254.169.254/latest/meta-data/placement/availability-zone)

cat > /etc/cloud-appointment/application.env <<EOF
AWS_REGION=${aws_region}
DB_HOST=${database_host}
DB_NAME=${database_name}
DB_PORT=${database_port}
DB_SECRET_ARN=${database_secret_arn}
RDS_CA_BUNDLE=/etc/cloud-appointment/rds-global-bundle.pem
INSTANCE_ID=$${INSTANCE_ID}
AVAILABILITY_ZONE=$${AZ}
SESSION_COOKIE_SECURE=${session_cookie_secure}
EOF
chmod 0600 /etc/cloud-appointment/application.env

cat > /etc/systemd/system/cloud-appointment.service <<'EOF'
[Unit]
Description=Cloud Appointment Management Application
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=nginx
Group=nginx
WorkingDirectory=/opt/cloud-appointment
EnvironmentFile=/etc/cloud-appointment/application.env
ExecStart=/opt/cloud-appointment/.venv/bin/gunicorn --workers 2 --bind 127.0.0.1:8000 --timeout 30 "app:create_app()"
Restart=always
RestartSec=5
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/cloud-appointment

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/nginx/conf.d/cloud-appointment.conf <<'EOF'
server {
    listen 80 default_server;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }
}
EOF

rm -f /etc/nginx/conf.d/default.conf
systemctl daemon-reload
systemctl enable --now cloud-appointment nginx
