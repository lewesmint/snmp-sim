"""
Value linking system for bidirectional OID synchronization.

Allows linking multiple OIDs together so that when one is updated via SET,
all linked OIDs are automatically updated with the same value.

Particularly useful for augmented tables where columns should stay synchronized
(e.g., ifDescr and ifName in IF-MIB/IF-MIB-X).
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class ValueLinkEndpoint:
    """Represents a single link endpoint (table + column)."""

    def __init__(self, table_oid: Optional[str], column_name: str) -> None:
        self.table_oid = table_oid
        self.column_name = column_name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_oid": self.table_oid,
            "column": self.column_name,
        }


class ValueLink:
    """Represents a bidirectional linkage between multiple endpoints."""

    def __init__(
        self,
        link_id: str,
        endpoints: List[ValueLinkEndpoint],
        scope: str = "per-instance",
        match: str = "shared-index",
        source: str = "schema",
        description: Optional[str] = None,
        create_missing: bool = False,
    ) -> None:
        self.link_id = link_id
        self.endpoints = endpoints
        self.scope = scope
        self.match = match
        self.source = source
        self.description = description or ""
        self.create_missing = create_missing

    def __repr__(self) -> str:
        return (
            f"ValueLink({self.link_id}, endpoints={len(self.endpoints)}, "
            f"scope={self.scope}, source={self.source})"
        )


class ValueLinkManager:
    """Manages bidirectional value links between OIDs."""

    def __init__(self) -> None:
        self._links: List[ValueLink] = []
        # Map: column_name -> List[ValueLink] for fast lookup
        self._column_to_links: Dict[str, List[ValueLink]] = {}
        # Track in-progress updates to prevent infinite loops
        self._updating: Set[str] = set()

    def add_link(
        self,
        link_id: str,
        endpoints: List[ValueLinkEndpoint],
        scope: str = "per-instance",
        match: str = "shared-index",
        source: str = "schema",
        description: Optional[str] = None,
        create_missing: bool = False,
    ) -> None:
        """Add a new value link."""
        if len(endpoints) < 2:
            logger.warning(f"Link {link_id} has fewer than 2 endpoints, skipping")
            return

        link = ValueLink(
            link_id,
            endpoints,
            scope=scope,
            match=match,
            source=source,
            description=description,
            create_missing=create_missing,
        )
        self._links.append(link)

        for endpoint in endpoints:
            col_name = endpoint.column_name
            if col_name not in self._column_to_links:
                self._column_to_links[col_name] = []
            self._column_to_links[col_name].append(link)

        logger.info(f"Added value link: {link}")

    def remove_link(self, link_id: str, source: Optional[str] = None) -> bool:
        """Remove a link by id. Returns True if removed."""
        removed = False
        remaining: List[ValueLink] = []
        for link in self._links:
            if link.link_id == link_id and (source is None or link.source == source):
                removed = True
                continue
            remaining.append(link)

        if not removed:
            return False

        self._links = remaining
        self._column_to_links.clear()
        for link in self._links:
            for endpoint in link.endpoints:
                col_name = endpoint.column_name
                self._column_to_links.setdefault(col_name, []).append(link)

        return True

    def _build_endpoints_from_columns(
        self,
        column_names: List[str],
        table_oid: Optional[str],
    ) -> List[ValueLinkEndpoint]:
        return [ValueLinkEndpoint(table_oid, col) for col in column_names]

    def _table_oid_from_columns(
        self,
        columns: List[str],
        objects: Dict[str, Any],
    ) -> Optional[str]:
        for col_name in columns:
            if col_name in objects:
                col_oid = objects[col_name].get("oid", [])
                if len(col_oid) >= 2:
                    table_oid_parts = col_oid[:-2]
                    return ".".join(str(x) for x in table_oid_parts)
        return None

    def _parse_link_config(
        self,
        link_config: Dict[str, Any],
        objects: Optional[Dict[str, Any]],
    ) -> Tuple[str, List[ValueLinkEndpoint], str, str, str, Optional[str], bool]:
        link_id = link_config.get("id") or ""
        scope = link_config.get("scope", "per-instance")
        match = link_config.get("match", "shared-index")
        source = link_config.get("source", "schema")
        description = link_config.get("description")
        create_missing = bool(link_config.get("create_missing", False))

        endpoints: List[ValueLinkEndpoint] = []
        if "endpoints" in link_config:
            for entry in link_config.get("endpoints", []):
                if not isinstance(entry, dict):
                    continue
                endpoints.append(
                    ValueLinkEndpoint(entry.get("table_oid"), entry.get("column", ""))
                )
        else:
            columns = link_config.get("columns", [])
            table_oid = None
            if scope == "per-instance" and objects:
                table_oid = self._table_oid_from_columns(columns, objects)
            endpoints = self._build_endpoints_from_columns(columns, table_oid)

        endpoints = [e for e in endpoints if e.column_name]
        return link_id, endpoints, scope, match, source, description, create_missing

    def load_links_from_schema(self, schema: Dict[str, Any]) -> None:
        """Load value links from schema JSON."""
        if not isinstance(schema, dict):
            return

        links_config = schema.get("links", [])
        if not links_config:
            return

        objects = schema.get("objects", schema)
        if not isinstance(objects, dict):
            objects = {}

        for i, link_config in enumerate(links_config):
            if not isinstance(link_config, dict):
                logger.warning(f"Link config #{i} is not a dict, skipping")
                continue

            link_id, endpoints, scope, match, _, description, create_missing = self._parse_link_config(
                link_config, objects
            )
            if not link_id:
                link_id = f"link_{i}"

            self.add_link(
                link_id,
                endpoints,
                scope=scope,
                match=match,
                source="schema",
                description=description,
                create_missing=create_missing,
            )

    def load_links_from_state(self, link_configs: List[Dict[str, Any]]) -> None:
        if not link_configs:
            return

        for i, link_config in enumerate(link_configs):
            if not isinstance(link_config, dict):
                logger.warning(f"State link config #{i} is not a dict, skipping")
                continue

            link_id, endpoints, scope, match, _, description, create_missing = self._parse_link_config(
                link_config, None
            )
            if not link_id:
                link_id = f"state_link_{i}"

            self.add_link(
                link_id,
                endpoints,
                scope=scope,
                match=match,
                source="state",
                description=description,
                create_missing=create_missing,
            )

    def export_links(self, include_schema: bool = True) -> List[Dict[str, Any]]:
        links: List[Dict[str, Any]] = []
        for link in self._links:
            if not include_schema and link.source != "state":
                continue
            links.append(
                {
                    "id": link.link_id,
                    "scope": link.scope,
                    "type": "bidirectional",
                    "match": link.match,
                    "description": link.description,
                    "source": link.source,
                    "create_missing": link.create_missing,
                    "endpoints": [ep.to_dict() for ep in link.endpoints],
                }
            )
        return links

    def export_state_links(self) -> List[Dict[str, Any]]:
        return self.export_links(include_schema=False)

    def get_linked_targets(
        self,
        column_name: str,
        table_oid: Optional[str] = None,
    ) -> List[ValueLinkEndpoint]:
        """Get list of endpoints linked to the given source endpoint."""
        if column_name not in self._column_to_links:
            return []

        linked: List[ValueLinkEndpoint] = []
        seen: Set[Tuple[Optional[str], str]] = set()
        for link in self._column_to_links[column_name]:
            source_matches = False
            for endpoint in link.endpoints:
                if endpoint.column_name != column_name:
                    continue
                if link.scope == "per-instance" and table_oid and endpoint.table_oid != table_oid:
                    continue
                source_matches = True
                break

            if not source_matches:
                continue

            for endpoint in link.endpoints:
                if endpoint.column_name == column_name and endpoint.table_oid == table_oid:
                    continue
                key = (endpoint.table_oid, endpoint.column_name)
                if key in seen:
                    continue
                seen.add(key)
                linked.append(endpoint)

        return linked

    def should_propagate(
        self,
        column_name: str,
        instance_key: Optional[str] = None,
    ) -> bool:
        update_key = f"{column_name}:{instance_key}" if instance_key else column_name
        return update_key not in self._updating

    def begin_update(
        self,
        column_name: str,
        instance_key: Optional[str] = None,
    ) -> None:
        update_key = f"{column_name}:{instance_key}" if instance_key else column_name
        self._updating.add(update_key)

    def end_update(
        self,
        column_name: str,
        instance_key: Optional[str] = None,
    ) -> None:
        update_key = f"{column_name}:{instance_key}" if instance_key else column_name
        self._updating.discard(update_key)

    def clear(self) -> None:
        """Clear all links and state."""
        self._links.clear()
        self._column_to_links.clear()
        self._updating.clear()


_link_manager = ValueLinkManager()


def get_link_manager() -> ValueLinkManager:
    """Get the global ValueLinkManager instance."""
    return _link_manager
