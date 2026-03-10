resource "azurerm_resource_group" "main" {
  name     = "allergo_business_case"
  location = local.location
  tags     = local.tags
}
