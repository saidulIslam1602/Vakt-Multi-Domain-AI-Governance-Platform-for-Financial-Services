# Azure Container Apps — managed microservice hosting

resource "azurerm_container_app_environment" "main" {
  name                = "${local.prefix}-cae"
  location            = local.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

resource "azurerm_container_registry" "main" {
  name                = "${local.prefix}acr"
  resource_group_name = azurerm_resource_group.main.name
  location            = local.location
  sku                 = "Standard"
  admin_enabled       = false
  tags                = local.tags
}

locals {
  acr_url = azurerm_container_registry.main.login_server
  # DATABASE_URL is stored in Key Vault (azurerm_key_vault_secret.database_url).
  # Container Apps pull it via secretRef at runtime — the plain-text connection
  # string never appears in Container App environment variables.
  sb_fqdn = "${azurerm_servicebus_namespace.main.name}.servicebus.windows.net"
  img = {
    ingest     = "${azurerm_container_registry.main.login_server}/ingest-service:latest"
    document   = "${azurerm_container_registry.main.login_server}/document-service:latest"
    processing = "${azurerm_container_registry.main.login_server}/processing-service:latest"
    search     = "${azurerm_container_registry.main.login_server}/search-service:latest"
    chat       = "${azurerm_container_registry.main.login_server}/chat-service:latest"
    frontend   = "${azurerm_container_registry.main.login_server}/frontend:latest"
  }
}

# --- Ingest Service ---
resource "azurerm_container_app" "ingest" {
  name                         = "ingest-service"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  identity { type = "SystemAssigned" }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = "System"
  }

  # ── Key Vault secret references ───────────────────────────────────────────
  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
    identity            = "System"
  }
  secret {
    name                = "imap-password"
    key_vault_secret_id = azurerm_key_vault_secret.imap_password.versionless_id
    identity            = "System"
  }
  secret {
    name                = "allergo-db-encryption-key"
    key_vault_secret_id = azurerm_key_vault_secret.db_encryption_key.versionless_id
    identity            = "System"
  }

  template {
    min_replicas = 1
    max_replicas = 5

    container {
      name   = "ingest"
      image  = local.img.ingest
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "AZURE_BLOB_ACCOUNT_URL"
        value = "https://${azurerm_storage_account.docs.name}.blob.core.windows.net"
      }
      env {
        name  = "AZURE_SERVICEBUS_NAMESPACE_FQDN"
        value = local.sb_fqdn
      }
      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name        = "IMAP_PASSWORD"
        secret_name = "imap-password"
      }
      env {
        name        = "ALLERGO_DB_ENCRYPTION_KEY"
        secret_name = "allergo-db-encryption-key"
      }
      env {
        name  = "AUTH_ENABLED"
        value = "false"
      }
      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
    }

    http_scale_rule {
      name                = "http-scale"
      concurrent_requests = "20"
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}

# --- Processing Worker ---
resource "azurerm_container_app" "processing" {
  name                         = "processing-service"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  identity { type = "SystemAssigned" }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = "System"
  }

  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
    identity            = "System"
  }
  secret {
    name                = "smtp-password"
    key_vault_secret_id = azurerm_key_vault_secret.smtp_password.versionless_id
    identity            = "System"
  }
  secret {
    name                = "openai-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.openai_api_key.versionless_id
    identity            = "System"
  }
  secret {
    name                = "azure-search-key"
    key_vault_secret_id = azurerm_key_vault_secret.search_api_key.versionless_id
    identity            = "System"
  }

  template {
    min_replicas = 1
    max_replicas = 10

    container {
      name   = "processing"
      image  = local.img.processing
      cpu    = 1.0
      memory = "2Gi"

      env {
        name  = "AZURE_BLOB_ACCOUNT_URL"
        value = "https://${azurerm_storage_account.docs.name}.blob.core.windows.net"
      }
      env {
        name  = "AZURE_SERVICEBUS_NAMESPACE_FQDN"
        value = local.sb_fqdn
      }
      env {
        name  = "AZURE_SEARCH_ENDPOINT"
        value = "https://${azurerm_search_service.main.name}.search.windows.net"
      }
      env {
        name        = "AZURE_SEARCH_KEY"
        secret_name = "azure-search-key"
      }
      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = azurerm_cognitive_account.openai.endpoint
      }
      env {
        name        = "AZURE_OPENAI_API_KEY"
        secret_name = "openai-api-key"
      }
      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name        = "SMTP_PASSWORD"
        secret_name = "smtp-password"
      }
      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
    }

    custom_scale_rule {
      name             = "servicebus-scale"
      custom_rule_type = "azure-servicebus"
      metadata = {
        messageCount     = "10"
        namespace        = azurerm_servicebus_namespace.main.name
        topicName        = azurerm_servicebus_topic.document_events.name
        subscriptionName = azurerm_servicebus_subscription.processing_worker.name
      }
    }
  }
}

