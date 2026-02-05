#!/bin/bash

source $(dirname $0)/hack/functions.sh

# Cluster name is used as VM name as well as Assisted Installer console name
cluster_name="sno-$USER-$(date +%m%d%y)"
# Infra Env object name is derived from the cluster name
infraenv_name=${cluster_name}_infra-env
# Public SSH key file name
public_key=$HOME/.ssh/openshift-dev.pub
# Used to pull images from registries during cluster install
pull_secret=$HOME/.sno-deploy/openshift_pull.json
# Used to authenticate with Assisted Installer API
offline_token=$HOME/.sno-deploy/offline-token
# Storage pool name where ISO and cluster VM data will be stored
pool_name=default
# Default cores to use for VM
cores=8
# Default memory to use for VM
memory=32768
# Default domain to use
base_domain=e2e.bos.redhat.com
# Default openshift version to install
openshift_version=4.10
# Telco configs apply pinned cored and default telco operators are installed
telco_config=true
# Configure RT kernel as machine config (note Telco configs will also apply RT kernel, this is used if only RT is requested on SNO)
add_rtkernel=false

# Helper messages in print statements
pkey_helper_msg="public key is required - create with 'ssh-keygen -t rsa -b 4096 -f ~/.ssh/openshift-dev -q -N \"\"' command"
pull_helper_msg="pull secret is required - download from https://console.redhat.com/openshift/create/local"
offline_helper_msg="offline token is required - download from https://cloud.redhat.com/openshift/token"
# HyperThreading file location, used to determine is we are running on a host with HT enabled and how many cores we should pin
ht_file="/sys/devices/system/cpu/smt/active"

print_usage() {
  printf "
Flags:
    -h | this help message
    -n | cluster name (default $cluster_name)
    -p | pool name (default $pool_name)
    -f | file for SSH public key (default $public_key)
         $pkey_helper_msg
    -s | file for pull secret (default $pull_secret)
         $pull_helper_msg
    -o | file for offline token (default $offline_token)
         $offline_helper_msg
    -c | cores for the vm (default $cores)
    -m | memory for the vm (default $memory)  
    -d | base domain (default $base_domain)  
    -v | openshift version (default $openshift_version)
    -b | basic cluster configuration (do not apply RT kernel or Telco-specific options)
    -k | add RT kernel to basic cluster configuration
"
}

while getopts "n:p:f:s:o:c:m:d:v:bkh" f; do
  case "$f" in
  n)
    cluster_name=${OPTARG}
    infraenv_name=${cluster_name}_infra-env
    check_empty "$cluster_name" "cluster name"
    ;;
  p)
    pool_name=${OPTARG}
    check_empty "$pool_name" "pool name"
    ;;
  f)
    public_key=${OPTARG}
    check_empty "$public_key" "public key"
    ;;
  s)
    pull_secret=${OPTARG}
    check_empty "$pull_secret" "pull secret"
    ;;
  o)
    offline_token=${OPTARG}
    check_empty "$offline_token" "offline token"
    ;;
  c)
    cores=${OPTARG}
    check_empty "$cores" "cores"
    ;;
  m)
    memory=${OPTARG}
    check_empty "$memory" "memory"
    ;;
  d)
    base_domain=${OPTARG}
    check_empty "$base_domain" "base domain"
    ;;
  v)
    openshift_version=${OPTARG}
    check_empty "$openshift_version" "openshift version"
    ;;
  b)
    telco_config=false
    ;;
  k)
    add_rtkernel=true
    ;;
  h)
    print_usage
    exit 0
    ;;
  *)
    print_usage
    exit 1
    ;;
  esac
done

if [ -z "$cluster_name" ] ; then
  echo "Cluster name argument is mandatory"
  exit 1
fi

if [ ! -f $public_key ] ; then
  echo $pkey_helper_msg
  exit 1
fi

if [ ! -f $pull_secret ]; then
  echo $pull_helper_msg
  exit 1
fi

if [ ! -f $offline_token ]; then
  echo $offline_helper_msg
  exit 1
fi

# Create the cluster home and work directories
cluster_home=$(get_cluster_home $cluster_name true)
if [ $? -ne 0 ] ; then
  # The variable contains the error string on failure
  echo $cluster_home
  exit 1
fi
work_dir=${cluster_home}/workdir
mkdir -p $work_dir

echo " - creating aicli directory if not present"
mkdir -p $HOME/.aicli

echo " - updating aicli image"
aicli_update

echo " - creating aicli cluster ($cluster_name)"
aicli create cluster $cluster_name \
  -P openshift_version=$openshift_version \
  -P sno=true \
  -P base_dns_domain=$base_domain \
  -P user_managed_networking=true \
  -P requested_hostname=$cluster_name \
  -P network_type=OVNKubernetes # SDN network is not supported for SNO clusters
if [ $? -ne 0 ]; then
  echo " |_ ❌ Failed to create the cluster"
  exit 1
fi

cluster_id=$(aicli info cluster $cluster_name -f id | grep -oP 'id:\s+\K([0-9A-Za-z-]+)')
echo "Cluster created with ID: ($cluster_id)"

