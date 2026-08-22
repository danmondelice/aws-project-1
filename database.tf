resource "aws_db_subnet_group" "main" {
  name = "${local.name_prefix}-db-subnet-group"

  subnet_ids = [
    aws_subnet.db_az1.id,
    aws_subnet.db_az2.id
  ]

  tags = {
    Name = "${local.name_prefix}-db-subnet-group"
  }
}

resource "aws_db_parameter_group" "mysql" {
  name   = "${local.name_prefix}-mysql-tls"
  family = "mysql8.4"

  parameter {
    name  = "require_secure_transport"
    value = "1"
  }

  tags = {
    Name = "${local.name_prefix}-mysql-tls"
  }
}

resource "aws_db_instance" "main" {
  identifier = "${local.name_prefix}-mysql"

  engine         = "mysql"
  engine_version = "8.4.9"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username

  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  parameter_group_name   = aws_db_parameter_group.mysql.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = false
  multi_az               = var.ha_mode

  backup_retention_period    = var.ha_mode ? 7 : 1
  copy_tags_to_snapshot      = true
  auto_minor_version_upgrade = true

  deletion_protection       = var.ha_mode
  skip_final_snapshot       = !var.ha_mode
  final_snapshot_identifier = var.ha_mode ? "${local.name_prefix}-mysql-final" : null
  apply_immediately         = true

  monitoring_interval = var.ha_mode ? 60 : 0
  monitoring_role_arn = var.ha_mode ? aws_iam_role.rds_enhanced_monitoring.arn : null

  tags = {
    Name = "${local.name_prefix}-mysql"
    Tier = "database"
  }
}

resource "aws_iam_role_policy" "database_secret_access" {
  name = "${local.name_prefix}-database-secret-access"
  role = aws_iam_role.ec2_ssm.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "ReadDatabaseCredentials"
      Effect   = "Allow"
      Action   = "secretsmanager:GetSecretValue"
      Resource = aws_db_instance.main.master_user_secret[0].secret_arn
    }]
  })
}
