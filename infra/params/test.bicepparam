using '../main.bicep'

param env = 'test'
param location = 'westeurope'
param monthlyBudget = 150
param budgetContact = 'it@travelnauts.example'
param pgPassword = readEnvironmentVariable('PG_PASSWORD')
param entraTenantId = readEnvironmentVariable('ENTRA_TENANT_ID', '')
param entraClientId = readEnvironmentVariable('ENTRA_CLIENT_ID', '')
