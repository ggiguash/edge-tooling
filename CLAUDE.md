# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Edge Tooling is a multi-tool deployment and development toolkit for OpenShift and edge computing environments. The repository provides automation for deploying OpenShift clusters in various configurations, managing cloud infrastructure, and setting up development workspaces.

## Tool Quick Reference

| Component | Path | Purpose |
|-----------|------|---------|
| Two-Node Toolbox | `two-node-toolbox/` | OpenShift two-node cluster deployment (arbiter/fencing topologies) |
| EC2 Deploy | `ec2-deploy/` | Standalone EC2 instance setup for development |
| SNO Deploy | `sno-deploy/` | Single Node OpenShift with DU configuration |
| LVM Operator Environment | `environments/lvm-operator/` | Development workspace template for LVMS |

## Getting Started - Use Case Guide

**Choose your tool based on your goal:**

- **Need a two-node HA OpenShift cluster?** → Use Two-Node Toolbox
- **Need a standalone EC2 development host?** → Use EC2 Deploy
- **Need a single-node OpenShift with DU config?** → Use SNO Deploy
- **Developing the LVM Operator?** → Use LVM Operator Environment

**Common workflow:** Deploy an EC2 instance with `ec2-deploy/`, then use `two-node-toolbox/` to deploy a cluster on that instance.

---

## Two-Node Toolbox (two-node-toolbox/)

A comprehensive deployment automation framework for OpenShift two-node clusters in development and testing environments.

### Purpose

Deploy and manage OpenShift clusters with high availability configurations:
- **Two-Node with Arbiter (TNA)**: Master nodes + separate arbiter node for quorum
- **Two-Node with Fencing (TNF)**: Master nodes with BMC-based fencing for HA

### Deployment Methods

| Method | Use Case | Playbook |
|--------|----------|----------|
| Dev-scripts | Traditional, full control | `setup.yml` |
| Kcli | Modern, faster setup | `kcli-install.yml` |

### Key Commands

```bash
# From two-node-toolbox/deploy/ directory:

# Deploy AWS hypervisor and cluster in one command
make deploy arbiter-ipi   # Deploy arbiter topology cluster
make deploy fencing-ipi   # Deploy fencing topology cluster

# Instance lifecycle management
make create              # Create new EC2 instance
make init                # Initialize deployed instance
make start               # Start stopped EC2 instance
make stop                # Stop running EC2 instance
make destroy             # Destroy EC2 instance and resources

# Cluster operations
make redeploy-cluster    # Redeploy OpenShift cluster
make shutdown-cluster    # Shutdown cluster VMs
make startup-cluster     # Start cluster VMs and proxy
make clean               # Clean OpenShift cluster
make full-clean          # Complete cleanup including cache

# Utilities
make ssh                 # SSH into EC2 instance
make info                # Display instance information
make inventory           # Update inventory.ini with current instance IP
```

### Ansible Playbooks

#### Dev-scripts Method
```bash
# Install required collections
ansible-galaxy collection install -r collections/requirements.yml

# Interactive deployment (prompts for topology)
ansible-playbook setup.yml -i inventory.ini

# Non-interactive deployment
ansible-playbook setup.yml -e "topology=arbiter" -e "interactive_mode=false" -i inventory.ini
ansible-playbook setup.yml -e "topology=fencing" -e "interactive_mode=false" -i inventory.ini

# Redfish stonith configuration (for fencing topology)
ansible-playbook redfish.yml -i inventory.ini

# Cleanup
ansible-playbook clean.yml -i inventory.ini
```

#### Kcli Method
```bash
# Deploy fencing cluster (default topology for kcli)
ansible-playbook kcli-install.yml -i inventory.ini

# Custom cluster configuration
ansible-playbook kcli-install.yml -i inventory.ini -e "test_cluster_name=my-cluster"

# Force cleanup and redeploy
ansible-playbook kcli-install.yml -i inventory.ini -e "force_cleanup=true"
```

