# AWS Portfolio Project Session Record

Date: August 21, 2026

Project: `aws-project-1`

AWS account verified: `382352119953`

AWS Region: `us-east-2`

AWS CLI profile: `school645`

Project directory: `/Users/danmon1/cloud-projects/aws-project-1`

## Purpose of this document

This document is the detailed proof and engineering record for the work performed on the AWS Terraform portfolio project. It records the architecture, implementation sequence, commands, validation evidence, operational decisions, problems encountered, security improvements, Git milestones, and final teardown.

No passwords or secret values are recorded here. Resource identifiers shown are historical evidence and may change when the environment is rebuilt.

## Final outcome

- Built and deployed a secure three-tier AWS environment with Terraform.
- Validated both cost-optimized lab mode and production-style HA mode.
- Proved two healthy application instances across `us-east-2a` and `us-east-2b`.
- Proved two healthy ALB targets and two AZ-local NAT gateways in HA mode.
- Proved encrypted, private RDS running Multi-AZ with seven-day backup retention.
- Enforced IMDSv2 and used Systems Manager instead of SSH.
- Enforced MySQL TLS with `require_secure_transport=1`.
- Enabled RDS Enhanced Monitoring in HA mode.
- Added and validated CloudWatch alarms and SNS integration.
- Tightened security-group egress.
- Added an optional ACM HTTPS listener and HTTP redirect interface.
- Deployed the application page immutably through a new Launch Template version and ASG instance refresh.
- Committed and pushed all source changes to GitHub.
- Safely destroyed all 44 Terraform-managed AWS resources.
- Confirmed Terraform state is empty and no major billable resources remain.
- Preserved local Terraform state and backup files for audit/reference.

## Architecture implemented

```text
Internet
   |
Application Load Balancer
Public subnets in two Availability Zones
   |
Auto Scaling Group / EC2
Private application subnets in two Availability Zones
   |
Amazon RDS for MySQL
Private database subnets in two Availability Zones
```

Core components:

- Terraform with AWS provider 6.x.
- VPC CIDR `10.20.0.0/21`.
- Two public, two private application, and two private database subnets.
- Internet Gateway and public route table.
- One NAT Gateway in lab mode; one per AZ in HA mode.
- Internet-facing Application Load Balancer.
- EC2 Launch Template and Auto Scaling Group.
- Amazon Linux 2023 with Nginx installed through user data.
- Private encrypted RDS MySQL 8.4.9.
- RDS-managed master credentials in Secrets Manager.
- IAM roles for EC2/SSM and RDS Enhanced Monitoring.
- CloudWatch alarms, target tracking, and SNS alerts.
- No inbound SSH rule.

## Address plan

| Tier | AZ1 | AZ2 |
|---|---|---|
| Public | `10.20.0.0/27` | `10.20.0.32/27` |
| Private application | `10.20.1.0/24` | `10.20.2.0/24` |
| Private database | `10.20.3.0/27` | `10.20.3.32/27` |

The application tier received the largest subnets because Auto Scaling can increase instance count. Public and database tiers use smaller `/27` networks. Unused VPC space remains available for endpoints, cache, containers, or future service tiers.

## Lab and HA behavior

| Capability | Lab mode | HA mode |
|---|---|---|
| NAT Gateways | One shared gateway | Two gateways, one per AZ |
| ASG minimum/desired/maximum | `1/1/2` | `2/2/4` |
| RDS topology | Single-AZ | Multi-AZ |
| Backup retention | One day | Seven days |
| RDS deletion protection | Disabled | Enabled |
| Final snapshot policy | Skip for temporary lab | Required in HA configuration |
| RDS Enhanced Monitoring | Disabled | 60-second interval |

Lab mode intentionally reduces cost and cannot survive loss of the AZ containing its only application instance or NAT Gateway. HA mode removes those cost-driven single points of failure.

## Major implementation phases

### 1. Repository and Terraform foundation

Created the Terraform working files and protected local artifacts with `.gitignore`:

```bash
touch versions.tf providers.tf variables.tf locals.tf networking.tf outputs.tf terraform.tfvars.example
terraform init
terraform fmt
terraform validate
```

Ignored artifacts include:

- `.terraform/`
- `*.tfstate` and `*.tfstate.*`
- `*.tfvars` except the safe example file
- Terraform plan files
- environment files, private keys, and local AWS configuration

### 2. Networking

