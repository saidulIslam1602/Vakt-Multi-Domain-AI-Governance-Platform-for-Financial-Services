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
  acr_url     = azurerm_container_registry.main.login_server
  db_url  = "postgresql://allergoadmin:${var.postgres_admin_password}@${azurerm_postgresql_flexible_server.main.fqdn}:5432/allergo?sslmode=require"
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
        name  = "DATABASE_URL"
        value = local.db_url
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
        name  = "AZURE_OPENAI_ENDPOINT"
        value = azurerm_cognitive_account.openai.endpoint
      }
      env {
        name  = "DATABASE_URL"
        value = local.db_url
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

  template {
    min_replicas = 1
    max_replicas = 5

    container {
      name   = "document"
      image  = local.img.document
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "DATABASE_URL"
        value = local.db_url
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
        name  = "AZURE_OPENAI_ENDPOINT"
        value = azurerm_cognitive_account.openai.endpoint
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
        name  = "INGEST_SERVICE_URL"
        value = "https://${azurerm_container_app.ingest.ingress[0].fqdn}"
      }
      env {
        name  = "DOCUMENT_SERVICE_URL"
        value = "https://${azurerm_container_app.document.ingress[0].fqdn}"
      }
      env {
        name  = "SEARCH_SERVICE_URL"
        value = "https://${azurerm_container_app.search.ingress[0].fqdn}"
      }
      env {
        name  = "CHAT_SERVICE_URL"
        value = "https://${azurerm_container_app.chat.ingress[0].fqdn}"
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
    name  = "nextauth-secret"
    value = var.nextauth_secret
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