# --- Document Service ---
resource "azurerm_container_app" "document" {
  name                         = "document-service"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  identity { type = "SystemAssigned" }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = "System"
  }

  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
    identity            = "System"
  }

  template {
    min_replicas = 1
    max_replicas = 5

    container {
      name   = "document"
      image  = local.img.document
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        # pydantic-settings field: azure_storage_account_url → AZURE_STORAGE_ACCOUNT_URL
        name  = "AZURE_STORAGE_ACCOUNT_URL"
        value = "https://${azurerm_storage_account.docs.name}.blob.core.windows.net"
      }
      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name  = "AUTH_ENABLED"
        value = "false"
      }
      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}

# --- Search Service ---
resource "azurerm_container_app" "search" {
  name                         = "search-service"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  identity { type = "SystemAssigned" }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = "System"
  }

  template {
    min_replicas = 1
    max_replicas = 5

    container {
      name   = "search"
      image  = local.img.search
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "AZURE_SEARCH_ENDPOINT"
        value = "https://${azurerm_search_service.main.name}.search.windows.net"
      }
      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = azurerm_cognitive_account.openai.endpoint
      }
      env {
        name  = "AUTH_ENABLED"
        value = "false"
      }
      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}

# --- Chat Service ---
resource "azurerm_container_app" "chat" {
  name                         = "chat-service"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  identity { type = "SystemAssigned" }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = "System"
  }

  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
    identity            = "System"
  }

  secret {
    name                = "openai-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.openai_api_key.versionless_id
    identity            = "System"
  }

  secret {
    name                = "azure-search-key"
    key_vault_secret_id = azurerm_key_vault_secret.search_api_key.versionless_id
    identity            = "System"
  }

  template {
    min_replicas = 1
    max_replicas = 5

    container {
      name   = "chat"
      image  = local.img.chat
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "AZURE_SEARCH_ENDPOINT"
        value = "https://${azurerm_search_service.main.name}.search.windows.net"
      }
      env {
        name        = "AZURE_SEARCH_KEY"
        secret_name = "azure-search-key"
      }
      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = azurerm_cognitive_account.openai.endpoint
      }
      env {
        name        = "AZURE_OPENAI_API_KEY"
        secret_name = "openai-api-key"
      }
      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name  = "AUTH_ENABLED"
        value = "false"
      }
      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}

# --- Frontend ---
resource "azurerm_container_app" "frontend" {
  name                         = "frontend"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  identity { type = "SystemAssigned" }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = "System"
  }

  template {
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "frontend"
      image  = local.img.frontend
      cpu    = 0.5
      memory = "1Gi"

      env {
        # Internal Container Apps DNS — traffic stays inside the environment,
        # no TLS overhead, no 307 redirect loop on POST/streaming endpoints.
        # See: https://learn.microsoft.com/en-us/azure/container-apps/connect-apps
        name  = "INGEST_SERVICE_URL"
        value = "http://ingest-service"
      }
      env {
        name  = "DOCUMENT_SERVICE_URL"
        value = "http://document-service"
      }
      env {
        name  = "SEARCH_SERVICE_URL"
        value = "http://search-service"
      }
      env {
        name  = "CHAT_SERVICE_URL"
        value = "http://chat-service"
      }
      env {
        name  = "NEXTAUTH_URL"
        value = "https://${local.prefix}-frontend.${var.location}.azurecontainerapps.io"
      }
      env {
        name        = "NEXTAUTH_SECRET"
        secret_name = "nextauth-secret"
      }
    }
  }

  secret {
    name                = "nextauth-secret"
    key_vault_secret_id = azurerm_key_vault_secret.nextauth_secret.versionless_id
    identity            = "System"
  }

  ingress {
    external_enabled = true
    target_port      = 3000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}
