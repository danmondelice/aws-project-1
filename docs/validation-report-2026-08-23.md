# Application Validation and Resilience Report

**Date:** August 23, 2026
**Environment:** AWS account `382352119953`, `us-east-2`, Lab mode
**Workload:** Nginx → Gunicorn → Flask → private RDS MySQL
**Purpose:** Interview-ready evidence of functional, performance, security, infrastructure, deployment, and failure-recovery testing.

## Executive summary

The live application passed its process-health, rolling-deployment, security-control, authorization, input-handling, infrastructure-posture, and load tests. The final EC2 instance (`i-0b29f199ab5865e16`, Launch Template v5) was healthy behind the ALB, online in Systems Manager, had no public IP, and required IMDSv2. All five CloudWatch alarms were `OK`.

Testing exposed a real dependency-coupling defect when the student environment stopped RDS during an Auto Scaling refresh. The original Flask factory synchronously initialized the database schema, so a replacement instance could not start Gunicorn while RDS was unavailable. The application was changed to start independently, retry schema initialization in a bounded background process, serve `/health` without RDS, return `503` from `/ready`, and render public pages in explicit degraded mode. A new immutable ASG rollout then succeeded while RDS remained stopped.

## Final live state

| Control | Verified result |
|---|---|
| AWS identity | Account `382352119953` |
| ASG | Desired 1; one `InService/Healthy` instance on Launch Template v5 |
| ALB target | `healthy` |
| Systems Manager | `Online`, Amazon Linux, agent `3.3.4624.0` |
| RDS | Student-lab controlled stop; encrypted, private, Single-AZ Lab mode |
| CloudWatch | All five project alarms `OK` |
| EC2 exposure | No public IPv4 address; app SG only |
| IMDS | Tokens `required` (IMDSv2) |
| Artifact bucket | Public access fully blocked, AES256 encryption, versioning enabled |

## Functional and resilience testing

| Test | Result |
|---|---|
| `/health` | `200`; process remains healthy without RDS |
| `/ready` during RDS stop | `503`; dependency outage reported correctly |
| `/` during RDS stop | `200`; explicit degraded mode, 0.663 s sampled response |
| `/stats` during RDS stop | `200`; 1.142 s sampled response |
| `/api/stats` during RDS stop | `200`; aggregate fallback response |
| Unauthenticated `/api/appointments` | JSON `401`, not an HTML redirect |
| Immutable deployment | S3 version → Launch Template version → ASG instance refresh |
| ASG refresh with stopped RDS | Successful; replacement passed ALB health |
| Previous database workflow | Registration and appointment create/read persisted in private RDS |

The process and readiness endpoints intentionally answer different questions. `/health` tells the ALB whether Nginx/Gunicorn/Flask can serve traffic. `/ready` performs a real `SELECT 1` against MySQL and reports whether database-dependent features are ready.

## Performance results

Tests ran through the public ALB against the single-instance Lab fleet.

| Endpoint | Requests / concurrency | Failures | Throughput | Mean | p95 | p99 |
|---|---:|---:|---:|---:|---:|---:|
| `/health` | 100 / 5 | 0 | 41.05 req/s | 121.8 ms | 144 ms | 150 ms |
| `/` degraded | 50 / 2 | 0 | 14.81 req/s | 135.1 ms | 203 ms | 265 ms |

An earlier `/stats` ApacheBench run reported apparent failed requests when the response length changed as live counters incremented. Follow-up requests proved these were ApacheBench fixed-length warnings, not connection or HTTP failures. A diagnostic run completed 10/10 requests with zero failures.

These figures are validation measurements, not a production capacity claim. The fleet used one `t3.micro`, two synchronous Gunicorn workers, HTTP, and no CDN or cache.

## Application security tests

