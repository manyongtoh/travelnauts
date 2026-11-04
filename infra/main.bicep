// Travelnauts company brain: one resource group per environment (test, pilot, live) in Travelnauts' Azure.
// Same template for all three; only the parameter file differs. NOT YET DEPLOYED: review with Travelnauts'
// Azure admin first (region, naming, network rules, spending limits).
targetScope = 'resourceGroup'

@allowed(['test', 'pilot', 'live'])
param env string
param location string = 'westeurope'
param prefix string = 'brain'
@description('Monthly budget alarm for this resource group, in EUR')
param monthlyBudget int = 300
param budgetContact string
@description('Postgres admin login; the password lives in Key Vault after deployment')
param pgAdmin string = 'brainadmin'
@secure()
param pgPassword string
param image string = 'mcr.microsoft.com/k8se/quickstart:latest'
param entraTenantId string
param entraClientId string

var name = '${prefix}-${env}'
var isLive = env == 'live'
var dataStage = env == 'test' ? 'synthetic' : (env == 'pilot' ? 'anonymised' : 'live')
var tsWrite = env == 'live' ? 'drafts' : (env == 'pilot' ? 'off' : 'drafts')

resource logs 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'log-${name}'
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${name}'
  location: location
  kind: 'web'
  properties: { Application_Type: 'web', WorkspaceResourceId: logs.id }
}

resource idApi 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${name}-api'
  location: location
}

resource idWorker 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${name}-worker'
  location: location
}

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${name}-${uniqueString(resourceGroup().id)}'
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    enablePurgeProtection: isLive ? true : null
    publicNetworkAccess: 'Enabled'
  }
}

resource pgSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'database-url'
  properties: { value: 'postgresql+psycopg://${pgAdmin}:${pgPassword}@${pg.properties.fullyQualifiedDomainName}:5432/brain?sslmode=require' }
}

resource st 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: toLower(replace('st${name}${uniqueString(resourceGroup().id)}', '-', ''))
  location: location
  sku: { name: isLive ? 'Standard_ZRS' : 'Standard_LRS' }
  kind: 'StorageV2'
  properties: { minimumTlsVersion: 'TLS1_2', allowBlobPublicAccess: false, supportsHttpsTrafficOnly: true }
}

resource blob 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: st
  name: 'default'
}

resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = [for c in ['documents', 'testsets', 'backups']: {
  parent: blob
  name: c
}]

resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' = {
  name: 'pg-${name}'
  location: location
  sku: isLive ? { name: 'Standard_D2ds_v4', tier: 'GeneralPurpose' } : { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: pgAdmin
    administratorLoginPassword: pgPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: env == 'test' ? 7 : 30, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
  }
}

resource pgVector 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2022-12-01' = {
  parent: pg
  name: 'azure.extensions'
  properties: { value: 'VECTOR', source: 'user-override' }
}

resource pgDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2022-12-01' = {
  parent: pg
  name: 'brain'
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: toLower(replace('cr${name}${uniqueString(resourceGroup().id)}', '-', ''))
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

// Roles: both identities read secrets and pull images; nothing else.
var kvSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6'
var acrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
resource kvRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for id in [idApi, idWorker]: {
  name: guid(kv.id, id.id, kvSecretsUser)
  scope: kv
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUser), principalId: id.properties.principalId, principalType: 'ServicePrincipal' }
}]
resource acrRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for id in [idApi, idWorker]: {
  name: guid(acr.id, id.id, acrPull)
  scope: acr
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPull), principalId: id.properties.principalId, principalType: 'ServicePrincipal' }
}]

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${name}'
  location: location
  properties: {
    appLogsConfiguration: { destination: 'log-analytics', logAnalyticsConfiguration: { customerId: logs.properties.customerId, sharedKey: logs.listKeys().primarySharedKey } }
  }
}

var commonEnv = [
  { name: 'BRAIN_ENV', value: env }
  { name: 'BRAIN_DATA_STAGE', value: dataStage }
  { name: 'BRAIN_TRAVELSPIRIT_WRITE', value: tsWrite }
  { name: 'BRAIN_AUTH', value: env == 'test' ? 'sandbox' : 'entra' }
  { name: 'ENTRA_TENANT_ID', value: entraTenantId }
  { name: 'ENTRA_CLIENT_ID', value: entraClientId }
  { name: 'AZURE_KEYVAULT_NAME', value: kv.name }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: insights.properties.ConnectionString }
  { name: 'BRAIN_DATABASE_URL', secretRef: 'database-url' }
]

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${name}-api'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${idApi.id}': {} } }
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'auto' }
      registries: [{ server: acr.properties.loginServer, identity: idApi.id }]
      secrets: [{ name: 'database-url', keyVaultUrl: '${kv.properties.vaultUri}secrets/database-url', identity: idApi.id }]
    }
    template: {
      containers: [{ name: 'api', image: image, env: commonEnv, resources: { cpu: json('0.5'), memory: '1Gi' }
        command: ['brain', 'serve', '--host', '0.0.0.0', '--port', '8000'] }]
      scale: { minReplicas: isLive ? 1 : 0, maxReplicas: 3 }
    }
  }
  dependsOn: [kvRoles, acrRoles, pgSecret]
}

resource worker 'Microsoft.App/jobs@2024-03-01' = {
  name: 'cj-${name}-worker'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${idWorker.id}': {} } }
  properties: {
    environmentId: cae.id
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: { cronExpression: '*/5 * * * *', parallelism: 1, replicaCompletionCount: 1 }
      replicaTimeout: 600
      replicaRetryLimit: 1
      registries: [{ server: acr.properties.loginServer, identity: idWorker.id }]
      secrets: [{ name: 'database-url', keyVaultUrl: '${kv.properties.vaultUri}secrets/database-url', identity: idWorker.id }]
    }
    template: {
      containers: [{ name: 'worker', image: image, env: commonEnv, resources: { cpu: json('0.5'), memory: '1Gi' }
        command: ['brain', 'worker', '--once'] }]
    }
  }
  dependsOn: [kvRoles, acrRoles, pgSecret]
}

resource budget 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: 'budget-${name}'
  properties: {
    category: 'Cost'
    amount: monthlyBudget
    timeGrain: 'Monthly'
    timePeriod: { startDate: '2026-12-01' }
    notifications: {
      at80: { enabled: true, operator: 'GreaterThan', threshold: 80, contactEmails: [budgetContact] }
      at100: { enabled: true, operator: 'GreaterThan', threshold: 100, contactEmails: [budgetContact] }
    }
  }
}

output apiUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
output keyVault string = kv.name
output registry string = acr.properties.loginServer
