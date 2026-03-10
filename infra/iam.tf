# IAM — role assignments for managed identities

# ACR pull for all Container Apps
locals {
  container_apps = {
    ingest     = azurerm_container_app.ingest
    processing = azurerm_container_app.processing
    document   = azurerm_container_app.document
    search     = azurerm_container_app.search
    chat       = azurerm_container_app.chat
    frontend   = azurerm_container_app.frontend
  }
}

resource "azurerm_role_assignment" "acr_pull" {
  for_each = local.container_apps

  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = each.value.identity[0].principal_id
}

# Azure OpenAI — Cognitive Services User for processing, search, chat
resource "azurerm_role_assignment" "openai_user" {
  for_each = {
    processing = azurerm_container_app.processing
    search     = azurerm_container_app.search
    chat       = azurerm_container_app.chat
  }

  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = each.value.identity[0].principal_id
}

# Azure AI Search — Search Index Data Reader for search and chat
resource "azurerm_role_assignment" "search_data_reader" {
  for_each = {
    search = azurerm_container_app.search
    chat   = azurerm_container_app.chat
  }

  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Index Data Reader"
  principal_id         = each.value.identity[0].principal_id
}

# Azure AI Search — Search Index Data Contributor for the processing worker (writes chunks)
resource "azurerm_role_assignment" "search_data_contributor" {
  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = azurerm_container_app.processing.identity[0].principal_id
}

# Blob Storage — Storage Blob Data Contributor for ingest (upload) and processing (download + upload)
resource "azurerm_role_assignment" "blob_contributor" {
  for_each = {
    ingest     = azurerm_container_app.ingest
    processing = azurerm_container_app.processing
  }

  scope                = azurerm_storage_account.docs.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = each.value.identity[0].principal_id
}

# Blob Storage Delegator — required for user-delegation SAS URL generation
resource "azurerm_role_assignment" "blob_delegator" {
  scope                = azurerm_storage_account.docs.id
  role_definition_name = "Storage Blob Delegator"
  principal_id         = azurerm_container_app.ingest.identity[0].principal_id
}

# Service Bus — Data Sender for ingest, Data Receiver for processing
resource "azurerm_role_assignment" "sb_sender" {
  scope                = azurerm_servicebus_namespace.main.id
  role_definition_name = "Azure Service Bus Data Sender"
  principal_id         = azurerm_container_app.ingest.identity[0].principal_id
}

resource "azurerm_role_assignment" "sb_receiver" {
  scope                = azurerm_servicebus_namespace.main.id
  role_definition_name = "Azure Service Bus Data Receiver"
  principal_id         = azurerm_container_app.processing.identity[0].principal_id
}
