// NavPort on Azure — the whole of resource group rg-navport, as code.
//
//   navport-env    Container Apps environment, express mode, no log storage
//   navport        Container App running the API image from Docker Hub
//   navport-web    Static Web App serving the dashboard (Free)
//   navport_budget monthly cost budget with email alerts
//
// Deploy (see infra/README.md):
//   az deployment group create -g rg-navport -f infra/main.bicep -p infra/main.bicepparam \
//     -p dockerHubToken=<read-only token> alertEmail=<address>
//
// The pipelines own what changes often: the Backend workflow publishes the
// image, the Frontend workflow uploads the site. This file owns what the
// services are and how they're sized, so the setup can be recreated, reviewed
// and diffed (az deployment group what-if) instead of retyped by hand.

targetScope = 'resourceGroup'

@description('Region for the API. The Static Web App has its own, below.')
param location string = resourceGroup().location

@description('Static Web Apps runs in a few regions only; East Asia is the nearest to India.')
param staticSiteLocation string = 'eastasia'

param environmentName string = 'navport-env'
param apiAppName string = 'navport'
param staticSiteName string = 'navport-web'

@description('API image, pinned to a commit: docker.io/<user>/navport-backend:sha-<commit>.')
param image string

param dockerHubUser string

@secure()
@description('Read-only Docker Hub access token. Never committed; passed at deploy time.')
param dockerHubToken string

@description('The dashboard\'s address: the only browser origin the API accepts.')
param corsOrigin string

// Sized from what the API actually uses on Azure: at most ~260 MB of memory
// and 0.05 vCPU. 0.25 vCPU / 0.5 GiB is the smallest Container Apps size and
// halves the per-second rate of 0.5 / 1.0. How long an idle replica lingers
// is not configurable here: express manages scale-down itself and ignores
// scale.cooldownPeriod.
@allowed([ '0.25', '0.5', '1.0' ])
param cpu string = '0.25'
param memory string = '0.5Gi'

param minReplicas int = 0
param maxReplicas int = 2

@description('Monthly budget in the subscription currency (INR). Normal running cost is about INR 15.')
param budgetAmount int = 50

@description('Who gets the budget alerts, comma-separated. Passed at deploy time, not committed.')
param alertEmail string

var alertEmails = map(split(alertEmail, ','), e => trim(e))

@description('First day of the month the budget starts counting from.')
param budgetStartDate string = '2026-09-01T00:00:00Z'
param budgetEndDate string = '2028-08-31T00:00:00Z'

param repositoryUrl string = 'https://github.com/Krishu-24/NavPort'

// ---------------------------------------------------------------- API

resource environment 'Microsoft.App/managedEnvironments@2026-07-01' = {
  name: environmentName
  location: location
  properties: {
    // Express: Azure's fully managed tier for HTTP apps, with fast scale from
    // zero. Azure migrated this environment to it automatically in October
    // 2026. The settings below are the ones express reports for it; stated so
    // a deployment changes nothing it doesn't mean to.
    environmentMode: 'Express'
    // No Log Analytics workspace: logs are streamed live
    // (az containerapp logs show --follow) and never stored or billed.
    appLogsConfiguration: {}
    publicNetworkAccess: 'Enabled'
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    peerAuthentication: {
      mtls: {
        enabled: false
      }
    }
    peerTrafficConfiguration: {
      encryption: {
        enabled: false
      }
    }
  }
}

var registrySecretName = 'dockerio-${toLower(dockerHubUser)}'

resource api 'Microsoft.App/containerApps@2026-07-01' = {
  name: apiAppName
  location: location
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      registries: [
        {
          server: 'docker.io'
          username: dockerHubUser
          passwordSecretRef: registrySecretName
        }
      ]
      secrets: [
        {
          name: registrySecretName
          value: dockerHubToken
        }
      ]
    }
    template: {
      containers: [
        {
          name: apiAppName
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            { name: 'NAVPORT_ENV', value: 'production' }
            { name: 'NAVPORT_TRUST_PROXY', value: 'true' }
            { name: 'WEB_CONCURRENCY', value: '2' }
            { name: 'NAVPORT_CORS_ORIGINS', value: corsOrigin }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scaler'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
}

// ---------------------------------------------------------------- dashboard

resource site 'Microsoft.Web/staticSites@2024-04-01' = {
  name: staticSiteName
  location: staticSiteLocation
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    // Content arrives from the Frontend workflow, which authenticates with
    // the site's deployment token; the repository link is informational.
    repositoryUrl: repositoryUrl
    branch: 'main'
    provider: 'GitHub'
    #disable-next-line BCP037 // accepted by the API, missing from the Bicep type definitions
    deploymentAuthPolicy: 'DeploymentToken'
    allowConfigFileUpdates: true
    stagingEnvironmentPolicy: 'Enabled'
  }
}

// ---------------------------------------------------------------- budget

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'navport_budget'
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: budgetStartDate
      endDate: budgetEndDate
    }
    // Half the budget is already more than a normal month, so the first alert
    // means something is waking the API far more than usual.
    notifications: {
      actual_GreaterThan_50_Percent: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 50
        contactEmails: alertEmails
      }
      actual_GreaterThan_100_Percent: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        contactEmails: alertEmails
      }
      forecasted_GreaterThan_100_Percent: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: alertEmails
      }
    }
  }
}

output apiUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
output dashboardUrl string = 'https://${site.properties.defaultHostname}'
