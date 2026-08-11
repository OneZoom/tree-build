"""Shared HTTP User-Agent for outbound requests from tree-build."""

# See https://meta.wikimedia.org/wiki/User-Agent_policy
USER_AGENT = "OneZoom-tree-build/1.0 (https://www.onezoom.org/; mail@onezoom.org)"
USER_AGENT_HEADERS = {"User-Agent": USER_AGENT}
