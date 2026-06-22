# Standalone OPA server for Zoiko AI — serves the policy bundle in ./policies.
# Used by zoiko-api, zoiko-governance, and zoiko-execution as their fail-closed
# policy decision point (set OPA_URL to this service's URL on all three).
FROM openpolicyagent/opa:latest-debug

COPY policies /policies

EXPOSE 8181

# Base image's ENTRYPOINT is ["/opa"] — override it so the shell form below
# (needed for $PORT substitution) actually runs instead of being appended
# as arguments to /opa.
ENTRYPOINT ["/bin/sh", "-c"]

# Render injects $PORT; default to OPA's standard 8181 for local/non-Render use.
CMD ["/opa run --server --addr 0.0.0.0:${PORT:-8181} --log-level info /policies"]
