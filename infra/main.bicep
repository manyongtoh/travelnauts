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
@description('Who gets alert mails (outage, audit chain, critical brain alerts). Defaults to the budget contact.')
param alertEmail string = budgetContact
@secure()
@description('Optional Teams incoming webhook for brain alerts. Empty: alerts go by mail only.')
param alertWebhook string = ''

var name = '${prefix}-${env}'
var isLive = env == 'live'
var dataStage = env == 'test' ? 'synthetic' : (env == 'pilot' ? 'anonymised' : 'live')
var hasHook = !empty(alertWebhook)
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
  sku: isLive ? { name: 'Standard_D2ds_v4', tier: 'GeneralPurpose' } : { name: 'Standard_B2s', tier: 'Burstable' }
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
// Written out per identity: a loop over resources is not allowed (BCP178).
resource kvRoleApi 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, idApi.id, kvSecretsUser)
  scope: kv
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUser), principalId: idApi.properties.principalId, principalType: 'ServicePrincipal' }
}
resource acrRoleApi 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, idApi.id, acrPull)
  scope: acr
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPull), principalId: idApi.properties.principalId, principalType: 'ServicePrincipal' }
}
resource kvRoleWorker 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, idWorker.id, kvSecretsUser)
  scope: kv
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUser), principalId: idWorker.properties.principalId, principalType: 'ServicePrincipal' }
}
resource acrRoleWorker 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, idWorker.id, acrPull)
  scope: acr
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPull), principalId: idWorker.properties.principalId, principalType: 'ServicePrincipal' }
}

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

// Workers run the alert check, so only they get the webhook.
resource hookSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (hasHook) {
  parent: kv
  name: 'alert-webhook'
  properties: { value: alertWebhook }
}
var hookSecretRef = hasHook ? [{ name: 'alert-webhook', keyVaultUrl: '${kv.properties.vaultUri}secrets/alert-webhook', identity: idWorker.id }] : []
var workerEnv = concat(commonEnv, hasHook ? [{ name: 'BRAIN_ALERT_WEBHOOK', secretRef: 'alert-webhook' }] : [])

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
        command: ['sh', '-c', 'brain migrate && brain serve --host 0.0.0.0 --port 8000']
        probes: [
          { type: 'Liveness', httpGet: { path: '/healthz', port: 8000 }, periodSeconds: 30 }
          { type: 'Readiness', httpGet: { path: '/readyz', port: 8000 }, periodSeconds: 10 }
        ] }]
      // The API is stateless: more people means more replicas, each with its own connection pool.
      scale: { minReplicas: isLive ? 2 : 0, maxReplicas: isLive ? 10 : 3
        rules: [{ name: 'http', http: { metadata: { concurrentRequests: '30' } } }] }
    }
  }
  dependsOn: [kvRoleApi, kvRoleWorker, acrRoleApi, acrRoleWorker, pgSecret]
}

// Two worker jobs: the scheduler (every 5 minutes, queues periodic work and does one pass) and the scaled
// workers, started by KEDA when jobs are waiting: one replica per 20 queued jobs, up to 10 at once. Jobs are
// claimed with row locks, so any number of workers can run side by side.
resource drain 'Microsoft.App/jobs@2024-03-01' = {
  name: 'cj-${name}-drain'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${idWorker.id}': {} } }
  properties: {
    environmentId: cae.id
    configuration: {
      triggerType: 'Event'
      eventTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
        scale: { minExecutions: 0, maxExecutions: 10, pollingInterval: 30
          rules: [{ name: 'queue', type: 'postgresql', auth: [{ secretRef: 'database-conn', triggerParameter: 'connection' }]
            metadata: { query: 'SELECT COUNT(*) FROM jobs WHERE status = \'queued\' AND run_after <= now()', targetQueryValue: '20' } }] }
      }
      replicaTimeout: 1800
      replicaRetryLimit: 1
      registries: [{ server: acr.properties.loginServer, identity: idWorker.id }]
      secrets: concat([
        { name: 'database-url', keyVaultUrl: '${kv.properties.vaultUri}secrets/database-url', identity: idWorker.id }
        { name: 'database-conn', keyVaultUrl: '${kv.properties.vaultUri}secrets/database-conn', identity: idWorker.id }
      ], hookSecretRef)
    }
    template: {
      containers: [{ name: 'worker', image: image, env: workerEnv, resources: { cpu: json('0.5'), memory: '1Gi' }
        command: ['brain', 'worker', '--drain'] }]
    }
  }
  dependsOn: [kvRoleApi, kvRoleWorker, acrRoleApi, acrRoleWorker, pgSecret, pgConn, hookSecret]
}

