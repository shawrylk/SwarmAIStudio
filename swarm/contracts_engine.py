"""
Universal Contract & Docusaurus Engine for Swarm AI Studio
Provides universal, language-agnostic contract specification parsing,
statechart Mermaid visualization, CEL invariant verification, and Docusaurus docs export:
1. OpenAPI 3.x / Swagger 2.0 (REST/HTTP Endpoints, Schemas, Parameters)
2. AsyncAPI 3.x / 2.x (Channel Topics, Event Messages, WebSocket/UDP Payloads)
3. FlatBuffers (.fbs) & Protobuf (.proto) (Tables, Structs, Enums, Unions, RPCs)
4. SCXML / Statecharts (W3C State Machines -> Docusaurus Mermaid Diagrams)
5. CEL (Common Expression Language) Invariants (Declarative Pre/Post-Condition Rules)
6. Docusaurus Documentation Generator (Structured docs/contracts/... hierarchy)
"""

import os
import re
import ast
import json
import yaml
import time
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Tuple
from swarm.logger import log_event


# ─────────────────────────────────────────────────────────────────────────────
# 1. OPENAPI 3.x & SWAGGER 2.0 PARSER
# ─────────────────────────────────────────────────────────────────────────────

def _looks_like_openapi(content: str) -> bool:
    """Cheap structural pre-check before full parsing.

    Requires an explicit `openapi:`/`swagger:` marker, or a top-level `paths`
    mapping whose keys look like URL routes. This rejects unrelated JSON that
    merely contains a "paths" field (tsconfig.json, launchSettings.json, etc.).
    """
    try:
        data = json.loads(content)
    except Exception:
        try:
            data = yaml.safe_load(content)
        except Exception:
            return False
    if not isinstance(data, dict):
        return False
    if data.get("openapi") or data.get("swagger"):
        return True
    paths = data.get("paths")
    if isinstance(paths, dict) and paths:
        return any(str(k).startswith("/") for k in paths.keys())
    return False


