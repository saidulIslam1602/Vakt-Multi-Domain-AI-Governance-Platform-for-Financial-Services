# GitHub Repository Secrets & Variables

This file documents all secrets and variables required for the CI/CD workflows.
**Never commit actual values here.**  Add them in:
`GitHub repo → Settings → Secrets and variables → Actions`

---

## Secrets (encrypted, not visible in logs)

| Name | Description | How to get it |
|------|-------------|---------------|
| `AZURE_CLIENT_ID` | OIDC federated credential — Client ID of the Azure AD app registration | Azure Portal → App registrations → your app → Overview |
| `AZURE_TENANT_ID` | Azure AD Tenant ID | Azure Portal → Azure Active Directory → Overview |
| `AZURE_SUBSCRIPTION_ID` | Azure Subscription ID | Azure Portal → Subscriptions |

> **OIDC setup:** Create a federated identity credential on your app registration for `repo:saidulIslam1602/Business_Case_Study:ref:refs/heads/main` and the `production` environment.

---

## Variables (visible in logs — non-sensitive)

| Name | Example value | Description |
|------|--------------|-------------|
| `ACR_NAME` | `allergodevacr` | Azure Container Registry name (without `.azurecr.io`) |
| `RESOURCE_GROUP` | `allergo-dev-rg` | Azure Resource Group where Container Apps live |

---

## Environments

The `deploy` jobs use the GitHub environment named **`production`**.
Create it at: `Settings → Environments → New environment → production`

Recommended protection rules:
- Required reviewers: add yourself
- Deployment branches: `main` only
