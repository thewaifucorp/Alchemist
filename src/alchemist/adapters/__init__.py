from .n8n import N8nAdapter
from .langflow import LangFlowAdapter

ADAPTERS = {"n8n": N8nAdapter(), "langflow": LangFlowAdapter()}