Implemented:

- VPC DNS support and hostnames.
- Six capacity-planned subnets across two AZs.
- Internet Gateway.
- Public route table and associations.
- Conditional NAT resources controlled by `ha_mode`.
- Separate application route tables.
- Isolated database route table with no internet default route.

The ASG explicitly depends on application route-table associations, and NAT gateways depend on public route-table associations. This avoids a first-boot race in which private instances launch before outbound routing is ready.

### 3. Security and IAM

Implemented three security boundaries:

```text
Internet -> ALB security group -> application security group -> database security group
```

- ALB accepts HTTP and conditionally HTTPS from the internet.
- Application ingress accepts HTTP only from the ALB security group.
- Database ingress accepts MySQL only from the application security group.
- Port 22 is not exposed.
- EC2 uses `AmazonSSMManagedInstanceCore` through an instance profile.
- EC2 can retrieve only the RDS-managed database secret referenced by Terraform.

### 4. Load balancing and compute

Implemented:

- Application Load Balancer across both public subnets.
- HTTP target group and health checks.
- Amazon Linux 2023 AMI discovery.
- Encrypted 8 GiB gp3 root volume.
- IMDSv2 enforcement with `http_tokens = "required"`.
- Launch Template with explicit numeric latest version reference.
- ASG across both application subnets with ELB health checks.
- Rolling instance refresh.
- Target-tracking CPU scaling.

### 5. IMDSv2-safe bootstrap

The initial metadata calls were corrected because tokenless metadata requests fail when IMDSv2 is required. The final bootstrap obtains and uses a token:

```bash
TOKEN=$(curl -fsS -X PUT \
  "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

INSTANCE_ID=$(curl -fsS \
  -H "X-aws-ec2-metadata-token: ${TOKEN}" \
  http://169.254.169.254/latest/meta-data/instance-id)
```

`dnf update -y` was removed from first boot to avoid nondeterministic startup and delayed ALB health checks. Fleet patching should use new AMIs and rolling replacement.

Validation command:

```bash
bash -n user_data.sh
```

### 6. Immutable landing-page deployment

The application page was upgraded without modifying the running server:

```text
user_data.sh change
  -> new Launch Template version
  -> ASG version update
  -> replacement instance
  -> ALB health checks pass
  -> old instance drains and terminates
```

The update plan reported:

```text
Plan: 0 to add, 2 to change, 0 to destroy.
```

The replacement instance became healthy before the prior instance was terminated. The page displayed live instance ID and Availability Zone metadata.

### 7. Database and secrets

Implemented:

- Private RDS MySQL.
- Storage encryption.
- RDS-managed master password in Secrets Manager.
- DB subnet group spanning two AZs.
- Single-AZ lab mode and Multi-AZ HA mode.
- Automatic minor upgrades.
- Conditional backup retention and deletion protection.
- Exact engine pin `8.4.9`.

Terraform never generated or stored the master password as a Terraform random value. No password was committed or printed.

### 8. Monitoring

Implemented:

- ASG average CPU target tracking at 50 percent.
- Fleet high-CPU alarm.
- ALB unhealthy-target alarm.
- ALB 5xx alarm.
- RDS high-CPU alarm.
- RDS low-free-storage alarm.
- SNS alert topic.

Alarms use explicit `datapoints_to_alarm` and `treat_missing_data` settings. Error-count and utilization alarms treat missing data as non-breaching; target health treats missing data as breaching.

### 9. Production security hardening

#### HTTPS and ACM

Terraform now supports an optional same-Region ACM certificate ARN:

```hcl
acm_certificate_arn = "arn:aws:acm:us-east-2:123456789012:certificate/example"
```

When supplied:

- ALB port 443 is enabled.
- TLS policy `ELBSecurityPolicy-TLS13-1-2-2021-06` is used.
- HTTP redirects permanently to HTTPS.

The student account contained no issued ACM certificate and no Route 53 hosted zone. HTTPS configuration validated successfully but was not activated. A self-signed certificate was deliberately not used as fake production evidence.

Read-only prerequisite checks:

```bash
aws acm list-certificates \
  --profile school645 \
  --region us-east-2 \
  --certificate-statuses ISSUED

aws route53 list-hosted-zones --profile school645
```

Both returned empty lists.

#### RDS TLS

A custom MySQL 8.4 parameter group enforces:

```text
require_secure_transport = 1
```

