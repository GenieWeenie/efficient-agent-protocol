def reverse_text(text: str) -> str:
    return text[::-1]


REVERSE_TEXT_SCHEMA = {
    "name": "reverse_text",
    "description": "Reverses the provided text.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "minLength": 1,
                "description": "Text to reverse.",
            }
        },
        "required": ["text"],
        "additionalProperties": False,
    },
}


def get_plugin_manifest() -> dict:
    return {
        "plugin_name": "sample_plugin",
        "version": "0.1.0",
        "tools": [
            {
                "name": "reverse_text",
                "function": reverse_text,
                "schema": REVERSE_TEXT_SCHEMA,
            }
        ],
    }


__all__ = ["get_plugin_manifest", "reverse_text", "REVERSE_TEXT_SCHEMA"]
