"""Domain services for the admin BFF.

Long-running orchestration logic that does not fit cleanly into a
single API route. Each service is stateless and brokers persistence
to the monolith / control plane.
"""
