FROM fedora:28

# This is an argument for a URL to an internal CA file to trust
ARG ca_file
# This is an argument for a URL to a DNF repo file of a repo that contains brewkoji
ARG rcm_tools_repo_file
ADD $ca_file /usr/share/pki/ca-trust-source/anchors/custom-ca.crt
ADD $rcm_tools_repo_file /etc/yum.repos.d/rcm-tools-fedora.repo
RUN update-ca-trust

RUN dnf -y install \
  --setopt=deltarpm=0 \
  --setopt=install_weak_deps=false \
  --setopt=tsflags=nodocs \
  # Install brewkoji for the koji.conf.d config file
  brewkoji \
  # Install rhpkg for go analyzer
  rhpkg \
  python3-dockerfile-parse \
  git-core \
  cpio \
  python3-koji \
  'python3-neomodel >= 3.3.0' \
  golang \
  && dnf clean all \
  # workaround for unpacking broken rpms in unprivileged container
  && setcap CAP_DAC_OVERRIDE+ep /usr/bin/cpio

# Tools needed for Go analysis
RUN go get rsc.io/goversion && \
    go get github.com/release-engineering/retrodep && \
    mv ~/go/bin/goversion ~/go/bin/retrodep /usr/bin/

RUN mkdir /src
WORKDIR /src
COPY . .

# Use develop so that we can pass the `--no-deps` argument, since the deps are installed via RPM.
# Normally we'd use `pip3 install . --no-deps`, but that doesn't fully install the submodules.
RUN python3 setup.py develop --no-deps --prefix /usr

# Add the utility scripts folder as an executable path
ENV PATH "/src/scripts:${PATH}"

USER 1001
# TODO: Change this once we have a startup script
CMD ["/bin/bash"]
