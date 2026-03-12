variable "environment" {
  type        = string
  description = "Deployment environment: dev | staging | prod"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod"
  }
}

variable "location" {
  type        = string
  default     = "norwayeast"
  description = "Azure region"
}

variable "postgres_admin_password" {
  type        = string
  sensitive   = true
  description = "PostgreSQL flexible server admin password"
}

variable "azure_openai_location" {
  type        = string
  default     = "swedencentral"
  description = "Azure OpenAI is region-specific; Sweden Central has GPT-4o"
}

variable "nextauth_secret" {
  type        = string
  sensitive   = true
  description = "NextAuth.js secret for session signing (min 32 chars)"
}

variable "smtp_password" {
  type        = string
  sensitive   = true
  default     = ""
  description = "SMTP account password for contract renewal email notifications"
}

variable "imap_password" {
  type        = string
  sensitive   = true
  default     = ""
  description = "IMAP account password for email document ingestion"
}

variable "db_encryption_key" {
  type        = string
  sensitive   = true
  description = "32-byte hex key for AES encryption of IMAP passwords in DB. Generate: python3 -c \"import secrets; print(secrets.token_hex(32))\""
}

variable "openai_api_key" {
  type        = string
  sensitive   = true
  description = "Azure OpenAI API key — required when the resource has no custom subdomain (regional endpoint). Retrieve: az cognitiveservices account keys list -g <rg> -n <name> --query key1 -o tsv"
}
