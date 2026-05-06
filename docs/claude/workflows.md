# Common Workflows

## EC2 → Two-Node Toolbox Deployment

1. Deploy EC2 instance: `cd ec2-deploy && make deploy init`
2. Configure instance: `./configure.sh`
3. Clone two-node-toolbox on instance or use Ansible from local machine
4. Deploy cluster: `cd two-node-toolbox/deploy && make deploy arbiter-ipi`

## SNO for Single-Node Testing

1. Ensure prerequisites in `~/.sno-deploy/`
2. Deploy: `make CLUSTER="test-cluster"`
3. Access: Use credentials from `~/.sno-deploy/test-cluster/creds/`

## LVM Operator Development

1. Clone workspace: `git clone <this-repo> lvm-workspace`
2. Clone repos: `cd lvm-workspace/environments/lvm-operator/repos && git clone <lvm-operator>`
3. Develop with full context from workspace root
