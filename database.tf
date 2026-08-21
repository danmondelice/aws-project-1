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

resource "aws_db_instance" "main" {
  identifier = "${local.name_prefix}-mysql"

  engine         = "mysql"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username

  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
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