### Configuration Files

| File | Purpose |
|------|---------|
| `inventory.ini` | Ansible inventory (copy from `inventory.ini.sample`) |
| `roles/dev-scripts/install-dev/files/config_arbiter.sh` | Arbiter topology config |
| `roles/dev-scripts/install-dev/files/config_fencing.sh` | Fencing topology config |
| `roles/*/files/pull-secret.json` | OpenShift pull secret |
| `vars/kcli.yml` | Kcli variable overrides |
| `proxy.env` | Generated proxy config (source to access cluster) |

---

## EC2 Deploy (ec2-deploy/)

Scripts for deploying and configuring standalone EC2 instances for development purposes.

### Purpose

Quickly provision a RHEL-based EC2 development host that can be used as a hypervisor for OpenShift cluster deployments.

### Prerequisites

1. **AWS CLI configured** with `AWS_PROFILE` environment variable set
2. **Environment file**: Copy `.env.template` to `.env` and configure

Verify AWS CLI setup:
```bash
aws configure list
```

### Key Commands

```bash
# From ec2-deploy/ directory:

# Deploy an EC2 instance and initialize it
make deploy init

# After SSH connection, run the configure script:
./configure.sh
# This will:
#   - Set a password for pitadmin (cockpit access)
#   - Login to RHSM for dnf access

# Utility commands
make ssh       # SSH into the EC2 instance
make info      # Get instance info
make destroy   # Cleanup the deployment
```

---

## SNO Deploy (sno-deploy/)

Quickly stand up a Single Node OpenShift (SNO) cluster with Workload Partitioning enabled and DU (Distributed Unit) configuration.

### Purpose

Deploy SNO clusters configured for telco edge workloads with:
- Workload Partitioning
- DU-specific operators and configuration
- Real-time kernel support (optional)

### Prerequisites

Place these files in `~/.sno-deploy/` (default location):
- `openshift_pull.json` - From https://console.redhat.com/openshift/create/local
- `offline-token` - From https://cloud.redhat.com/openshift/token
- SSH key (`~/.ssh/openshift-dev` or specify with `-f`)

Check prerequisites:
```bash
make tool_check
```

### Key Commands

```bash
# From sno-deploy/ directory:

# Deploy SNO cluster with defaults (8 cores, 32GB RAM)
make CLUSTER="my-cluster-name"

# Deploy with custom settings
make CLUSTER="my-cluster-name" DEPLOY_ARGS="-c 16 -m 65536"

# Basic cluster (no RT kernel or DU config)
make all_basic CLUSTER="my-cluster-name"

# Individual tasks
make CLUSTER=$CLUSTER deploy     # Create and install cluster
make CLUSTER=$CLUSTER env_prep   # Download credentials, create env file
make CLUSTER=$CLUSTER generate   # Generate DU configs
make CLUSTER=$CLUSTER apply      # Apply DU configs to cluster
```

### Command-Line Options

| Flag | Description | Default |
|------|-------------|---------|
| `-n` | Cluster name | `sno-<user>-<date>` |
| `-c` | CPU cores | 8 |
| `-m` | Memory (MB) | 32768 |
| `-v` | OpenShift version | 4.10 |
| `-d` | Base domain | e2e.bos.redhat.com |
| `-f` | SSH public key file | `~/.ssh/openshift-dev.pub` |
| `-s` | Pull secret file | `~/.sno-deploy/openshift_pull.json` |
| `-o` | Offline token file | `~/.sno-deploy/offline-token` |
| `-b` | Basic cluster (no RT/DU) | - |
| `-k` | Add RT kernel to basic | - |

### Cluster Configuration Directory

All cluster files are stored in `~/.sno-deploy/$CLUSTER/`:
- `creds/` - kubeconfig, kubeadmin-password
- `workdir/` - Intermediate files
- `$CLUSTER.env` - Cluster environment file

---

