import assert from "node:assert/strict";
import test from "node:test";

import { createEAPRuntimeClient, normalizeBaseUrl } from "../index.js";

test("normalizeBaseUrl strips trailing slashes", () => {
  assert.equal(normalizeBaseUrl("http://127.0.0.1:8080///"), "http://127.0.0.1:8080");
});

test("runEapWorkflow posts macro payload with auth header", async () => {
  const calls = [];
  const fetchStub = async (url, options) => {
    calls.push({ url, options });
    return new Response(
      JSON.stringify({ request_id: "req_1", pointer_id: "ptr_1", summary: "ok" }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  };
  const client = createEAPRuntimeClient(
    { baseUrl: "http://localhost:9000", apiKey: "secret", timeoutMs: 5000 },
    fetchStub,
  );
  const macro = { steps: [{ step_id: "s1", tool_name: "echo", arguments: {} }] };
  const response = await client.runEapWorkflow(macro);

  assert.equal(response.pointer_id, "ptr_1");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://localhost:9000/v1/eap/macro/execute");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.headers.Authorization, "Bearer secret");
  assert.deepEqual(JSON.parse(calls[0].options.body), { macro });
});

test("getEapRunStatus and getEapPointerSummary use expected GET paths", async () => {
  const calledUrls = [];
  const fetchStub = async (url) => {
    calledUrls.push(url);
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  const client = createEAPRuntimeClient({ baseUrl: "http://localhost:9000" }, fetchStub);

  await client.getEapRunStatus("run_123");
  await client.getEapPointerSummary("ptr_abc");

  assert.deepEqual(calledUrls, [
    "http://localhost:9000/v1/eap/runs/run_123",
    "http://localhost:9000/v1/eap/pointers/ptr_abc/summary",
  ]);
});

test("request errors include upstream message", async () => {
  const fetchStub = async () =>
    new Response(JSON.stringify({ error_type: "not_found", message: "missing run" }), {
      status: 404,
      headers: { "content-type": "application/json" },
    });
  const client = createEAPRuntimeClient({ baseUrl: "http://localhost:9000" }, fetchStub);

  await assert.rejects(
    async () => client.getEapRunStatus("run_missing"),
    (error) => error instanceof Error && error.message === "missing run",
  );
});