| Test | Result |
|---|---|
| CSRF: registration without token | Rejected with `400` |
| CSRF: telemetry without token | Rejected with `400` |
| SQL injection login attempt | Did not bypass authentication |
| Cross-user appointment lookup | Returned `404` |
| Stored XSS marker | Escaped in rendered HTML; raw marker absent |
| API authentication contract | Protected API returns JSON `401` |
| Password storage | Werkzeug password hash, never plaintext |
| SQL construction | Parameterized PyMySQL queries |
| Location collection | Explicit browser consent; rounded to two decimals |
| Visitor analytics | Random UUID; no raw IP; referrer hostname only |

Verified response headers:

- `Content-Security-Policy` with self-only scripts/styles and `frame-ancestors 'none'`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- Cookies use `HttpOnly` and `SameSite=Lax`

Current Lab traffic uses HTTP because no validated domain/ACM certificate is configured. Consequently cookies cannot yet use `Secure`, browser geolocation is generally unavailable, and transport confidentiality is not production-ready. The Terraform HTTPS/ACM path should be enabled with a real domain before public production use.

## AWS security and operations evidence

- ALB is the only public application entry point.
- EC2 is private, has no public IP, exposes no SSH rule, and is administered through Systems Manager.
- ALB SG → application SG on TCP/80; application SG → database SG on TCP/3306.
- RDS is private-only and storage-encrypted; application connections validate the AWS RDS CA and require TLS through the MySQL parameter group.
- RDS manages the master credential in Secrets Manager. The instance role can retrieve only the referenced database secret.
- The EC2 root volume is encrypted gp3 and deleted on termination.
- The application artifact bucket blocks all public access, uses server-side encryption and versioning, and the role has object/version access only to the release object.
- CloudWatch covers fleet CPU, unhealthy targets, ALB 5xx, RDS CPU, and RDS free storage; alarms notify SNS.
- Lab mode uses one NAT, one EC2 instance, and Single-AZ RDS to control cost. HA mode uses two NATs, minimum two application instances, and Multi-AZ RDS.

## Errors, diagnosis, and remediation

### 1. Versioned S3 artifact access returned 403

**Symptom:** EC2 bootstrap could read the object generally but failed when requesting the exact version.
**Cause:** IAM allowed `s3:GetObject` but the version-pinned deployment also required `s3:GetObjectVersion`.
**Fix:** Added the version action for the exact artifact ARN, validated Terraform, and rolled a new instance.
**Outcome:** Immutable version-pinned application downloads succeeded.

### 2. RDS stopped during validation

**Symptom:** RDS transitioned to `stopping`/`stopped`; application readiness failed.
**Evidence:** RDS events showed no engine/storage failure, and Terraform had not requested destruction. The behavior was external to the application and consistent with student-lab administrative controls.
**Action:** Waited for a stable stopped state, restarted only `cloud-portfolio-lab-mysql`, and observed its normal startup. The environment subsequently stopped it again.
**Outcome:** The event became a controlled dependency-outage test rather than an unclassified failure.

### 3. ASG replacement could not boot while RDS was unavailable

**Symptom:** ALB reported `Target.Timeout` and then `Target.ResponseCodeMismatch`; Gunicorn workers exited.
**Diagnosis:** SSM logs showed `pymysql.err.OperationalError (2003)` during synchronous `initialize_schema()` in the Flask factory.
**Fix:** Decoupled process startup from RDS, added bounded exponential schema retries, explicit database-availability state, fast aggregate fallback, and correct `/health` versus `/ready` behavior.
**Outcome:** Launch Template v5 passed the ALB health check and completed the ASG replacement while RDS remained stopped.

### 4. Protected API returned a browser redirect

**Symptom:** Unauthenticated `/api/appointments` returned `302` to login.
**Cause:** One authentication decorator served both HTML and JSON routes.
**Fix:** API paths now return JSON `401`; browser routes retain the login redirect.
**Outcome:** Correct machine-readable API contract verified locally and live.

### 5. Test-shell reserved variables

**Symptom:** A zsh loop lost access to commands after assigning `path`; a later loop failed assigning `status`.
**Cause:** `path` and `status` are special zsh variables.
**Fix:** Renamed them to `route_path` and `db_state`.
**Outcome:** Harness corrected; no application code was implicated.

