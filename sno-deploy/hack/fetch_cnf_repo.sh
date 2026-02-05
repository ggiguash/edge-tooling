#!/bin/bash

source $(dirname $0)/functions.sh

##
# CNF Repo contains latest policy templates in:
#   cnf-features-deploy/ztp/gitops-subscriptions/argocd/resource-hook-example
#
# This script is here to help pull in latest for later processing and to keep templates up to date
##
cnf_repo=https://github.com/openshift-kni/cnf-features-deploy.git

print_usage() {
    printf "
$(basename $0) -n <cluster_name> [-ur]
    -n | cluster name (mandatory)
    -u | update to latest from ($cnf_repo)
    -r | rebuild from latest ($cnf_repo)
"
}

build() {
    cd $cnf_repo_dir
    go mod tidy && go mod vendor
    cd $cnf_policy_gen_path
    go build -mod=vendor -o PolicyGenerator
}

cluster_name=""
update=false
rebuild=false
while getopts "n:ur" f; do
    case "$f" in
    n)
        cluster_name=${OPTARG}
        check_empty "$cluster_name" "cluster name"
        ;;
    u)
        update=true
        ;;
    r)
        rebuild=true
        ;;
    *)
        print_usage
        exit 1
        ;;
    esac
done

# The get_cluster_home function checks for the directory validity
cluster_home=$(get_cluster_home ${cluster_name})
if [ $? -ne 0 ] ; then
    # The variable contains the error string on failure
    echo $cluster_home
    exit 1
fi

cnf_repo_dir=${cluster_home}/workdir/cnf-features-deploy
if [ -e "$cnf_repo_dir" ] && [ $update == true ]; then
    cd $cnf_repo_dir
    git pull
elif [ ! -e "$cnf_repo_dir" ]; then
    mkdir -p $cnf_repo_dir
    cd $cluster_home/workdir
    git clone --recursive $cnf_repo
fi

cnf_policy_gen_path=${cnf_repo_dir}/ztp/policygenerator
if [ ! -f $cnf_policy_gen_path/PolicyGenerator ] || [ $rebuild == true ]; then
    echo "building PolicyGenerator bin"
    build
fi
