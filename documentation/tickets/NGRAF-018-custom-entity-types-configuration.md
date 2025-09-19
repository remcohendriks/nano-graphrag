# NGRAF-018: Enable Custom Entity Types and Typed Relationships

## Summary
Add configuration support for custom entity types and implement typed relationships for domain-specific knowledge graphs.

## Description
Currently entity types are hardcoded and all relationships are generic. This ticket enables domain-specific entity extraction for any strongly-related document corpus (legal, medical, financial, technical specifications, etc).

## Feature Branch
`feature/ngraf-018-custom-entity-types`

## Implementation

### 1. Add Entity Types to Config

#### File: `nano_graphrag/config.py`
```python
@dataclass(frozen=True)
class EntityExtractionConfig:
    # ... existing fields ...
    entity_types: List[str] = field(default_factory=lambda: [
        "PERSON", "ORGANIZATION", "LOCATION", "EVENT", "DATE",
        "TIME", "MONEY", "PERCENTAGE", "PRODUCT", "CONCEPT"
    ])

    @classmethod
    def from_env(cls) -> 'EntityExtractionConfig':
        # ... existing code ...
        entity_types_str = os.getenv("ENTITY_TYPES", "")
        entity_types = entity_types_str.split(",") if entity_types_str else None

        return cls(
            # ... existing fields ...
            entity_types=entity_types or cls.__dataclass_fields__["entity_types"].default_factory()
        )
```

### 2. Use Config in Extractor Factory

#### File: `nano_graphrag/entity_extraction/factory.py`
```python
def create_extractor(config: GraphRAGConfig, llm_func=None) -> BaseEntityExtractor:
    entity_config = config.entity_extraction

    extractor_config = ExtractorConfig(
        entity_types=entity_config.entity_types,  # Use configured types
        # ... rest of existing fields ...
    )
    # ... rest of function ...
```

### 3. Fix GraphRAG Initialization

#### File: `nano_graphrag/graphrag.py`
Remove the hardcoded `DEFAULT_ENTITY_TYPES` and let config flow through.

### 4. Add Typed Relationships to Neo4j

#### File: `nano_graphrag/_storage/gdb_neo4j.py`
```python
async def upsert_edges_batch(
    self, edges_data: list[tuple[str, str, dict[str, str]]]
):
    if not edges_data:
        return

    edges_params = []
    for source_id, target_id, edge_data in edges_data:
        edge_data_copy = edge_data.copy()

        relation_type = edge_data_copy.get("relation_type", "RELATED")
        relation_type = self._sanitize_label(relation_type)

        if "weight" in edge_data_copy:
            try:
                edge_data_copy["weight"] = float(edge_data_copy["weight"])
            except (ValueError, TypeError):
                edge_data_copy["weight"] = 0.0
        else:
            edge_data_copy.setdefault("weight", 0.0)

        edges_params.append({
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": relation_type,
            "edge_data": edge_data_copy
        })

    async with self.async_driver.session(database=self.neo4j_database) as session:
        await session.run(
            f"""
            UNWIND $edges AS edge
            MATCH (s:`{self.namespace}`)
            WHERE s.id = edge.source_id
            MATCH (t:`{self.namespace}`)
            WHERE t.id = edge.target_id
            MERGE (s)-[r:RELATED]->(t)
            SET r += edge.edge_data
            SET r.relation_type = edge.relation_type
            """,
            edges=edges_params
        )
```

### 5. Configurable Relation Mapping

