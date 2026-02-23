# examples/test_state_manager.py
import json
import sys

from eap.protocol.state_manager import StateManager

def main():
    print("--- Starting State Manager Test ---\n")
    
    # 1. Simulate a massive tool output (e.g., scraping a heavy webpage)
    # We'll create a dummy HTML string that is roughly 50,000 characters long.
    dummy_html_chunk = "<div><p>Some noisy, unstructured data.</p></div>\n"
    massive_payload = dummy_html_chunk * 1000 
    
    # 2. The "Old Way" (Ping-Pong Loop)
    # The tool finishes and tries to send the whole thing back to the LLM.
    old_way_size_bytes = sys.getsizeof(massive_payload)
    print(f"[OLD WAY] The tool wants to return raw data to the LLM.")
    print(f"[OLD WAY] Size of payload hitting the context window: {old_way_size_bytes:,} bytes")
    print(f"[OLD WAY] Result: High latency, massive token consumption, potential context overflow.\n")

    # 3. The "New Way" (Stateful Protocol)
    print(f"--- Applying the Stateful Batched Protocol (SBP) ---\n")
    
    # Initialize our environment memory
    manager = StateManager()
    
    # The tool finishes, but instead of sending it to the LLM, it hands it to the StateManager
    pointer_response = manager.store_and_point(
        raw_data=massive_payload,
        summary="Successfully scraped the target website. Data is heavy and unstructured.",
        metadata={"source": "https://example.com/heavy-page", "status": 200}
    )
    
    # Calculate the size of the new payload going to the LLM
    new_way_size_bytes = sys.getsizeof(json.dumps(pointer_response))
    
    print(f"[NEW WAY] The tool stored the data locally and generated a pointer.")
    print(f"[NEW WAY] Payload sent to the LLM context window:\n")
    print(json.dumps(pointer_response, indent=2))
    print(f"\n[NEW WAY] Size of payload hitting the context window: {new_way_size_bytes:,} bytes")
    
    # 4. Show the math
    reduction = (1 - (new_way_size_bytes / old_way_size_bytes)) * 100
    print(f"\n--- Result ---")
    print(f"Token/Context Payload reduced by {reduction:.2f}%!")
    
    # 5. Prove the data is still there if a downstream tool needs it
    print("\n[VERIFICATION] Retrieving data via pointer...")
    retrieved_data = manager.retrieve(pointer_response["pointer_id"])
    print(f"[VERIFICATION] Data successfully retrieved. Length matches original: {len(retrieved_data) == len(massive_payload)}")

if __name__ == "__main__":
    main()
