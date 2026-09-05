resource "aws_secretsmanager_secret" "rds_secret" {
  name                    = "pdeue/rds_url"
  recovery_window_in_days = 0
  tags = { Environment = var.environment }
}

resource "aws_secretsmanager_secret" "hmac_secret" {
  name                    = "pdeue/hmac_key"
  recovery_window_in_days = 0
  tags = { Environment = var.environment }
}
