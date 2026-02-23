package eapsdk

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

type ClientConfig struct {
	BaseURL       string
	APIKey        string
	Model         string
	Timeout       time.Duration
	HTTPClient    *http.Client
}

type Client struct {
	baseURL    string
	apiKey     string
	model      string
	httpClient *http.Client
	timeout    time.Duration
}

func NewClient(config ClientConfig) *Client {
	timeout := config.Timeout
	if timeout <= 0 {
		timeout = 30 * time.Second
	}

	httpClient := config.HTTPClient
	if httpClient == nil {
		httpClient = &http.Client{}
	}

	return &Client{
		baseURL:    strings.TrimRight(config.BaseURL, "/"),
		apiKey:     config.APIKey,
		model:      config.Model,
		httpClient: httpClient,
		timeout:    timeout,
	}
}

func (c *Client) Chat(ctx context.Context, request ChatRequest) (*ChatResponse, error) {
	if request.Model == "" && c.model != "" {
		request.Model = c.model
	}
	var response ChatResponse
	if err := c.postJSON(ctx, "/v1/eap/chat", request, &response); err != nil {
		return nil, err
	}
	return &response, nil
}

func (c *Client) GenerateMacro(ctx context.Context, request GenerateMacroRequest) (*GenerateMacroResponse, error) {
	var response GenerateMacroResponse
	if err := c.postJSON(ctx, "/v1/eap/macro/generate", request, &response); err != nil {
		return nil, err
	}
	return &response, nil
}

func (c *Client) ExecuteMacro(ctx context.Context, request ExecuteMacroRequest) (*ExecuteMacroResponse, error) {
	var response ExecuteMacroResponse
	if err := c.postJSON(ctx, "/v1/eap/macro/execute", request, &response); err != nil {
		return nil, err
	}
	return &response, nil
}

func (c *Client) postJSON(ctx context.Context, path string, requestBody interface{}, responseBody interface{}) error {
	requestBytes, err := json.Marshal(requestBody)
	if err != nil {
		return fmt.Errorf("marshal request: %w", err)
	}

	timeoutCtx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()

	request, err := http.NewRequestWithContext(
		timeoutCtx,
		http.MethodPost,
		c.baseURL+path,
		bytes.NewReader(requestBytes),
	)
	if err != nil {
		return fmt.Errorf("build request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/json")
	if c.apiKey != "" {
		request.Header.Set("Authorization", "Bearer "+c.apiKey)
	}

	response, err := c.httpClient.Do(request)
	if err != nil {
		return fmt.Errorf("request failed: %w", err)
	}
	defer response.Body.Close()

	bodyBytes, err := io.ReadAll(response.Body)
	if err != nil {
		return fmt.Errorf("read response body: %w", err)
	}

	if response.StatusCode < 200 || response.StatusCode >= 300 {
		var apiErr APIErrorPayload
		_ = json.Unmarshal(bodyBytes, &apiErr)
		if apiErr.Message == "" {
			apiErr.Message = string(bodyBytes)
		}
		if apiErr.Message == "" {
			apiErr.Message = response.Status
		}
		return fmt.Errorf("%s (%d)", apiErr.Message, response.StatusCode)
	}

	if err := json.Unmarshal(bodyBytes, responseBody); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}
	return nil
}
