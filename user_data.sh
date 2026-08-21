#!/bin/bash
set -euo pipefail


dnf install -y nginx


TOKEN=$(curl -fsS -X PUT \
  "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")


INSTANCE_ID=$(curl -fsS \
  -H "X-aws-ec2-metadata-token: ${TOKEN}" \
  http://169.254.169.254/latest/meta-data/instance-id)


AZ=$(curl -fsS \
  -H "X-aws-ec2-metadata-token: ${TOKEN}" \
  http://169.254.169.254/latest/meta-data/placement/availability-zone)


cat > /usr/share/nginx/html/index.html <<EOF
<!DOCTYPE html>
<html>
<head>
  <title>AWS Cloud Portfolio</title>
</head>
<body>
  <h1>AWS Highly Available Web Architecture</h1>
  <p>Served from EC2 instance: ${INSTANCE_ID}</p>
  <p>Availability Zone: ${AZ}</p>
  <p>Managed with Terraform and Auto Scaling.</p>
</body>
</html>
EOF


systemctl enable --now nginx
