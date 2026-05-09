"""
api/ — Job board API clients for ResumeWing.

Each module in this package is a self-contained client for one job board.
All clients return List[Job] with a consistent schema.
The aggregator (aggregator.py) is the single entry point for the UI.

Board tiers:
  Tier 1 (primary)     — JSearch, Adzuna
  Tier 2 (supplemental)— The Muse, USAJobs, Remotive
"""
