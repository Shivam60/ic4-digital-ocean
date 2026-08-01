READINESS_TIMEOUT_SECONDS=${READINESS_TIMEOUT_SECONDS:-30}

ensure_venv() {
    local requirements=$1
    if [ ! -d .venv ]; then
        "${PYTHON:-python3}" -m venv .venv
    fi
    source .venv/bin/activate
    pip install --quiet --disable-pip-version-check -r "$requirements"
}

load_env() {
    local env_file=$1
    if [ ! -f "$env_file" ]; then
        echo "missing $env_file" >&2
        exit 1
    fi
    set -a
    source "$env_file"
    set +a
}

wait_for_url() {
    local url=$1 label=$2 waited=0
    until curl --silent --fail --output /dev/null "$url"; do
        if [ "$waited" -ge "$READINESS_TIMEOUT_SECONDS" ]; then
            echo "$label did not become ready within ${READINESS_TIMEOUT_SECONDS}s" >&2
            exit 1
        fi
        sleep 1
        waited=$((waited + 1))
    done
    echo "$label is ready"
}
