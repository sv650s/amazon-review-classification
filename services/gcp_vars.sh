export PROJECT="sb-capstone"
export PROJECT_ID="sb-capstone-250223"
export SERVICE="capstone-service"
export REPO_HOSTNAME="gcr.io"
export IMAGE_NAME="${SERVICE}-image"
export IMAGE_NAME_FULL="${REPO_HOSTNAME}/${PROJECT_ID}/${IMAGE_NAME}"
export BUCKET_NAME="${PROJECT}-bucket"
export CLUSTER_NAME="${PROJECT}-cluster"
export DEPLOYMENT_NAME="${PROJECT}-deployment"
export REGION="us-west1"
export ZONE="us-west1-a"
export DB_MACHINE_TYPE="db-f1-micro"
export DB_INSTANCE_NAME="${PROJECT_ID}-mysql-v1"
export DB_IP="35.230.77.154"
