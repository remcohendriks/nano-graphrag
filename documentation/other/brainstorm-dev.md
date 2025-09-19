# Extending nano-graphrag with Custom Entity Types: A Technical Deep Dive

## Executive Summary

This document explores the architectural implications and implementation strategies for extending nano-graphrag to support domain-specific entity types, using U.S. Executive Orders as a concrete example. The analysis reveals fundamental tensions between flexibility and structure that mirror broader challenges in knowledge graph construction.

## The Current State: A Two-Strategy System

### Architectural Foundation

The nano-graphrag entity extraction system currently operates on two parallel tracks:

1. **DSPy Module (`TypedEntityRelationshipExtractor`)**: A structured approach with 62 predefined entity types, offering self-refinement through critique-and-refine loops
2. **LLM Prompt-Based (`LLMEntityExtractor`)**: A flexible approach using few-shot prompting with gleaning iterations

This duality isn't accidental—it reflects a fundamental tradeoff between precision (DSPy) and adaptability (LLM prompts).

### The Hidden Complexity

What appears simple on the surface—adding "EXECUTIVE_ORDER" to a list—reveals deeper architectural questions:

- **Type Ontology**: Are executive orders a subtype of LAW, DOCUMENT, or something entirely distinct?
- **Relationship Semantics**: Standard relationships like "mentions" fail to capture the legal weight of "supersedes" or "implements"
- **Temporal Modeling**: Orders exist in legal time (effective dates) vs. publication time vs. signing time
- **Property Extraction**: Entity types alone miss critical structured data (order numbers, CFR references, statutory authorities)

## The Executive Order Challenge: A Perfect Storm

Executive orders present unique challenges that expose limitations in generic entity extraction:

### 1. Structured Identifiers with Semantic Weight
```
EO 14028 → Not just a number, but a legal identifier with:
- Temporal ordering (14028 came after 14027)
- Presidential association (14000s = Biden administration)
- Revocation chains (may revoke EO 13800)
```

### 2. Multi-Modal Relationships
Executive orders don't just "relate to" each other—they:
- **Supersede**: Legal replacement with granular section-level changes
- **Amend**: Surgical modifications to existing orders
- **Implement**: Statutory directives requiring executive action
- **Reference**: Cross-citations creating dependency graphs

### 3. Hierarchical Theme Clustering
Orders naturally cluster around policy domains:
```
Cybersecurity Cluster:
├── EO 14028 (Improving Cybersecurity)
├── EO 13636 (Critical Infrastructure)
└── EO 13800 (Strengthening Cybersecurity) [REVOKED]
```

## Implementation Strategies: A Nuanced Analysis

### Strategy 1: Configuration-Based Extension (The Pragmatist's Choice)

**Implementation Sketch:**
```python
@dataclass
class EntityExtractionConfig:
    entity_types: List[str] = field(default_factory=lambda: [
        "PERSON", "ORGANIZATION", "LOCATION",
        "EXECUTIVE_ORDER",  # Custom addition
    ])
    entity_patterns: Dict[str, str] = field(default_factory=lambda: {
        "EXECUTIVE_ORDER": r"(?:EO|Executive Order)\s*\d{5}"
    })
```

**Why This Falls Short:**
- Treats symptoms, not the disease
- No semantic understanding of what makes an EO special
- Relationships remain generic
- Pattern matching is brittle (what about "E.O." or "Exec. Order"?)

**When It Works:**
- Quick prototypes
- Well-defined, stable domains
- When relationship types don't matter
- Small-scale deployments

### Strategy 2: Custom Extractor Implementation (The Engineer's Dream)

**Conceptual Implementation:**
```python
class ExecutiveOrderExtractor(BaseEntityExtractor):
    def __init__(self):
        self.eo_pattern = re.compile(r'(?:E\.?O\.?|Executive Order)\s*(\d{5})')
        self.supersedes_pattern = re.compile(r'supersedes?\s+(?:E\.?O\.?\s*)?(\d{5})')

    async def extract_single(self, text: str, chunk_id: str):
        # Extract orders with structured properties
        orders = {}
        for match in self.eo_pattern.finditer(text):
            eo_number = match.group(1)
            orders[f"EO_{eo_number}"] = {
                "entity_type": "EXECUTIVE_ORDER",
                "number": int(eo_number),
                "properties": self._extract_properties(text, eo_number)
            }

        # Extract specialized relationships
        relationships = self._extract_legal_relationships(text, orders)

        return ExtractionResult(nodes=orders, edges=relationships)
```

