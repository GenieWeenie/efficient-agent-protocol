# EAP Go SDK

Go SDK for EAP macro APIs based on `docs/sdk_contract.md`.

## Usage

```go
package main

import (
	"context"
	"fmt"
	"time"

	eapsdk "github.com/efficient-agent-protocol/sdk/go"
)

func main() {
	client := eapsdk.NewClient(eapsdk.ClientConfig{
		BaseURL: "https://api.example.com",
		APIKey:  "your-api-key",
		Model:   "nemotron-orchestrator-8b",
		Timeout: 30 * time.Second,
	})

	resp, err := client.GenerateMacro(context.Background(), eapsdk.GenerateMacroRequest{
		Query: "Read README.md and summarize setup steps",
		AgentManifest: map[string]interface{}{
			"read_local_file_abcd1234": map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"file_path": map[string]interface{}{"type": "string"},
				},
				"required": []string{"file_path"},
			},
		},
	})
	if err != nil {
		panic(err)
	}

	execResp, err := client.ExecuteMacro(context.Background(), eapsdk.ExecuteMacroRequest{Macro: resp.Macro})
	if err != nil {
		panic(err)
	}
	fmt.Println(execResp.PointerID, execResp.Summary)
}
```
