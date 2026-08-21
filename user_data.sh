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
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AWS Cloud Portfolio</title>
  <style>
    :root {
      color-scheme: dark;
      --ink: #f8fafc;
      --muted: #a7b4c5;
      --surface: rgba(15, 29, 49, 0.82);
      --line: rgba(148, 163, 184, 0.2);
      --orange: #ff9900;
      --blue: #38bdf8;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 10% 10%, rgba(56, 189, 248, 0.16), transparent 28rem),
        radial-gradient(circle at 90% 20%, rgba(255, 153, 0, 0.13), transparent 24rem),
        #07111f;
    }

    header,
    main,
    footer {
      width: min(1120px, calc(100% - 40px));
      margin: 0 auto;
    }

    header {
      padding: 84px 0 48px;
    }

    .eyebrow {
      margin: 0 0 16px;
      color: var(--orange);
      font-size: 0.78rem;
      font-weight: 800;
      letter-spacing: 0.18em;
      text-transform: uppercase;
    }

    h1 {
      max-width: 850px;
      margin: 0;
      font-size: clamp(2.7rem, 7vw, 5.6rem);
      line-height: 0.98;
      letter-spacing: -0.055em;
    }

    .intro {
      max-width: 760px;
      margin: 28px 0 0;
      color: var(--muted);
      font-size: 1.12rem;
      line-height: 1.8;
    }

    section {
      margin: 28px 0;
    }

    .section-title {
      margin-bottom: 20px;
    }

    .section-title h2,
    .runtime h2 {
      margin: 0 0 8px;
      font-size: 1.45rem;
    }

    .section-title p,
    .card p,
    .runtime p {
      color: var(--muted);
      line-height: 1.7;
    }

    .section-title p,
    .card p {
      margin: 0;
    }

    .cards {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
    }

    .card,
    .architecture,
    .runtime {
      border: 1px solid var(--line);
      border-radius: 18px;
      background: var(--surface);
      box-shadow: 0 18px 60px rgba(0, 0, 0, 0.2);
      backdrop-filter: blur(14px);
    }

    .card {
      min-height: 190px;
      padding: 26px;
    }

    .card h3 {
      margin: 0 0 14px;
      font-size: 1.02rem;
    }

    .architecture,
    .runtime {
      padding: 30px;
    }

    .flow {
      display: flex;
      align-items: center;
      gap: 10px;
      overflow-x: auto;
      padding: 8px 0 4px;
    }

    .service {
      flex: 1 0 170px;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: rgba(7, 17, 31, 0.72);
      text-align: center;
      font-size: 0.92rem;
      font-weight: 700;
    }

    .arrow {
      color: var(--orange);
      font-size: 1.35rem;
      font-weight: 900;
    }

    .runtime code {
      color: var(--blue);
      font-family: "SFMono-Regular", Consolas, monospace;
    }

    .tags {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 24px;
    }

    .tag {
      padding: 8px 12px;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: #d9e5f2;
      background: rgba(56, 189, 248, 0.07);
      font-size: 0.8rem;
      font-weight: 700;
    }

    footer {
      padding: 34px 0 50px;
      color: #7f8da0;
      font-size: 0.86rem;
      text-align: center;
    }

    footer span {
      color: var(--orange);
    }

    @media (max-width: 820px) {
      header {
        padding-top: 54px;
      }

      .cards {
        grid-template-columns: 1fr;
      }

      .card {
        min-height: auto;
      }
    }
  </style>
</head>
<body>

<header>
  <p class="eyebrow">AWS Cloud Infrastructure Portfolio</p>
  <h1>Highly Available Web Architecture</h1>
  <p class="intro">
    A secure three-tier AWS environment provisioned with Terraform. Public traffic
    enters through an Application Load Balancer while compute and database resources
    remain inside private subnets across two Availability Zones.
  </p>
</header>

<main>

  <section>
    <div class="section-title">
      <h2>Architecture Controls</h2>
      <p>Security, resilience, and operations are designed into the platform.</p>
    </div>

    <div class="cards">
      <div class="card">
        <h3>Network Isolation</h3>
        <p>
          The ALB uses public subnets, EC2 runs in private application subnets,
          and Amazon RDS remains isolated in dedicated database subnets.
        </p>
      </div>

      <div class="card">
        <h3>Elastic Compute</h3>
        <p>
          A Launch Template and Auto Scaling Group replace unhealthy instances
          and scale capacity using target-tracking CPU policies.
        </p>
      </div>

      <div class="card">
        <h3>Encrypted Data</h3>
        <p>
          EC2 root storage and RDS storage are encrypted, while RDS manages its
          master credentials directly in AWS Secrets Manager.
        </p>
      </div>

      <div class="card">
        <h3>Systems Manager</h3>
        <p>
          Administrative access uses AWS Systems Manager rather than exposing
          SSH or inbound port 22.
        </p>
      </div>

      <div class="card">
        <h3>Monitoring</h3>
        <p>
          CloudWatch monitors CPU utilization, unhealthy ALB targets, and
          infrastructure error conditions.
        </p>
      </div>

      <div class="card">
        <h3>Availability Modes</h3>
        <p>
          Lab mode controls cost with one NAT Gateway and Single-AZ RDS; HA mode
          enables AZ-local NAT Gateways, two application instances, and Multi-AZ RDS.
        </p>
      </div>
    </div>
  </section>

  <section class="architecture">
    <div class="section-title">
      <h2>Request Flow</h2>
      <p>The path this request followed through the AWS environment.</p>
    </div>

    <div class="flow">
      <div class="service">Internet</div>
      <div class="arrow">→</div>

      <div class="service">Application Load Balancer</div>
      <div class="arrow">→</div>

      <div class="service">Private EC2 / Auto Scaling</div>
      <div class="arrow">→</div>

      <div class="service">Private Amazon RDS</div>
    </div>
  </section>

  <section class="runtime">
    <h2>Live Deployment Metadata</h2>

    <p>
      <strong>EC2 Instance:</strong>
      <code>${INSTANCE_ID}</code>
    </p>

    <p>
      <strong>Availability Zone:</strong>
      <code>${AZ}</code>
    </p>

    <p>
      <strong>Deployment:</strong>
      <code>Terraform Managed</code>
    </p>

    <div class="tags">
      <span class="tag">Terraform</span>
      <span class="tag">Amazon VPC</span>
      <span class="tag">EC2</span>
      <span class="tag">ALB</span>
      <span class="tag">Auto Scaling</span>
      <span class="tag">RDS</span>
      <span class="tag">CloudWatch</span>
      <span class="tag">Systems Manager</span>
    </div>
  </section>

</main>

<footer>
  AWS Cloud Infrastructure Portfolio • Built with
  <span>Terraform</span>
</footer>

</body>
</html>
EOF


systemctl enable --now nginx