**The Hidden Costs:**
- Maintenance nightmare as patterns evolve
- Misses implicit relationships
- Domain expertise becomes technical debt
- Testing complexity explodes with edge cases

**The Hidden Benefits:**
- Zero LLM costs for known patterns
- Deterministic extraction
- Property extraction comes "for free"
- Can enforce legal constraints

### Strategy 3: Hybrid Prompt Engineering (The Realist's Balance)

**Advanced Prompt Template:**
```python
EXECUTIVE_ORDER_PROMPT = """
You are analyzing U.S. Executive Orders. In addition to standard entities, identify:

EXECUTIVE ORDERS:
- Format: "EO XXXXX" where XXXXX is a 5-digit number
- Properties to extract:
  - Number (e.g., 14028)
  - Title (full title after number)
  - Date signed
  - Signing president (if mentioned)

SPECIALIZED RELATIONSHIPS for Executive Orders:
- SUPERSEDES: When one EO legally replaces another
- AMENDS: When one EO modifies specific sections of another
- IMPLEMENTS: When an EO implements statutory requirements
- REFERENCES: When an EO cites another for context
- REVOKES: When an EO completely invalidates another

Example extraction:
Text: "Executive Order 14028 of May 12, 2021, Improving the Nation's Cybersecurity,
supersedes Executive Order 13800 and implements sections 2 and 3 of the
Cybersecurity Act of 2021."

Entities:
("entity", "EO 14028", "EXECUTIVE_ORDER", "Executive Order signed May 12, 2021,
titled 'Improving the Nation's Cybersecurity', focusing on federal cybersecurity
modernization and supply chain security")
("entity", "EO 13800", "EXECUTIVE_ORDER", "Previous executive order on cybersecurity
that was superseded by EO 14028")
("entity", "CYBERSECURITY ACT OF 2021", "LAW", "Federal statute requiring executive
action on cybersecurity measures")

Relationships:
("relationship", "EO 14028", "EO 13800", "supersedes", 1.0)
("relationship", "EO 14028", "CYBERSECURITY ACT OF 2021", "implements sections 2 and 3", 0.9)
"""
```

**Why This Is Powerful:**
- Leverages LLM's contextual understanding
- Handles variations naturally
- Discovers implicit relationships
- Adapts to new patterns without code changes

**Why This Is Dangerous:**
- Prompt engineering is an art, not a science
- Token costs scale with document size
- Non-deterministic results
- Vulnerable to prompt injection in adversarial settings

### Strategy 4: Schema-Driven Architecture (The Architect's Vision)

**Comprehensive Schema Design:**
```python
@dataclass
class EntityTypeSchema:
    name: str
    parent_type: Optional[str]  # Inheritance hierarchy

    # Recognition
    patterns: List[Pattern]
    keywords: List[str]
    context_clues: List[str]

    # Properties
    required_properties: Dict[str, PropertyDef]
    optional_properties: Dict[str, PropertyDef]

    # Relationships
    valid_outgoing_relations: List[RelationSchema]
    valid_incoming_relations: List[RelationSchema]

    # Validation
    validators: List[Callable]

    # Extraction hints
    llm_examples: List[Example]
    extraction_strategy: str  # "pattern", "llm", "hybrid"

class ExecutiveOrderSchema(EntityTypeSchema):
    def __init__(self):
        super().__init__(
            name="EXECUTIVE_ORDER",
            parent_type="LEGAL_DOCUMENT",
            patterns=[
                Pattern(r'Executive Order (\d{5})', groups={"number": 1}),
                Pattern(r'E\.O\. (\d{5})', groups={"number": 1}),
            ],
            required_properties={
                "number": PropertyDef(type=int, validator=lambda x: 10000 <= x <= 99999),
                "title": PropertyDef(type=str, extractor="after_number_until_comma"),
            },
            valid_outgoing_relations=[
                RelationSchema("supersedes", target_types=["EXECUTIVE_ORDER"]),
                RelationSchema("implements", target_types=["LAW", "STATUTE"]),
            ]
        )
```