Attaching a parameter group to an existing DB returned `pending-reboot`, so a controlled reboot was performed:

```bash
aws rds reboot-db-instance \
  --profile school645 \
  --region us-east-2 \
  --db-instance-identifier cloud-portfolio-lab-mysql

aws rds wait db-instance-available \
  --profile school645 \
  --region us-east-2 \
  --db-instance-identifier cloud-portfolio-lab-mysql
```

Proof after reboot:

```text
ParameterApplyStatus: in-sync
require_secure_transport: 1
```

#### RDS Enhanced Monitoring

HA mode enabled RDS Enhanced Monitoring at 60-second granularity with a dedicated IAM role trusted only by `monitoring.rds.amazonaws.com` and the AWS-managed `AmazonRDSEnhancedMonitoringRole` policy.

Verified RDS properties:

```text
MultiAZ: true
MonitoringInterval: 60
PendingModifiedValues: empty
TLS parameter group: in-sync
```

#### Tighter egress

- ALB egress: TCP/80 only to the two private application subnet CIDRs.
- Application egress: TCP/443 to package repositories and AWS APIs.
- Application egress: TCP/3306 only to `10.20.3.0/26`, which contains both DB subnets.
- Database security group: no outbound rule.

A new HA instance successfully installed Nginx, registered with SSM, and passed ALB health checks under these restrictions.

## Important validation commands

### Terraform validation

```bash
terraform fmt -check
terraform validate
terraform plan
terraform plan -var="ha_mode=true"
terraform plan -detailed-exitcode
```

Exit code `0` with `No changes` was recorded after both the HA architecture validation and hardened HA validation.

### AWS identity

```bash
aws sts get-caller-identity --profile school645
```

Verified account:

```text
382352119953
```

### Auto Scaling evidence

```bash
aws autoscaling describe-auto-scaling-groups \
  --profile school645 \
  --region us-east-2 \
  --auto-scaling-group-names cloud-portfolio-lab-asg \
  --query 'AutoScalingGroups[0].Instances[*].[InstanceId,AvailabilityZone,LifecycleState,HealthStatus]' \
  --output table
```

HA evidence showed two `InService` and `Healthy` instances, one in `us-east-2a` and one in `us-east-2b`.

### ALB target health

```bash
aws elbv2 describe-target-health \
  --profile school645 \
  --region us-east-2 \
  --target-group-arn "$(terraform output -raw target_group_arn)" \
  --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State,TargetHealth.Reason]' \
  --output table
```

Both HA targets reported `healthy` with no failure reason.

### Systems Manager

```bash
aws ssm describe-instance-information \
  --profile school645 \
  --region us-east-2 \
  --query 'InstanceInformationList[*].[InstanceId,PingStatus,PlatformName,AgentVersion]' \
  --output table
```

Both hardened HA instances reported `Online` using Amazon Linux and SSM Agent `3.3.4624.0`.

### CloudWatch alarms

```bash
aws cloudwatch describe-alarms \
  --profile school645 \
  --region us-east-2 \
  --alarm-name-prefix cloud-portfolio-lab \
  --query 'MetricAlarms[*].[AlarmName,StateValue,StateReason]' \
  --output table
```

After metrics populated, all five alarms reported `OK`:

- `cloud-portfolio-lab-alb-5xx`
- `cloud-portfolio-lab-database-high-cpu`
- `cloud-portfolio-lab-database-low-storage`
- `cloud-portfolio-lab-high-cpu`
- `cloud-portfolio-lab-unhealthy-targets`

### RDS evidence

```bash
aws rds describe-db-instances \
  --profile school645 \
  --region us-east-2 \
  --db-instance-identifier cloud-portfolio-lab-mysql
```

HA evidence included:

```text
Status: available
MultiAZ: true
BackupRetentionPeriod: 7
DeletionProtection: true
StorageEncrypted: true
PubliclyAccessible: false
MonitoringInterval: 60
```

### NAT evidence

```bash
aws ec2 describe-nat-gateways \
  --profile school645 \
  --region us-east-2 \
  --filter 'Name=tag:Name,Values=cloud-portfolio-lab-nat-*' \
           'Name=state,Values=available'
```

HA mode showed two available NAT gateways in different public subnets.

## HA upgrade evidence

The initial HA upgrade plan reported:

```text
Plan: 2 to add, 3 to change, 0 to destroy.
```

