pipeline {
    agent { node { label 'built-in'; customWorkspace '/home/ubuntu/bomi/data/jenkins/workspace/bomi-robot-verify' } }
    options { disableConcurrentBuilds(); skipDefaultCheckout(true); timestamps(); timeout(time: 20, unit: 'MINUTES') }
    stages {
        stage('Checkout robot-main') { steps { checkout scm } }
        stage('Verify Robot') { steps { sh 'BOMI_SOURCE_DIR="$WORKSPACE" scripts/ci/verify-robot.sh' } }
    }
    post { always { echo 'Robot deployment is disabled; verification only' } }
}
