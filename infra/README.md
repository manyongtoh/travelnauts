# Azure infrastructure

`main.bicep` builds one environment in its own resource group: Container Apps (the API and screens, and a
worker job every 5 minutes), PostgreSQL with pgvector, Key Vault, Blob Storage, Log Analytics and
Application Insights, a container registry, one managed identity for the API and one for the worker, and
a monthly budget alarm. Test, pilot and live use the same template with their own parameter file.

Status: written, **not yet deployed or validated** against an Azure subscription. Before the first deploy,
go through it with Travelnauts' Azure administrator: region, naming, network rules (private endpoints for
Postgres and Key Vault in pilot and live), Entra app registrations per environment, and spending limits.

```bash
az group create -n rg-brain-test -l westeurope
PG_PASSWORD=... az deployment group create -g rg-brain-test --template-file infra/main.bicep --parameters infra/params/test.bicepparam
```

Not covered by the template yet: Entra ID app registrations and app roles (created once per environment
in the portal or with `az ad app`), Azure AI Content Safety, the model deployments in Azure AI Foundry,
Langfuse, and the Power BI workspace.
