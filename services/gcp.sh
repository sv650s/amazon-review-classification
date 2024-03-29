#!/bin/bash
#
# https://cloud.google.com/kubernetes-engine/docs/tutorials/hello-app
#
# Use this script to set up and tear down GCP resources using gsutil
#
# NOTES:
# You can stream logs from the command line by running:
#  $ gcloud app logs tail -s default
#
# To view your application in the web browser run:
#  $ gcloud app browse

source gcp_vars.sh

usage() {
    echo "Usage: $0 <cmd> [cmd params]"
    echo "Available cmd's"
    echo "     bucket_copy - copy model files to file bucket ${BUCKET_NAME}"
    echo "     bucket_create - create file bucket ${BUCKET_NAME}"
    echo "     bucket_delete -  delete file bucket ${BUCKET_NAME}"
    echo "     cluster_start - create a k8 cluster and deploy container to this cluster. The container needs to exist. You should run <image_upload> job before"
    echo "     cluster_stop - shutdown project"
    echo "     db_create - creates database. You only need to call this once at the begging of the project"
    echo "     db_delete - deletes database from GCP completely. GCP will not allow you to use the same name for 7 days"
    echo "     db_stop - shutdown database"
    echo "     db_start - start already instantiated database"
    echo "     image_delete - delete all images from our GCP container registry"
    echo "     image_deploy - specify a new version of container to deploy to k8 cluster"
    echo "     image_upload - tag docker image and upload. Requires additional <version to tag image> <docker image id>"
    echo "     setup - initialize project"
    echo "     start_all - Calls setup, bucket_copy image_deploy, and cluster_start. Requires additional <version to tag image> <docker image id>"
    echo "     teardown - opposite of setup - will teardown or shutdown gcp resources for the project"
    echo "              currently, this does the following: db stop, file bucket delete, stop k8 cluster"
}


version="latest"