def parse_openapi(content: Union[str, Dict[str, Any]], filepath: str = "") -> Dict[str, Any]:
    """
    Parses OpenAPI 3.x or Swagger 2.0 specification from YAML/JSON content.
    Extracts info, servers, REST endpoints, parameters, request bodies, responses, and schemas.
    """
    data = {}
    if isinstance(content, dict):
        data = content
    else:
        try:
            data = json.loads(content)
        except Exception:
            try:
                data = yaml.safe_load(content)
            except Exception as e:
                log_event("warn", "contracts", f"Failed to parse OpenAPI YAML/JSON in {filepath}: {e}")
                return {"type": "openapi", "valid": False, "error": str(e), "filepath": filepath}

    _paths = data.get("paths") if isinstance(data, dict) else None
    _has_routes = isinstance(_paths, dict) and any(str(k).startswith("/") for k in _paths.keys())
    if not isinstance(data, dict) or (not data.get("openapi") and not data.get("swagger") and not _has_routes):
        return {"type": "openapi", "valid": False, "error": "Not a valid OpenAPI or Swagger definition", "filepath": filepath}

    openapi_ver = data.get("openapi") or data.get("swagger") or "3.0.0"
    info = data.get("info", {})
    title = info.get("title", Path(filepath).stem if filepath else "OpenAPI Specification")
    version = info.get("version", "1.0.0")
    description = info.get("description", "")

    # Servers / Base URLs
    servers = []
    if "servers" in data:
        for s in data["servers"]:
            if isinstance(s, dict):
                servers.append({"url": s.get("url", ""), "description": s.get("description", "")})
            elif isinstance(s, str):
                servers.append({"url": s, "description": ""})
    elif "host" in data:
        base_path = data.get("basePath", "")
        schemes = data.get("schemes", ["https"])
        servers.append({"url": f"{schemes[0]}://{data['host']}{base_path}", "description": "Swagger 2.0 Host"})

    # Endpoints & Operations
    endpoints = []
    paths = data.get("paths", {})
    for path_key, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        
        path_params = path_item.get("parameters", [])
        for method in ["get", "post", "put", "delete", "patch", "options", "head"]:
            if method not in path_item:
                continue
            
            op = path_item[method]
            if not isinstance(op, dict):
                continue
            
            op_id = op.get("operationId", f"{method}_{path_key}")
            summary = op.get("summary", "")
            op_desc = op.get("description", "")
            tags = op.get("tags", ["default"])
            
            # Combine path-level and operation-level parameters
            raw_params = list(path_params) + list(op.get("parameters", []))
            params = []
            for p in raw_params:
                if isinstance(p, dict):
                    p_schema = p.get("schema", {})
                    p_type = p_schema.get("type", p.get("type", "string"))
                    params.append({
                        "name": p.get("name", ""),
                        "in": p.get("in", "query"),
                        "required": p.get("required", False),
                        "type": p_type,
                        "description": p.get("description", "")
                    })

            # Request Body (OpenAPI 3 vs Swagger 2)
            request_body = {}
            if "requestBody" in op:
                rb = op["requestBody"]
                rb_content = rb.get("content", {})
                content_types = list(rb_content.keys())
                primary_ct = content_types[0] if content_types else "application/json"
                schema_ref = rb_content.get(primary_ct, {}).get("schema", {})
                request_body = {
                    "required": rb.get("required", False),
                    "content_type": primary_ct,
                    "schema": schema_ref
                }
            elif method in ["post", "put", "patch"]:
                # Check for body parameters in Swagger 2
                for p in raw_params:
                    if isinstance(p, dict) and p.get("in") == "body":
                        request_body = {
                            "required": p.get("required", False),
                            "content_type": "application/json",
                            "schema": p.get("schema", {})
                        }
                        break

            # Responses
            responses = {}
            for status_code, resp_obj in op.get("responses", {}).items():
                if isinstance(resp_obj, dict):
                    resp_desc = resp_obj.get("description", "")
                    resp_content = resp_obj.get("content", {})
                    resp_schema = {}
                    if resp_content:
                        first_ct = list(resp_content.keys())[0]
                        resp_schema = resp_content.get(first_ct, {}).get("schema", {})
                    elif "schema" in resp_obj:
                        resp_schema = resp_obj.get("schema", {})
                    responses[str(status_code)] = {
                        "description": resp_desc,
                        "schema": resp_schema
                    }

            endpoints.append({
                "path": path_key,
                "method": method.upper(),
                "operation_id": op_id,
                "summary": summary,
                "description": op_desc,
                "tags": tags,
                "parameters": params,
                "request_body": request_body,
                "responses": responses
            })

    # Components / Definitions
    schemas = {}
    components = data.get("components", {})
    if "schemas" in components:
        schemas = components["schemas"]
    elif "definitions" in data:
        schemas = data["definitions"]

    return {
        "type": "openapi",
        "valid": True,
        "spec_version": openapi_ver,
        "title": title,
        "version": version,
        "description": description,
        "servers": servers,
        "endpoints": endpoints,
        "endpoint_count": len(endpoints),
        "schemas": schemas,
        "schema_count": len(schemas),
        "filepath": filepath,
        "raw_data": data
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. ASYNCAPI 3.x & 2.x PARSER
# ─────────────────────────────────────────────────────────────────────────────

def parse_asyncapi(content: Union[str, Dict[str, Any]], filepath: str = "") -> Dict[str, Any]:
    """
    Parses AsyncAPI 2.x / 3.x specifications for event-driven, WebSocket, and UDP systems.
    Extracts channels, operations (pub/sub), messages, and payload schemas.
    """
    data = {}
    if isinstance(content, dict):
        data = content
    else:
        try:
            data = json.loads(content)
        except Exception:
            try:
                data = yaml.safe_load(content)
            except Exception as e:
                log_event("warn", "contracts", f"Failed to parse AsyncAPI YAML/JSON in {filepath}: {e}")
                return {"type": "asyncapi", "valid": False, "error": str(e), "filepath": filepath}

    if not isinstance(data, dict) or (not data.get("asyncapi") and not data.get("channels")):
        return {"type": "asyncapi", "valid": False, "error": "Not a valid AsyncAPI definition", "filepath": filepath}

    asyncapi_ver = data.get("asyncapi", "3.0.0")
    info = data.get("info", {})
    title = info.get("title", Path(filepath).stem if filepath else "AsyncAPI Specification")
    version = info.get("version", "1.0.0")
    description = info.get("description", "")

    # Servers & protocols
    servers = []
    for s_name, s_obj in data.get("servers", {}).items():
        if isinstance(s_obj, dict):
            servers.append({
                "name": s_name,
                "host": s_obj.get("host", s_obj.get("url", "")),
                "protocol": s_obj.get("protocol", "ws"),
                "description": s_obj.get("description", "")
            })

    # Channels & Operations
    channels = []
    raw_channels = data.get("channels", {})
    
    for ch_name, ch_obj in raw_channels.items():
        if not isinstance(ch_obj, dict):
            continue
        
        address = ch_obj.get("address", ch_name)
        ch_desc = ch_obj.get("description", "")
        
        messages = []
        # AsyncAPI 2.x: publish / subscribe properties
        for action in ["publish", "subscribe"]:
            if action in ch_obj and isinstance(ch_obj[action], dict):
                act_obj = ch_obj[action]
                msg_obj = act_obj.get("message", {})
                messages.append({
                    "action": action.upper(),
                    "name": msg_obj.get("name", msg_obj.get("title", f"{ch_name}_{action}")),
                    "summary": msg_obj.get("summary", act_obj.get("summary", "")),
                    "payload": msg_obj.get("payload", {})
                })

        # AsyncAPI 3.x messages under channel.messages
        if "messages" in ch_obj:
            for m_key, m_val in ch_obj["messages"].items():
                if isinstance(m_val, dict):
                    messages.append({
                        "action": "MESSAGE",
                        "name": m_val.get("name", m_key),
                        "summary": m_val.get("summary", ""),
                        "payload": m_val.get("payload", {})
                    })

        channels.append({
            "name": ch_name,
            "address": address,
            "description": ch_desc,
            "messages": messages
        })

    # AsyncAPI 3.x operations top-level
    operations = []
    for op_name, op_obj in data.get("operations", {}).items():
        if isinstance(op_obj, dict):
            operations.append({
                "name": op_name,
                "action": op_obj.get("action", "send"),
                "channel": op_obj.get("channel", {}).get("$ref", "") if isinstance(op_obj.get("channel"), dict) else str(op_obj.get("channel", "")),
                "summary": op_obj.get("summary", "")
            })

    components = data.get("components", {})
    schemas = components.get("schemas", {})

    return {
        "type": "asyncapi",
        "valid": True,
        "spec_version": asyncapi_ver,
        "title": title,
        "version": version,
        "description": description,
        "servers": servers,
        "channels": channels,
        "channel_count": len(channels),
        "operations": operations,
        "schemas": schemas,
        "filepath": filepath,
        "raw_data": data
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. FLATBUFFERS (.fbs) & PROTOBUF (.proto) PARSER
# ─────────────────────────────────────────────────────────────────────────────

def parse_flatbuffers(content: str, filepath: str = "") -> Dict[str, Any]:
    """
    Parses Google FlatBuffers (.fbs) schema definition.
    Extracts namespaces, includes, enums, structs, tables, unions, root_type, and RPC services.
    """
    clean_lines = []
    in_block_comment = False
    for line in content.split("\n"):
        line_s = line.strip()
        if in_block_comment:
            if "*/" in line_s:
                in_block_comment = False
                line_s = line_s.split("*/", 1)[1].strip()
            else:
                continue
        if "/*" in line_s:
            if "*/" in line_s:
                line_s = re.sub(r'/\*.*?\*/', '', line_s).strip()
            else:
                in_block_comment = True
                line_s = line_s.split("/*", 1)[0].strip()
        if "//" in line_s:
            line_s = line_s.split("//", 1)[0].strip()
        if line_s:
            clean_lines.append(line_s)

    full_text = " ".join(clean_lines)

    # 1. Namespaces & Includes
    namespaces = re.findall(r'namespace\s+([a-zA-Z0-9_.]+)\s*;', full_text)
    includes = re.findall(r'include\s+["\']([^"\']+)["\']\s*;', full_text)
    root_type_match = re.search(r'root_type\s+([a-zA-Z0-9_]+)\s*;', full_text)
    root_type = root_type_match.group(1) if root_type_match else ""

    # 2. Enums
    enums = []
    enum_matches = re.finditer(r'enum\s+([a-zA-Z0-9_]+)\s*(?::\s*([a-zA-Z0-9_]+))?\s*\{([^}]+)\}', full_text)
    for em in enum_matches:
        enum_name = em.group(1)
        base_type = em.group(2) or "byte"
        body = em.group(3)
        values = []
        for item in body.split(","):
            item = item.strip()
            if not item:
                continue
            if "=" in item:
                k, v = item.split("=", 1)
                values.append({"name": k.strip(), "value": v.strip()})
            else:
                values.append({"name": item.strip(), "value": None})
        enums.append({
            "name": enum_name,
            "base_type": base_type,
            "values": values
        })

    # 3. Structs
    structs = []
    struct_matches = re.finditer(r'struct\s+([a-zA-Z0-9_]+)\s*\{([^}]+)\}', full_text)
    for sm in struct_matches:
        s_name = sm.group(1)
        body = sm.group(2)
        fields = []
        for field_stmt in body.split(";"):
            field_stmt = field_stmt.strip()
            if not field_stmt:
                continue
            if ":" in field_stmt:
                f_name, f_type = field_stmt.split(":", 1)
                fields.append({"name": f_name.strip(), "type": f_type.strip()})
        structs.append({"name": s_name, "fields": fields})

    # 4. Tables
    tables = []
    table_matches = re.finditer(r'table\s+([a-zA-Z0-9_]+)\s*(?:\([^)]*\))?\s*\{([^}]+)\}', full_text)
    for tm in table_matches:
        t_name = tm.group(1)
        body = tm.group(2)
        fields = []
        for field_stmt in body.split(";"):
            field_stmt = field_stmt.strip()
            if not field_stmt:
                continue
            if ":" in field_stmt:
                f_name, rest = field_stmt.split(":", 1)
                f_name = f_name.strip()
                f_type = rest.strip()
                default_val = None
                required = False
                
                if "(" in f_type and ")" in f_type:
                    meta = re.findall(r'\(([^)]+)\)', f_type)
                    for m in meta:
                        if "required" in m.lower():
                            required = True
                    f_type = re.sub(r'\([^)]+\)', '', f_type).strip()

                if "=" in f_type:
                    f_type_clean, default_val = f_type.split("=", 1)
                    f_type = f_type_clean.strip()
                    default_val = default_val.strip()

                fields.append({
                    "name": f_name,
                    "type": f_type,
                    "default": default_val,
                    "required": required
                })
        tables.append({
            "name": t_name,
            "is_root": (t_name == root_type),
            "fields": fields
        })

    # 5. Unions
    unions = []
    union_matches = re.finditer(r'union\s+([a-zA-Z0-9_]+)\s*\{([^}]+)\}', full_text)
    for um in union_matches:
        u_name = um.group(1)
        body = um.group(2)
        variants = [v.strip() for v in body.split(",") if v.strip()]
        unions.append({"name": u_name, "variants": variants})

    # 6. RPC Services
    rpc_services = []
    rpc_matches = re.finditer(r'rpc_service\s+([a-zA-Z0-9_]+)\s*\{([^}]+)\}', full_text)
    for rm in rpc_matches:
        s_name = rm.group(1)
        body = rm.group(2)
        methods = []
        for m in body.split(";"):
            m = m.strip()
            if not m:
                continue
            m_match = re.search(r'([a-zA-Z0-9_]+)\s*\(\s*([a-zA-Z0-9_]+)\s*\)\s*:\s*([a-zA-Z0-9_]+)', m)
            if m_match:
                methods.append({
                    "name": m_match.group(1),
                    "request": m_match.group(2),
                    "response": m_match.group(3)
                })
        rpc_services.append({"name": s_name, "methods": methods})

    return {
        "type": "flatbuffers",
        "valid": True,
        "filepath": filepath,
        "title": Path(filepath).name if filepath else "FlatBuffers Schema",
        "namespaces": namespaces,
        "includes": includes,
        "root_type": root_type,
        "enums": enums,
        "structs": structs,
        "tables": tables,
        "unions": unions,
        "rpc_services": rpc_services,
        "summary": f"{len(tables)} tables, {len(structs)} structs, {len(enums)} enums, {len(rpc_services)} services"
    }


def parse_protobuf(content: str, filepath: str = "") -> Dict[str, Any]:
    """
    Parses Protocol Buffers (.proto) schema definition (proto2/proto3).
    Extracts syntax, package, imports, enums, messages, fields, and gRPC services.
    """
    syntax_match = re.search(r'syntax\s*=\s*["\']([^"\']+)["\'];', content)
    syntax = syntax_match.group(1) if syntax_match else "proto3"

    package_match = re.search(r'package\s+([a-zA-Z0-9_.]+);', content)
    package = package_match.group(1) if package_match else ""

    imports = re.findall(r'import\s+["\']([^"\']+)["\'];', content)

    # Enums
    enums = []
    enum_matches = re.finditer(r'enum\s+([a-zA-Z0-9_]+)\s*\{([^}]+)\}', content)
    for em in enum_matches:
        enum_name = em.group(1)
        body = em.group(2)
        values = []
        for line in body.split(";"):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                values.append({"name": k.strip(), "number": v.strip()})
        enums.append({"name": enum_name, "values": values})

    # Messages
    messages = []
    msg_matches = re.finditer(r'message\s+([a-zA-Z0-9_]+)\s*\{([^}]+)\}', content)
    for mm in msg_matches:
        msg_name = mm.group(1)
        body = mm.group(2)
        fields = []
        for line in body.split(";"):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            if "=" in line:
                decl, num_part = line.split("=", 1)
                num = num_part.strip()
                tokens = decl.strip().split()
                repeated = False
                optional = False
                if "repeated" in tokens:
                    repeated = True
                    tokens.remove("repeated")
                if "optional" in tokens:
                    optional = True
                    tokens.remove("optional")
                
                if len(tokens) >= 2:
                    f_type = tokens[0]
                    f_name = tokens[1]
                    fields.append({
                        "name": f_name,
                        "type": f_type,
                        "number": num,
                        "repeated": repeated,
                        "optional": optional
                    })
        messages.append({"name": msg_name, "fields": fields})

    # Services / gRPC
    services = []
    service_matches = re.finditer(r'service\s+([a-zA-Z0-9_]+)\s*\{([^}]+)\}', content)
    for sm in service_matches:
        s_name = sm.group(1)
        body = sm.group(2)
        rpcs = []
        rpc_matches = re.finditer(r'rpc\s+([a-zA-Z0-9_]+)\s*\(\s*(stream\s+)?([a-zA-Z0-9_.]+)\s*\)\s*returns\s*\(\s*(stream\s+)?([a-zA-Z0-9_.]+)\s*\)', body)
        for rm in rpc_matches:
            rpcs.append({
                "name": rm.group(1),
                "client_stream": bool(rm.group(2)),
                "request": rm.group(3),
                "server_stream": bool(rm.group(4)),
                "response": rm.group(5)
            })
        services.append({"name": s_name, "rpcs": rpcs})

    return {
        "type": "protobuf",
        "valid": True,
        "filepath": filepath,
        "title": Path(filepath).name if filepath else "Protobuf Schema",
        "syntax": syntax,
        "package": package,
        "imports": imports,
        "enums": enums,
        "messages": messages,
        "services": services,
        "summary": f"{len(messages)} messages, {len(enums)} enums, {len(services)} gRPC services"
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. SCXML / STATECHARTS PARSER & MERMAID DIAGRAM GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def parse_scxml(content: str, filepath: str = "") -> Dict[str, Any]:
    """
    Parses W3C SCXML state machine definitions from XML.
    Extracts initial state, states, compound/nested states, transitions, events, guards, and actions.
    """
    try:
        clean_xml = re.sub(r'\sxmlns="[^"]+"', '', content)
        clean_xml = re.sub(r'\sxmlns:[a-zA-Z0-9_]+="[^"]+"', '', clean_xml)
        root = ET.fromstring(clean_xml)
    except Exception as e:
        log_event("warn", "contracts", f"Failed to parse SCXML in {filepath}: {e}")
        return {
            "type": "statechart",
            "valid": False,
            "error": str(e),
            "filepath": filepath,
            "name": Path(filepath).stem if filepath else "State Machine"
        }

    sm_name = root.attrib.get("name", Path(filepath).stem if filepath else "State Machine")
    initial_state = root.attrib.get("initial", "")
    datamodel = root.attrib.get("datamodel", "")

    states = []
    transitions = []
    
    if not initial_state:
        init_elem = root.find("initial")
        if init_elem is not None:
            init_trans = init_elem.find("transition")
            if init_trans is not None and "target" in init_trans.attrib:
                initial_state = init_trans.attrib["target"]

    def _parse_state_node(elem: ET.Element, parent_id: Optional[str] = None) -> Dict[str, Any]:
        state_id = elem.attrib.get("id", f"State_{id(elem)}")
        is_final = (elem.tag == "final")
        is_parallel = (elem.tag == "parallel")
        state_initial = elem.attrib.get("initial", "")
        
        local_transitions = []
        for t in elem.findall("transition"):
            target = t.attrib.get("target", "")
            event = t.attrib.get("event", "*")
            cond = t.attrib.get("cond") or t.attrib.get("guard") or ""
            local_transitions.append({
                "source": state_id,
                "target": target,
                "event": event,
                "condition": cond
            })
            transitions.append({
                "source": state_id,
                "target": target,
                "event": event,
                "condition": cond
            })

        child_states = []
        for child in elem:
            if child.tag in ["state", "parallel", "final"]:
                child_info = _parse_state_node(child, parent_id=state_id)
                child_states.append(child_info)

        onentry_actions = []
        onexit_actions = []
        for onentry in elem.findall("onentry"):
            for action in onentry:
                onentry_actions.append(action.tag)
        for onexit in elem.findall("onexit"):
            for action in onexit:
                onexit_actions.append(action.tag)

        return {
            "id": state_id,
            "type": "final" if is_final else ("parallel" if is_parallel else ("compound" if child_states else "atomic")),
            "parent": parent_id,
            "initial": state_initial,
            "transitions": local_transitions,
            "children": child_states,
            "onentry": onentry_actions,
            "onexit": onexit_actions
        }

    for elem in root:
        if elem.tag in ["state", "parallel", "final"]:
            st = _parse_state_node(elem)
            states.append(st)

    if not initial_state and states:
        initial_state = states[0]["id"]

    mermaid_diagram = generate_mermaid_statechart({
        "name": sm_name,
        "initial_state": initial_state,
        "states": states,
        "transitions": transitions
    })

    return {
        "type": "statechart",
        "valid": True,
        "filepath": filepath,
        "name": sm_name,
        "initial_state": initial_state,
        "datamodel": datamodel,
        "states": states,
        "state_count": len(states),
        "transitions": transitions,
        "transition_count": len(transitions),
        "mermaid": mermaid_diagram
    }


def generate_mermaid_statechart(scxml_data: Dict[str, Any]) -> str:
    """
    Generates clean, Docusaurus-ready Mermaid stateDiagram-v2 representation.
    """
    lines = ["stateDiagram-v2"]
    initial = scxml_data.get("initial_state", "")
    if initial:
        lines.append(f"    [*] --> {initial}")

    def _render_state(state: Dict[str, Any], indent: str = "    "):
        s_id = state["id"]
        s_type = state.get("type", "atomic")
        children = state.get("children", [])
        
        if children:
            lines.append(f"{indent}state {s_id} {{")
            child_init = state.get("initial", "")
            if child_init:
                lines.append(f"{indent}    [*] --> {child_init}")
            for c in children:
                _render_state(c, indent + "    ")
            lines.append(f"{indent}}}")
        elif s_type == "final":
            lines.append(f"{indent}{s_id} --> [*]")

    for s in scxml_data.get("states", []):
        _render_state(s, "    ")

    for t in scxml_data.get("transitions", []):
        src = t.get("source", "")
        tgt = t.get("target", "")
        event = t.get("event", "")
        cond = t.get("condition", "")
        
        if not src or not tgt:
            continue
        
        label_parts = []
        if event and event != "*":
            label_parts.append(event)
        if cond:
            label_parts.append(f"[{cond}]")
            
        label = " : " + " ".join(label_parts) if label_parts else ""
        lines.append(f"    {src} --> {tgt}{label}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 5. CEL (COMMON EXPRESSION LANGUAGE) INVARIANTS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def parse_cel_invariants(content: Union[str, Dict[str, Any], List[Any]], filepath: str = "") -> List[Dict[str, Any]]:
    """
    Parses declarative CEL invariant rule definitions from YAML/JSON files.
    Accepts list of rules or object with 'invariants' / 'rules' key.
    """
    data = None
    if isinstance(content, (dict, list)):
        data = content
    else:
        try:
            data = json.loads(content)
        except Exception:
            try:
                data = yaml.safe_load(content)
            except Exception as e:
                log_event("warn", "contracts", f"Failed to parse CEL invariants in {filepath}: {e}")
                return []

    rules_list = []
    if isinstance(data, list):
        rules_list = data
    elif isinstance(data, dict):
        if "invariants" in data and isinstance(data["invariants"], list):
            rules_list = data["invariants"]
        elif "rules" in data and isinstance(data["rules"], list):
            rules_list = data["rules"]
        elif "invariants" in data and isinstance(data["invariants"], dict):
            rules_list = [{"name": k, **(v if isinstance(v, dict) else {"rule": v})} for k, v in data["invariants"].items()]
        else:
            rules_list = [data]

    normalized_rules = []
    for idx, r in enumerate(rules_list):
        if not isinstance(r, dict):
            continue
        name = r.get("name") or r.get("id") or f"invariant_{idx+1}"
        expr = r.get("rule") or r.get("expr") or r.get("condition") or r.get("invariant") or ""
        target = r.get("target", "global")
        severity = r.get("severity", "ERROR").upper()
        description = r.get("description", r.get("desc", ""))
        pre_cond = r.get("precondition", "")
        post_cond = r.get("postcondition", "")
        
        if expr:
            normalized_rules.append({
                "name": name,
                "rule": expr,
                "target": target,
                "severity": severity,
                "description": description,
                "precondition": pre_cond,
                "postcondition": post_cond,
                "filepath": filepath
            })

    return normalized_rules


class SafeCELEvaluator(ast.NodeVisitor):
    """
    Safe AST-based evaluator for Common Expression Language (CEL) syntax and invariants.
    Zero use of Python's dangerous eval(); executes arithmetic, comparisons, logical
    connectives, member indexing, field lookups, and built-in functions deterministically.
    """

    def __init__(self, context: Dict[str, Any]):
        self.context = context

    def evaluate(self, node: ast.AST) -> Any:
        return self.visit(node)

    def visit_Constant(self, node: ast.Constant) -> Any:
        return node.value

    def visit_Name(self, node: ast.Name) -> Any:
        id_str = node.id
        if id_str in ("true", "True"):
            return True
        if id_str in ("false", "False"):
            return False
        if id_str in ("null", "nil", "None"):
            return None
        if id_str in self.context:
            return self.context[id_str]
        
        if id_str == "size":
            return len
        if id_str == "has":
            return lambda v: v is not None
        if id_str in ("min", "max", "abs"):
            return getattr(__builtins__, id_str) if isinstance(__builtins__, dict) else getattr(__builtins__, id_str)
        
        return None

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        val = self.visit(node.value)
        attr = node.attr
        if val is None:
            return None
        if isinstance(val, dict):
            return val.get(attr)
        if hasattr(val, attr):
            return getattr(val, attr)
        return None

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        val = self.visit(node.value)
        slice_val = self.visit(node.slice)
        if val is None:
            return None
        try:
            return val[slice_val]
        except Exception:
            return None

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return not bool(operand)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        return operand

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left = self.visit(node.left)
        right = self.visit(node.right)
        
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        return None

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        if isinstance(node.op, ast.And):
            for v in node.values:
                if not bool(self.visit(v)):
                    return False
            return True
        if isinstance(node.op, ast.Or):
            for v in node.values:
                if bool(self.visit(v)):
                    return True
            return False
        return False

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            res = False
            if isinstance(op, ast.Eq):
                res = (left == right)
            elif isinstance(op, ast.NotEq):
                res = (left != right)
            elif isinstance(op, ast.Lt):
                res = (left < right)
            elif isinstance(op, ast.LtE):
                res = (left <= right)
            elif isinstance(op, ast.Gt):
                res = (left > right)
            elif isinstance(op, ast.GtE):
                res = (left >= right)
            elif isinstance(op, ast.In):
                res = (left in right) if right is not None else False
            elif isinstance(op, ast.NotIn):
                res = (left not in right) if right is not None else True
            
            if not res:
                return False
            left = right
        return True

    def visit_Call(self, node: ast.Call) -> Any:
        if isinstance(node.func, ast.Attribute):
            target_obj = self.visit(node.func.value)
            method_name = node.func.attr
            args = [self.visit(a) for a in node.args]
            
            if target_obj is None:
                return False
            
            if method_name in ("startsWith", "startswith"):
                return str(target_obj).startswith(str(args[0]))
            if method_name in ("endsWith", "endswith"):
                return str(target_obj).endswith(str(args[0]))
            if method_name in ("contains", "includes"):
                return str(args[0]) in str(target_obj)
            if method_name == "matches":
                return bool(re.search(str(args[0]), str(target_obj)))
            if method_name in ("size", "length"):
                return len(target_obj)
            if method_name == "has":
                return args[0] in target_obj if isinstance(target_obj, (dict, list, set)) else hasattr(target_obj, str(args[0]))

        func_val = self.visit(node.func)
        args = [self.visit(a) for a in node.args]
        
        if callable(func_val):
            return func_val(*args)
        
        return None

    def visit_List(self, node: ast.List) -> Any:
        return [self.visit(elt) for elt in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> Any:
        return tuple(self.visit(elt) for elt in node.elts)

    def visit_Dict(self, node: ast.Dict) -> Any:
        return {self.visit(k): self.visit(v) for k, v in zip(node.keys, node.values)}


def evaluate_cel_expression(expr: str, context: Dict[str, Any]) -> bool:
    """
    Evaluates a single CEL expression against a state dictionary context.
    Transforms CEL syntax (&&, ||, !, true, false, null, .size()) into an AST and evaluates safely.
    """
    if not expr or not expr.strip():
        return True

    clean_expr = expr.strip()
    clean_expr = re.sub(r'&&', ' and ', clean_expr)
    clean_expr = re.sub(r'\|\|', ' or ', clean_expr)
    clean_expr = re.sub(r'!(?!=)', ' not ', clean_expr)
    clean_expr = re.sub(r'\btrue\b', 'True', clean_expr)
    clean_expr = re.sub(r'\bfalse\b', 'False', clean_expr)
    clean_expr = re.sub(r'\bnull\b', 'None', clean_expr)
    clean_expr = re.sub(r'\bnil\b', 'None', clean_expr)
    clean_expr = clean_expr.strip()

    try:
        parsed_ast = ast.parse(clean_expr, mode='eval')
        evaluator = SafeCELEvaluator(context)
        res = evaluator.evaluate(parsed_ast.body)
        return bool(res)
    except Exception as e:
        log_event("warn", "contracts", f"CEL expression evaluation error on '{expr}': {e}")
        return False


def validate_cel_invariants(invariants: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates a list of CEL invariants against given state context.
    Returns status, passed/failed rule breakdown, and diagnostic details.
    """
    results = []
    passed_count = 0
    failed_count = 0

    for inv in invariants:
        rule_expr = inv.get("rule", "")
        rule_name = inv.get("name", "unnamed_rule")
        severity = inv.get("severity", "ERROR")
        desc = inv.get("description", "")
        target = inv.get("target", "global")
        
        pre_cond = inv.get("precondition", "")
        if pre_cond and not evaluate_cel_expression(pre_cond, context):
            results.append({
                "name": rule_name,
                "rule": rule_expr,
                "target": target,
                "severity": severity,
                "passed": True,
                "status": "SKIPPED_PRECONDITION",
                "description": desc
            })
            passed_count += 1
            continue

        passed = evaluate_cel_expression(rule_expr, context)
        if passed:
            passed_count += 1
            results.append({
                "name": rule_name,
                "rule": rule_expr,
                "target": target,
                "severity": severity,
                "passed": True,
                "status": "PASSED",
                "description": desc
            })
        else:
            failed_count += 1
            results.append({
                "name": rule_name,
                "rule": rule_expr,
                "target": target,
                "severity": severity,
                "passed": False,
                "status": "FAILED",
                "description": desc,
                "error": f"Violation of invariant '{rule_name}': {rule_expr}"
            })

    return {
        "valid": (failed_count == 0),
        "total_rules": len(invariants),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "results": results
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. UNIVERSAL REPOSITORY SCANNER & DISCOVERY
# ─────────────────────────────────────────────────────────────────────────────

def scan_and_parse_contracts(repo_path: str) -> Dict[str, Any]:
    """
    Scans repository directory for all language-agnostic contract specifications:
    - OpenAPI/Swagger: (*.openapi.json/yaml, *swagger.json/yaml, openapi.yaml, etc.)
    - AsyncAPI: (*asyncapi.json/yaml)
    - FlatBuffers: (*.fbs)
    - Protobuf: (*.proto)
    - SCXML / Statecharts: (*.scxml, statechart*.xml)
    - CEL Invariants: (*.cel.yaml/json, invariants.yaml/json)
    """
    if not repo_path:
        return _empty_contracts_catalog()

    rp = Path(repo_path)
    if not rp.exists() or not rp.is_dir():
        return _empty_contracts_catalog()

    openapi_specs = []
    asyncapi_specs = []
    flatbuffers_specs = []
    protobuf_specs = []
    statecharts = []
    cel_invariants = []

    scan_subdirs = ["schemas", "contracts", "docs", "api", "proto", "specs", "statecharts", ""]
    seen_files = set()

    for sub in scan_subdirs:
        target_dir = rp / sub if sub else rp
        if not target_dir.exists() or not target_dir.is_dir():
            continue

        try:
            for item in target_dir.rglob("*"):
                if not item.is_file() or str(item) in seen_files:
                    continue
                
                path_str = str(item)
                if any(ignored in path_str for ignored in [".git", "node_modules", ".gemini", ".claude", "__pycache__", ".venv"]):
                    continue

                seen_files.add(path_str)
                name_lower = item.name.lower()
                suffix_lower = item.suffix.lower()

                if suffix_lower == ".fbs":
                    try:
                        content = item.read_text(encoding="utf-8", errors="ignore")
                        flatbuffers_specs.append(parse_flatbuffers(content, filepath=str(item)))
                    except Exception as e:
                        log_event("warn", "contracts", f"Error reading FlatBuffers {item.name}: {e}")

                elif suffix_lower == ".proto":
                    try:
                        content = item.read_text(encoding="utf-8", errors="ignore")
                        protobuf_specs.append(parse_protobuf(content, filepath=str(item)))
                    except Exception as e:
                        log_event("warn", "contracts", f"Error reading Proto {item.name}: {e}")

                elif suffix_lower == ".scxml" or (suffix_lower == ".xml" and ("scxml" in name_lower or "statechart" in name_lower)):
                    try:
                        content = item.read_text(encoding="utf-8", errors="ignore")
                        statecharts.append(parse_scxml(content, filepath=str(item)))
                    except Exception as e:
                        log_event("warn", "contracts", f"Error reading SCXML {item.name}: {e}")

                elif "cel" in name_lower or "invariant" in name_lower:
                    if suffix_lower in [".yaml", ".yml", ".json"]:
                        try:
                            content = item.read_text(encoding="utf-8", errors="ignore")
                            inv_rules = parse_cel_invariants(content, filepath=str(item))
                            cel_invariants.extend(inv_rules)
                        except Exception as e:
                            log_event("warn", "contracts", f"Error reading CEL Invariants {item.name}: {e}")

                elif suffix_lower in [".yaml", ".yml", ".json"]:
                    # Only files that structurally validate are recorded. The old
                    # heuristic matched the substring "paths" anywhere in the first
                    # 500 chars, so tsconfig.json ("compilerOptions.paths") and
                    # launchSettings.json were misfiled as OpenAPI specs. We now
                    # parse first and require an explicit openapi/swagger marker
                    # (or a top-level paths object) before accepting.
                    try:
                        content = item.read_text(encoding="utf-8", errors="ignore")
                        head = content[:400].lower()
                        if "asyncapi" in head:
                            spec = parse_asyncapi(content, filepath=str(item))
                            if spec.get("valid"):
                                asyncapi_specs.append(spec)
                        elif _looks_like_openapi(content):
                            spec = parse_openapi(content, filepath=str(item))
                            if spec.get("valid"):
                                openapi_specs.append(spec)
                        elif "invariants" in head:
                            inv_rules = parse_cel_invariants(content, filepath=str(item))
                            cel_invariants.extend(inv_rules)
                    except Exception:
                        pass
        except Exception as e:
            log_event("warn", "contracts", f"Error scanning directory {target_dir}: {e}")

    total_count = (
        len(openapi_specs) +
        len(asyncapi_specs) +
        len(flatbuffers_specs) +
        len(protobuf_specs) +
        len(statecharts) +
        (1 if cel_invariants else 0)
    )

    return {
        "repo_path": repo_path,
        "total_contracts": total_count,
        "openapi": openapi_specs,
        "asyncapi": asyncapi_specs,
        "flatbuffers": flatbuffers_specs,
        "protobuf": protobuf_specs,
        "statecharts": statecharts,
        "cel_invariants": cel_invariants,
        "summary": {
            "openapi_count": len(openapi_specs),
            "asyncapi_count": len(asyncapi_specs),
            "flatbuffers_count": len(flatbuffers_specs),
            "protobuf_count": len(protobuf_specs),
            "statecharts_count": len(statecharts),
            "cel_invariants_count": len(cel_invariants)
        }
    }


def _empty_contracts_catalog() -> Dict[str, Any]:
    return {
        "repo_path": "",
        "total_contracts": 0,
        "openapi": [],
        "asyncapi": [],
        "flatbuffers": [],
        "protobuf": [],
        "statecharts": [],
        "cel_invariants": [],
        "summary": {
            "openapi_count": 0,
            "asyncapi_count": 0,
            "flatbuffers_count": 0,
            "protobuf_count": 0,
            "statecharts_count": 0,
            "cel_invariants_count": 0
        }
    }


def format_contracts_prompt_block(repo_path: str) -> str:
    """
    Constructs an authoritative Markdown prompt block summarizing all active contract
    specifications, endpoints, schemas, state transitions, and CEL invariants for subagents.
    """
    catalog = scan_and_parse_contracts(repo_path)
    if catalog["total_contracts"] == 0 and not catalog["cel_invariants"]:
        return "=== [UNIVERSAL CONTRACTS & SCHEMAS] ===\nNo formal contract specifications (OpenAPI, FlatBuffers, SCXML, CEL) detected in repo.\n=========================================="

    lines = ["=== [UNIVERSAL CONTRACTS & ARCHITECTURAL INVARIANTS] ==="]
    
    if catalog["openapi"]:
        lines.append("\n📜 [REST / OPENAPI SPECIFICATIONS]:")
        for spec in catalog["openapi"]:
            lines.append(f"- **{spec.get('title', 'API')}** (v{spec.get('version', '1.0')}) — {spec.get('endpoint_count', 0)} endpoints:")
            for ep in spec.get("endpoints", [])[:8]:
                lines.append(f"  • `{ep['method']}` `{ep['path']}` — {ep.get('summary', ep.get('operation_id', ''))}")
            if len(spec.get("endpoints", [])) > 8:
                lines.append(f"  • ... and {len(spec.get('endpoints', [])) - 8} more endpoints")

    if catalog["asyncapi"]:
        lines.append("\n📡 [ASYNCAPI / EVENT SPECIFICATIONS]:")
        for spec in catalog["asyncapi"]:
            lines.append(f"- **{spec.get('title', 'Events')}** — {spec.get('channel_count', 0)} channels:")
            for ch in spec.get("channels", [])[:6]:
                lines.append(f"  • Channel `{ch['name']}` ({ch.get('address', '')})")

    if catalog["flatbuffers"]:
        lines.append("\n⚡ [FLATBUFFERS BINARY SCHEMAS (.fbs)]:")
        for spec in catalog["flatbuffers"]:
            lines.append(f"- **{spec.get('title', 'Schema')}** (Root: `{spec.get('root_type', 'None')}`):")
            for t in spec.get("tables", [])[:6]:
                fields_str = ", ".join([f"{f['name']}:{f['type']}" for f in t.get("fields", [])[:4]])
                lines.append(f"  • Table `{t['name']}` ({fields_str})")

    if catalog["protobuf"]:
        lines.append("\n📦 [PROTOBUF SCHEMAS (.proto)]:")
        for spec in catalog["protobuf"]:
            lines.append(f"- **{spec.get('title', 'Proto')}** (Package: `{spec.get('package', 'global')}`):")
            for m in spec.get("messages", [])[:6]:
                lines.append(f"  • Message `{m['name']}` ({len(m.get('fields', []))} fields)")

    if catalog["statecharts"]:
        lines.append("\n🔄 [SCXML STATE MACHINES & TRANSITIONS]:")
        for sc in catalog["statecharts"]:
            lines.append(f"- **{sc.get('name', 'State Machine')}** (Initial: `{sc.get('initial_state', '')}`):")
            for tr in sc.get("transitions", [])[:8]:
                cond_str = f" [{tr['condition']}]" if tr.get('condition') else ""
                lines.append(f"  • `{tr['source']}` ➔ `{tr['target']}` on event `{tr['event']}`{cond_str}")

    if catalog["cel_invariants"]:
        lines.append("\n🛡️ [CEL INVARIANT RULES & CONSTRAINTS]:")
        for inv in catalog["cel_invariants"]:
            lines.append(f"- `[{inv.get('severity', 'ERROR')}]` **{inv.get('name', '')}** (Target: `{inv.get('target', 'all')}`): `{inv.get('rule', '')}`")
            if inv.get("description"):
                lines.append(f"  _{inv.get('description')}_")

    lines.append("\n========================================================")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 7. DOCUSAURUS DOCUMENTATION GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def export_to_docusaurus(source: Union[str, Dict[str, Any]], docs_output_dir: str) -> Dict[str, Any]:
    """
    Compiles all discovered contracts (OpenAPI, AsyncAPI, FlatBuffers, Protobuf,
    SCXML diagrams with Mermaid, CEL invariants) into a production-ready
    Docusaurus documentation hierarchy under docs_output_dir/contracts/...
    """
    if isinstance(source, dict):
        catalog = source
    else:
        catalog = scan_and_parse_contracts(str(source))

    out_base = Path(docs_output_dir)
    contracts_dir = out_base / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    generated_files = []

    cat_file = contracts_dir / "_category_.json"
    cat_file.write_text(json.dumps({
        "label": "Universal Contracts & Schemas",
        "position": 2,
        "link": {
            "type": "generated-index",
            "description": "Language-agnostic API, Statechart, and Binary Serialization specifications."
        }
    }, indent=2), encoding="utf-8")
    generated_files.append(str(cat_file))

    index_md = f"""---
id: contracts-overview
title: 📜 System Contracts & Schema Catalog
sidebar_label: Overview
sidebar_position: 1
---

# 📜 Universal System Contracts & Schemas

Welcome to the **Universal Contract Engine Documentation**. This documentation is automatically synchronized and compiled directly from language-agnostic specifications across the project.

## 📊 Catalog Breakdown

| Contract Category | Discovered Specifications | Target Protocol / Engine |
| :--- | :---: | :--- |
| **OpenAPI / REST** | `{catalog['summary']['openapi_count']}` | HTTP / RESTful JSON Endpoints |
| **AsyncAPI** | `{catalog['summary']['asyncapi_count']}` | WebSocket / UDP / Event Streams |
| **FlatBuffers** | `{catalog['summary']['flatbuffers_count']}` | Zero-Copy Binary IPC & Gaming |
| **Protobuf / gRPC** | `{catalog['summary']['protobuf_count']}` | gRPC / Microservices |
| **SCXML Statecharts** | `{catalog['summary']['statecharts_count']}` | Deterministic State Machines |
| **CEL Invariants** | `{catalog['summary']['cel_invariants_count']}` | Declarative Pre/Post Conditions |

---

## 🚀 Navigation

- [OpenAPI REST Endpoints](./openapi/overview.md)
- [AsyncAPI Event Channels](./asyncapi/overview.md)
- [FlatBuffers Binary Schemas](./flatbuffers/overview.md)
- [Protobuf Definitions](./protobuf/overview.md)
- [SCXML State Machines & Mermaid Diagrams](./statecharts/overview.md)
- [CEL Declarative Invariants](./invariants/overview.md)
"""
    index_file = contracts_dir / "index.md"
    index_file.write_text(index_md, encoding="utf-8")
    generated_files.append(str(index_file))

    if catalog["openapi"]:
        o_dir = contracts_dir / "openapi"
        o_dir.mkdir(parents=True, exist_ok=True)
        (o_dir / "_category_.json").write_text(json.dumps({"label": "OpenAPI / REST", "position": 2}, indent=2), encoding="utf-8")
        
        for idx, spec in enumerate(catalog["openapi"]):
            safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', spec.get("title", f"spec_{idx+1}")).lower()
            spec_md = [
                "---",
                f"id: openapi-{safe_name}",
                f"title: \"{spec.get('title', 'OpenAPI Specification')}\"",
                f"sidebar_label: \"{spec.get('title', 'API')}\"",
                "---",
                "",
                f"# {spec.get('title', 'OpenAPI Specification')}",
                f"> Version `{spec.get('version', '1.0')}` | Spec Version `{spec.get('spec_version', '3.0')}`",
                "",
                spec.get("description", "RESTful API Specification."),
                "",
                "## 🌐 Servers",
                ""
            ]
            for s in spec.get("servers", []):
                spec_md.append(f"- `{s['url']}` ({s.get('description') or 'Default Server'})")
            
            spec_md.extend([
                "",
                "## 🛣️ Endpoints",
                "",
                "| Method | Path | Summary | Operation ID |",
                "| :--- | :--- | :--- | :--- |"
            ])
            for ep in spec.get("endpoints", []):
                spec_md.append(f"| **`{ep['method']}`** | `{ep['path']}` | {ep.get('summary', '')} | `{ep.get('operation_id', '')}` |")

            spec_md.extend(["", "## 🔍 Endpoint Specifications", ""])
            for ep in spec.get("endpoints", []):
                spec_md.append(f"### `{ep['method']}` {ep['path']}")
                if ep.get("summary"):
                    spec_md.append(f"**Summary**: {ep['summary']}")
                if ep.get("description"):
                    spec_md.append(f"\n{ep['description']}\n")
                
                if ep.get("parameters"):
                    spec_md.extend([
                        "\n**Parameters**:",
                        "| Name | In | Type | Required | Description |",
                        "| :--- | :--- | :--- | :---: | :--- |"
                    ])
                    for p in ep["parameters"]:
                        spec_md.append(f"| `{p['name']}` | `{p['in']}` | `{p['type']}` | {'✓' if p['required'] else '—'} | {p.get('description', '')} |")

                if ep.get("request_body"):
                    spec_md.append("\n**Request Body**:")
                    spec_md.append("```json")
                    spec_md.append(json.dumps(ep["request_body"], indent=2))
                    spec_md.append("```")

                if ep.get("responses"):
                    spec_md.extend([
                        "\n**Responses**:",
                        "| Status | Description |",
                        "| :--- | :--- |"
                    ])
                    for st, r in ep["responses"].items():
                        spec_md.append(f"| `{st}` | {r.get('description', '')} |")
                
                spec_md.append("\n---")

            out_file = o_dir / f"{safe_name}.md"
            out_file.write_text("\n".join(spec_md), encoding="utf-8")
            generated_files.append(str(out_file))

    if catalog["asyncapi"]:
        a_dir = contracts_dir / "asyncapi"
        a_dir.mkdir(parents=True, exist_ok=True)
        (a_dir / "_category_.json").write_text(json.dumps({"label": "AsyncAPI Channels", "position": 3}, indent=2), encoding="utf-8")

        for idx, spec in enumerate(catalog["asyncapi"]):
            safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', spec.get("title", f"async_{idx+1}")).lower()
            spec_md = [
                "---",
                f"id: asyncapi-{safe_name}",
                f"title: \"{spec.get('title', 'AsyncAPI Specification')}\"",
                f"sidebar_label: \"{spec.get('title', 'Events')}\"",
                "---",
                "",
                f"# {spec.get('title', 'AsyncAPI Specification')}",
                f"> Spec Version `{spec.get('spec_version', '3.0')}`",
                "",
                spec.get("description", "Event-driven and streaming message channels."),
                "",
                "## 📡 Channels & Topics",
                "",
                "| Channel Name | Address | Action | Message |",
                "| :--- | :--- | :---: | :--- |"
            ]
            for ch in spec.get("channels", []):
                for m in ch.get("messages", []):
                    spec_md.append(f"| `{ch['name']}` | `{ch.get('address', '')}` | `{m.get('action', '')}` | `{m.get('name', '')}` |")
            
            out_file = a_dir / f"{safe_name}.md"
            out_file.write_text("\n".join(spec_md), encoding="utf-8")
            generated_files.append(str(out_file))

    if catalog["flatbuffers"]:
        f_dir = contracts_dir / "flatbuffers"
        f_dir.mkdir(parents=True, exist_ok=True)
        (f_dir / "_category_.json").write_text(json.dumps({"label": "FlatBuffers Schemas", "position": 4}, indent=2), encoding="utf-8")

        for idx, spec in enumerate(catalog["flatbuffers"]):
            safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', spec.get("title", f"fb_{idx+1}")).lower()
            spec_md = [
                "---",
                f"id: flatbuffers-{safe_name}",
                f"title: \"{spec.get('title', 'FlatBuffers Schema')}\"",
                f"sidebar_label: \"{spec.get('title', 'FBS')}\"",
                "---",
                "",
                f"# {spec.get('title', 'FlatBuffers Schema')}",
                f"> Root Type: `{spec.get('root_type', 'None')}`",
                "",
                "## 📋 Tables & Structs",
                ""
            ]
            for t in spec.get("tables", []):
                spec_md.extend([
                    f"### Table `{t['name']}` {'(Root)' if t.get('is_root') else ''}",
                    "| Field | Type | Default | Required |",
                    "| :--- | :--- | :--- | :---: |"
                ])
                for f in t.get("fields", []):
                    spec_md.append(f"| `{f['name']}` | `{f['type']}` | `{f.get('default') or 'None'}` | {'✓' if f.get('required') else '—'} |")
                spec_md.append("")

            for s in spec.get("structs", []):
                spec_md.extend([
                    f"### Struct `{s['name']}`",
                    "| Field | Type |",
                    "| :--- | :--- |"
                ])
                for f in s.get("fields", []):
                    spec_md.append(f"| `{f['name']}` | `{f['type']}` |")
                spec_md.append("")

            if spec.get("rpc_services"):
                spec_md.extend([
                    "## ⚡ RPC Services",
                    "| Service | Method | Request | Response |",
                    "| :--- | :--- | :--- | :--- |"
                ])
                for s in spec["rpc_services"]:
                    for m in s.get("methods", []):
                        spec_md.append(f"| `{s['name']}` | `{m['name']}` | `{m['request']}` | `{m['response']}` |")

            out_file = f_dir / f"{safe_name}.md"
            out_file.write_text("\n".join(spec_md), encoding="utf-8")
            generated_files.append(str(out_file))

    if catalog["protobuf"]:
        p_dir = contracts_dir / "protobuf"
        p_dir.mkdir(parents=True, exist_ok=True)
        (p_dir / "_category_.json").write_text(json.dumps({"label": "Protobuf & gRPC", "position": 5}, indent=2), encoding="utf-8")

        for idx, spec in enumerate(catalog["protobuf"]):
            safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', spec.get("title", f"proto_{idx+1}")).lower()
            spec_md = [
                "---",
                f"id: protobuf-{safe_name}",
                f"title: \"{spec.get('title', 'Protobuf Definition')}\"",
                f"sidebar_label: \"{spec.get('title', 'Proto')}\"",
                "---",
                "",
                f"# {spec.get('title', 'Protobuf Definition')}",
                f"> Syntax: `{spec.get('syntax', 'proto3')}` | Package: `{spec.get('package', 'global')}`",
                "",
                "## ✉️ Messages",
                ""
            ]
            for m in spec.get("messages", []):
                spec_md.extend([
                    f"### Message `{m['name']}`",
                    "| Number | Field Name | Type | Modifiers |",
                    "| :---: | :--- | :--- | :--- |"
                ])
                for f in m.get("fields", []):
                    mods = []
                    if f.get("repeated"): mods.append("repeated")
                    if f.get("optional"): mods.append("optional")
                    spec_md.append(f"| `{f.get('number', '')}` | `{f['name']}` | `{f['type']}` | {', '.join(mods) or '—'} |")
                spec_md.append("")

            if spec.get("services"):
                spec_md.extend([
                    "## 🚀 gRPC Services",
                    "| Service | RPC Method | Request Type | Response Type |",
                    "| :--- | :--- | :--- | :--- |"
                ])
                for s in spec["services"]:
                    for rpc in s.get("rpcs", []):
                        req_str = f"stream {rpc['request']}" if rpc.get("client_stream") else rpc['request']
                        resp_str = f"stream {rpc['response']}" if rpc.get("server_stream") else rpc['response']
                        spec_md.append(f"| `{s['name']}` | `{rpc['name']}` | `{req_str}` | `{resp_str}` |")

            out_file = p_dir / f"{safe_name}.md"
            out_file.write_text("\n".join(spec_md), encoding="utf-8")
            generated_files.append(str(out_file))

    if catalog["statecharts"]:
        s_dir = contracts_dir / "statecharts"
        s_dir.mkdir(parents=True, exist_ok=True)
        (s_dir / "_category_.json").write_text(json.dumps({"label": "SCXML Statecharts", "position": 6}, indent=2), encoding="utf-8")

        for idx, sc in enumerate(catalog["statecharts"]):
            safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', sc.get("name", f"sm_{idx+1}")).lower()
            spec_md = [
                "---",
                f"id: statechart-{safe_name}",
                f"title: \"{sc.get('name', 'State Machine')}\"",
                f"sidebar_label: \"{sc.get('name', 'State Machine')}\"",
                "---",
                "",
                f"# {sc.get('name', 'State Machine')}",
                f"> Initial State: `{sc.get('initial_state', 'None')}`",
                "",
                "## 📊 Interactive Mermaid State Diagram",
                "",
                "```mermaid",
                sc.get("mermaid", "stateDiagram-v2\n    [*] --> Idle"),
                "```",
                "",
                "## 🔄 Transition Invariant Matrix",
                "",
                "| Source State | Target State | Event Trigger | Guard Condition |",
                "| :--- | :--- | :--- | :--- |"
            ]
            for t in sc.get("transitions", []):
                cond_str = f"`{t['condition']}`" if t.get('condition') else "—"
                spec_md.append(f"| `{t['source']}` | `{t['target']}` | `{t.get('event', '*')}` | {cond_str} |")

            out_file = s_dir / f"{safe_name}.md"
            out_file.write_text("\n".join(spec_md), encoding="utf-8")
            generated_files.append(str(out_file))

    if catalog["cel_invariants"]:
        i_dir = contracts_dir / "invariants"
        i_dir.mkdir(parents=True, exist_ok=True)
        (i_dir / "_category_.json").write_text(json.dumps({"label": "CEL Invariants", "position": 7}, indent=2), encoding="utf-8")

        spec_md = [
            "---",
            "id: cel-invariants-overview",
            "title: \"🛡️ CEL Declarative Invariant Rules\"",
            "sidebar_label: \"CEL Invariants\"",
            "---",
            "",
            "# 🛡️ Common Expression Language (CEL) Invariant Rules",
            "",
            "These declarative invariant rules are continuously validated against state payloads during execution:",
            "",
            "| Severity | Rule Name | Target Scope | Expression | Description |",
            "| :---: | :--- | :--- | :--- | :--- |"
        ]
        for inv in catalog["cel_invariants"]:
            spec_md.append(f"| `{inv.get('severity', 'ERROR')}` | **{inv.get('name', '')}** | `{inv.get('target', 'global')}` | `{inv.get('rule', '')}` | {inv.get('description', '')} |")

        spec_md.extend([
            "",
            "## 🧪 Evaluation Semantics",
            "CEL invariants evaluate boolean assertions over dynamic runtime state objects (`state`, `payload`, `request`, `user`).",
            "- If a rule evaluates to `false`, the Zero-Trust Gate rejects the transaction or draft.",
            "- Preconditions can be configured via `precondition` fields to guard rule activation."
        ])

        out_file = i_dir / "overview.md"
        out_file.write_text("\n".join(spec_md), encoding="utf-8")
        generated_files.append(str(out_file))

    log_event("info", "contracts", f"Exported {len(generated_files)} Docusaurus markdown files to {contracts_dir}")
    return {
        "success": True,
        "contracts_dir": str(contracts_dir),
        "exported_files_count": len(generated_files),
        "files": generated_files
    }