if [ $telco_config = true ] ; then
  pinned_cores=2
  if [ -e $ht_file ] && [ "$(cat $ht_file)" = "1" ] ; then
    # if HT is enabled, 2 cores are equal to 4 vCPUs
    pinned_cores=4
    echo " - hyperthreading detected, changed pinned management workloads to ($pinned_cores cores)"
  fi
  # Limit control plane to 2 cores or 4 vCPUs for a Telco DU SNO cluster
  mco_core_pinning_config ${work_dir}/mco-core-pinning.yaml $pinned_cores
else
  echo " - skipping cluster core pinning setup"
fi

# Telco DU configuration requires realtime kernel
if [ $telco_config = true ] || [ $add_rtkernel = true ] ; then
  mco_rt_kernel_config ${work_dir}/mco-rt-kernel.yaml
else
  echo " - skipping realtime kernel setup"
fi

echo " - creating manifests"
aicli create manifests --dir . $cluster_name
echo " - downloading ISO"
aicli download iso $cluster_name

echo " - running virtual machine install"
sudo echo " - Using Sudo"
if [ $? -ne 0 ]; then
  echo " |_ ❌ Failed sudo"
  exit 1
fi

# Read the directory of the pool
pool_dir=$(sudo virsh pool-dumpxml $pool_name | tr -d '\n' | sed 's/<\/path>.*//g' | sed 's/.*<path>//g')
if [ $? -ne 0 ] || [ -z "$pool_dir" ] ; then
  echo " |_ ❌ Failed to obtain the path from $pool_name pool"
  exit 1
fi

# Cluster ISO should be located in the pool directory, or another pool is created by virt-install
sudo mv ${work_dir}/${cluster_name}.iso ${pool_dir}/${cluster_name}.iso
if [ $? -ne 0 ] ; then
  echo " |_ ❌ Failed to move the cluster ISO file to the $pool_dir path"
  exit 1
fi

osvariant=$(osinfo-query -f short-id os | grep ' linux' | tail -1)
sudo virt-install --name=$cluster_name \
  --vcpus=$cores,cores=$cores \
  --cpu host \
  --cpuset=auto \
  --memory=$memory \
  --disk pool=${pool_name},size=120 \
  --cdrom=${pool_dir}/$cluster_name.iso \
  --os-variant $osvariant \
  --noautoconsole \
  --wait=-1 \
  --events on_reboot=restart &
install_pid=$!

sleep 2
if [ -e /proc/$install_pid ]; then
  echo " |_ ✅ Successfully started discovery virtual machine"
else
  echo " |_ ❌ Failed to start virtual machine"
  exit 1
fi

echo " - waiting for the hosts to be ready"
while true ; do
  host_count=$(aicli info cluster $cluster_name -f enabled_host_count | grep ^enabled_host_count: | awk '{print $2}')
  if [ "$host_count" == "1" ] ; then
    echo " |_ ✅ hosts are ready"
    break
  else
    echo " |_ ❌ hosts not ready yet - trying again, this might take a moment"
  fi

  # Verify that the VM installation is still working
  if [ ! -e /proc/$install_pid ]; then
    echo " |_ ❌ Failed to install virtual machine"
    exit 1
  fi
  sleep 10
done

# Avoid patching the cluster prematurely before it is in "pending-for-input" state
watching_cluster_events $cluster_name "pending-for-input"

function aicli_get_host_name() {
  local cluster_name=$1
  local host_name=$(aicli get hosts | tr -d ' ' | grep '^|' | awk -v cname="$cluster_name" -F'|' '$4 == cname {print $2}')
  echo $host_name
}

echo " - patching the cluster"
updated_name=false
updated_networks=false
while true ; do
  if [ "$updated_name" == "false" ] ; then
    # The 'aicli update host' command only works if the current cluster host name argument is correct. 
    # In some cases, the current host name may not be 'localhost'.
    # To work around race conditions when updating the cluster host name, run the following steps:
    # - Get the current cluster host name
    # - Update to the new name
    # - Set the updated flag after verifying that the update worked
    cluster_host=$(aicli_get_host_name $cluster_name)
    if [ ! -z "$cluster_host" ] ; then
      aicli update host $cluster_host -P name=$cluster_name

      cluster_host=$(aicli_get_host_name $cluster_name)
      [ "$cluster_name" == "$cluster_host" ] && updated_name=true
    fi
  fi

  if [ "$updated_networks" == "false" ] ; then
    cluster_cidr=$(aicli info cluster $cluster_name -f connectivity_majority_groups | grep ^connectivity_majority_groups: | awk -F\" '{print $2}')
    if [[ $cluster_cidr =~ /[0-9]{1,2}$ ]] ; then
      aicli update cluster -P machine_networks="[$cluster_cidr]" $cluster_name
      [ $? -eq 0 ] && updated_networks=true
    fi
  fi

  if [ "$updated_name" == "true" ] && [ "$updated_networks" == "true" ]  ; then
    echo " |_ ✅ Successfully patched cluster"
    break
  else
    echo " |_ ❌ Failed to patch cluster - trying again, this might take a moment"
  fi
  sleep 10
done

# Avoid starting the installation prematurely before the cluster is in "ready" state
watching_cluster_events $cluster_name "ready"

echo " - starting cluster install"
while true; do
  aicli start cluster $cluster_name
  if [ $? -eq 0 ] ; then
    echo " |_ ✅ Successfully started install process"
    break
  else
    echo " |_ ❌ Failed to start install process trying again"
  fi
  sleep 10
done

# Wait for the cluster installation to finish
watching_cluster_events $cluster_name "installed"

echo "Cluster is up!"