It performed:

- One additional EIP.
- One additional NAT Gateway.
- AZ2 application default-route migration to NAT 2.
- ASG capacity change from `1/1/2` to `2/2/4`.
- RDS Single-AZ to Multi-AZ conversion.
- Backup retention increase from one to seven days.
- RDS deletion protection and final-snapshot behavior.

The hardened HA upgrade later reported:

```text
Plan: 2 to add, 3 to change, 0 to destroy.
```

It additionally activated the already-created RDS Enhanced Monitoring role and 60-second interval.

## Problems encountered and resolutions

### ASG service-linked role transient failure

The initial infrastructure apply reported an Auto Scaling service-linked-role access error while validating the load balancer configuration. AWS subsequently launched the instance successfully. The role and policies were inspected read-only, the ASG state was reconciled, and a recovery plan added the remaining scaling policy/alarm resources.

### IMDSv2 metadata failure risk

The original user data used tokenless metadata requests while the Launch Template required IMDSv2. It was corrected to request and supply an IMDSv2 token.

### Nondeterministic first boot

`dnf update -y` was removed. A current AMI plus immutable instance replacement is a cleaner fleet-patching model.

### NAT/ASG dependency race

Explicit dependencies were added so NAT routing and application route associations exist before instances bootstrap.

### RDS HA modification timing

The original HA expression would set `apply_immediately=false`, potentially deferring Multi-AZ conversion until a maintenance window. The project now uses `apply_immediately=true` so short-lived portfolio validation can prove the resulting state.

### RDS engine-family mismatch caught by plan

The live DB used MySQL 8.4, while the first TLS parameter group draft used `mysql8.0`. The plan exposed `default.mysql8.4`; the custom group was corrected to `mysql8.4` and the engine pinned to `8.4.9` before apply.

### RDS parameter normalization

AWS stores `require_secure_transport=ON` as `1`. Terraform was updated to declare canonical value `1`, eliminating perpetual drift.

### Existing RDS parameter-group reboot

Attaching the TLS group to an existing DB required a one-time reboot. The DB returned `available`, the group returned `in-sync`, and the parameter returned value `1` afterward.

### EIP release eventual-consistency error during downgrade

The first final HA-to-lab downgrade encountered:

```text
InvalidNetworkInterfaceID.NotFound
```

AWS had already removed the NAT network interface while EIP release still referenced it. A fresh Terraform plan showed only the expected project EIP release, AZ2 route correction, and ASG scale-down. The exact retry plan succeeded:

```text
Apply complete! Resources: 0 added, 2 changed, 1 destroyed.
```

No unrelated resource was touched.

## Git milestones

Important commits created and pushed:

```text
80e029a Improve landing page and document immutable deployment
30a918d Validate high availability architecture
6261211 Add production security hardening
```

Git author identity was configured as:

```text
Daniel Mondelice <dmondelice718@gmail.com>
```

Commands used:

```bash
git config --global user.name "Daniel Mondelice"
git config --global user.email "dmondelice718@gmail.com"

git add README.md user_data.sh
git commit -m "Improve landing page and document immutable deployment"
git push origin main

git add README.md database.tf
git commit -m "Validate high availability architecture"
git push origin main

git add README.md database.tf iam.tf load_balancer.tf monitoring.tf \
  security_groups.tf terraform.tfvars.example variables.tf
git commit -m "Add production security hardening"
git push origin main
```

The landing-page commit author was amended once and safely updated with `--force-with-lease`. No Git history was deleted, and no Terraform state was committed.

## Final teardown procedure

### Identity and scope verification

Before destructive work:

```bash
aws sts get-caller-identity --profile school645
pwd
git status --short --branch
terraform state list
```

Confirmed:

- Account `382352119953`.
- Directory `/Users/danmon1/cloud-projects/aws-project-1`.
- Branch `main` matched `origin/main`.
- State contained only the expected project resources.

### Safe HA-to-lab transition

Because HA mode enables RDS deletion protection, local `ha_mode` was returned to `false` and applied before destroy.

Final converged check:

```bash
terraform plan -detailed-exitcode -no-color
```

Result:

```text
No changes. Your infrastructure matches the configuration.
```

### Destroy-plan review

```bash
terraform plan -destroy -no-color
```

Result:

```text
Plan: 0 to add, 0 to change, 44 to destroy.
```

