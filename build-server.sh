#!/bin/bash

# Use a podman container to set up a python flask server based on our API
# description.

# --rm ... remove container when finished
# --volume path/to/a/:/path/to/b ... map a to b in the container
# openapitools/ ...  the container to run
# generate [...] ...  the command to invoke in the container
podman run --rm \
    --volume ${PWD}/server/:/server:Z \
    openapitools/openapi-generator-cli \
    generate -i /server/tuhiwui.yaml \
    -g python-flask -o /server/build/
if [[ $? -ne 0 ]]; then
     exit $?
fi

case $1 in
    --run)
        pushd server/build > /dev/null
        python3 -m openapi_server
        popd > /dev/null
        ;;
    **)
        ;;
esac
