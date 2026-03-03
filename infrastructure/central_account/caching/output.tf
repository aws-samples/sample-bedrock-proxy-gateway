output "valkey_endpoint" {
  value = aws_elasticache_serverless_cache.sts_cache.endpoint
}
