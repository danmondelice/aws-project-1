resource "aws_security_group" "alb" {
  name        = "${local.name_prefix}-alb-sg"
  description = "Allow web traffic to the Application Load Balancer"
  vpc_id      = aws_vpc.main.id


  ingress {
    description = "HTTP from internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  dynamic "ingress" {
    for_each = var.acm_certificate_arn == null ? [] : [1]

    content {
      description = "HTTPS from internet"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }


  egress {
    description = "HTTP to private application subnets"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = [
      "10.20.1.0/24",
      "10.20.2.0/24"
    ]
  }


  tags = {
    Name = "${local.name_prefix}-alb-sg"
  }
}


resource "aws_security_group" "app" {
  name        = "${local.name_prefix}-app-sg"
  description = "Allow application traffic only from the ALB"
  vpc_id      = aws_vpc.main.id


  ingress {
    description     = "HTTP from ALB"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }


  egress {
    description = "HTTPS for package repositories and AWS service APIs"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "MySQL to private database subnets"
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = ["10.20.3.0/26"]
  }


  tags = {
    Name = "${local.name_prefix}-app-sg"
  }
}


resource "aws_security_group" "database" {
  name        = "${local.name_prefix}-db-sg"
  description = "Allow database traffic only from application instances"
  vpc_id      = aws_vpc.main.id


  ingress {
    description     = "MySQL from application tier"
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }


  egress = []


  tags = {
    Name = "${local.name_prefix}-db-sg"
  }
}
