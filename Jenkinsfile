pipeline {
    agent {
        node {
            label 'built-in'
            customWorkspace '/home/ubuntu/bomi/data/jenkins/workspace/bomi-production'
        }
    }

    options {
        disableConcurrentBuilds()
        skipDefaultCheckout(true)
        timestamps()
        timeout(time: 20, unit: 'MINUTES')
    }

    environment {
        BOMI_ENV_FILE = '/home/ubuntu/bomi/secrets/production.env'
        BOMI_COMPOSE_FILE = 'infra/compose.prod.yml'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Validate') {
            steps {
                sh '''
                    set -eu
                    bash -n scripts/deploy/deploy-production.sh
                    docker compose \
                      --env-file "$BOMI_ENV_FILE" \
                      -f "$BOMI_COMPOSE_FILE" \
                      config --quiet
                '''
            }
        }

        stage('Build') {
            steps {
                sh '''
                    set -eu
                    docker compose \
                      --env-file "$BOMI_ENV_FILE" \
                      -f "$BOMI_COMPOSE_FILE" \
                      build backend frontend
                '''
            }
        }

        stage('Deploy') {
            steps {
                sh '''
                    set -eu
                    BOMI_SOURCE_DIR="$WORKSPACE" \
                    BOMI_ENV_FILE="$BOMI_ENV_FILE" \
                      scripts/deploy/deploy-production.sh
                '''
            }
        }
    }

    post {
        success {
            echo "BOMI deployment succeeded: ${env.GIT_COMMIT}"
        }
        failure {
            echo "BOMI deployment failed: ${env.BUILD_URL}"
        }
    }
}
