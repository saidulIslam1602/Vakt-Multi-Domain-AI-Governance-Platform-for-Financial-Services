# Azure Key Vault — centralised secret management
#
# ALL sensitive runtime values (DB passwords, SMTP credentials, IMAP password,
# NextAuth secret) are stored here instead of as plain-text Container App env
# vars.  Each Container App has a System-Assigned Managed Identity with the
# "Key Vault Secrets User" role scoped to this vault — no static credentials
# needed anywhere.
#
# Secret references in container_apps.tf use the pattern:
#   secretRef → Container App secret referencing this KV secret URI
#   env var   → secretRef pointing at the Container App secret

data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "main" {
  name                       = "${local.prefix}-kv"
  location                   = local.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 90
  purge_protection_enabled   = true # prevents accidental / malicious permanent deletion

  # Public network access is ENABLED so that the GitHub Actions runner
  # (a public IP) can call `az keyvault secret show` during the migrate-db
  # step.  AzureServices bypass is kept so Container Apps and Terraform can
  # always reach the vault regardless of IP.  For a production hardening pass,
  # replace this with a self-hosted runner inside a VNET and flip back to
  # public_network_access_enabled = false + network_acls default_action = "Deny".
  public_network_access_enabled = true

  network_acls {
    default_action = "Allow"
    bypass         = "AzureServices"
  }

  # RBAC authorisation model (preferred over legacy access policies)
  enable_rbac_authorization = true

  tags = local.tags
}

# ── Secrets ────────────────────────────────────────────────────────────────────

resource "azurerm_key_vault_secret" "postgres_password" {
  name         = "postgres-admin-password"
  value        = var.postgres_admin_password
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.tags

  depends_on = [azurerm_key_vault.main]
}

# Full DATABASE_URL — composed here so services never need to know the raw
# password.  Container Apps pull this via secretRef at runtime.
#
# If the secret already exists in the vault (created out-of-band or by a
# previous partial apply), import it into state before applying:
#   terraform import azurerm_key_vault_secret.database_url \
#     "https://allergodev-kv.vault.azure.net/secrets/database-url/e14f8b221c734402abb81fe993d88ca1"
import {
  to = azurerm_key_vault_secret.database_url
  id = "https://allergodev-kv.vault.azure.net/secrets/database-url/e14f8b221c734402abb81fe993d88ca1"
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  value        = "postgresql://allergoadmin:${urlencode(var.postgres_admin_password)}@${azurerm_postgresql_flexible_server.main.fqdn}:5432/allergo?sslmode=require"
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.tags
}

resource "azurerm_key_vault_secret" "nextauth_secret" {
  name         = "nextauth-secret"
  value        = var.nextauth_secret
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.tags

  depends_on = [azurerm_key_vault.main]
}

# SMTP password — stored in KV; injected into processing-service at runtime.
# Set the actual value via:
#   az keyvault secret set --vault-name <kv-name> --name smtp-password --value "<pass>"
resource "azurerm_key_vault_secret" "smtp_password" {
  name         = "smtp-password"
  value        = var.smtp_password
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.tags

  depends_on = [azurerm_key_vault.main]
}

# IMAP password — stored in KV; injected into ingest-service at runtime.
resource "azurerm_key_vault_secret" "imap_password" {
  name         = "imap-password"
  value        = var.imap_password
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.tags

  depends_on = [azurerm_key_vault.main]
}

# DB encryption key — used by ingest-service to AES-encrypt IMAP passwords
# stored in email_ingest_configs.  Required by PostgresEmailConfigRepository.
# Generate: python3 -c "import secrets; print(secrets.token_hex(32))"
import {
  to = azurerm_key_vault_secret.db_encryption_key
  id = "https://allergodev-kv.vault.azure.net/secrets/allergo-db-encryption-key/83f2e6b0bf3947b58bb4e382f7818863"
}

resource "azurerm_key_vault_secret" "db_encryption_key" {
  name         = "allergo-db-encryption-key"
  value        = var.db_encryption_key
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.tags

  depends_on = [azurerm_key_vault.main]
}

# Azure OpenAI API key — used by chat-service and processing-service when the
# resource has no custom subdomain (regional endpoint requires key auth).
# Retrieve: az cognitiveservices account keys list -g <rg> -n <name> --query key1 -o tsv
import {
  to = azurerm_key_vault_secret.openai_api_key
  id = "https://allergodev-kv.vault.azure.net/secrets/openai-api-key/1cef041f1cd548a98546a66a15b9f4d1"
}

