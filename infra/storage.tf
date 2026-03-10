# Azure Blob Storage — raw documents and extracted text

resource "azurerm_storage_account" "docs" {
  name                     = "${local.prefix}docs"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = local.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
  allow_nested_items_to_be_public = false

  blob_properties {
    delete_retention_policy {
      days = 14
    }
    versioning_enabled = true
  }

  tags = local.tags
}

resource "azurerm_storage_container" "raw_documents" {
  name                  = "raw-documents"
  storage_account_name  = azurerm_storage_account.docs.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "raw_text" {
  name                  = "raw-text"
  storage_account_name  = azurerm_storage_account.docs.name
  container_access_type = "private"
}

# Lifecycle management: move to cool tier after 30 days, archive after 180
resource "azurerm_storage_management_policy" "lifecycle" {
  storage_account_id = azurerm_storage_account.docs.id

  rule {
    name    = "archive-old-documents"
    enabled = true
    filters {
      blob_types   = ["blockBlob"]
      prefix_match = ["raw-documents/"]
    }
    actions {
      base_blob {
        tier_to_cool_after_days_since_modification_greater_than    = 30
        tier_to_archive_after_days_since_modification_greater_than = 180
      }
    }
  }
}
