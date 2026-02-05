#!/bin/bash

source $(dirname $0)/functions.sh

refreshed=false
all_clusters=""
cluster_data=""
cluster_name=${1}
offline_token=${2}

if [ $# -ne 2 ]; then
    echo "Usage: $(basename $0) <cluster_name> <offline_token_file>"
    exit 1
fi

refresh_token() {
    curl -sL \
        --data-urlencode "client_id=cloud-services" \
        --data-urlencode "grant_type=refresh_token" \
        --data-urlencode "refresh_token=$(cat $offline_token)" \
        https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token | jq '.access_token' -r >$HOME/.aicli/token.txt
}

fetch_cluster_data() {
    all_clusters=$(curl -sLH "Authorization: Bearer $(cat ~/.aicli/token.txt)" https://api.openshift.com/api/assisted-install/v2/clusters)
    if [ $? -eq 0 ] && [ ! $(echo $all_clusters | jq 'if type!="array" then .code else "200" end') = "401" ]; then
        echo " |_ ✅ Successfully fetched cluster data"
    elif [ $refreshed = "false" ]; then
        echo " |_ ❌ Failed to fetch cluster id"
        echo " |_    Attempting to refresh token"
        refresh_token
        refreshed="true"
        fetch_cluster_data
    else
        echo " | err: $all_clusters"
        echo " |_ ❌ Failed to fetch cluster id"
        exit 1
    fi
}

fetch_cluster_credentials() {
    mkdir -p $cluster_home/creds
    curl -sL \
        -H "Authorization: Bearer $(cat ~/.aicli/token.txt)" \
        "https://api.openshift.com/api/assisted-install/v2/clusters/$1/downloads/credentials?file_name=$2" \
        -o "$cluster_home/creds/$2"
    if [ $? -eq 0 ]; then
        echo " |_ ✅ Successfully fetched $2"
    else
        echo " |_ ❌ Failed to fetch $2"
    fi
}

# The get_cluster_home function checks for the directory validity
cluster_home=$(get_cluster_home ${cluster_name})
if [ $? -ne 0 ] ; then
    # The variable contains the error string on failure
    echo $cluster_home
    exit 1
fi

fetch_cluster_data

cluster_id=$(echo $all_clusters | jq -e ".[] | select(.name ==\"$cluster_name\") | .id" -r)
if [ $? -eq 0 ]; then
    echo " |_ ✅ Successfully found cluster ($cluster_name)"
else
    echo " |_ ❌ Failed to fetch cluster id for cluster name ($cluster_name)"
    exit 1
fi
cluster_data=$(curl -sLH "Authorization: Bearer $(cat ~/.aicli/token.txt)" https://api.openshift.com/api/assisted-install/v2/clusters/$cluster_id)
cluster_vip=$(echo $cluster_data | jq '.ingress_vip' -r)
base_dns_domain=$(echo $cluster_data | jq '.base_dns_domain' -r)
cluster_network_cidr=$(echo $cluster_data | jq '.cluster_network_cidr' -r)
cluster_network_host_prefix=$(echo $cluster_data | jq '.cluster_networks[].host_prefix' -r)
machine_network_cidr=$(echo $cluster_data | jq '.machine_network_cidr' -r)
service_network_cidr=$(echo $cluster_data | jq '.service_network_cidr' -r)
host_mac_address=$(echo $cluster_data | jq '.hosts[0].inventory | fromjson | .interfaces[0].mac_address' -r)
host_memory=$(echo $cluster_data | jq '.hosts[0].inventory | fromjson | .memory.physical_bytes' -r)
host_cores=$(echo $cluster_data | jq '.hosts[0].inventory | fromjson | .cpu.count' -r)
openshift_version=$(echo $cluster_data | jq '.openshift_version' -r)

fetch_cluster_credentials $cluster_id kubeconfig
fetch_cluster_credentials $cluster_id kubeadmin-password

cat $cluster_home/creds/kubeconfig | yq eval ".clusters[0].cluster.server=\"https://${cluster_vip}:6443\"" - >$cluster_home/creds/kubeconfig-local
if [ $? -eq 0 ]; then
    echo " |_ ✅ Successfully created kubeconfig-local"
else
    echo " |_ ❌ Failed to create kubeconfig-local"
fi

echo "Generating hosts file"
cat <<EOF >$cluster_home/creds/hosts
$cluster_vip	api.$cluster_name.$base_dns_domain
$cluster_vip	oauth-openshift.apps.$cluster_name.$base_dns_domain
$cluster_vip	console-openshift-console.apps.$cluster_name.$base_dns_domain
$cluster_vip	grafana-openshift-monitoring.apps.$cluster_name.$base_dns_domain
$cluster_vip	thanos-querier-openshift-monitoring.apps.$cluster_name.$base_dns_domain
$cluster_vip	prometheus-k8s-openshift-monitoring.apps.$cluster_name.$base_dns_domain
$cluster_vip	alertmanager-main-openshift-monitoring.apps.$cluster_name.$base_dns_domain

$cluster_vip	$cluster_name
EOF

echo "Generating env file"
cat <<EOF >$cluster_home/$cluster_name.env
export SNO_CONFIG_NET_INTERFACE=enp1s0
export SNO_CONFIG_NET_HOST_PREFIX=$cluster_network_host_prefix
export SNO_CONFIG_NET_SERVICE_CIDR=$service_network_cidr
export SNO_CONFIG_NET_CLUSTER_CIDR=$cluster_network_cidr
export SNO_CONFIG_NET_MACHINE_CIDR=$machine_network_cidr
export SNO_CONFIG_NET_MAC_ADDRESS=$host_mac_address
export SNO_CONFIG_NET_CLUSTER_IP=$cluster_vip
export SNO_CONFIG_RESERVED_CORES=0,1
export SNO_CONFIG_ISOLATED_CORES=2-$(expr $host_cores - 1)
export SNO_CONFIG_BASE_DOMAIN=$base_dns_domain
export SNO_CONFIG_HOSTNAME=$cluster_name
export SNO_CONFIG_HUGE_PAGES=1
export SNO_CONFIG_OPENSHIFT_VERSION=$openshift_version
export SNO_CONFIG_OPENSHIFT_RELEASE=$(echo $openshift_version | grep -oP '\K([0-9]+.[0-9]+)')
export SNO_CONFIG_OPERATOR_CHANNEL=stable
EOF
