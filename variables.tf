variable "aws_region" {
  description = "AWS region for the deployment"
  type        = string
  default     = "us-east-2"
}


variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "cloud-portfolio"
}


variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "lab"
}


variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.20.0.0/21"


  validation {
    condition     = var.vpc_cidr == "10.20.0.0/21"
    error_message = "This portfolio architecture currently requires vpc_cidr to be 10.20.0.0/21 because its subnet CIDRs are explicitly capacity-planned within this range."
  }
}


variable "ha_mode" {
  description = "Enable production-style high availability resources"
  type        = bool
  default     = false
}

variable "instance_type" {
  description = "EC2 instance type for the application tier"
  type        = string
  default     = "t3.micro"
}


variable "asg_min_size" {
  description = "Minimum number of application instances"
  type        = number
  default     = 1
}


variable "asg_desired_capacity" {
  description = "Desired number of application instances"
  type        = number
  default     = 1
}


variable "asg_max_size" {
  description = "Maximum number of application instances"
  type        = number
  default     = 2
}

variable "db_instance_class" {
  description = "RDS instance class for the database tier"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "Initial RDS storage allocation in GiB"
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Maximum RDS storage allocation for autoscaling in GiB"
  type        = number
  default     = 100
}

variable "db_name" {
  description = "Initial MySQL database name"
  type        = string
  default     = "portfolio"
}

variable "db_username" {
  description = "Master username for the MySQL database"
  type        = string
  default     = "dbadmin"
}
