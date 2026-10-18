#!/usr/bin/env python3
"""
Generate shared contracts from Pydantic models.

Outputs:
- shared/schemas/*.json - JSON Schema files for each model
- shared/types.ts - TypeScript type definitions
- shared/openapi.json - OpenAPI 3.1 specification

Usage:
    python scripts/gen_contracts.py

Run this after modifying backend/app/schemas.py to keep contracts in sync.
"""

import json
import re
import sys
from pathlib import Path

# Import every component through the canonical backend package
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.schemas import (
    Card,
    CardBase,
    CartItem,
    CategoryRate,
    ChosenReward,
    ClassifyMerchantRequest,
    ClassifyMerchantResult,
    DemoInjectRequest,
    EmailClassification,
    ErrorDetail,
    Event,
    EventType,
    FieldConfidence,
    HealthCheck,
    InboundEmail,
    InboundEmailAttachment,
    InboundResult,
    LookupRequest,
    LookupResult,
    Membership,
    MembershipBase,
    Merchant,
    MerchantBase,
    Reward,
    RewardBase,
    RewardCreate,
    RewardKind,
    RewardSource,
    RewardStatus,
    ScoredReward,
    StackRequest,
    StackResult,
    SyncResponse,
    Wallet,
    WalletUpdate,
    CardNetwork,
)

# Models to export
MODELS = [
    # Enums
    RewardKind,
    RewardSource,
    RewardStatus,
    CardNetwork,
    EventType,
    EmailClassification,
    # Merchant
    MerchantBase,
    Merchant,
    ClassifyMerchantRequest,
    ClassifyMerchantResult,
    # Reward
    FieldConfidence,
    RewardBase,
    Reward,
    RewardCreate,
    # Card & Membership
    CategoryRate,
    CardBase,
    Card,
    MembershipBase,
    Membership,
    # Wallet
    Wallet,
    WalletUpdate,
    # Stacking
    CartItem,
    StackRequest,
    ChosenReward,
    StackResult,
    # Lookup
    LookupRequest,
    ScoredReward,
    LookupResult,
    # Email Intake
    InboundEmailAttachment,
    InboundEmail,
    InboundResult,
    DemoInjectRequest,
    # Sync
    Event,
    SyncResponse,
    # System
    ErrorDetail,
    HealthCheck,
]

SHARED_DIR = Path(__file__).parent.parent / "shared"
SCHEMAS_DIR = SHARED_DIR / "schemas"
TYPES_FILE = SHARED_DIR / "types.ts"
OPENAPI_FILE = SHARED_DIR / "openapi.json"


def json_schema_to_typescript(schema: dict, name: str, all_schemas: dict) -> str:
    """Convert JSON Schema to TypeScript type definition."""

    def resolve_ref(ref: str) -> str:
        """Resolve a $ref to a type name."""
        if ref.startswith("#/$defs/"):
            return ref.split("/")[-1]
        return ref.split("/")[-1]

    def schema_to_ts(s: dict, indent: int = 0) -> str:
        """Convert a schema object to TypeScript."""
        ind = "  " * indent

        # Handle $ref
        if "$ref" in s:
            return resolve_ref(s["$ref"])

        # Handle anyOf (nullable types, unions)
        if "anyOf" in s:
            types = []
            for item in s["anyOf"]:
                if item.get("type") == "null":
                    types.append("null")
                else:
                    types.append(schema_to_ts(item, indent))
            return " | ".join(types)

        # Handle allOf
        if "allOf" in s:
            types = [schema_to_ts(item, indent) for item in s["allOf"]]
            return " & ".join(types)

        # Handle oneOf
        if "oneOf" in s:
            types = [schema_to_ts(item, indent) for item in s["oneOf"]]
            return " | ".join(types)

        # Handle enum
        if "enum" in s:
            return " | ".join(f'"{v}"' for v in s["enum"])

        # Handle const
        if "const" in s:
            v = s["const"]
            if isinstance(v, str):
                return f'"{v}"'
            return str(v)

        # Handle type
        t = s.get("type")

        if t == "string":
            if "format" in s:
                fmt = s["format"]
                if fmt in ("date-time", "date", "time"):
                    return "string"  # ISO date strings
                if fmt == "uuid":
                    return "string"
            return "string"

        if t == "integer" or t == "number":
            return "number"

        if t == "boolean":
            return "boolean"

        if t == "null":
            return "null"

        if t == "array":
            items = s.get("items", {})
            item_type = schema_to_ts(items, indent)
            return f"{item_type}[]"

        if t == "object":
            props = s.get("properties", {})
            required = set(s.get("required", []))
            additional = s.get("additionalProperties")

            if not props and additional:
                val_type = schema_to_ts(additional, indent) if isinstance(additional, dict) else "any"
                return f"Record<string, {val_type}>"

            if not props:
                return "Record<string, any>"

            lines = ["{"]
            for prop_name, prop_schema in props.items():
                optional = "?" if prop_name not in required else ""
                prop_type = schema_to_ts(prop_schema, indent + 1)
                desc = prop_schema.get("description", "")
                if desc:
                    lines.append(f"{ind}  /** {desc} */")
                lines.append(f"{ind}  {prop_name}{optional}: {prop_type};")
            lines.append(f"{ind}}}")
            return "\n".join(lines)

        # Default
        return "any"

    # Handle enum types specially
    if "enum" in schema:
        values = schema["enum"]
        union = " | ".join(json.dumps(v) for v in values)
        return f"export type {name} = {union};\n"

    # Regular object type
    ts_type = schema_to_ts(schema)

    # Add description as JSDoc
    desc = schema.get("description", "")
    jsdoc = f"/** {desc} */\n" if desc else ""

    return f"{jsdoc}export interface {name} {ts_type}\n"


