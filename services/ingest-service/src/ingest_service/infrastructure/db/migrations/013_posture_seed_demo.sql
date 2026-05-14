-- Migration 013: Dev/demo seeds for infra posture (IaC policy findings + pipeline snapshot).
-- Matches local noop JWT tenant `dev-tenant` and multi-tenant default.

INSERT INTO infra_findings (
    id, tenant_id, severity, rule_id, title, file_path, line_start, line_end,
    policy_pack_ref, remediation_hint, detail_json, source_scan_id
) VALUES
(
    'a1000000-0000-4000-8000-000000000001',
    'dev-tenant',
    'HIGH',
    'CKV_AZURE_88',
    'Ensure Azure Key Vault enables purge protection',
    'infra/keyvault.tf',
    12,
    18,
    'checkov@3.x / Azurerm',
    'Set purge_protection_enabled = true on azurerm_key_vault for production SKUs.',
    '{"check_id": "CKV_AZURE_88", "guideline": "https://docs.prismacloud.io/en/enterprise-edition/policy-reference/azure-policies/azure-general-policies/ensure-azure-key-vault-enables-purge-protection"}',
    'seed-local'
),
(
    'a1000000-0000-4000-8000-000000000002',
    'dev-tenant',
    'MEDIUM',
    'CKV_AZURE_42',
    'Ensure SSH access is restricted from the internet',
    'infra/network.tf',
    44,
    52,
    'checkov@3.x / Azurerm',
    'Narrow source_address_prefix on NSG rules; prefer JIT or bastion.',
    '{"check_id": "CKV_AZURE_42"}',
    'seed-local'
),
(
    'a1000000-0000-4000-8000-000000000003',
    'dev-tenant',
    'LOW',
    'CKV2_AZURE_1',
    'Ensure storage accounts adhere to naming rules',
    'infra/storage.tf',
    3,
    3,
    'checkov@3.x / Azurerm',
    'Align storage account name length and allowed characters with Azure constraints.',
    '{"check_id": "CKV2_AZURE_1"}',
    'seed-local'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO pipeline_runs (
    id, tenant_id, workflow, conclusion, sha, triggered_at, metadata_json
) VALUES (
    'b2000000-0000-4000-8000-000000000001',
    'dev-tenant',
    'Terraform',
    'success',
    'demo0123456789abcdef0123456789abcdef01234567',
    now() - interval '15 minutes',
    '{"job": "plan", "repository": "Allergo_Nordic", "note": "fixture row for agent pipeline context"}'
)
ON CONFLICT (id) DO NOTHING;
