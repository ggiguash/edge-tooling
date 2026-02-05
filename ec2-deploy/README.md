# EC2 Deploy Scripts
These make targets will help you setup and configure an EC2 instance for development purposes.

## Environment
### AWS CLI
You will need to have the AWS CLI Configured and the `AWS_PROFILE` environment variable configured.
You can check if you have the AWS CLI configured by running the following:

```bash
$ aws configure list
      Name                    Value             Type    Location
      ----                    -----             ----    --------
   profile            openshift-dev              env    ['AWS_PROFILE', 'AWS_DEFAULT_PROFILE']
access_key     ****************4SU3 shared-credentials-file    
secret_key     ****************z0DF shared-credentials-file    
    region                us-east-2      config-file    ~/.aws/config
```

If you need an AWS account: https://devservices.dpp.openshift.com/support/aws_new_resource_account/ (VPN Required)
For getting adn configuring the CLI: https://docs.aws.amazon.com/cli/

### .env
The `.env.template` file has all of the required variables for the EC2 deployment, initialization, and connection. Copy the `.env.template` file to `.env` and set all the variables to the valid values for your user.


## Deployment

```bash
# Deploy an EC2 instance and initialize it
$ make deploy init

# This will leave you in a command prompt for the EC2 instance. You should run the configure script here.
# You will need to:
#   - Set a password for pitadmin (cockpit access)
#   - Login to RHSM for dnf access
[ec2-user@ip-x-x-x-x ~]$ ./configure.sh
```

### Utility commands
```bash
# SSH into the EC2 instance
$ make ssh

# Get instance info
$ make info

# Cleanup the deployment
$ make destroy
```