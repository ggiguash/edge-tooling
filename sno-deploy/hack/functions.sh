#!/bin/bash

# Assisted installer CLI image
assisted_installer_image=quay.io/karmab/aicli:latest

function get_cluster_home() {
    local cluster_name=$1
    local create_home=${2:-false}
    local cluster_home=$HOME/.sno-deploy/$cluster_name
    if [ -z "$cluster_name" ] ; then
        echo "The cluster name argument is mandatory"
        return 1
    fi

    if [ $create_home == true ] && [ ! -e ${cluster_home} ] ; then
        mkdir -p $cluster_home
        if [ $? -ne 0 ] ; then
            echo "Failed to create the '$cluster_home' directory"
            return 1
        fi
    fi 

    if [ ! -e "$cluster_home" ] ; then
        echo "The cluster home directory '$cluster_home' does not exist"
        return 1
    fi
    echo $cluster_home
    return 0
}

function check_empty() {
    # If the next value starts with a hyphen, it is empty as we encountered the next option
    if [ -z "$1" ] || [[ $1 == -* ]]; then
        echo "$2 can not be empty"
        exit 1
    fi
}

function aicli_update() {
    podman pull $assisted_installer_image
}

function aicli() {
    podman run --net host -i --rm -e AI_OFFLINETOKEN=$(cat $offline_token) \
        -v $HOME/.aicli:/root/.aicli:z -v $work_dir:/workdir:z -v $pull_secret:/workdir/openshift_pull.json:z \
        -v $public_key:/root/.ssh/id_rsa.pub:z -w /workdir $assisted_installer_image "$@"
    if [ $? != 0 ] ; then
        echo " |  ❌ Failed to run the aicli command"
        exit 1
    fi
}

function watching_cluster_events() {
    local clusterName=$1
    local evtName=$2
    local prevEvent=""

    echo " - watching cluster events for '$evtName' event"
    while true; do
        # Note: The xargs command trims spaces from the string
        local lastEvent=$(aicli get events $clusterName 2>/dev/null | grep '^|' | tail -1 | xargs -0)
        if [ $? -ne 0 ]; then
            echo " |  ❌ Failed watching cluster events - trying again"
        else
            local curEvent=$(echo $lastEvent | awk -F'|' '{print $2, $3}')
            if [ "$prevEvent" != "$curEvent" ] ; then
                echo $curEvent
                prevEvent="$curEvent"
            fi

            local status=$(aicli info cluster $clusterName -f status | grep ^status: | awk '{print $2}')
            if [ "$status" == "$evtName" ]; then
                break
            fi
        fi
        sleep 5
    done
}

function mco_core_pinning_config() {
    local yamlOut=$1
    local mcoCores=$2
    [ -z "${mcoCores}" ] && mcoCores=2

    if [ -z "$yamlOut" ] ; then
      echo " |_ ❌ Failed to generate MCO core pinning configuration"
      return 1    
    fi

    echo " - creating workload partitioning config for $mcoCores cores"
    local workprt=$(cat <<EOF | base64 -w 0
[crio.runtime.workloads.management]
activation_annotation = "target.workload.openshift.io/management"
annotation_prefix = "resources.workload.openshift.io"
resources = { "cpushares" = 0, "cpuset" = "0-$(( mcoCores - 1))" }
EOF
)

    echo " - creating workload pinning config for $mcoCores cores"
    local workpin=$(cat <<EOF | base64 -w 0
{
  "management": {
    "cpuset": "0-$(( mcoCores - 1))"
  }
}
EOF
)

    echo " - creating sno machine configs for $mcoCores cores"
    cat <<EOF >$yamlOut
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfig
metadata:
  labels:
    machineconfiguration.openshift.io/role: master
  name: 02-master-workload-partitioning
spec:
  config:
    ignition:
      version: 3.2.0
    storage:
      files:
      - contents:
          source: data:text/plain;charset=utf-8;base64,${workprt}
        mode: 420
        overwrite: true
        path: /etc/crio/crio.conf.d/01-workload-partitioning
        user:
          name: root
      - contents:
          source: data:text/plain;charset=utf-8;base64,${workpin}
        mode: 420
        overwrite: true
        path: /etc/kubernetes/openshift-workload-pinning
        user:
          name: root
EOF
}

function mco_rt_kernel_config() {
    local yamlOut=$1

    if [ -z "$yamlOut" ] ; then
      echo " |_ ❌ Failed to generate MCO realtime kernel configuration"
      return 1    
    fi

    echo " - creating realtime kernel machine configs"
    cat <<EOF >$yamlOut
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfig
metadata:
  labels:
    machineconfiguration.openshift.io/role: master
  name: realtime-master
spec:
  kernelType: realtime
EOF
}
