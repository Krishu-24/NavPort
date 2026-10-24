using 'main.bicep'

// Everything here is public anyway (addresses, the image name). The two
// private values — the Docker Hub token and the alert email — are passed on
// the command line at deploy time; see infra/README.md.

param image = 'docker.io/arnav24sinha/navport-backend:sha-de593c31fa9ec9720a8e0efe65b275dda56b555d'
param dockerHubUser = 'arnav24sinha'
param corsOrigin = 'https://happy-grass-01991ca00.6.azurestaticapps.net'

param dockerHubToken = ''
param alertEmail = ''
