#!/bin/bash

# Bootstrap script

######
# region | Helper Functions
######

fetch_kubectl() {
    if which kubectl &> /dev/null ; then
        echo  " |_ ✅ kubectl already installed"
        return
    fi

    echo "Downloading kubectl"
    curl -sLO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
    if [ $? -eq 0 ]; then
        echo " |_ ✅ Successfully downloaded kubectl"
    else
        echo " |_ ❌ Failed to download kubectl"
        return
    fi
    curl -sLO "https://dl.k8s.io/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl.sha256"
    if [ $? -eq 0 ]; then
        echo " |_ ✅ Successfully downloaded kubectl-sha"
    else
        echo " |_ ❌ Failed to download kubectl-sha, not installing kubectl"
        return
    fi

    echo "Validating kubectl download"
    echo "$(<kubectl.sha256) kubectl" | sha256sum --check
    if [ $? -eq 0 ]; then
        echo " |_ ✅ Successfully validated kubectl download"
    else
        echo " |_ ❌ Failed to validate kubectl download, not installing"
        return
    fi

    echo "Installing kubectl"
    sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
    if [ $? -eq 0 ]; then
        echo " |_ ✅ Successfully installed kubectl"
    else
        echo " |_ ❌ Failed to install kubectl"
    fi
}

fetch_cockpit() {
    if rpm -q cockpit &> /dev/null ; then
        echo  " |_ ✅ cockpit already installed"
        return
    fi

    echo "Installing cockpit"
    sudo dnf install -y cockpit
    if [ $? -eq 0 ]; then
        echo " |_ ✅ Successfully installed cockpit"
    else
        echo " |_ ❌ Failed to install cockpit"
    fi
    sudo systemctl enable --now cockpit.socket
    if [ $? -eq 0 ]; then
        echo " |_ ✅ Successfully enabled and started cockpit"
    else
        echo " |_ ❌ Failed to enable and start cockpit"
    fi

    echo "######################################################################################"
    echo "NOTE! Logging into 'cockpit' Web UI requires an administrator user with password login"
    echo "The current user can be configured for the Web UI login using the following commands:"
    echo "  sudo usermod -a -G adm $(whoami)"
    echo "  sudo passwd $(whoami)"
    echo "######################################################################################"
}

install_rpm_deps() {
    echo "Installing RPM dependencies"
    sudo dnf install -y $RPM_PACKAGES
    if [ $? -eq 0 ]; then
        echo " |_ ✅ Successfully installed packages"
    else
        echo " |_ ❌ Failed to install some or all the packages"
        return
    fi

    if [ $(sudo systemctl is-enabled libvirtd) != "enabled" ] ; then
        echo "Enabling libvirtd"
        sudo systemctl enable libvirtd
    fi
    if [ $(sudo systemctl is-active libvirtd) != "active" ] ; then
        echo "Starting libvirtd"
        sudo systemctl start --no-block libvirtd
    fi
}

install_go() {
    if which go &> /dev/null ; then
        echo  " |_ ✅ golang already installed"
        return
    fi

    curl -sLO "https://golang.org/dl/go$GO_VERSION.linux-amd64.tar.gz"
    rm -rf "$INSTALL_DIR/go" && tar -C "$INSTALL_DIR" -xzf "go$GO_VERSION.linux-amd64.tar.gz"
    if [ $? -eq 0 ]; then
        rm "go$GO_VERSION.linux-amd64.tar.gz"
        echo " |_ ✅ Successfully installed golang"
    else
        echo " |_ ❌ Failed to install golang"
    fi
}

install_yq() {
    if which yq &> /dev/null ; then
        echo  " |_ ✅ yq already installed"
        return
    fi

    curl -sLo "$INSTALL_DIR/bin/yq" "https://github.com/mikefarah/yq/releases/download/$YQ_VERSION/$YQ_BINARY"
    if [ $? -eq 0 ]; then
        chmod +x $INSTALL_DIR/bin/yq
        echo " |_ ✅ Successfully installed yq"
    else
        echo " |_ ❌ Failed to install yq"
    fi
}

######
# endregion | Helper Functions
######

######
# region | Main script
######

GO_VERSION=1.17.2
YQ_VERSION=v4.12.2
YQ_BINARY=yq_linux_amd64
RPM_PACKAGES="git podman podman-docker vim libosinfo-1.9.0-1.el8.x86_64 libvirt virt-install qemu-kvm jq"

INSTALL_DIR=$HOME/.local
if [ "$EUID" -eq 0 ]; then
    INSTALL_DIR=/usr/local
fi
[ ! -e $INSTALL_DIR/bin ] && mkdir -p $INSTALL_DIR/bin

INSTALL_COCKPIT="no"
INSTALL_KUBECTL="no"

while getopts "ck" f; do
    case "${f}" in
    c)
        INSTALL_COCKPIT="yes"
        ;;
    k)
        INSTALL_KUBECTL="yes"
        ;;
    esac
done

install_rpm_deps
install_go
install_yq

[ $INSTALL_COCKPIT = "yes" ] && fetch_cockpit
[ $INSTALL_KUBECTL = "yes" ] && fetch_kubectl

exit 0

######
# endregion | Main script
######
