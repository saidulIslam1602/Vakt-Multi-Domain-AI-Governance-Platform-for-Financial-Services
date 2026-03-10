terraform {
  required_version = ">= 1.7"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }
  backend "azurerm" {
    resource_group_name  = "allergo-tfstate-rg"
    storage_account_name = "allergotfstate"
    container_name       = "tfstate"
    key                  = "allergo-nordic.tfstate"
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

locals {
  location = var.location
  prefix   = "allergo${var.environment}"
  tags = {
    project     = "allergo-nordic"
    environment = var.environment
    managed_by  = "terraform"
  }
}
