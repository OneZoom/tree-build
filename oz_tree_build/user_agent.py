"""Shared HTTP User-Agent for outbound requests from tree-build."""

# See https://meta.wikimedia.org/wiki/User-Agent_policy
# Should match what's in OZTree repo's static/wikimedia-cidrs.json
# Which tells wikimedia we'll mostly be hitting their API from our dev/prod server
USER_AGENT = "OneZoom-bot/1.0 (https://www.onezoom.org/; mail@onezoom.org)"
USER_AGENT_HEADERS = {"User-Agent": USER_AGENT}
