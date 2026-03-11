output "ingest_service_url" {
  value = "https://${azurerm_container_app.ingest.ingress[0].fqdn}"
}

output "document_service_url" {
  value = "https://${azurerm_container_app.document.ingress[0].fqdn}"
}

output "search_service_url" {
  value = "https://${azurerm_container_app.search.ingress[0].fqdn}"
}

output "chat_service_url" {
  value = "https://${azurerm_container_app.chat.ingress[0].fqdn}"
}

output "frontend_url" {
  value = "https://${azurerm_container_app.frontend.ingress[0].fqdn}"
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "postgres_fqdn" {
  value = azurerm_postgresql_flexible_server.main.fqdn
}

output "key_vault_name" {
  description = "Name of the Azure Key Vault — set as GitHub repo variable KEY_VAULT_NAME."
  value       = azurerm_key_vault.main.name
}