resource pgConn 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'database-conn'
  properties: { value: 'host=${pg.properties.fullyQualifiedDomainName} port=5432 user=${pgAdmin} password=${pgPassword} dbname=brain sslmode=require' }
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
      secrets: concat([{ name: 'database-url', keyVaultUrl: '${kv.properties.vaultUri}secrets/database-url', identity: idWorker.id }], hookSecretRef)
    }
    template: {
      containers: [{ name: 'worker', image: image, env: workerEnv, resources: { cpu: json('0.5'), memory: '1Gi' }
        command: ['brain', 'worker', '--once'] }]
    }
  }
  dependsOn: [kvRoleApi, kvRoleWorker, acrRoleApi, acrRoleWorker, pgSecret, hookSecret]
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

// Alerts outside the brain, so someone hears about it even when the brain itself is down.
resource ag 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-${name}'
  location: 'global'
  properties: {
    groupShortName: take('brain${env}', 12)
    enabled: true
    emailReceivers: [{ name: 'admin', emailAddress: alertEmail, useCommonAlertSchema: true }]
  }
}

// 1. The site answers: /readyz checked every 5 minutes from three European locations.
resource readyTest 'Microsoft.Insights/webtests@2022-06-15' = {
  name: 'wt-${name}-ready'
  location: location
  tags: { 'hidden-link:${insights.id}': 'Resource' }
  kind: 'standard'
  properties: {
    SyntheticMonitorId: 'wt-${name}-ready'
    Name: 'readyz ${env}'
    Enabled: true
    Frequency: 300
    Timeout: 30
    Kind: 'standard'
    RetryEnabled: true
    Locations: [{ Id: 'emea-nl-ams-azr' }, { Id: 'emea-gb-db3-azr' }, { Id: 'emea-fr-pra-edge' }]
    Request: { RequestUrl: 'https://${api.properties.configuration.ingress.fqdn}/readyz', HttpVerb: 'GET', ParseDependentRequests: false }
    ValidationRules: { ExpectedHttpStatusCode: 200, SSLCheck: true, SSLCertRemainingLifetimeCheck: 7 }
  }
}

resource readyAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-${name}-ready'
  location: 'global'
  properties: {
    description: 'The brain does not answer, or its database is unreachable (runbook: database restarts).'
    severity: 1
    enabled: true
    scopes: [readyTest.id, insights.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria'
      webTestId: readyTest.id
      componentId: insights.id
      failedLocationCount: 2
    }
    actions: [{ actionGroupId: ag.id }]
  }
}

// 2. Critical alerts from the brain's own check, and an alert channel that fails.
var logAlerts = [
  {
    key: 'critical'
    sev: 1
    text: 'A critical brain alert (see Maintenance and the runbook).'
    q: 'ContainerAppConsoleLogs_CL | where Log_s contains "BRAIN_ALERT env=" and Log_s contains "[CRITICAL]"'
  }
  {
    key: 'delivery'
    sev: 2
    text: 'The Teams webhook for brain alerts is failing.'
    q: 'ContainerAppConsoleLogs_CL | where Log_s contains "BRAIN_ALERT_DELIVERY_FAILED"'
  }
]
resource logAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = [for a in logAlerts: {
  name: 'alert-${name}-${a.key}'
  location: location
  properties: {
    displayName: 'Brain ${a.key} (${env})'
    description: a.text
    severity: a.sev
    enabled: true
    scopes: [logs.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      allOf: [
        {
          query: a.q
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 }
        }
      ]
    }
    actions: { actionGroups: [ag.id] }
  }
}]

// 3. Dead man's switch: the check writes a heartbeat every 15 minutes. No heartbeat for 45 minutes means the
//    scheduler or the workers are down, which the brain cannot report about itself.
resource heartbeat 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: 'alert-${name}-heartbeat'
  location: location
  properties: {
    displayName: 'Brain scheduler silent (${env})'
    description: 'No alert check has run for 45 minutes: restart the worker job (runbook: worker stops).'
    severity: 1
    enabled: true
    scopes: [logs.id]
    evaluationFrequency: 'PT15M'
    windowSize: 'PT45M'
    criteria: {
      allOf: [
        {
          query: 'ContainerAppConsoleLogs_CL | where Log_s contains "BRAIN_ALERT_HEARTBEAT"'
          timeAggregation: 'Count'
          operator: 'LessThan'
          threshold: 1
          failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 }
        }
      ]
    }
    actions: { actionGroups: [ag.id] }
  }
}

output apiUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
output keyVault string = kv.name
output registry string = acr.properties.loginServer
