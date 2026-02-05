#!/bin/bash

source $(dirname $0)/functions.sh

VERIFY_INTERVAL=${VERIFY_INTERVAL:-60}
k="kubectl $KUBECTL_FLAGS"

function verify_resources() {
    echo "- verifying resources"
    data=$(eval $k get catalogsource redhat-operators -n openshift-marketplace -ojson)
    result=$(echo $data | jq -e '.status.connectionState.lastObservedState == "READY"')
    if [ $? -eq 0 ] && [ "$data" != "" ]; then
        echo " |_ ✅ catalog resource exists and is ready"
    else
        echo " |  redhat-operators catalog is not in a ready state yet"
        echo " |_ ❌ Failed verification"
        return 1
    fi
}

function verify_configs() {
    echo "- verifying configs"
    echo " | - verifying performance config"
    data=$(eval $k \
        get performanceprofile openshift-node-performance-profile -ojson)
    result=$(echo $data | jq -e '.status.conditions[] | select(.type == "Available") | .status == "True"')
    if [ $? -eq 0 ] && [ "$data" != "" ]; then
        echo " |_ ✅ Successfully verified openshift-node-performance-profile"
    else
        echo " |_ ❌ Failed verification openshift-node-performance-profile"
        return 1
    fi

    echo " | - verifying tuning config"
    result=$(eval $k \
        get tuned performance-patch -n openshift-cluster-node-tuning-operator -ojson)
    if [ $? -eq 0 ]; then
        echo " |_ ✅ Successfully verified tuned performance patch exists"
    else
        echo " |_ ❌ Failed verification tuned performance patch"
        return 1
    fi

    # We check the kernel version of all nodes here
    # if the number of realtime kernel version count does not match the node count we error out
    echo " | - verifying realtime kernel"
    result=$(eval $k \
        get nodes -ojson | jq -e '
        .items as $root |
        [.items[].status.nodeInfo.kernelVersion | select(contains(".rt")) ]
        | length == ($root | length)
        ')
    if [ $? -eq 0 ]; then
        echo " |_ ✅ Successfully verified all nodes are using realtime kernel"
    else
        echo " |_ ❌ Failed verification of realtime kernel on all nodes"
        return 1
    fi
}

function verify_operators() {
    echo "- verifying operators"
    err=0
    for file in ${cluster_home}/workdir/generated/out_ref/customResource/common/Subscription-*.yaml; do
        name=$(cat $file | yq eval '.metadata.name' -)
        namespace=$(cat $file | yq eval '.metadata.namespace' -)
        result=$(eval $k get subs $name -n $namespace)
        if [ $? -eq 0 ]; then
            echo " |_ ✅ Successfull verified $name was created in $namespace"
        else
            err=1
            echo " |_ ❌ Failed verification $name in $namespace"
        fi
    done
    if [ $err -ne 0 ]; then
        return 1
    fi

    operators=$(eval $k get csv -A -ojson)
    errored_operators=$(echo $operators | jq '.items | unique_by(.metadata.name) | [.[]| select(.status.phase != "Succeeded") | {name:.metadata.name, namespace: .metadata.namespace}]')
    result=$(echo $errored_operators | jq -e 'length == 0')
    if [ $? -eq 0 ]; then
        echo $operators | jq -r \
            '.items | unique_by(.metadata.name) | .[]| select(.status.phase == "Succeeded") | " |- Name: \(.metadata.name)\n |  Namespace: \(.metadata.namespace)"'
        echo " |_ ✅ Successfully verified operators"
    else
        echo " | $errored_operators"
        echo " |_ ❌ Failed to verify operators, the above operators have not succeeded"
        return 1
    fi
}

function print_usage() {
    printf "
$(basename $0) -n <cluster_name> [-rocal]
    -n | cluster name (mandatory)
    -r | verify resources
    -o | verify operators
    -c | verify configs
    -a | verify all of the resources, operators, configs
    -l | loop and retry verification until successful
"
}

cluster_name=""
resources=false
operators=false
configure=false
retryLoop=false
retryMessage="stopping on attempt %d"
retryCounts=1
while getopts "n:rocal" f; do
    case "$f" in
    n)
        cluster_name=${OPTARG}
        check_empty "$cluster_name" "cluster name"
        ;;
    r)
        resources=true
        ;;
    o)
        operators=true
        ;;
    c)
        configure=true
        ;;
    a)
        resources=true
        operators=true
        configure=true
        ;;
    l)
        retryLoop=true
        retryMessage="retrying in ${VERIFY_INTERVAL}s - attempt %d"
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

if [ $resources == true ]; then
    while true ; do 
        verify_resources
        if [ $? -ne 0 ]; then
            printf " |_ ❌ Failed resource verification, $retryMessage\n" $retryCounts
            [ $retryLoop = false ] && exit 1
            sleep $VERIFY_INTERVAL
            let retryCounts++
        else
            break
        fi
    done
fi

if [ $operators == true ]; then
    while true ; do 
        verify_operators
        if [ $? -ne 0 ]; then
            printf " |_ ❌ Failed operator verification, $retryMessage\n" $retryCounts
            [ $retryLoop = false ] && exit 1
            sleep $VERIFY_INTERVAL
            let retryCounts++
        else
            break
        fi
    done
fi

if [ $configure == true ]; then
    while true ; do 
        verify_configs
        if [ $? -ne 0 ]; then
            printf " |_ ❌ Failed configs verification, $retryMessage\n" $retryCounts
            [ $retryLoop = false ] && exit 1
            sleep $VERIFY_INTERVAL
            let retryCounts++
        else
            break
        fi
    done
fi
