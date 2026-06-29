# Standalone OPA server for Zoiko AI — serves the Rego bundle in ./opa/policies.
# Used by all Render services (zoiko-api, zoiko-governance, zoiko-execution,
# zoiko-sc002-*, zoiko-sc003-*, zoiko-sc004-*, zoiko-sc005-*) as their
# fail-closed policy decision point. Set OPA_URL to this service's Render URL
# on every backend service.
#
# Build context is the repo root so the policies dir is reachable as opa/policies.
FROM openpolicyagent/opa:latest-debug

COPY opa/policies /policies

EXPOSE 8181

# Base image ENTRYPOINT is ["/opa"] — override it so the shell form below
# (needed for $PORT substitution) runs directly instead of being appended
# as arguments to /opa.
ENTRYPOINT ["/bin/sh", "-c"]

# Render injects $PORT; default to 8181 for local / non-Render use.
CMD ["/opa run --server --addr 0.0.0.0:${PORT:-8181} --log-level info /policies"]
