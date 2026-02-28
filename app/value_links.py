"""Value linking system for bidirectional OID synchronization.

Allows linking multiple OIDs together so that when one is updated via SET,
all linked OIDs are automatically updated with the same value.

Particularly useful for augmented tables where columns should stay synchronized
(e.g., ifDescr and ifName in IF-MIB/IF-MIB-X).
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)
_MIN_LINK_ENDPOINTS = 2
_MIN_COLUMN_OID_LENGTH = 2

type JsonObject = dict[str, object]


@dataclass(slots=True)
class ValueLinkEndpoint:
    """Represents a single link endpoint (table + column)."""

    table_oid: str | None
    column_name: str
    is_base: bool = False  # Mark which endpoint is the BASE (master)

    def to_dict(self) -> JsonObject:
        """Serialize the endpoint to a JSON-compatible dictionary."""
        return {
            "table_oid": self.table_oid,
            "column": self.column_name,
            "is_base": self.is_base,
        }


@dataclass(slots=True)
class ValueLink:
    """Represents a bidirectional linkage between multiple endpoints."""

    link_id: str
    endpoints: list[ValueLinkEndpoint]
    scope: str = "per-instance"
    match: str = "shared-index"
    source: str = "schema"
    description: str = ""
    create_missing: bool = False

    def __repr__(self) -> str:
        """Return a compact debugging representation of the link."""
        return (
            f"ValueLink({self.link_id}, endpoints={len(self.endpoints)}, "
            f"scope={self.scope}, source={self.source})"
        )


class ValueLinkManager:
    """Manages bidirectional value links between OIDs."""

    def __init__(self) -> None:
        """Initialize in-memory link index and update guards."""
        self._links: list[ValueLink] = []
        # Map: column_name -> List[ValueLink] for fast lookup
        self._column_to_links: dict[str, list[ValueLink]] = {}
        # Track in-progress updates to prevent infinite loops
        self._updating: set[str] = set()

    def add_link(
        self,
        link_id: str,
        endpoints: list[ValueLinkEndpoint],
        *,
        scope: str = "per-instance",
        match: str = "shared-index",
        source: str = "schema",
        description: str | None = None,
        create_missing: bool = False,
    ) -> None:
        """Add a new value link."""
        if len(endpoints) < _MIN_LINK_ENDPOINTS:
            logger.warning("Link %s has fewer than 2 endpoints, skipping", link_id)
            return

        link = ValueLink(
            link_id,
            endpoints,
            scope=scope,
            match=match,
            source=source,
            description=description or "",
            create_missing=create_missing,
        )
        self._links.append(link)

        for endpoint in endpoints:
            col_name = endpoint.column_name
            if col_name not in self._column_to_links:
                self._column_to_links[col_name] = []
            self._column_to_links[col_name].append(link)

        logger.info("Added value link: %s", link)

    def remove_link(self, link_id: str, source: str | None = None) -> bool:
        """Remove a link by id. Returns True if removed."""
        removed = False
        remaining: list[ValueLink] = []
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
        column_names: list[str],
        table_oid: str | None,
    ) -> list[ValueLinkEndpoint]:
        """Create endpoint objects from a list of column names."""
        return [ValueLinkEndpoint(table_oid, col) for col in column_names]

    def _table_oid_from_columns(
        self,
        columns: list[str],
        objects: JsonObject,
    ) -> str | None:
        """Infer table OID from object metadata for the given columns."""
        for col_name in columns:
            if col_name in objects:
                col_data = objects[col_name]
                if not isinstance(col_data, dict):
                    continue
                col_oid = col_data.get("oid", [])
                if len(col_oid) >= _MIN_COLUMN_OID_LENGTH:
                    table_oid_parts = col_oid[:-_MIN_COLUMN_OID_LENGTH]
                    return ".".join(str(x) for x in table_oid_parts)
        return None

    def _parse_link_config(
        self,
        link_config: JsonObject,
        objects: JsonObject | None,
    ) -> tuple[str, list[ValueLinkEndpoint], str, str, str, str | None, bool]:
        """Parse one link config entry into normalized link construction fields."""
        raw_link_id = link_config.get("id")
        link_id = raw_link_id if isinstance(raw_link_id, str) else ""

        raw_scope = link_config.get("scope")
        scope = raw_scope if isinstance(raw_scope, str) else "per-instance"

        raw_match = link_config.get("match")
        match = raw_match if isinstance(raw_match, str) else "shared-index"

        raw_source = link_config.get("source")
        source = raw_source if isinstance(raw_source, str) else "schema"

        raw_description = link_config.get("description")
        description = raw_description if isinstance(raw_description, str) else None

        create_missing = bool(link_config.get("create_missing", False))

        endpoints: list[ValueLinkEndpoint] = []
        endpoints_raw = link_config.get("endpoints")
        if isinstance(endpoints_raw, list):
            for entry in endpoints_raw:
                if not isinstance(entry, dict):
                    continue
                table_oid = entry.get("table_oid")
                column_name = entry.get("column")
                is_base = entry.get("is_base", False)
                endpoints.append(
                    ValueLinkEndpoint(
                        table_oid if isinstance(table_oid, str) else None,
                        column_name if isinstance(column_name, str) else "",
                        bool(is_base),
                    )
                )
        else:
            columns_raw = link_config.get("columns")
            columns = (
                [col for col in columns_raw if isinstance(col, str)]
                if isinstance(columns_raw, list)
                else []
            )
            table_oid = None
            if scope == "per-instance" and objects:
                table_oid = self._table_oid_from_columns(columns, objects)
            endpoints = self._build_endpoints_from_columns(columns, table_oid)

        endpoints = [e for e in endpoints if e.column_name]
        return link_id, endpoints, scope, match, source, description, create_missing

    def load_links_from_schema(self, schema: JsonObject) -> None:
        """Load value links from schema JSON."""
        links_config = schema.get("links", [])
        if not isinstance(links_config, list) or not links_config:
            return

        objects = schema.get("objects", schema)
        if not isinstance(objects, dict):
            objects = {}

        for i, link_config in enumerate(links_config):
            if not isinstance(link_config, dict):
                logger.warning("Link config #%s is not a dict, skipping", i)
                continue

            link_id, endpoints, scope, match, _, description, create_missing = (
                self._parse_link_config(link_config, objects)
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

    def load_links_from_state(self, link_configs: list[JsonObject]) -> None:
        """Load persisted runtime links from state JSON records."""
        if not link_configs:
            return

        for i, link_config in enumerate(link_configs):
            link_id, endpoints, scope, match, _, description, create_missing = (
                self._parse_link_config(link_config, None)
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

    def export_links(self, *, include_schema: bool = True) -> list[JsonObject]:
        """Export links as JSON-serializable records.

        Args:
            include_schema: When False, include only state-origin links.

        """
        links: list[JsonObject] = []
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

    def export_state_links(self) -> list[JsonObject]:
        """Export only links that should be persisted in runtime state."""
        return self.export_links(include_schema=False)

    def get_linked_targets(
        self,
        column_name: str,
        table_oid: str | None = None,
    ) -> list[ValueLinkEndpoint]:
        """Get list of endpoints linked to the given source endpoint."""
        if column_name not in self._column_to_links:
            return []

        linked: list[ValueLinkEndpoint] = []
        seen: set[tuple[str | None, str]] = set()
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
        instance_key: str | None = None,
    ) -> bool:
        """Check whether a propagation update is not already in progress."""
        update_key = f"{column_name}:{instance_key}" if instance_key else column_name
        return update_key not in self._updating

    def begin_update(
        self,
        column_name: str,
        instance_key: str | None = None,
    ) -> None:
        """Mark a column/instance pair as actively being propagated."""
        update_key = f"{column_name}:{instance_key}" if instance_key else column_name
        self._updating.add(update_key)

    def end_update(
        self,
        column_name: str,
        instance_key: str | None = None,
    ) -> None:
        """Clear the in-progress marker for a propagated update."""
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
