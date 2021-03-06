#!/bin/bash

set -e

# go to the repo root
cd $(dirname $0)/../../../..

if [[ -t 0 ]]; then
  DOCKER_TTY_ARGS="-it"
else
  # The input device on kokoro is not a TTY, so -it does not work.
  DOCKER_TTY_ARGS=
fi

# Pin the dockcross image since newer versions of the image break the build
# We use an older version of dockcross image that has gcc4.9.4 because it was built
# before https://github.com/dockcross/dockcross/pull/449
# Thanks to that, wheel build with this image aren't actually
# compliant with manylinux2014, but only with manylinux_2_24
PINNED_DOCKCROSS_IMAGE_VERSION=dockcross/manylinux2014-aarch64:20200929-608e6ac

# running dockcross image without any arguments generates a wrapper
# scripts that can be used to run commands under the dockcross image
# easily.
# See https://github.com/dockcross/dockcross#usage for details
docker run $DOCKER_TTY_ARGS --rm $PINNED_DOCKCROSS_IMAGE_VERSION >dockcross-manylinux2014-aarch64.sh
chmod +x dockcross-manylinux2014-aarch64.sh

# the wrapper script has CRLF line endings and bash doesn't like that
# so we change CRLF line endings into LF.
sed -i 's/\r//g' dockcross-manylinux2014-aarch64.sh

# The dockcross wrapper script runs arbitrary commands under the selected dockcross
# image with the following properties which make its use very convenient:
# * the current working directory is mounted under /work so the container can easily
#   access the current workspace
# * the processes in the container run under the same UID and GID as the host process so unlike
#   vanilla "docker run" invocations, the workspace doesn't get polluted with files
#   owned by root.
./dockcross-manylinux2014-aarch64.sh --image $PINNED_DOCKCROSS_IMAGE_VERSION -- "$@"