Every planned target was a Terraform-managed `cloud-portfolio-lab` resource or a direct dependency inside project VPC `vpc-03ff0a1278a29182e`. The account-level Auto Scaling service-linked role was not included.

### Destroy execution

```bash
terraform destroy -auto-approve -no-color
```

Final result:

```text
Destroy complete! Resources: 44 destroyed.
```

RDS took approximately two minutes to delete. The ASG took approximately six minutes because Terraform allowed normal connection draining. The last NAT Gateway took approximately 81 seconds. None of these operations were interrupted.

## Final teardown proof

### Terraform state

```bash
terraform state list
```

Result: no output. Terraform state is empty.

### Major billable-resource inventory

The following read-only checks all returned empty lists in account `382352119953`, Region `us-east-2`:

```bash
aws ec2 describe-nat-gateways \
  --profile school645 --region us-east-2 \
  --filter 'Name=state,Values=available,pending'

aws ec2 describe-addresses \
  --profile school645 --region us-east-2

aws elbv2 describe-load-balancers \
  --profile school645 --region us-east-2

aws autoscaling describe-auto-scaling-groups \
  --profile school645 --region us-east-2

aws ec2 describe-instances \
  --profile school645 --region us-east-2 \
  --filters 'Name=instance-state-name,Values=pending,running,stopping,stopped'

aws rds describe-db-instances \
  --profile school645 --region us-east-2
```

Verified empty:

- NAT Gateways.
- Elastic IPs.
- Application Load Balancers.
- Auto Scaling Groups.
- Active EC2 instances.
- RDS instances.

Additional project-specific checks also returned empty:

- VPCs tagged `Project=cloud-portfolio`.
- CloudWatch alarms prefixed `cloud-portfolio-lab`.
- SNS topics containing `cloud-portfolio`.
- IAM roles containing `cloud-portfolio`.
- RDS snapshots associated with `cloud-portfolio`.

No resource remained in a deleting state at final verification.

## Local data preservation

The Terraform state files were deliberately preserved and remain ignored by Git:

```text
terraform.tfstate
terraform.tfstate.backup
```

After successful destroy, the current state file is small because it contains an empty resource graph. The backup contains the prior state snapshot for local audit/recovery context. Neither file is tracked by Git.

Do not delete the project directory or state files. Do not commit state to Git because state can contain infrastructure metadata and sensitive values.

## Rebuild procedure

The environment can be recreated later from the committed Terraform code:

```bash
cd /Users/danmon1/cloud-projects/aws-project-1
aws sso login --profile school645
export AWS_PROFILE=school645

terraform init
terraform fmt -check
terraform validate
terraform plan
terraform apply
```

The ignored local `terraform.tfvars` currently selects lab mode. Verify its contents before rebuilding.

Expected values that will change after recreation:

- EC2 instance IDs.
- Launch Template versions or IDs.
- ALB DNS name and ARN.
- RDS endpoint and resource ID.
- NAT Gateway IDs and public IPs.
- Subnet, route-table, security-group, and VPC IDs.
- RDS-managed Secrets Manager secret ARN.

These changes are normal because Terraform creates new AWS resources.

## Production hardening roadmap

Recommended next steps:

- Register or use a controlled domain and automate Route 53/ACM DNS validation.
- Activate the optional HTTPS listener and verify browser-trusted TLS.
- Add AWS WAF managed rules.
- Enable ALB access logging with encrypted centralized retention.
- Add VPC endpoints for SSM, EC2 Messages, SSM Messages, CloudWatch Logs, Secrets Manager, and S3 where appropriate.
- Use customer-managed KMS keys and scoped key policies.
- Add RDS latency, connection, failover, and event alarms from real workload baselines.
- Configure Session Manager session logging.
- Add CloudTrail, AWS Config, GuardDuty, and Security Hub controls.
- Add CI checks for Terraform formatting, validation, linting, policy-as-code, and plan review.
- Move Terraform state to an encrypted remote backend with locking, versioning, and least-privilege access.

## Final assurance

- AWS account was verified before destructive work.
- Only Terraform-managed `cloud-portfolio` resources were destroyed.
- No unrelated AWS resources were manually deleted.
- No service-linked or account-level IAM role was deleted.
- No new infrastructure was created after final destroy.
- Git history and GitHub repository were preserved.
- Terraform source, README, and local state files were preserved.
- Final billable-resource checks were empty.
