# EAP TypeScript SDK

TypeScript SDK for EAP macro APIs based on `docs/sdk_contract.md`.

## Install

```bash
npm install
npm run build
```

## Usage

```ts
import { EAPClient } from "./dist/index.js";

const client = new EAPClient({
  baseUrl: "https://api.example.com",
  apiKey: process.env.EAP_API_KEY,
  model: "nemotron-orchestrator-8b",
});

const macro = await client.generateMacro({
  query: "Read README.md and summarize setup steps",
  agent_manifest: {
    read_local_file_abcd1234: {
      type: "object",
      properties: { file_path: { type: "string" } },
      required: ["file_path"],
    },
  },
});

const result = await client.executeMacro({ macro: macro.macro });
console.log(result.pointer_id, result.summary);
```
