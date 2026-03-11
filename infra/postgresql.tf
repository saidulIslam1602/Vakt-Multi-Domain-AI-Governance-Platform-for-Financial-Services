# Azure Database for PostgreSQL Flexible Server

resource "azurerm_postgresql_flexible_server" "main" {
  name                         = "${local.prefix}-pg"
  resource_group_name          = azurerm_resource_group.main.name
  location                     = local.location
  version                      = "16"
  administrator_login          = "allergoadmin"
  administrator_password       = var.postgres_admin_password
  storage_mb                   = 32768
  sku_name                     = var.environment == "prod" ? "GP_Standard_D2s_v3" : "B_Standard_B1ms"
  backup_retention_days        = 7
  geo_redundant_backup_enabled = var.environment == "prod"
  zone                         = "1"
  tags                         = local.tags
}

resource "azurerm_postgresql_flexible_server_database" "allergo" {
  name      = "allergo"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "utf8"
}

resource "azurerm_postgresql_flexible_server_configuration" "pgvector" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "VECTOR,UUID-OSSP,PG_TRGM,PGCRYPTO"
}

# Firewall: allow Azure services
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}