def generate_json_schemas():
    """Generate JSON Schema files for each model."""
    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)

    all_schemas = {}

    for model in MODELS:
        name = model.__name__

        # Handle enums
        if hasattr(model, "__members__"):
            schema = {
                "title": name,
                "type": "string",
                "enum": [m.value for m in model],
            }
        else:
            schema = model.model_json_schema()

        all_schemas[name] = schema

        # Write individual schema file
        schema_path = SCHEMAS_DIR / f"{name}.json"
        with open(schema_path, "w") as f:
            json.dump(schema, f, indent=2)

    print(f"Generated {len(all_schemas)} JSON schemas in {SCHEMAS_DIR}")
    return all_schemas


def generate_typescript_types(all_schemas: dict):
    """Generate TypeScript type definitions."""

    lines = [
        "/**",
        " * Lapse Shared Types",
        " *",
        " * AUTO-GENERATED from Pydantic models. Do not edit directly.",
        " * Regenerate with: python scripts/gen_contracts.py",
        " */",
        "",
        "// =============================================================================",
        "// ENUMS",
        "// =============================================================================",
        "",
    ]

    # Generate enums first
    enum_models = [m for m in MODELS if hasattr(m, "__members__")]
    for model in enum_models:
        name = model.__name__
        values = [f'  {m.name} = "{m.value}",' for m in model]
        lines.append(f"export enum {name} {{")
        lines.extend(values)
        lines.append("}")
        lines.append("")

    lines.extend([
        "// =============================================================================",
        "// INTERFACES",
        "// =============================================================================",
        "",
    ])

    # Generate interfaces
    interface_models = [m for m in MODELS if not hasattr(m, "__members__")]
    for model in interface_models:
        name = model.__name__
        schema = all_schemas[name]
        ts_def = json_schema_to_typescript(schema, name, all_schemas)
        lines.append(ts_def)

    # Write file
    with open(TYPES_FILE, "w") as f:
        f.write("\n".join(lines))

    print(f"Generated TypeScript types at {TYPES_FILE}")


def generate_openapi_spec():
    """Generate OpenAPI specification from FastAPI app."""
    from backend.app.main import app

    openapi = app.openapi()

    with open(OPENAPI_FILE, "w") as f:
        json.dump(openapi, f, indent=2)

    print(f"Generated OpenAPI spec at {OPENAPI_FILE}")


def main():
    print("Generating Lapse contracts...")
    print()

    # Generate JSON schemas
    all_schemas = generate_json_schemas()

    # Generate TypeScript types
    generate_typescript_types(all_schemas)

    # Generate OpenAPI spec
    generate_openapi_spec()

    print()
    print("Done! Remember to commit:")
    print("  - shared/schemas/*.json")
    print("  - shared/types.ts")
    print("  - shared/openapi.json")


if __name__ == "__main__":
    main()
