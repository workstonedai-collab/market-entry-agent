"""Small explicit tool contracts shared by JSON-action and future adapters."""
import copy


def field(kind, **kwargs):
    return {"type": kind, **kwargs}


TEXT = field("string", minLength=1, maxLength=128)
SCHEMAS = {
    "project_state": ({"kind":TEXT,"id":TEXT}, []),
    "country_baseline": ({"countries": field("array", maxItems=5, items=TEXT)}, []),
    "research_plan": ({}, []),
    "web_search": ({"query_index": field("integer", minimum=0, maximum=5)}, ["query_index"]),
    "fetch_page": ({"evidence_id": TEXT, "source_id": TEXT}, []),
    "search_evidence": ({"query": field("string", maxLength=2000)}, []),
    "read_evidence": ({"id": TEXT, "offset": field("integer", minimum=0, maximum=30000),
                       "limit": field("integer", minimum=1, maximum=6000)}, ["id"]),
    "recall": ({}, []),
    "list_sources": ({}, []),
    "fetch_feed": ({"id": TEXT}, ["id"]),
    "finish": ({"report": field("object")}, ["report"]),
    "load_skill": ({"name": TEXT}, ["name"]),
    "read_result": ({"step": field("integer", minimum=0, maximum=29),
                     "offset": field("integer", minimum=0, maximum=200000),
                     "limit": field("integer", minimum=1, maximum=6000)}, ["step"]),
}


def check(schema, value, label="arguments"):
    kind = schema.get("type")
    types = {"string": str, "object": dict, "array": list, "integer": int}
    if kind and (not isinstance(value, types[kind]) or (kind == "integer" and isinstance(value, bool))):
        raise ValueError(label + " must be " + kind)
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 1000000):
            raise ValueError(label + " exceeds its text bounds")
    if kind == "integer" and not schema.get("minimum", -1e20) <= value <= schema.get("maximum", 1e20):
        raise ValueError(label + " exceeds its numeric bounds")
    if kind == "array":
        if len(value) > schema.get("maxItems", 1000):
            raise ValueError(label + " has too many items")
        for index, item in enumerate(value):
            check(schema.get("items", {}), item, label + "[" + str(index) + "]")
    if kind == "object":
        properties = schema.get("properties", {})
        if any(key not in value for key in schema.get("required", [])):
            raise ValueError(label + " is missing a required field")
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ValueError(label + " contains an unsupported field")
        for key, item in value.items():
            if key in properties:
                check(properties[key], item, label + "." + key)


OUTPUTS = {
    "project_state": {"project":field("object"),"guide":field("object")},
    "country_baseline": {"evidence_ids": field("array", items=TEXT), "comparison": field("object")},
    "research_plan": {"schema": TEXT, "lenses": field("array")},
    "web_search": {"query": field("string"), "results": field("array")},
    "fetch_page": {"id": TEXT},
    "search_evidence": {"results": field("array")},
    "read_evidence": {"id": TEXT, "body": field("string"), "countries": field("array"), "topics": field("array")},
    "recall": {"previous": field("array"), "facts": field("array")},
    "list_sources": {"sources": field("array")},
    "fetch_feed": {"added": field("integer", minimum=0)},
    "finish": {"report": field("object")},
    "load_skill": {"name": TEXT, "version": TEXT},
    "read_result": {"step": field("integer"), "text": field("string"), "offset": field("integer")},
}


class ToolRegistry:
    def __init__(self, tools):
        self.tools = {}
        for tool in tools:
            item = copy.deepcopy(tool)
            properties, required = SCHEMAS[item["name"]]
            item["input_schema"] = field("object", properties=properties, required=required, additionalProperties=False)
            output = OUTPUTS[item["name"]]
            item["output_schema"] = field("object", properties=output, required=list(output))
            item["policy"] = {"read_only": item["name"] != "finish",
                              "external_writes": False,
                              "workspace_writes": item["name"] in ("country_baseline", "web_search", "fetch_page", "fetch_feed", "load_skill", "finish"),
                              "network": item["name"] in ("web_search", "fetch_page", "fetch_feed"),
                              "timeout_seconds": {"web_search": 40, "fetch_page": 25, "fetch_feed": 12}.get(item["name"]),
                              "reuse": item["name"] in ("project_state", "read_evidence", "research_plan", "load_skill", "country_baseline", "search_evidence", "list_sources", "recall")}
            self.tools[item["name"]] = item

    def validate(self, name, arguments):
        if name not in self.tools:
            raise ValueError("Unknown tool; select a documented action")
        check(self.tools[name]["input_schema"], arguments)
        if name == "project_state" and arguments.get("id") and not arguments.get("kind"):
            raise ValueError("Record lookup requires kind with id")
        if name == "fetch_page" and bool(arguments.get("evidence_id")) == bool(arguments.get("source_id")):
            raise ValueError("Choose exactly one of evidence_id or source_id")
        return self.tools[name]

    def result(self, name, value):
        check(self.tools[name]["output_schema"], value, "tool_result")
        return value

    def describe(self):
        return list(self.tools.values())
