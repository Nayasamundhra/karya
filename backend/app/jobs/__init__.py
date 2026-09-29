"""Standalone maintenance scripts, run on a schedule external to the API process.

Nothing here is imported by ``app.main`` - each module is invoked with
``python -m app.jobs.<name>`` from whatever the deployment platform offers
for periodic jobs. See the module docstrings for what runs and why an
in-process scheduler was deliberately not added.
"""
