"""CAMPAIGN ENGINE — DAG-based multi-step operation orchestration.

A Campaign is a directed acyclic graph of ImperiumTask nodes. ORACLE
plans the nodes, TITAN OPS executes them, WARDEN GRID monitors execution
health, and RollbackRegistry handles per-node reversal on failure.

Campaigns are persisted to var/state/campaigns.jsonl.

Public surface:
    Campaign           — campaign data model
    CampaignNode       — single DAG node (wraps ImperiumTask)
    CampaignStatus     — campaign lifecycle enum
    CampaignEngine     — execution engine
    CampaignRegistry   — persistence layer
    get_engine()       — process-level singleton
"""

from pradyos.campaign.model import Campaign, CampaignNode, CampaignStatus, NodeStatus
from pradyos.campaign.registry import CampaignRegistry
from pradyos.campaign.engine import CampaignEngine, get_engine

__all__ = [
    "Campaign",
    "CampaignNode",
    "CampaignStatus",
    "NodeStatus",
    "CampaignRegistry",
    "CampaignEngine",
    "get_engine",
]