#### File: `nano_graphrag/_extraction.py`
```python
import os
import json

def get_relation_patterns():
    """Load relation patterns from environment or use defaults."""
    patterns_json = os.getenv("RELATION_PATTERNS", "")
    if patterns_json:
        try:
            return json.loads(patterns_json)
        except json.JSONDecodeError:
            pass

    # Generic domain-agnostic patterns
    return {
        "supersedes": "SUPERSEDES",
        "superseded by": "SUPERSEDED_BY",
        "amends": "AMENDS",
        "implements": "IMPLEMENTS",
        "revokes": "REVOKES",
        "depends on": "DEPENDS_ON",
        "references": "REFERENCES",
        "derived from": "DERIVED_FROM",
        "conflicts with": "CONFLICTS_WITH",
        "replaces": "REPLACES",
        "extends": "EXTENDS",
        "inherits from": "INHERITS_FROM",
        "uses": "USES",
        "requires": "REQUIRES",
        "contradicts": "CONTRADICTS"
    }

def map_relation_type(description: str, patterns: dict = None) -> str:
    if patterns is None:
        patterns = get_relation_patterns()

    desc_lower = description.lower()
    for pattern, rel_type in patterns.items():
        if pattern in desc_lower:
            return rel_type
    return "RELATED"

# In extract_entities function, after extracting edges:
relation_patterns = get_relation_patterns()
for edge_key, edge_list in maybe_edges.items():
    for edge_data in edge_list:
        description = edge_data.get("description", "")
        edge_data["relation_type"] = map_relation_type(description, relation_patterns)
```

## Configuration Examples

### Legal Domain
```bash
export ENTITY_TYPES="PERSON,ORGANIZATION,DATE,STATUTE,REGULATION,CASE,COURT"
export RELATION_PATTERNS='{"cites": "CITES", "overrules": "OVERRULES", "affirms": "AFFIRMS"}'
```

### Medical Domain
```bash
export ENTITY_TYPES="DRUG,DISEASE,SYMPTOM,PROTEIN,GENE,PATHWAY,CLINICAL_TRIAL"
export RELATION_PATTERNS='{"treats": "TREATS", "causes": "CAUSES", "inhibits": "INHIBITS"}'
```

### Software Engineering
```bash
export ENTITY_TYPES="CLASS,METHOD,PACKAGE,MODULE,LIBRARY,API,SERVICE"
export RELATION_PATTERNS='{"imports": "IMPORTS", "calls": "CALLS", "implements": "IMPLEMENTS"}'
```

### Financial Domain
```bash
export ENTITY_TYPES="COMPANY,EXECUTIVE,INVESTOR,PRODUCT,MARKET,CURRENCY,TRANSACTION"
export RELATION_PATTERNS='{"acquires": "ACQUIRES", "invests in": "INVESTS_IN", "competes with": "COMPETES_WITH"}'
```

## Testing

### File: `tests/test_custom_entity_config.py`
```python
import pytest
from nano_graphrag.config import EntityExtractionConfig

def test_entity_types_from_env(monkeypatch):
    monkeypatch.setenv("ENTITY_TYPES", "DRUG,DISEASE,PROTEIN")
    config = EntityExtractionConfig.from_env()
    assert config.entity_types == ["DRUG", "DISEASE", "PROTEIN"]

def test_entity_types_default():
    config = EntityExtractionConfig()
    assert "PERSON" in config.entity_types
    assert len(config.entity_types) == 10
```

### File: `tests/test_relation_types.py`
```python
import pytest
from nano_graphrag._extraction import map_relation_type, get_relation_patterns

def test_relation_mapping_defaults():
    assert map_relation_type("This supersedes the previous version") == "SUPERSEDES"
    assert map_relation_type("It depends on module X") == "DEPENDS_ON"
    assert map_relation_type("unrelated text") == "RELATED"

def test_custom_relation_patterns(monkeypatch):
    monkeypatch.setenv("RELATION_PATTERNS", '{"inhibits": "INHIBITS", "activates": "ACTIVATES"}')
    patterns = get_relation_patterns()

    assert map_relation_type("Drug X inhibits protein Y", patterns) == "INHIBITS"
    assert map_relation_type("Gene A activates pathway B", patterns) == "ACTIVATES"
```

## Definition of Done

- [ ] Entity types configurable via ENTITY_TYPES environment variable
- [ ] Relation patterns configurable via RELATION_PATTERNS environment variable
- [ ] Works for any domain without code changes
- [ ] Neo4j stores relation_type as edge property
- [ ] Tests pass

## Pull Request Should Contain

- Config changes for entity types
- Factory and GraphRAG initialization fixes
- Neo4j typed relationship support
- Configurable relation type mapping
- Test coverage for multiple domains