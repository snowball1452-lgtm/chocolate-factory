# docs/agent-control/adapters/meshos_adapter.py

import urllib.request
import urllib.error
import json
from typing import List, Dict, Any, Optional

class MeshOSAdapter:
    """
    Adapter for the MeshOS memory graph, which runs on PostgreSQL + Hasura GraphQL at localhost:8080.
    """
    def __init__(self, endpoint: str = "http://localhost:8080/v1/graphql"):
        self.endpoint = endpoint

    def _execute(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            "query": query,
            "variables": variables or {}
        }
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(self.endpoint, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        
        try:
            with urllib.request.urlopen(req) as response:
                body = response.read().decode('utf-8')
                res_json = json.loads(body)
                if "errors" in res_json:
                    raise RuntimeError(f"GraphQL errors: {res_json['errors']}")
                return res_json.get("data", {})
        except Exception as e:
            raise RuntimeError(f"MeshOS query execution failed: {e}")

    def store_epd(self, epd: Dict[str, Any], agent_id: str) -> str:
        """
        Stores an Effective Policy Document (EPD) in MeshOS and returns its unique ID.
        """
        query = """
        mutation StoreEPD($epd: jsonb!, $agent_id: String!) {
          insert_epd_one(object: {epd: $epd, agent_id: $agent_id}) {
            id
          }
        }
        """
        variables = {
            "epd": epd,
            "agent_id": agent_id
        }
        data = self._execute(query, variables)
        record = data.get("insert_epd_one")
        if not record:
            raise RuntimeError("No record returned from store_epd mutation")
        return record["id"]

    def retrieve_epd(self, epd_id: str) -> Dict[str, Any]:
        """
        Retrieves an Effective Policy Document (EPD) from MeshOS by ID.
        """
        query = """
        query RetrieveEPD($id: uuid!) {
          epd_by_pk(id: $id) {
            id
            epd
            agent_id
          }
        }
        """
        variables = {"id": epd_id}
        data = self._execute(query, variables)
        return data.get("epd_by_pk") or {}

    def store_memory(
        self,
        content: str,
        agent_id: str,
        memory_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Stores a memory node in the MeshOS memory graph and returns its ID.
        """
        query = """
        mutation StoreMemory($content: String!, $agent_id: String!, $memory_type: String!, $metadata: jsonb) {
          insert_memory_one(object: {content: $content, agent_id: $agent_id, memory_type: $memory_type, metadata: $metadata}) {
            id
          }
        }
        """
        variables = {
            "content": content,
            "agent_id": agent_id,
            "memory_type": memory_type,
            "metadata": metadata or {}
        }
        data = self._execute(query, variables)
        record = data.get("insert_memory_one")
        if not record:
            raise RuntimeError("No record returned from store_memory mutation")
        return record["id"]

    def recall(self, query_str: str, agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Recalls memories for a given agent by executing a semantic/keyword search query.
        """
        query = """
        query RecallMemories($query: String!, $agent_id: String!, $limit: Int!) {
          memory(where: {agent_id: {_eq: $agent_id}, content: {_ilike: $query}}, limit: $limit) {
            id
            content
            memory_type
            metadata
          }
        }
        """
        variables = {
            "query": f"%{query_str}%",
            "agent_id": agent_id,
            "limit": limit
        }
        data = self._execute(query, variables)
        return data.get("memory", [])

    def link_memories(self, source_id: str, target_id: str, edge_type: str) -> str:
        """
        Creates a directed edge between two memories in the memory graph and returns the link ID.
        """
        query = """
        mutation LinkMemories($source_id: uuid!, $target_id: uuid!, $edge_type: String!) {
          insert_memory_edge_one(object: {source_id: $source_id, target_id: $target_id, edge_type: $edge_type}) {
            id
          }
        }
        """
        variables = {
            "source_id": source_id,
            "target_id": target_id,
            "edge_type": edge_type
        }
        data = self._execute(query, variables)
        record = data.get("insert_memory_edge_one")
        if not record:
            raise RuntimeError("No record returned from link_memories mutation")
        return record["id"]

    def get_agent_history(self, agent_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all memories stored for a given agent_id in reverse chronological order.
        """
        query = """
        query GetAgentHistory($agent_id: String!) {
          memory(where: {agent_id: {_eq: $agent_id}}, order_by: {created_at: desc}) {
            id
            content
            memory_type
            metadata
          }
        }
        """
        variables = {"agent_id": agent_id}
        data = self._execute(query, variables)
        return data.get("memory", [])
