# Azure Service Bus — document event pipeline

resource "azurerm_servicebus_namespace" "main" {
  name                = "${local.prefix}bus"
  location            = local.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Standard"
  tags                = local.tags
}

resource "azurerm_servicebus_topic" "document_events" {
  name                  = "document-events"
  namespace_id          = azurerm_servicebus_namespace.main.id
  partitioning_enabled  = true
  max_size_in_megabytes = 1024
  default_message_ttl   = "P7D"
}

resource "azurerm_servicebus_subscription" "processing_worker" {
  name                                 = "processing-worker"
  topic_id                             = azurerm_servicebus_topic.document_events.id
  max_delivery_count                   = 5
  lock_duration                        = "PT5M"
  dead_lettering_on_message_expiration = true
}
