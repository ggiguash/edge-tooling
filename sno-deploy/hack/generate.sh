#!/bin/bash

source $(dirname $0)/functions.sh

run_policyGen() {
    src=$(readlink -f ${1:-no_source_given})
    dst=$(readlink -f ${2:-no_dest_given})
    echo "src: $src"
    echo "dst: $dst"
    local policy_gen_bin="ztp/policygenerator/PolicyGenerator"
    ${cluster_home}/workdir/cnf-features-deploy/$policy_gen_bin \
      -sourcePath $cluster_home/workdir/cnf-features-deploy/ztp/source-crs \
      -pgtPath $src \
      -outPath $dst \
      -wrapInPolicy=false
}

# The get_cluster_home function checks for the directory validity
cluster_name=$1
cluster_home=$(get_cluster_home $cluster_name)
if [ $? -ne 0 ] ; then
    # The variable contains the error string on failure
    echo $cluster_home
    exit 1
fi

# Generate the Policy yaml and Operator subscriptions for a DU SNO Cluster
source_file=${cluster_home}/${cluster_name}.env
if [ ! -f $source_file ]; then
    echo " | ${source_file}.env file does not exist"
    echo " | run (make CLUSTER=<cluster_name> env_prep) to generate the .env file"
    exit 1
fi
source $source_file

gen_dir=$cluster_home/workdir/generated
mkdir -p $gen_dir/source
for f in ./day_two/templates/*.yaml; do
    envsubst <${f} >$gen_dir/source/$(basename ${f})
done

echo "- Generating raw CRs"
mkdir -p $gen_dir/out_ref
mkdir -p $gen_dir/generated_ref
for file in $gen_dir/source/*; do
    echo "$file"
    cat $file | yq eval '.spec.sourceFiles[] |= .policyName=""' - >$gen_dir/generated_ref/$(basename $file)
done

run_policyGen $gen_dir/generated_ref $gen_dir/out_ref

echo "- Patch Work"
echo "  Done as temporary fixes"
for file in $gen_dir/out_ref/customResource/du-sno/PerformanceProfile-*.yaml; do
    echo " | Changing apiVersion to v2 $(basename $file)"
    mv $file "${file}_bak"
    cat "${file}_bak" | yq eval '.apiVersion ="performance.openshift.io/v2"' - >$file
    rm "${file}_bak"
done

# Subscription status are updated to account for raw yaml validation failures
# The installPlanApproval field is also changed to Automatic for local development
for file in $gen_dir/out_ref/customResource/common/Subscription-*.yaml; do
        echo " | Updating Subscription status $(basename $file)"
        mv $file "${file}_bak"
        cat "${file}_bak" | yq eval '.status.lastUpdated ="2022-01-10T10:10:10Z" | .spec.installPlanApproval = "Automatic"' - >$file
        rm "${file}_bak"
done
