#!/bin/bash

source $(dirname $0)/functions.sh

APPLY_INTERVAL=${APPLY_INTERVAL:-60}
k="kubectl $KUBECTL_FLAGS"

function apply_olm_metadata_refresh() {
    bundles=$(eval $k get configmaps -n openshift-marketplace -ojson | jq '.items[]|select(.metadata.annotations |has("operators.operatorframework.io.bundle.package.v1")) | .metadata.name' -r)
    for bundle in $bundles; do
        echo "deleting bundle configmap $bundle"
        eval $k delete configmap $bundle -n openshift-marketplace
    done

    empty_bundles=$(eval $k get configmaps -n openshift-marketplace -ojson | jq '.items[]|select(.data == null and (.metadata.annotations |length) == 0) | .metadata.name' -r)
    for bundle in $empty_bundles; do
        echo "deleting empty bundle $bundle"
        eval $k delete configmap $bundle -n openshift-marketplace
    done

    # after we delete empty bundles we need to clean up any failed installs to allow the operator install to continue
    failed_installplans=$(eval $k get installplans -A -ojson | jq '[.items[] | select(.status.phase == "Failed") | .metadata]')
    for ((i = 0; i < $(echo $failed_installplans | jq 'length' -r); i++)); do
        printf "deleting failed installs bundle %s\n" $(echo $failed_installplans | jq ".[$i].name" -r)
        eval $k delete installplan $(echo $failed_installplans | jq ".[$i] | \"\(.name) -n \(.namespace)\"" -r)
    done
}

function apply_operators() {
    $(dirname $0)/verify.sh -n $cluster_name -r
    if [ $? -ne 0 ]; then
        return 1
    fi

    # Sometimes we need to clean up error states that will stop operators from installing
    # we look for a empty bundles and delete them
    apply_olm_metadata_refresh

    echo "applying operators"
    eval $k apply -Rf $cluster_home/workdir/generated/out_ref/customResource/common
    if [ $? -eq 0 ]; then
        echo " |_ ✅ Successfully applied operators"
        return 0
    fi
    return 1
}

function apply_configs() {
    $(dirname $0)/verify.sh -n $cluster_name -o
    if [ $? -ne 0 ]; then
        return 1
    fi

    local applied_group=false
    local applied_tuning=false
    echo "applying configurations"

    echo " - applying group du"
    eval $k apply -Rf $cluster_home/workdir/generated/out_ref/customResource/group-du-sno
    if [ $? -eq 0 ]; then
        echo " |_ ✅ Successfully applied group du"
        applied_group=true
    else
        echo " |_ ❌ Failed to apply group du"
    fi

    echo " - applying performance tuning"
    eval $k apply -Rf $cluster_home/workdir/generated/out_ref/customResource/du-sno
    if [ $? -eq 0 ]; then
        echo " |_ ✅ Successfully applied performance tuning"
        applied_tuning=true
    else
        echo " |_ ❌ Failed to apply performance tuning"
    fi
    
    if [ $applied_group = false ] || [ $applied_tuning = false ] ; then
        return 1
    fi
    return 0
}

print_usage() {
    printf "
$(basename $0) -n <cluster_name> [-ocl]
    -n | cluster name (mandatory)
    -o | apply operators
    -c | apply configs
    -l | loop and retry apply until successful
"
}

cluster_name=""
operators=false
configure=false
retryLoop=false
retryMessage="stopping on attempt %d"
retryCounts=1
while getopts "n:ocl" f; do
    case "$f" in
    n)
        cluster_name=${OPTARG}
        check_empty "$cluster_name" "cluster name"
        ;;
    o)
        operators=true
        ;;
    c)
        configure=true
        ;;
    l)
        retryLoop=true
        retryMessage="retrying in ${APPLY_INTERVAL}s - attempt %d"
        ;;
    *)
        print_usage
        exit 1
        ;;
    esac
done

# The cluster_home function checks for the directory validity
cluster_home=$(get_cluster_home ${cluster_name})
if [ $? -ne 0 ] ; then
    # The variable contains the error string on failure
    echo $cluster_home
    exit 1
fi

if [ $operators == true ]; then
    while true ; do 
        apply_operators
        if [ $? -ne 0 ]; then
            printf " |_ ❌ Failed to apply operators, $retryMessage\n" $retryCounts
            [ $retryLoop = false ] && exit 1
            sleep $APPLY_INTERVAL
            let retryCounts++
        else
            break
        fi
    done
fi

if [ $configure == true ]; then
    configRetryCount=1
    while true ; do 
        apply_configs
        if [ $? -ne 0 ]; then
            printf " |_ ❌ Failed to apply configs, $retryMessage\n" $retryCounts
            [ $retryLoop = false ] && exit 1
            sleep $APPLY_INTERVAL
            let retryCounts++
            let configRetryCount++
        else
            break
        fi
        if [ $configRetryCount -gt 5 ]; then
            apply_olm_metadata_refresh
        fi
    done
fi