if [ $# -gt 0 ]; then
    command=$1
    if [ $# -gt 1 ]; then
        version=$2
    fi
    if [ $# -gt 2 ]; then
        image_id=$3
    fi
else
    echo "ERROR: missing commaand"
    usage
    exit 1
fi

echo "version: $version"

image_upload() {
    # push docker container
    # https://cloud.google.com/kubernetes-engine/docs/tutorials/hello-app
    # docker build -t gcr.io/${PROJECT_ID}/hello-app:v1 .
    if [ "x$version" == "x" -o "x$image_id" == "x" ]; then
        echo -e "ERROR: image_upload requireds <version> and <image_id> parameters"
        usage
        exit 1
    fi

    docker tag $image_id ${IMAGE_NAME_FULL}:$version

    gcloud auth configure-docker --quiet

    echo -e "\npushing docker image: ${IMAGE_NAME_FULL}:$version"
    docker push ${IMAGE_NAME_FULL}:$version
}


setup() {
    # update gcloud tools
    gcloud components update

    # set current project in gsutil
    gcloud config set project ${PROJECT_ID}
    gcloud config set compute/zone ${ZONE}


    bucket_create
    bucket_copy
    db_start
}

teardown() {

    # completely tear down the project
    #   1. shutdown k8 cluster
    #   2. delete file buckets
    #   3. stop database

    cluster_stop
    bucket_delete
    image_delete
    db_stop

}

bucket_copy() {
    # copy model files to GCP
    gsutil cp models/* gs://${BUCKET_NAME}

}

bucket_create() {
    # references for bucket permissions
    # initially I thought I had to set this but setting iam for the service acccount user
    # give you access to private files in the file buckets - no further work needed
    # https://cloud.google.com/storage/docs/gsutil/commands/iam
    # https://cloud.google.com/storage/docs/gsutil/commands/acl

    gsutil ls gs://${BUCKET_NAME}
    if [ $? -eq 1 ]; then
        # create bucket
        echo -e "${BUCKET_NAME} not found. Creating file bucket"
        gsutil mb gs://${BUCKET_NAME}/
    fi
}

bucket_delete() {

    # tear down the GCP bucket
    echo -e "deleting storage bucket: ${BUCKET_NAME}"
    gsutil rm -r gs://${BUCKET_NAME}
    # this bucket is automatically created by GCP for app engine even though we don't use it
    gsutil rm -r gs://artifacts.${PROJECT_ID}.appspot.com

}


cluster_stop() {

    echo -e "deleting service: ${DEPLOYMENT_NAME}"
    kubectl delete service ${DEPLOYMENT_NAME}

    echo -e "deleting cluster name: ${CLUSTER_NAME}"
    gcloud container clusters delete ${CLUSTER_NAME}

}


cluster_start() {
    if [ x$version == "x" ]; then
        "ERROR: missing version"
        usage
        exit 1
    fi

    echo -e "creating cluster: ${CLUSTER_NAME}"
    gcloud beta container clusters create ${CLUSTER_NAME} --num-nodes=1 --enable-stackdriver-kubernetes
    if [ $? -eq 1 ]; then
        echo -e "ERROR: failed to create cluster"
        exit 1
    fi

    gcloud compute instances list
    if [ $? -eq 1 ]; then
        echo -e "ERROR: failed to get instances list"
        exit 1
    fi
    sleep 3

    echo -e "\ncreating deployment: ${DEPLOYMENT_NAME}"
    kubectl create deployment ${DEPLOYMENT_NAME} --image=${IMAGE_NAME_FULL}:$version
    if [ $? -eq 1 ]; then
        echo -e "ERROR: failed to create deployment"
        exit 1
    fi

    echo -e "\ngetting pods"
    kubectl get pods


    echo -e "\nexposing ${DEPLOYMENT_NAME}"
    kubectl expose deployment ${DEPLOYMENT_NAME} --type=LoadBalancer --port 80 --target-port 5000
    if [ $? -eq 1 ]; then
        echo -e "ERROR: failed to expose deployment"
        exit 1
    fi


    # we need to assign a static ip to our compute instance since we are accessing
    # MySql via a public IP address and we need to allow traffic to come in from that IP
    instance_name=`gcloud compute instances list | tail -1 | awk '{print $1}'`
    echo -e "\nsetting static ip for compute instance ${instance_name}..."
    gcloud compute addresses create ${instance_name} --region ${REGION}
    if [ $? -eq 1 ]; then
        echo -e "ERROR: requesting static ip for compute instance"
        exit 1
    fi

    # get external IP of our instance
    instance_external_ip=`gcloud compute instances list | tail -1 | awk '{print $5}'`
    my_ip=`dig +short myip.opendns.com @resolver1.opendns.com`
    echo -e "\nadding external IP $instance_external_ip and $my_ip to database"
    gcloud sql instances patch ${DB_INSTANCE_NAME} --authorized-networks=${instance_external_ip},${my_ip}


    kubectl get service



}

# update a deployment with new image
image_deploy() {
    # reference: https://cloud.google.com/kubernetes-engine/docs/how-to/updating-apps
    echo -e "Run and update the following command"
    echo -e "kubectl set image deployment/${DEPLOYMENT_NAME} ${IMAGE_NAME}=${IMAGE_NAME_FULL}:$version"
    kubectl set image deployment/${DEPLOYMENT_NAME} ${IMAGE_NAME}=${IMAGE_NAME_FULL}:$version
}


# delete our image and all tags associated with image to clean our our registry
# reference: https://cloud.google.com/container-registry/docs/managing
image_delete() {

    # don't need to do this since we already know the image name
    # gcloud container images list --repository=${REPO_HOSTNAME}/${PROJECT_ID}
    tag=`gcloud container images list-tags ${IMAGE_NAME_FULL} | tail -1 | awk '{print $2}'`
    if [ "x${tag}" == "x" ]; then
        echo -e "\nWARNING: unable to get tagged image - skipping registry cleanup"
    else
        gcloud container images delete ${IMAGE_NAME_FULL}:${tag} --force-delete-tags
    fi
}

db_create() {
    # reference: https://cloud.google.com/sql/docs/mysqlo/create-instance

    # get my IP address
    my_ip=`dig +short myip.opendns.com @resolver1.opendns.com`

    # create mysql database
    # https://cloud.google.com/sql/docs/mysql/create-instance
    echo -e "creating database..."
    gcloud sql instances create ${DB_INSTANCE_NAME} --tier=${DB_MACHINE_TYPE} --region=${REGION} --authorized-networks=${my_ip}
    if [ $? -gt 0 ]; then
        echo -e "error creating database"
        exit 1
    fi
    # configure public IP for insance
    # https://cloud.google.com/sql/docs/mysql/configure-ip
    echo -e "setting username password..."
    gcloud sql users set-password root % --instance=${DB_INSTANCE_NAME} --password 'freel00k'
    if [ $? -gt 0 ]; then
        echo -e "error setting password"
        exit 1
    fi

    echo -e "\nconfiguring public ip access..."
    gcloud sql instances patch ${DB_INSTANCE_NAME} --assign-ip
    if [ $? -gt 0 ]; then
        echo -e "error assigning IP"
        exit 1
    fi
    gcloud sql instances describe ${DB_INSTANCE_NAME}
#    gcloud sql instances patch ${db_instance_name} --authorized-networks=${my_ip}

    # configure instance to use SSL
    echo -e "\nrequire ssl connections to database..."
    gcloud sql instances patch ${DB_INSTANCE_NAME} --require-ssl
    if [ $? -gt 0 ]; then
        echo -e "error configuring ssl"
        exit 1
    fi


    # TODO: in order to connect to MySQL data base we need to assign a static ip to our compute instance
    # set compute instance to have static IP
    # add compute instance static IP to accepted DB connection


#   mysql -uroot -p -h 35.247.24.229 \
#    --ssl-ca=server-ca.pem --ssl-cert=client-cert.pem \
#    --ssl-key=client-key.pem


}

db_delete() {

    # deletes database from GCP
    # use with caution - GCP will not allow you to re-use the same db instance name for 7 days
    # https://cloud.google.com/sql/docs/mysql/delete-instance
    echo -e "deleting database..."
    gcloud sql instances delete ${DB_INSTANCE_NAME}

}

db_stop() {

    # reference: https://cloud.google.com/sql/docs/mysql/start-stop-restart-instance
    echo -e "shutting down database..."
    gcloud sql instances patch $DB_INSTANCE_NAME --activation-policy NEVER

}

db_start() {

    # reference: https://cloud.google.com/sql/docs/mysql/start-stop-restart-instance
    echo -e "staring database..."
    gcloud sql instances patch $DB_INSTANCE_NAME --activation-policy ALWAYS

}


start_all() {
    # check to see if we have the right parameters
    if [ "x$version" == "x" -o "x$image_id" == "x" ]; then
        echo -e "ERROR: start_all requireds <version> and <image_id> parameters"
        usage
        exit 1
    fi
    setup # initializes your gcloud environment and starts your database
    if [ $? -gt 0 ]; then
        echo -e "error setting up project"
        exit 1
    fi
    bucket_copy # copy files to GCP file bucket if they are not already there
    if [ $? -gt 0 ]; then
        echo -e "error copying files to gcp bucket"
        exit 1
    fi
    image_upload # copy files to GCP file bucket
    if [ $? -gt 0 ]; then
        echo -e "error putting image into registry"
        exit 1
    fi
    cluster_start # creates your k8 cluster and deploys your container
    if [ $? -gt 0 ]; then
        echo -e "error starting k8 cluster"
        exit 1
    fi
}

# set current project for gcp
gcloud config set project ${PROJECT_ID}

if [ "x${command}" == "xbucket_copy" ]; then
    bucket_copy
elif [ "x${command}" == "xbucket_create" ]; then
    bucket_create
elif [ "x${command}" == "xbucket_delete" ]; then
    bucket_delete
elif [ "x${command}" == "xcluster_start" ]; then
    cluster_start
elif [ "x${command}" == "xcluster_stop" ]; then
    cluster_stop
elif [ "x${command}" == "xdb_create" ]; then
    db_create
elif [ "x${command}" == "xdb_delete" ]; then
    db_delete
elif [ "x${command}" == "xdb_stop" ]; then
    db_stop
elif [ "x${command}" == "xdb_start" ]; then
    db_start
elif [ "x${command}" == "ximage_delete" ]; then
    image_delete
elif [ "x${command}" == "ximage_deploy" ]; then
    image_deploy
elif [ "x${command}" == "ximage_upload" ]; then
    image_upload
elif [ "x${command}" == "xsetup" ]; then
    setup
elif [ "x${command}" == "xstart_all" ]; then
    start_all
elif [ "x${command}" == "xteardown" ]; then
    teardown
else
    echo -e "command $command not found"
    usage
    exit 1
fi


