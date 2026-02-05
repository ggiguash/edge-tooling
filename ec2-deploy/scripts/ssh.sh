#!/bin/bash
source ./.env

instance_ip=$(cat ${SHARED_DIR}/ssh_user)@$(cat ${SHARED_DIR}/public_address)

ssh $instance_ip