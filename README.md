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

## Validated Lab-to-HA upgrade

Both operating modes were deployed and verified in `us-east-2` on August 21, 2026. The validation started with the cost-optimized lab configuration and then changed only `ha_mode` to `true`.

| Evidence | Lab baseline | HA validation |
|---|---|---|
| Auto Scaling capacity | `min=1`, `desired=1`, `max=2` | `min=2`, `desired=2`, `max=4` |
| Application placement | One healthy instance | Two healthy instances, one in `us-east-2a` and one in `us-east-2b` |
| ALB targets | One healthy target | Two healthy targets |
| NAT gateways | One available gateway shared by both app subnets | Two available gateways, one per public subnet |
| RDS | Private, encrypted, Single-AZ, one-day backups | Private, encrypted, Multi-AZ, seven-day backups, deletion protection enabled |
| Terraform convergence | No changes | No changes |

The HA upgrade plan contained two additions, three in-place changes, and no destruction. It added the second Elastic IP and NAT Gateway, moved the AZ2 application default route to its local NAT Gateway, expanded the Auto Scaling Group, and converted RDS to Multi-AZ. RDS modifications use `apply_immediately = true` so this short-lived portfolio validation can prove the resulting state without waiting for a maintenance window.

The evidence can be reproduced with:

```bash
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names cloud-portfolio-lab-asg

aws elbv2 describe-target-health \
  --target-group-arn "$(terraform output -raw target_group_arn)"

aws ec2 describe-nat-gateways \
  --filter 'Name=tag:Name,Values=cloud-portfolio-lab-nat-*'

aws rds describe-db-instances \
  --db-instance-identifier cloud-portfolio-lab-mysql

terraform plan -detailed-exitcode
```

Optional AWS Console screenshots can be added under `docs/screenshots/` to complement this reproducible CLI evidence. Screenshots should show the ASG instance list, ALB target health, NAT gateway list, RDS availability configuration, and the final no-change Terraform plan without exposing account credentials or secret values.

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

When HA mode is active, first return to lab mode and apply that transition. This disables RDS deletion protection and restores teardown-safe snapshot behavior before destruction:

```bash
terraform apply -var="ha_mode=false"
terraform destroy -var="ha_mode=false"
```

After teardown, verify that NAT Gateways, Elastic IPs, RDS instances or snapshots, EC2 instances, and load balancers no longer remain in the account.
