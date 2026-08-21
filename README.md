# AWS Highly Available Web Architecture

This portfolio project provisions a secure three-tier AWS web environment with Terraform. It demonstrates network isolation, automatic scaling, managed operations, encrypted storage, and explicit cost-versus-availability tradeoffs.

## Architecture

```text
Internet
   |
Application Load Balancer — public subnets in two AZs
   |
Auto Scaling Group — private application subnets in two AZs
   |
Amazon RDS for MySQL — isolated database subnets in two AZs
```

The environment includes:

- A `10.20.0.0/21` VPC with public, private application, and private database subnet tiers.
- An internet-facing ALB that is the only public application entry point.
- Private Amazon Linux 2023 EC2 instances managed by an Auto Scaling Group.
- Systems Manager administration with no inbound SSH or port 22 rule.
- IMDSv2 enforcement and encrypted EC2 root volumes.
- Private, encrypted RDS MySQL with RDS-managed credentials in Secrets Manager.
- CPU target tracking, CloudWatch alarms, and an SNS alert topic.

## Lab and HA modes

| Capability | Lab mode | HA mode |
|---|---|---|
| NAT Gateways | One shared NAT Gateway | One NAT Gateway per AZ |
| Application capacity | One desired instance | Two desired instances |
| RDS | Single-AZ | Multi-AZ |
| RDS backup retention | One day | Seven days |
| RDS deletion protection | Disabled | Enabled |
| Final RDS snapshot | Skipped | Required |

Lab mode reduces cost and is not designed to survive the loss of the AZ containing its NAT Gateway or only application instance. HA mode removes these deliberate cost optimizations.

## Immutable application deployment

The landing page is installed by `user_data.sh` through the EC2 Launch Template. Application changes are deployed immutably:

1. Update and validate `user_data.sh`.
2. Terraform creates a new Launch Template version.
3. The Auto Scaling Group references that explicit version.
4. Instance refresh launches a replacement instance.
5. The ALB health check must pass before the new target serves traffic.
6. The old instance is terminated by Auto Scaling.

This avoids manually modifying running servers and keeps the deployed fleet reproducible from source control.

## Deployment

```bash
export AWS_PROFILE=school645
terraform init
terraform fmt -check
terraform validate
terraform plan -out=lab.tfplan
terraform apply lab.tfplan
```

After deployment:

```bash
terraform output -raw alb_dns_name
terraform output
```

Do not retrieve or commit the database password. RDS creates and maintains the master credential directly in Secrets Manager.

## Cost and teardown

NAT Gateway, ALB, EC2/EBS, RDS, Secrets Manager, CloudWatch, public IPv4, and data transfer can incur charges. Lab mode reduces—but does not eliminate—cost.

Destroy the environment promptly when testing is complete:

```bash
terraform destroy
```

After teardown, verify that NAT Gateways, Elastic IPs, RDS instances or snapshots, EC2 instances, and load balancers no longer remain in the account.
