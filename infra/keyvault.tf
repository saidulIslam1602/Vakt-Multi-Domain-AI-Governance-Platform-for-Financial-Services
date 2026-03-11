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
  name                        = "${local.prefix}-kv"
  location                    = local.location
  resource_group_name         = azurerm_resource_group.main.name
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  sku_name                    = "standard"
  soft_delete_retention_days  = 90
  purge_protection_enabled    = true   # prevents accidental / malicious permanent deletion

  # Disable public network access — only Azure services and the pipeline OIDC
  # identity can reach the vault.
  public_network_access_enabled = false

  network_acls {
    default_action = "Deny"
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

  depends_on = [
    azurerm_role_assignment.kv_secrets_officer_pipeline,
  ]
}

# Full DATABASE_URL — composed here so services never need to know the raw
# password.  Container Apps pull this via secretRef at runtime.
resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  value        = "postgresql://allergoadmin:${var.postgres_admin_password}@${azurerm_postgresql_flexible_server.main.fqdn}:5432/allergo?sslmode=require"
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.tags

  depends_on = [
    azurerm_role_assignment.kv_secrets_officer_pipeline,
  ]
}

resource "azurerm_key_vault_secret" "nextauth_secret" {
  name         = "nextauth-secret"
  value        = var.nextauth_secret
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.tags

  depends_on = [
    azurerm_role_assignment.kv_secrets_officer_pipeline,
  ]
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

  depends_on = [
    azurerm_role_assignment.kv_secrets_officer_pipeline,
  ]
}

# IMAP password — stored in KV; injected into ingest-service at runtime.
resource "azurerm_key_vault_secret" "imap_password" {
  name         = "imap-password"
  value        = var.imap_password
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.tags

  depends_on = [
    azurerm_role_assignment.kv_secrets_officer_pipeline,
  ]
}

# ── RBAC: pipeline (OIDC) can write secrets during terraform apply ─────────────

resource "azurerm_role_assignment" "kv_secrets_officer_pipeline" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# ── RBAC: each Container App managed identity can READ secrets ────────────────

resource "azurerm_role_assignment" "kv_secrets_user_ingest" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_container_app.ingest.identity[0].principal_id
}

resource "azurerm_role_assignment" "kv_secrets_user_processing" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_container_app.processing.identity[0].principal_id
}

resource "azurerm_role_assignment" "kv_secrets_user_document" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_container_app.document.identity[0].principal_id
}

resource "azurerm_role_assignment" "kv_secrets_user_search" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_container_app.search.identity[0].principal_id
}

resource "azurerm_role_assignment" "kv_secrets_user_chat" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_container_app.chat.identity[0].principal_id
}

resource "azurerm_role_assignment" "kv_secrets_user_frontend" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_container_app.frontend.identity[0].principal_id
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
