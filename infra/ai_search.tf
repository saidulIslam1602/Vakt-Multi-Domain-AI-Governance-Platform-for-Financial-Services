# Azure AI Search — full-text + vector search

resource "azurerm_search_service" "main" {
  name                = "${local.prefix}-search"
  resource_group_name = azurerm_resource_group.main.name
  location            = local.location
  sku                 = var.environment == "prod" ? "standard" : "basic"
  replica_count       = var.environment == "prod" ? 2 : 1
  partition_count     = 1
  semantic_search_sku = "free"
  tags                = local.tags
}