## LVM Operator Environment (environments/lvm-operator/)

A development workspace template for LVMS (Logical Volume Manager Storage) operator development.

### Purpose

Provide a structured workspace for developing the LVM Operator across multiple related repositories.

### Workflow

1. Clone this workspace as your development root
2. Clone LVMS source repositories under `repos/`
3. Work from the top-level directory for full context across all repos
4. Navigate into `repos/<repo-name>/` for specific implementations

### Repository Structure

| Repository | Category | Purpose |
|------------|----------|---------|
| `lvm-operator` | Development | Core operator source, bundle, must-gather |
| `topolvm` | Development | Underlying CSI driver for LVM |
| `release` | Testing | Prow-based CI/CD configuration |
| `konflux-release-data` | Deployment | Konflux build/release orchestration |
| `product-definitions` | Deployment | Product Security gatekeeper |

### Key Paths in lvm-operator

- `.tekton/` - Konflux pipeline definitions
- `api/` - LVM operator API definitions
- `bundle/` - Auto-generated bundle manifests
- `cmd/` - Operator binary entrypoints
- `internal/` - Primary operator source code
- `test/` - Unit, integration, and E2E tests

### Fork Model

All repositories **except `konflux-release-data`** use a fork model:
- Push changes to your personal fork first
- Create pull requests from fork to upstream
- `konflux-release-data` uses branching: `<user_alias>/<changeset_summary>`

---

## Common Workflows

### EC2 → Two-Node Toolbox Deployment

1. Deploy EC2 instance: `cd ec2-deploy && make deploy init`
2. Configure instance: `./configure.sh`
3. Clone two-node-toolbox on instance or use Ansible from local machine
4. Deploy cluster: `cd two-node-toolbox/deploy && make deploy arbiter-ipi`

### SNO for Single-Node Testing

1. Ensure prerequisites in `~/.sno-deploy/`
2. Deploy: `make CLUSTER="test-cluster"`
3. Access: Use credentials from `~/.sno-deploy/test-cluster/creds/`

### LVM Operator Development

1. Clone workspace: `git clone <this-repo> lvm-workspace`
2. Clone repos: `cd lvm-workspace/environments/lvm-operator/repos && git clone <lvm-operator>`
3. Develop with full context from workspace root

---

## Prerequisites Summary

| Requirement | Components | Source |
|-------------|------------|--------|
| AWS CLI + AWS_PROFILE | EC2 Deploy, Two-Node Toolbox | AWS account configuration |
| OpenShift Pull Secret | All cluster deployments | https://console.redhat.com/openshift/create/local |
| Offline Token | SNO Deploy | https://cloud.redhat.com/openshift/token |
| SSH Keys | All components | Generate with `ssh-keygen` |
| CI Token | CI builds | https://console-openshift-console.apps.ci.l2s4.p1.openshiftapps.com |
| RHEL Subscription | EC2/hypervisor hosts | Red Hat Subscription Manager |

---

## Maintaining This Documentation

### Automatic New Tool Detection

This repository includes a Claude Code hook that automatically detects new tool directories at session start. When a new tool directory is added (a directory with a Makefile or README.md), Claude will:

1. Detect the undocumented tool
2. Notify the user
3. Offer to update this CLAUDE.md file

**Hook location:** `.claude/hooks/detect-new-tools.sh`

**When adding a new tool**, update the `DOCUMENTED_TOOLS` array in the hook script:

```bash
DOCUMENTED_TOOLS=(
    "two-node-toolbox"
    "ec2-deploy"
    "sno-deploy"
    "environments/lvm-operator"
    "your-new-tool"  # Add new tools here
)
```

---

## Additional Resources

For detailed component-specific guidance, see:
- `two-node-toolbox/CLAUDE.md` - Full development guidelines, coding standards, architecture details
- `environments/lvm-operator/CLAUDE.md` - LVM Operator workspace navigation, Konflux build chain
- Component README files in each directory
