output "vpc_id" {
  description = "ID of the project VPC"
  value       = aws_vpc.main.id
}


output "vpc_cidr" {
  description = "CIDR block of the project VPC"
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value = [
    aws_subnet.public_az1.id,
    aws_subnet.public_az2.id
  ]
}


output "application_subnet_ids" {
  description = "Private application subnet IDs"
  value = [
    aws_subnet.app_az1.id,
    aws_subnet.app_az2.id
  ]
}


output "database_subnet_ids" {
  description = "Private database subnet IDs"
  value = [
    aws_subnet.db_az1.id,
    aws_subnet.db_az2.id
  ]
}

output "alb_security_group_id" {
  description = "Security group used by the Application Load Balancer"
  value       = aws_security_group.alb.id
}


output "app_security_group_id" {
  description = "Security group used by the application tier"
  value       = aws_security_group.app.id
}


output "database_security_group_id" {
  description = "Security group used by the database tier"
  value       = aws_security_group.database.id
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.app.dns_name
}


output "target_group_arn" {
  description = "ARN of the application target group"
  value       = aws_lb_target_group.app.arn
}

output "autoscaling_group_name" {
  description = "Name of the application Auto Scaling Group"
  value       = aws_autoscaling_group.app.name
}

output "sns_alert_topic_arn" {
  description = "SNS topic used for infrastructure alerts"
  value       = aws_sns_topic.alerts.arn
}

output "database_endpoint" {
  description = "Connection endpoint for the RDS database"
  value       = aws_db_instance.main.address
}

output "database_port" {
  description = "Connection port for the RDS database"
  value       = aws_db_instance.main.port
}

output "database_name" {
  description = "Name of the initial application database"
  value       = aws_db_instance.main.db_name
}

output "database_secret_arn" {
  description = "ARN of the RDS-managed Secrets Manager secret"
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
}
