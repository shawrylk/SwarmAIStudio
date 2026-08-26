"""
Comprehensive Unit Tests for Universal Contract & Docusaurus Engine
Validates:
1. OpenAPI 3.x / Swagger 2.0 parsing
2. AsyncAPI 3.x / 2.x parsing
3. FlatBuffers (.fbs) & Protobuf (.proto) parsing
4. SCXML Statecharts & Mermaid state diagram generation
5. CEL Invariant evaluation (expressions, operators, string methods, validation)
6. Docusaurus documentation hierarchy export
7. Swarm Loop Engine Pre-flight research & Zero-Trust QA integration
8. HTTP Server Backend API endpoints (/api/contracts/*)
"""

import unittest
import tempfile
import json
import yaml
import asyncio
import urllib.request
import threading
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch, AsyncMock

from swarm.contracts_engine import (
    parse_openapi,
    parse_asyncapi,
    parse_flatbuffers,
    parse_protobuf,
    parse_scxml,
    generate_mermaid_statechart,
    evaluate_cel_expression,
    validate_cel_invariants,
    scan_and_parse_contracts,
    format_contracts_prompt_block,
    export_to_docusaurus
)
from swarm.loop_engine import run_preflight_research
from swarm.server import SwarmHandler


class TestContractsEngine(unittest.TestCase):

    # ─────────────────────────────────────────────────────────────
    # 1. OPENAPI & SWAGGER PARSING
    # ─────────────────────────────────────────────────────────────

    def test_parse_openapi_3_yaml(self):
        openapi_yaml = """
openapi: 3.0.1
info:
  title: Payments Gateway
  version: 2.1.0
  description: High-performance payment processing endpoints
servers:
  - url: https://api.payments.io/v1
    description: Production Cluster
paths:
  /transactions/{id}:
    get:
      summary: Retrieve Transaction
      operationId: getTransactionById
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Successful response
          content:
            application/json:
              schema:
                type: object
    post:
      summary: Create Transaction
      operationId: createTransaction
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                amount:
                  type: number
      responses:
        '201':
          description: Created
components:
  schemas:
    Transaction:
      type: object
      properties:
        id:
          type: string
        amount:
          type: number
"""
        parsed = parse_openapi(openapi_yaml, filepath="api/payments.yaml")
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["title"], "Payments Gateway")
        self.assertEqual(parsed["version"], "2.1.0")
        self.assertEqual(len(parsed["servers"]), 1)
        self.assertEqual(parsed["endpoint_count"], 2)
        
        get_ep = [ep for ep in parsed["endpoints"] if ep["method"] == "GET"][0]
        self.assertEqual(get_ep["path"], "/transactions/{id}")
        self.assertEqual(get_ep["operation_id"], "getTransactionById")
        self.assertEqual(len(get_ep["parameters"]), 1)
        self.assertEqual(get_ep["parameters"][0]["name"], "id")

        post_ep = [ep for ep in parsed["endpoints"] if ep["method"] == "POST"][0]
        self.assertTrue(post_ep["request_body"]["required"])
        self.assertIn("201", post_ep["responses"])

    def test_parse_swagger_2_json(self):
        swagger_json = json.dumps({
            "swagger": "2.0",
            "info": {"title": "Legacy Swagger API", "version": "1.0.0"},
            "host": "api.legacy.com",
            "basePath": "/v2",
            "paths": {
                "/users": {
                    "get": {
                        "summary": "Get users",
                        "responses": {"200": {"description": "List users"}}
                    }
                }
            }
        })
        parsed = parse_openapi(swagger_json, filepath="swagger.json")
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["title"], "Legacy Swagger API")
        self.assertEqual(parsed["servers"][0]["url"], "https://api.legacy.com/v2")
        self.assertEqual(parsed["endpoint_count"], 1)

    def test_parse_openapi_invalid(self):
        invalid_text = "::: invalid non-dictionary yaml [[["
        parsed = parse_openapi(invalid_text, filepath="broken.yaml")
        self.assertFalse(parsed["valid"])
        self.assertIn("error", parsed)

    # ─────────────────────────────────────────────────────────────
    # 2. ASYNCAPI PARSING
    # ─────────────────────────────────────────────────────────────

    def test_parse_asyncapi_3(self):
        asyncapi_yaml = """
asyncapi: 3.0.0
info:
  title: Order Processing Stream
  version: 1.0.0
  description: Real-time order events
servers:
  production:
    host: kafka.orders.internal:9092
    protocol: kafka
channels:
  orderCreatedChannel:
    address: orders.events.created
    messages:
      OrderCreatedMessage:
        summary: Fired upon successful checkout
        payload:
          type: object
          properties:
            orderId:
              type: string
operations:
  receiveOrder:
    action: receive
    channel:
      $ref: '#/channels/orderCreatedChannel'
"""
        parsed = parse_asyncapi(asyncapi_yaml, filepath="asyncapi.yaml")
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["title"], "Order Processing Stream")
        self.assertEqual(len(parsed["channels"]), 1)
        self.assertEqual(parsed["channels"][0]["name"], "orderCreatedChannel")
        self.assertEqual(parsed["channels"][0]["address"], "orders.events.created")
        self.assertEqual(len(parsed["operations"]), 1)

    def test_parse_asyncapi_invalid(self):
        invalid_text = "raw string without asyncapi structure"
        parsed = parse_asyncapi(invalid_text, filepath="broken_async.yaml")
        self.assertFalse(parsed["valid"])

    # ─────────────────────────────────────────────────────────────
    # 3. FLATBUFFERS & PROTOBUF PARSING
    # ─────────────────────────────────────────────────────────────

    def test_parse_flatbuffers_schema(self):
        fbs_content = """
namespace Game.Combat;

enum WeaponType:byte { Sword = 0, Bow = 1, Staff = 2 }

struct Vec3 {
  x:float;
  y:float;
  z:float;
}

table Weapon {
  name:string (required);
  damage:short = 50;
  type:WeaponType = Sword;
}

table Hero {
  id:ulong;
  name:string;
  pos:Vec3;
  inventory:[Weapon];
}

union Entity { Hero, Weapon }

root_type Hero;

rpc_service CombatEngine {
  SpawnHero(Hero):Hero;
}
"""
        parsed = parse_flatbuffers(fbs_content, filepath="hero.fbs")
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["namespaces"], ["Game.Combat"])
        self.assertEqual(parsed["root_type"], "Hero")
        self.assertEqual(len(parsed["enums"]), 1)
        self.assertEqual(parsed["enums"][0]["name"], "WeaponType")
        self.assertEqual(len(parsed["structs"]), 1)
        self.assertEqual(parsed["structs"][0]["name"], "Vec3")
        self.assertEqual(len(parsed["tables"]), 2)
        
        hero_tbl = [t for t in parsed["tables"] if t["name"] == "Hero"][0]
        self.assertTrue(hero_tbl["is_root"])
        
        weapon_tbl = [t for t in parsed["tables"] if t["name"] == "Weapon"][0]
        name_field = [f for f in weapon_tbl["fields"] if f["name"] == "name"][0]
        self.assertTrue(name_field["required"])

        self.assertEqual(len(parsed["unions"]), 1)
        self.assertEqual(len(parsed["rpc_services"]), 1)
        self.assertEqual(parsed["rpc_services"][0]["methods"][0]["name"], "SpawnHero")

    def test_parse_protobuf_schema(self):
        proto_content = """
syntax = "proto3";

package banking.v1;

enum AccountStatus {
  UNSPECIFIED = 0;
  ACTIVE = 1;
  FROZEN = 2;
}

message Account {
  string id = 1;
  double balance = 2;
  AccountStatus status = 3;
  repeated string tags = 4;
}

message TransferRequest {
  string from_id = 1;
  string to_id = 2;
  double amount = 3;
}

service BankingService {
  rpc Transfer (TransferRequest) returns (Account);
}
"""
        parsed = parse_protobuf(proto_content, filepath="banking.proto")
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["syntax"], "proto3")
        self.assertEqual(parsed["package"], "banking.v1")
        self.assertEqual(len(parsed["enums"]), 1)
        self.assertEqual(len(parsed["messages"]), 2)
        
        acct_msg = [m for m in parsed["messages"] if m["name"] == "Account"][0]
        tags_field = [f for f in acct_msg["fields"] if f["name"] == "tags"][0]
        self.assertTrue(tags_field["repeated"])

        self.assertEqual(len(parsed["services"]), 1)
        self.assertEqual(parsed["services"][0]["rpcs"][0]["name"], "Transfer")

    # ─────────────────────────────────────────────────────────────
    # 4. SCXML STATECHARTS & MERMAID GENERATOR
    # ─────────────────────────────────────────────────────────────

    def test_parse_scxml_and_mermaid(self):
        scxml_content = """
<scxml name="OrderFSM" initial="Pending" version="1.0" datamodel="ecmascript">
  <state id="Pending">
    <transition event="PAY" target="Processing" cond="amount &gt; 0"/>
    <transition event="CANCEL" target="Cancelled"/>
  </state>
  <state id="Processing">
    <transition event="FULFILL" target="Shipped"/>
    <transition event="ERROR" target="Failed"/>
  </state>
  <final id="Shipped"/>
  <final id="Cancelled"/>
  <final id="Failed"/>
</scxml>
"""
        parsed = parse_scxml(scxml_content, filepath="order_fsm.scxml")
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["name"], "OrderFSM")
        self.assertEqual(parsed["initial_state"], "Pending")
        self.assertEqual(parsed["state_count"], 5)
        self.assertEqual(parsed["transition_count"], 4)

        mermaid = parsed["mermaid"]
        self.assertIn("stateDiagram-v2", mermaid)
        self.assertIn("[*] --> Pending", mermaid)
        self.assertIn("Pending --> Processing : PAY [amount > 0]", mermaid)
        self.assertIn("Shipped --> [*]", mermaid)

    # ─────────────────────────────────────────────────────────────
    # 5. CEL INVARIANTS EVALUATOR
    # ─────────────────────────────────────────────────────────────

    def test_evaluate_cel_arithmetic_and_comparisons(self):
        ctx = {"account": {"balance": 250.0, "limit": 500.0}}
        self.assertTrue(evaluate_cel_expression("account.balance >= 0.0", ctx))
        self.assertTrue(evaluate_cel_expression("account.balance < account.limit", ctx))
        self.assertTrue(evaluate_cel_expression("account.balance + 50.0 == 300.0", ctx))
        self.assertFalse(evaluate_cel_expression("account.balance > 1000.0", ctx))

    def test_evaluate_cel_logical_operators(self):
        ctx = {"user": {"active": True, "age": 28, "role": "admin"}}
        self.assertTrue(evaluate_cel_expression("user.active && user.age >= 18", ctx))
        self.assertTrue(evaluate_cel_expression("user.age < 10 || user.role == 'admin'", ctx))
        self.assertTrue(evaluate_cel_expression("!user.age == false", ctx))
        self.assertTrue(evaluate_cel_expression("!(user.age < 18)", ctx))
        self.assertFalse(evaluate_cel_expression("user.active && user.age < 18", ctx))

    def test_evaluate_cel_string_and_container_methods(self):
        ctx = {
            "req": {"path": "/api/v1/auth/login", "scopes": ["read", "write", "admin"]},
            "name": "SuperAdminUser"
        }
        self.assertTrue(evaluate_cel_expression("req.path.startsWith('/api/v1')", ctx))
        self.assertTrue(evaluate_cel_expression("req.path.endsWith('login')", ctx))
        self.assertTrue(evaluate_cel_expression("req.path.contains('auth')", ctx))
        self.assertTrue(evaluate_cel_expression("'admin' in req.scopes", ctx))
        self.assertTrue(evaluate_cel_expression("size(req.scopes) == 3", ctx))
        self.assertFalse(evaluate_cel_expression("'superuser' in req.scopes", ctx))

    def test_validate_cel_invariants_pass_fail(self):
        rules = [
            {"name": "non_negative_balance", "rule": "account.balance >= 0", "severity": "CRITICAL"},
            {"name": "allowed_currency", "rule": "account.currency in ['USD', 'EUR', 'GBP']", "severity": "ERROR"},
            {"name": "active_user", "rule": "user.is_active == true", "severity": "WARN"}
        ]
        
        valid_ctx = {
            "account": {"balance": 100, "currency": "USD"},
            "user": {"is_active": True}
        }
        res_pass = validate_cel_invariants(rules, valid_ctx)
        self.assertTrue(res_pass["valid"])
        self.assertEqual(res_pass["passed_count"], 3)
        self.assertEqual(res_pass["failed_count"], 0)

        invalid_ctx = {
            "account": {"balance": -50, "currency": "XYZ"},
            "user": {"is_active": False}
        }
        res_fail = validate_cel_invariants(rules, invalid_ctx)
        self.assertFalse(res_fail["valid"])
        self.assertEqual(res_fail["failed_count"], 3)
        self.assertIn("Violation of invariant", res_fail["results"][0]["error"])

    def test_validate_cel_preconditions(self):
        rules = [
            {
                "name": "vip_deposit_limit",
                "precondition": "user.is_vip == true",
                "rule": "tx.amount >= 1000",
                "severity": "ERROR"
            }
        ]
        non_vip_ctx = {"user": {"is_vip": False}, "tx": {"amount": 50}}
        res = validate_cel_invariants(rules, non_vip_ctx)
        self.assertTrue(res["valid"])
        self.assertEqual(res["results"][0]["status"], "SKIPPED_PRECONDITION")

    # ─────────────────────────────────────────────────────────────
    # 6. SCANNER, PROMPT BUILDER & DOCUSAURUS EXPORTER
    # ─────────────────────────────────────────────────────────────

    def test_scan_contracts_and_export_docusaurus(self):
        with tempfile.TemporaryDirectory() as tmp_repo, tempfile.TemporaryDirectory() as tmp_docs:
            rp = Path(tmp_repo)
            schemas_dir = rp / "schemas"
            schemas_dir.mkdir()

            # Write sample contracts
            (schemas_dir / "api.openapi.yaml").write_text("""
openapi: 3.0.0
info:
  title: Vault API
  version: 1.0.0
paths:
  /secrets:
    get:
      summary: List Secrets
      responses:
        '200':
          description: OK
""", encoding="utf-8")

            (schemas_dir / "types.fbs").write_text("""
namespace Storage;
table SecretItem { key:string (required); value:string; }
root_type SecretItem;
""", encoding="utf-8")

            (schemas_dir / "auth.scxml").write_text("""
<scxml name="AuthFSM" initial="LoggedOut">
  <state id="LoggedOut">
    <transition event="LOGIN" target="LoggedIn"/>
  </state>
  <final id="LoggedIn"/>
</scxml>
""", encoding="utf-8")

            (schemas_dir / "invariants.yaml").write_text("""
invariants:
  - name: positive_key_length
    rule: "size(secret.key) > 0"
    severity: CRITICAL
""", encoding="utf-8")

            # Scan
            catalog = scan_and_parse_contracts(str(rp))
            self.assertEqual(catalog["summary"]["openapi_count"], 1)
            self.assertEqual(catalog["summary"]["flatbuffers_count"], 1)
            self.assertEqual(catalog["summary"]["statecharts_count"], 1)
            self.assertEqual(catalog["summary"]["cel_invariants_count"], 1)

            # Prompt block
            prompt_block = format_contracts_prompt_block(str(rp))
            self.assertIn("Vault API", prompt_block)
            self.assertIn("SecretItem", prompt_block)
            self.assertIn("AuthFSM", prompt_block)
            self.assertIn("positive_key_length", prompt_block)

            # Docusaurus Export
            export_res = export_to_docusaurus(catalog, str(tmp_docs))
            self.assertTrue(export_res["success"])
            self.assertGreaterEqual(export_res["exported_files_count"], 5)
            
            contracts_path = Path(export_res["contracts_dir"])
            self.assertTrue((contracts_path / "_category_.json").exists())
            self.assertTrue((contracts_path / "index.md").exists())
            self.assertTrue((contracts_path / "openapi" / "vault_api.md").exists())
            self.assertTrue((contracts_path / "flatbuffers" / "types_fbs.md").exists())
            self.assertTrue((contracts_path / "statecharts" / "authfsm.md").exists())
            self.assertTrue((contracts_path / "invariants" / "overview.md").exists())

    # ─────────────────────────────────────────────────────────────
    # 7. LOOP ENGINE PRE-FLIGHT INTEGRATION
    # ─────────────────────────────────────────────────────────────

    def test_scanner_does_not_misclassify_tsconfig_as_openapi(self):
        """Regression: files that merely contain a 'paths' field (tsconfig.json,
        launchSettings.json) must NOT be recorded as OpenAPI specifications."""
        with tempfile.TemporaryDirectory() as tmp:
            rp = Path(tmp)
            (rp / "tsconfig.json").write_text(json.dumps({
                "compilerOptions": {
                    "baseUrl": ".",
                    "paths": {"@app/*": ["src/app/*"], "@lib/*": ["src/lib/*"]}
                }
            }), encoding="utf-8")
            (rp / "launchSettings.json").write_text(json.dumps({
                "profiles": {"http": {"applicationUrl": "http://localhost:5000"}}
            }), encoding="utf-8")
            # A genuine spec that MUST still be detected.
            (rp / "openapi.json").write_text(json.dumps({
                "openapi": "3.0.0",
                "info": {"title": "Real API", "version": "1.0.0"},
                "paths": {"/health": {"get": {"responses": {"200": {"description": "ok"}}}}}
            }), encoding="utf-8")

            catalog = scan_and_parse_contracts(str(rp))
            titles = [s.get("title") for s in catalog["openapi"]]
            self.assertEqual(catalog["summary"]["openapi_count"], 1, f"Over-matched: {titles}")
            self.assertIn("Real API", titles)

    def test_loop_engine_preflight_brief_contains_contracts_section(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as tmp_repo:
                rp = Path(tmp_repo)
                (rp / "invariants.yaml").write_text("invariants:\n  - name: check_rule\n    rule: 'x > 0'", encoding="utf-8")
                
                with patch("swarm.loop_engine.query_gemini", new_callable=AsyncMock) as mock_gemini, \
                     patch("swarm.loop_engine.fetch_latest_doc_context", return_value="Context7 Doc Snippet"):
                    mock_gemini.return_value = "# Pre-Flight Research Brief: Build Engine\n## 1. Summary\nDetails"
                    
                    brief_res = await run_preflight_research("Build Engine", str(rp), "Repo Context Block")
                    self.assertIn("### 📜 Universal Contract Invariants & Schemas", brief_res["content"])
                    self.assertIn("check_rule", brief_res["content"])

        asyncio.run(run_test())


class TestServerContractsEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start server on ephemeral port (port 0)
        cls.httpd = HTTPServer(('127.0.0.1', 0), SwarmHandler)
        cls.port = cls.httpd.server_address[1]
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _req(self, path, method="GET", data=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        headers = {"Content-Type": "application/json"} if data is not None else {}
        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_contracts_api_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp_repo, tempfile.TemporaryDirectory() as tmp_docs:
            rp = Path(tmp_repo)
            (rp / "invariants.yaml").write_text("""
invariants:
  - name: positive_balance
    rule: "account.balance >= 0"
    severity: CRITICAL
""", encoding="utf-8")

            # 1. GET /api/contracts/catalog
            status, catalog = self._req(f"/api/contracts/catalog?repo_path={rp}")
            self.assertEqual(status, 200)
            self.assertIn("cel_invariants", catalog)
            self.assertEqual(len(catalog["cel_invariants"]), 1)

            # 2. POST /api/contracts/validate (Pass)
            status, val_pass = self._req("/api/contracts/validate", method="POST", data={
                "repo_path": str(rp),
                "context": {"account": {"balance": 500}}
            })
            self.assertEqual(status, 200)
            self.assertTrue(val_pass["valid"])
            self.assertEqual(val_pass["passed_count"], 1)

            # 3. POST /api/contracts/validate (Fail)
            status, val_fail = self._req("/api/contracts/validate", method="POST", data={
                "repo_path": str(rp),
                "context": {"account": {"balance": -100}}
            })
            self.assertEqual(status, 200)
            self.assertFalse(val_fail["valid"])
            self.assertEqual(val_fail["failed_count"], 1)

            # 4. POST /api/contracts/export_docusaurus
            status, exp_res = self._req("/api/contracts/export_docusaurus", method="POST", data={
                "repo_path": str(rp),
                "output_dir": str(tmp_docs)
            })
            self.assertEqual(status, 200)
            self.assertTrue(exp_res["success"])
            self.assertGreaterEqual(exp_res["exported_files_count"], 2)


if __name__ == "__main__":
    unittest.main()