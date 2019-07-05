#!/bin/bash

srvroot=server/
srvpath=$srvroot/build/

export PYTHONPATH=$PWD/$srvroot:$PYTHONPATH

rebuild() {
    # Use a podman container to set up a python flask server based on our API
    # description.

    # --rm ... remove container when finished
    # --volume path/to/a/:/path/to/b ... map a to b in the container
    # openapitools/ ...  the container to run
    # generate [...] ...  the command to invoke in the container
    podman run --rm \
        --volume ${PWD}/server/:/server:Z \
        openapitools/openapi-generator-cli \
        generate -i /$srvroot/tuhiwui.yaml \
        -t $srvroot/templates \
        -g python-flask -o /$srvpath
    if [[ $? -ne 0 ]]; then
         exit $?
    fi
}

run() {
        pushd $srvpath > /dev/null
        python3 -m openapi_server
        popd > /dev/null
}

rebuild=0
run=0

while ! [[ -z "$1" ]]; do
    case $1 in
        --rebuild)
            rebuild=1
            shift
            ;;
        --run)
            run=1
            shift
            ;;
        **)
            echo "Invalid argument: $1"
            exit 1
            ;;
    esac
done

[[ $rebuild == 1 ]] && rebuild
[[ $run == 1 ]] && run
