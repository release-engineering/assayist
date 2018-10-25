try { // massive try{} catch{} around the entire build for failure notifications
    timestamps {
        node('docker') {
            checkout scm
            stage('Build the Assayist container image') {
                docker.withRegistry('https://quay.io/', 'quay-io-factory2-builder-sa-credentials') {
                    // rcm_tools_repo_url and ca_url parameters must be set
                    def image = docker.build "factory2/assayist:latest", "--build-arg rcm_tools_repo_file=${rcm_tools_repo_url} --build-arg ca_file=${ca_url} -f docker/Dockerfile ."
                    image.push()
                }
            }
        }
    }
} catch (e) {
    if (ownership.job.ownershipEnabled) {
        mail to: ownership.job.primaryOwnerEmail,
             cc: ownership.job.secondaryOwnerEmails.join(', '),
             subject: "Jenkins job ${env.JOB_NAME} #${env.BUILD_NUMBER} failed",
             body: "${env.BUILD_URL}\n\n${e}"
    }
    throw e
}
