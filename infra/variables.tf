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