resource "azurerm_key_vault_secret" "openai_api_key" {
  name         = "openai-api-key"
  value        = var.openai_api_key
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.tags

  depends_on = [azurerm_key_vault.main]
}

# Azure AI Search admin key — required when the search service is configured
# with authOptions=apiKeyOnly (the default). Used by chat-service and
# processing-service for vector search and index management.
# Retrieve: az search admin-key show --service-name <name> -g <rg> --query primaryKey -o tsv
import {
  to = azurerm_key_vault_secret.search_api_key
  id = "https://allergodev-kv.vault.azure.net/secrets/azure-search-key/65c3502090674513abbedb15d79e5eb8"
}

resource "azurerm_key_vault_secret" "search_api_key" {
  name         = "azure-search-key"
  value        = var.search_api_key
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.tags

  depends_on = [azurerm_key_vault.main]
}

# ── RBAC: pipeline (OIDC) must be bootstrapped MANUALLY by a subscription Owner ─
#
# The pipeline SP only holds Contributor on the subscription — it cannot create
# role assignments (Microsoft.Authorization/roleAssignments/write) anywhere.
# A subscription Owner must run the following TWO commands ONCE before the first
# `terraform apply` that touches Key Vault:
#
#   PIPELINE_OID=$(az ad sp show --id <AZURE_CLIENT_ID> --query id -o tsv)
#   KV_ID=$(az keyvault show -n allergodev-kv -g allergo_business_case --query id -o tsv)
#
#   # 1. Let the pipeline write/read secrets (needed for terraform apply to store secrets)
#   az role assignment create \
#     --assignee-object-id "$PIPELINE_OID" \
#     --assignee-principal-type ServicePrincipal \
#     --role "Key Vault Secrets Officer" \
#     --scope "$KV_ID"
#
#   # 2. Let the pipeline assign "Key Vault Secrets User" to managed identities
#   #    (needed so Terraform can create the kv_secrets_user_* assignments below)
#   az role assignment create \
#     --assignee-object-id "$PIPELINE_OID" \
#     --assignee-principal-type ServicePrincipal \
#     --role "User Access Administrator" \
#     --scope "$KV_ID"
#
# Both roles are scoped ONLY to the KV resource — not subscription-wide.
# This is intentionally NOT managed by Terraform to avoid the chicken-and-egg
# bootstrap problem where Terraform cannot grant itself the permission it needs.

# ── RBAC: each Container App managed identity can READ secrets ────────────────

resource "azurerm_role_assignment" "kv_secrets_user_ingest" {
  scope                            = azurerm_key_vault.main.id
  role_definition_name             = "Key Vault Secrets User"
  principal_id                     = azurerm_container_app.ingest.identity[0].principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "kv_secrets_user_processing" {
  scope                            = azurerm_key_vault.main.id
  role_definition_name             = "Key Vault Secrets User"
  principal_id                     = azurerm_container_app.processing.identity[0].principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "kv_secrets_user_document" {
  scope                            = azurerm_key_vault.main.id
  role_definition_name             = "Key Vault Secrets User"
  principal_id                     = azurerm_container_app.document.identity[0].principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "kv_secrets_user_search" {
  scope                            = azurerm_key_vault.main.id
  role_definition_name             = "Key Vault Secrets User"
  principal_id                     = azurerm_container_app.search.identity[0].principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "kv_secrets_user_chat" {
  scope                            = azurerm_key_vault.main.id
  role_definition_name             = "Key Vault Secrets User"
  principal_id                     = azurerm_container_app.chat.identity[0].principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "kv_secrets_user_frontend" {
  scope                            = azurerm_key_vault.main.id
  role_definition_name             = "Key Vault Secrets User"
  principal_id                     = azurerm_container_app.frontend.identity[0].principal_id
  skip_service_principal_aad_check = true
}

# ── Outputs (URIs used as secretRef values in container_apps.tf) ─────────────

output "kv_database_url_secret_uri" {
  description = "Versioned Key Vault secret URI for the full DATABASE_URL connection string."
  value       = azurerm_key_vault_secret.database_url.id
  sensitive   = true
}

output "kv_postgres_password_secret_uri" {
  description = "Versioned Key Vault secret URI for the raw postgres admin password."
  value       = azurerm_key_vault_secret.postgres_password.id
  sensitive   = true
}

output "kv_smtp_secret_uri" {
  value     = azurerm_key_vault_secret.smtp_password.id
  sensitive = true
}

output "kv_imap_secret_uri" {
  value     = azurerm_key_vault_secret.imap_password.id
  sensitive = true
}
