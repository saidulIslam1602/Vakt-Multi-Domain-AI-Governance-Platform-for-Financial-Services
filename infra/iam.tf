# IAM — role assignments for managed identities
# Note: Individual assignments (not for_each over resources) to avoid Terraform
# "empty identity list" plan-time errors with azurerm Container Apps.

# ── ACR Pull — all Container Apps need to pull images ─────────────────────────
resource "azurerm_role_assignment" "acr_pull_ingest" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_container_app.ingest.identity[0].principal_id
}

resource "azurerm_role_assignment" "acr_pull_processing" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_container_app.processing.identity[0].principal_id
}

resource "azurerm_role_assignment" "acr_pull_document" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_container_app.document.identity[0].principal_id
}

resource "azurerm_role_assignment" "acr_pull_search" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_container_app.search.identity[0].principal_id
}

resource "azurerm_role_assignment" "acr_pull_chat" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_container_app.chat.identity[0].principal_id
}

resource "azurerm_role_assignment" "acr_pull_frontend" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_container_app.frontend.identity[0].principal_id
}

# ── Azure OpenAI — Cognitive Services User ────────────────────────────────────
resource "azurerm_role_assignment" "openai_user_processing" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_container_app.processing.identity[0].principal_id
}

resource "azurerm_role_assignment" "openai_user_search" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_container_app.search.identity[0].principal_id
}

resource "azurerm_role_assignment" "openai_user_chat" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_container_app.chat.identity[0].principal_id
}

# ── Azure AI Search — Search Index Data Reader ────────────────────────────────
resource "azurerm_role_assignment" "search_reader_search" {
  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Index Data Reader"
  principal_id         = azurerm_container_app.search.identity[0].principal_id
}

resource "azurerm_role_assignment" "search_reader_chat" {
  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Index Data Reader"
  principal_id         = azurerm_container_app.chat.identity[0].principal_id
}

# ── Azure AI Search — Search Index Data Contributor (processing writes chunks) ─
resource "azurerm_role_assignment" "search_contributor_processing" {
  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = azurerm_container_app.processing.identity[0].principal_id
}

# ── Blob Storage — Data Contributor ──────────────────────────────────────────
resource "azurerm_role_assignment" "blob_contributor_ingest" {
  scope                = azurerm_storage_account.docs.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_container_app.ingest.identity[0].principal_id
}

resource "azurerm_role_assignment" "blob_contributor_processing" {
  scope                = azurerm_storage_account.docs.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_container_app.processing.identity[0].principal_id
}

# ── Blob Storage — Delegator (for user-delegation SAS in ingest) ──────────────
resource "azurerm_role_assignment" "blob_delegator_ingest" {
  scope                = azurerm_storage_account.docs.id
  role_definition_name = "Storage Blob Delegator"
  principal_id         = azurerm_container_app.ingest.identity[0].principal_id
}

# ── Service Bus — Sender (ingest publishes events) ────────────────────────────
resource "azurerm_role_assignment" "sb_sender_ingest" {
  scope                = azurerm_servicebus_namespace.main.id
  role_definition_name = "Azure Service Bus Data Sender"
  principal_id         = azurerm_container_app.ingest.identity[0].principal_id
}

# ── Service Bus — Receiver (processing worker consumes events) ────────────────
resource "azurerm_role_assignment" "sb_receiver_processing" {
  scope                = azurerm_servicebus_namespace.main.id
  role_definition_name = "Azure Service Bus Data Receiver"
  principal_id         = azurerm_container_app.processing.identity[0].principal_id
}
