# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# #########################################################
# Self-Signed Certificate for ALB HTTPS
# #########################################################

resource "tls_private_key" "alb" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "tls_self_signed_cert" "alb" {
  private_key_pem = tls_private_key.alb.private_key_pem

  subject {
    common_name  = aws_lb.ecs_alb.dns_name
    organization = "Bedrock Gateway"
  }

  validity_period_hours = 87600 # 10 years

  allowed_uses = [
    "key_encipherment",
    "digital_signature",
    "server_auth",
  ]
}

resource "aws_acm_certificate" "alb" {
  private_key      = tls_private_key.alb.private_key_pem
  certificate_body = tls_self_signed_cert.alb.cert_pem

  tags = var.common_tags

  lifecycle {
    create_before_destroy = true
  }
}

# #########################################################
# ALB configuration for ECS
# #########################################################

resource "aws_lb" "ecs_alb" {
  #checkov:skip=CKV2_AWS_76: "Log4j protection not required for this application stack"
  #checkov:skip=CKV2_AWS_28: "Ensure public facing ALB are protected by WAF"
  #checkov:skip=CKV_AWS_91: "ALB access logging enabled"
  #checkov:skip=CKV2_AWS_20: "ALB uses HTTPS for public communication"
  name                       = local.alb_name
  internal                   = false
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.ecs_alb_security_group.id]
  subnets                    = aws_subnet.public[*].id
  enable_deletion_protection = true
  idle_timeout               = 4000
  drop_invalid_header_fields = true

  access_logs {
    bucket  = module.alb_s3_bucket_for_logs.s3_bucket_id
    enabled = true
  }

  tags = var.common_tags
}

# HTTPS listener
resource "aws_lb_listener" "ecs_listener_https" {
  load_balancer_arn = aws_lb.ecs_alb.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-Res-2021-06"
  certificate_arn   = aws_acm_certificate.alb.arn

  mutual_authentication {
    mode                             = var.mtls_cert_ca_s3_path != "" ? "verify" : "off"
    trust_store_arn                  = var.mtls_cert_ca_s3_path != "" ? aws_lb_trust_store.mtls_trust_store[0].arn : null
    ignore_client_certificate_expiry = var.mtls_cert_ca_s3_path != "" ? false : null
  }

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.ecs_target_group.arn
  }
}

# HTTP to HTTPS redirect
resource "aws_lb_listener" "ecs_listener_http_redirect" {
  load_balancer_arn = aws_lb.ecs_alb.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# #########################################################
# Target Group
# #########################################################

resource "aws_lb_target_group" "ecs_target_group" {
  name        = local.alb_target_group_name
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    matcher             = "200"
  }

  tags = var.common_tags
}

# #########################################################
# Security Group
# #########################################################

resource "aws_security_group" "ecs_alb_security_group" {
  #checkov:skip=CKV_AWS_260: "Port 80 allowed for HTTPS redirect"
  name        = local.alb_security_group_name
  description = "Security group for ECS ALB"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow HTTPS traffic"
  }

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow HTTP traffic for redirect"
  }

  egress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
    description = "Allow traffic to ECS tasks"
  }

  tags = var.common_tags
}

# #########################################################
# mTLS Trust Store Configuration
# #########################################################

resource "aws_lb_trust_store" "mtls_trust_store" {
  count                            = var.mtls_cert_ca_s3_path != "" ? 1 : 0
  name                             = "${local.alb_name}-mtls"
  ca_certificates_bundle_s3_bucket = split("/", replace(var.mtls_cert_ca_s3_path, "s3://", ""))[0]
  ca_certificates_bundle_s3_key    = join("/", slice(split("/", replace(var.mtls_cert_ca_s3_path, "s3://", "")), 1, length(split("/", replace(var.mtls_cert_ca_s3_path, "s3://", "")))))

  tags = var.common_tags
}

# #########################################################
# S3 ALB log bucket definition
# #########################################################

module "alb_s3_bucket_for_logs" {
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-s3-bucket.git?ref=f90d8a385e4c70afd048e8997dcccf125b362236"

  bucket = local.alb_s3_bucket_name

  force_destroy = true

  control_object_ownership = true
  object_ownership         = "ObjectWriter"

  attach_elb_log_delivery_policy = true
  attach_lb_log_delivery_policy  = true
}
