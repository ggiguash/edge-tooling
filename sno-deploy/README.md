# SNO Development Cluster Setup

The purpose of this repo is to quickly stand up a SNO cluster with Workload Partitioning enabled & with configuration applied which approximates a "DU" cluster.

## Pre-req

To quickly check if you have all the right tools installed run the below command, it will install the missing tools.

```
make tool_check
```

You will need the below credentials, please be mindful that they should be kept secure 
> Note! 
> The ~/.sno-deploy directory is the default location for these files.

- `openshift_pull.json`
  - https://console.redhat.com/openshift/create/local
- `offline-token`
  - https://cloud.redhat.com/openshift/token
- `openshift-dev` ssh key
  - You can create a new SSH key below, or use a pre-existing one.
    ```
    ssh-keygen -t rsa -b 4096 -f ~/.ssh/openshift-dev -q -N ""
    ```

If you have a pre-existing private key, you can use the below command to generate a public key from it.

```sh
ssh-keygen -f ~/.ssh/openshift-dev.pem -y > ~/.ssh/openshift-dev.pub
```

## Usage

Run the following command to see all the supported arguments that can be passed to the deployment procedure via the DEPLOY_ARGS variable.
```sh
$ make help

Flags:
    -h | this help message
    -n | cluster name (default sno-ggiguash-120621)
    -p | pool name (default default)
    -f | file for SSH public key (default /home/ggiguash/.ssh/openshift-dev.pub)
         public key is required - create with 'ssh-keygen -t rsa -b 4096 -f ~/.ssh/openshift-dev -q -N ""' command
    -s | file for pull secret (default /home/ggiguash/.sno-deploy/openshift_pull.json)
         pull secret is required - download from https://console.redhat.com/openshift/create/local
    -o | file for offline token (default /home/ggiguash/.sno-deploy/offline-token)
         offline token is required - download from https://cloud.redhat.com/openshift/token
    -c | cores for the vm (default 8)
    -m | memory for the vm (default 32768)  
    -d | base domain (default e2e.bos.redhat.com)  
    -v | openshift version (default 4.10)
    -b | basic cluster configuration (do not apply RT kernel or Telco-specific options)
    -k | add RT kernel to basic cluster configuration
```

Deploy an SNO cluster with the default `8 cores` and `32GiB` of memory

```sh
make CLUSTER="my-cluster-name"
```

Alternatively, use DEPLOY_ARGS variable to change the default settings.
```
make CLUSTER="my-cluster-name" DEPLOY_ARGS="-c 16"
```

Tasks the `make` command will do.

1. Create cluster in `assisted installer`
1. Download discovery ISO.
1. Launch VM with discovery ISO.
1. Initiate install of the cluster.
1. Fetch and generate DU configs.
1. Install DU operators.
1. Install DU configs.

> Note! 
> Use the special `all_basic` make target to create a cluster without realtime kernel, core pinning and DU configuration or operators.

Once that command is run, it will initiate a VM with a Discovery ISO image that will reach out to `console.redhat.com` servers to begin the initialization steps. The script will launch the discovery ISO in the background and interact with the assisted installer API.

Things should progress automatically from this point on, it will take sometime for the cluster to come up so be patient. The script will call out for recent events to the assisted installer API so you should be able to see the recent events on your terminal.

> Note!
> The VM will be given the same `hostname` as the one given to the cluster.

Follow the next steps once your cluster is fully provisioned.

### Cluster Configuration

The script stores all the cluster configuration and intermediate files in `~/.sno-deploy/$CLUSTER` directory. 

```sh
$ ls -1 ~/.sno-deploy/sno-config-test/
creds
sno-config-test.env
workdir
```

The `workdir` directory contains all the intermediate files, while the `creds` directory and `$CLUSTER.env` file contain information necessary for connecting to the cluster after it is created. See the [env_prep](#env_prep) section for more information.

### Post Cluster Creation

The script will make a good effort to try and apply the `DU` configs to your cluster. This might take some time, but the process is idempotent and it can be rerun using the below command if the `DU` application is cancelled.

```sh
make CLUSTER=$CLUSTER apply
```

### Running tasks individually

> Note!
> This is not needed if you just ran the `make CLUSTER=$CLUSTER` default

If you need to ever run the make tasks individually, below is a description of what they do.

#### deploy

`deploy` will create the cluster and install it

```sh
make CLUSTER=$CLUSTER deploy
```

#### env_prep

`env_prep` will reach out to the assisted installer API and download your cluster credentials and create an `$CLUSTER.env` file that will be used for generating DU configs.

Furthermore, a `creds` folder will be generated with your `kubeconfig` as well as your `kubeadmin-password`. A Hosts file will also be generated for ease, please copy the contents and paste them into your `/etc/hosts` otherwise a `kubeconfig-local` file is also created with the local IP of your cluster if you wish to use that directly. (be advised there will be ssl errors that you will need to ignore)

```sh
make CLUSTER=$CLUSTER env_prep
```

#### generate

`generate` will download the latest configs from the DU repo, build the `PolicyGenerator` utility used by the `DU` team and generate the configs.

The [DU Policy Generator](https://github.com/openshift-kni/cnf-features-deploy/tree/master/ztp/policygenerator) is used to generate the configs from the templates and `$CLUSTER.env` file.

```sh
make CLUSTER=$CLUSTER clean generate
```

#### apply

`apply` will apply the generated configs to your cluster in two tasks, first it will create the operators in the clusters and then it will apply the configurations.

```sh
make CLUSTER=$CLUSTER apply
```