### 6. Terraform provider validation failed inside the restricted sandbox

**Symptom:** provider schema handshake failed although provider binaries matched arm64 and were executable.
**Cause:** execution restriction in the local tool sandbox.
**Fix:** Re-ran the same validation in the authorized execution context.
**Outcome:** `terraform validate` succeeded.

### 7. Mock readiness test used a nonexistent CA file

**Symptom:** local degraded-mode test raised `FileNotFoundError` instead of the expected MySQL exception.
**Cause:** incomplete test fixture; production bootstrap installs the CA bundle.
**Fix:** Mocked `pymysql.connect` at the database boundary.
**Outcome:** fast degraded startup, `503` readiness, and JSON `401` tests passed.

### 8. Transient local AWS endpoint/HTTP connectivity

**Symptom:** isolated AWS CLI endpoint failures and one HTTP probe hung while AWS resources remained healthy.
**Fix:** Added strict connect/overall timeouts, retried read-only checks, and correlated with ALB/ASG health.
**Outcome:** AWS target remained healthy; later probes succeeded. This was classified as test-client connectivity rather than an application outage.

### 9. Final Terraform plan initially could not refresh SSO credentials

**Symptom:** the first final plan could not resolve `portal.sso.us-east-1.amazonaws.com` and reported no valid credential source.
**Cause:** transient local DNS/network failure while refreshing the cached SSO role credentials.
**Fix:** Retried with `AWS_PROFILE=school645` explicitly set after connectivity recovered.
**Outcome:** Terraform returned exit code `0` and **No changes**, proving deployed infrastructure matched configuration.

## Commands used as evidence

```bash
python3 -m py_compile application/app.py
node --check application/static/app.js
bash -n user_data.sh
terraform fmt -check
terraform validate
terraform plan

curl --connect-timeout 5 --max-time 15 http://$ALB/health
curl --connect-timeout 5 --max-time 15 http://$ALB/ready
ab -n 100 -c 5 http://$ALB/health
ab -n 50 -c 2 http://$ALB/

aws sts get-caller-identity --profile school645
aws autoscaling describe-instance-refreshes --profile school645 --region us-east-2
aws autoscaling describe-auto-scaling-groups --profile school645 --region us-east-2
aws elbv2 describe-target-health --profile school645 --region us-east-2
aws ssm describe-instance-information --profile school645 --region us-east-2
aws cloudwatch describe-alarms --profile school645 --region us-east-2
aws rds describe-db-instances --profile school645 --region us-east-2
```

No secret value was printed or copied into this report.

## Interview talking points

1. I tested failure behavior, not only the happy path. An RDS stop exposed process/dependency coupling during an immutable ASG rollout.
2. I separated liveness from readiness so the load balancer evaluates the web process while operators can independently see database health.
3. I diagnosed private instances through SSM instead of adding SSH or public IP addresses.
4. I used versioned S3 artifacts and explicit Launch Template versions to make deployments reproducible and auditable.
5. I verified trust boundaries and least privilege at runtime, including IMDSv2, private EC2/RDS, secret-scoped IAM, TLS, encryption, and blocked public S3 access.
6. I treated benchmark anomalies as hypotheses: dynamic response length explained ApacheBench warnings, and AWS health evidence separated client connectivity from service health.

## Remaining production-hardening roadmap

- Configure a real domain, ACM certificate, HTTPS redirect, HSTS, and `Secure` cookies.
- Add WAF managed rules, rate limiting, centralized access/application logs, and distributed tracing.
- Move schema migration into a controlled one-time deployment job rather than per-worker initialization.
- Use RDS Proxy or application connection pooling and tune Gunicorn with representative load.
- Add automated pytest integration tests and a CI pipeline with dependency, IaC, and secret scanning.
- Add analytics retention/deletion policy and a user-facing privacy notice.
- Use an encrypted remote Terraform backend with locking.
- Run sustained load, AZ-failure, and Multi-AZ database-failover tests in HA mode.
