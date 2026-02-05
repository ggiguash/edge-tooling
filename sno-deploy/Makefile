.SILENT:

PATH:=$(PATH):$(HOME)/.local/bin:$(HOME)/.local/go/bin
SHELL:=env PATH=$(PATH) /bin/bash

CLUSTER?=
CLUSTER_HOME=$(HOME)/.sno-deploy/$(CLUSTER)
CORES?=8
MEMORY?=32768
OCP_VERSION?=4.11
DEPLOY_ARGS?=
PUBLIC_KEY=$(HOME)/.ssh/openshift-dev.pub
PULL_SECRET=$(HOME)/.sno-deploy/openshift_pull.json
OFFLINE_TOKEN=$(HOME)/.sno-deploy/offline-token
KUBECONFIG=$(CLUSTER_HOME)/creds/kubeconfig-local
KUBECTL_FLAGS=--tls-server-name=openshift.default

all: tool_check deploy env_prep clean generate apply_operators apply_du_configs verify
all_basic: tool_check deploy_basic env_prep clean

# Make sure not to delete the top-level directory when CLUSTER variable is empty
ifneq ($(CLUSTER),)
clean:
	rm -rf $(CLUSTER_HOME)/workdir/generated/
purge:	
	rm -rf $(CLUSTER_HOME)/*
else
clean:
	echo CLUSTER must be specified
purge:
	echo CLUSTER must be specified
endif

help:
	./sno-deploy.sh -h

tool_check:
	./hack/bootstrap.sh -k -c

deploy_basic: override DEPLOY_ARGS+=-b
deploy_basic: deploy

deploy:
	./sno-deploy.sh \
	-n $(CLUSTER) \
	-c $(CORES) \
	-m $(MEMORY) \
	-f $(PUBLIC_KEY) \
	-o $(OFFLINE_TOKEN) \
	-s $(PULL_SECRET) \
	-v $(OCP_VERSION) \
	$(DEPLOY_ARGS)

rebuild_policy_bin: export FETCH_ARG=-r
rebuild_policy_bin: fetch_cnf_repo

fetch_cnf_repo:
	./hack/fetch_cnf_repo.sh -n $(CLUSTER) $(FETCH_ARG)

generate: fetch_cnf_repo
	./hack/generate.sh $(CLUSTER)

env_prep:
	./hack/env_prep.sh $(CLUSTER) $(OFFLINE_TOKEN)

apply_operators:
	KUBECTL_FLAGS=$(KUBECTL_FLAGS) KUBECONFIG=$(KUBECONFIG) ./hack/apply.sh -n $(CLUSTER) -ol

apply_du_configs:
	KUBECTL_FLAGS=$(KUBECTL_FLAGS) KUBECONFIG=$(KUBECONFIG) ./hack/apply.sh -n $(CLUSTER) -cl

apply: apply_operators apply_du_configs

verify:
	KUBECTL_FLAGS=$(KUBECTL_FLAGS) KUBECONFIG=$(KUBECONFIG) ./hack/verify.sh -n $(CLUSTER) -al
