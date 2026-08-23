data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]


  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }


  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}


resource "aws_launch_template" "app" {
  name_prefix   = "${local.name_prefix}-app-"
  image_id      = data.aws_ami.amazon_linux.id
  instance_type = var.instance_type


  iam_instance_profile {
    name = aws_iam_instance_profile.ec2.name
  }


  vpc_security_group_ids = [
    aws_security_group.app.id
  ]


  block_device_mappings {
    device_name = "/dev/xvda"


    ebs {
      volume_size           = 8
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }


  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    application_bucket    = aws_s3_bucket.application_artifacts.id
    application_key       = aws_s3_object.application.key
    application_version   = aws_s3_object.application.version_id
    aws_region            = var.aws_region
    database_host         = aws_db_instance.main.address
    database_name         = aws_db_instance.main.db_name
    database_port         = aws_db_instance.main.port
    database_secret_arn   = aws_db_instance.main.master_user_secret[0].secret_arn
    session_cookie_secure = var.acm_certificate_arn == null ? "false" : "true"
  }))


  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }


  tag_specifications {
    resource_type = "instance"


    tags = {
      Name = "${local.name_prefix}-app"
      Tier = "application"
    }
  }


  tags = {
    Name = "${local.name_prefix}-launch-template"
  }
}

resource "aws_autoscaling_group" "app" {
  name = "${local.name_prefix}-asg"


  min_size         = var.ha_mode ? 2 : var.asg_min_size
  desired_capacity = var.ha_mode ? 2 : var.asg_desired_capacity
  max_size         = var.ha_mode ? 4 : var.asg_max_size


  vpc_zone_identifier = [
    aws_subnet.app_az1.id,
    aws_subnet.app_az2.id
  ]


  target_group_arns = [
    aws_lb_target_group.app.arn
  ]


  health_check_type         = "ELB"
  health_check_grace_period = 180
  default_instance_warmup   = 180


  launch_template {
    id      = aws_launch_template.app.id
    version = aws_launch_template.app.latest_version
  }


  instance_refresh {
    strategy = "Rolling"


    preferences {
      min_healthy_percentage = 50
    }
  }


  tag {
    key                 = "Name"
    value               = "${local.name_prefix}-app"
    propagate_at_launch = true
  }


  depends_on = [
    aws_route_table_association.app_az1,
    aws_route_table_association.app_az2,
    aws_iam_role_policy.application_artifact_access,
    aws_iam_role_policy.database_secret_access
  ]
}