**The Profound Implications:**
- Entities become first-class citizens with behaviors
- Validation ensures graph consistency
- Extraction strategies can be mixed per type
- Schema evolution through versioning
- Enables automated prompt generation

**The Sobering Reality:**
- Major refactoring of existing codebase
- Schema design requires deep domain expertise
- Versioning and migration complexity
- Performance overhead of validation

## The Philosophical Questions

### 1. Is an Entity Type a Classification or an Ontology?

Current system treats types as tags. Executive Orders demand types as ontological categories with:
- Inheritance (EXECUTIVE_ORDER → LEGAL_DOCUMENT → DOCUMENT)
- Properties (not just description)
- Behavioral constraints (valid relationships)
- Temporal aspects (versions, amendments)

### 2. Where Does Domain Logic Live?

Options:
- **In the Extractor**: Domain-specific code
- **In the Schema**: Declarative rules
- **In the Prompt**: Natural language instructions
- **In Post-Processing**: Validation and enrichment

Each choice has profound implications for maintainability, performance, and correctness.

### 3. How Do We Handle Relationship Semantics?

Generic relationships lose critical information:
- "mentions" vs. "supersedes" (legal weight)
- "related to" vs. "implements" (causal direction)
- "connected" vs. "amends section 3.2" (specificity)

## My Recommendation: A Phased Evolution

### Phase 1: Tactical Enhancement (Week 1)
```python
# Quick win: Configurable entity types
config = GraphRAGConfig(
    entity_extraction=EntityExtractionConfig(
        entity_types=DEFAULT_TYPES + ["EXECUTIVE_ORDER", "REGULATION", "STATUTE"],
        custom_patterns={"EXECUTIVE_ORDER": r"E\.?O\.?\s*\d{5}"}
    )
)
```

### Phase 2: Semantic Enrichment (Month 1)
- Custom prompt templates per document type
- Post-processing for relationship classification
- Property extraction via regex patterns
- Validation layer for consistency

### Phase 3: Architectural Foundation (Quarter 1)
- Introduce EntityTypeSchema base class
- Migrate existing types to schemas
- Build schema-driven prompt generation
- Implement validation framework

### Phase 4: Domain Specialization (Ongoing)
- Create domain-specific packages (legal, medical, financial)
- Schema marketplace for community sharing
- Fine-tuned models for specialized extraction
- Benchmark suites for extraction quality

## The Critical Success Factors

1. **Backwards Compatibility**: Existing code must continue working
2. **Progressive Enhancement**: Simple use cases stay simple
3. **Performance Preservation**: Schema overhead must be negligible
4. **Developer Experience**: Clear migration path and documentation
5. **Community Involvement**: Schema contributions from domain experts

## Technical Debt Considerations

### What We're Accumulating:
- Prompt template proliferation
- Pattern matching complexity
- Schema version management
- Test case explosion

### What We're Paying Down:
- Hardcoded entity types
- Inflexible relationship modeling
- Lack of validation
- Domain logic scatter

## The Competitive Landscape

Other GraphRAG implementations approach this differently:
- **Microsoft GraphRAG**: Fixed ontology with extensive prompts
- **LangChain**: Plugin architecture for custom extractors
- **LlamaIndex**: Property graphs with typed nodes
- **Neo4j**: Schema-first with OGM layers

Nano-graphrag's strength is its simplicity. The challenge is adding power without losing elegance.

## Conclusion: Beyond Executive Orders

The executive orders use case is a canary in the coal mine. If we solve it correctly, we enable:
- Medical knowledge graphs with drug-disease relationships
- Financial graphs with transaction semantics
- Software dependency graphs with version constraints
- Social networks with relationship dynamics

The key insight: **Entity types aren't just labels—they're the fundamental abstraction for encoding domain knowledge into the graph structure.**

## Call for Discussion

This analysis raises more questions than it answers:

1. Should nano-graphrag stay minimalist or embrace complexity?
2. Is schema-driven the right abstraction, or are we over-engineering?
3. How do we balance LLM flexibility with deterministic extraction?
4. What's the role of the community in defining domain schemas?

The path forward requires collective wisdom from the nano-graphrag community.

---

*Author: Claude (Anthropic)*
*Date: 2025-01-19*
*Context: Analysis requested for extending nano-graphrag with custom entity types for U.S. Executive Orders*