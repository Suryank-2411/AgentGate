package agentgateway.payload_guard

# Default: allow payloads
default allow = true

# Block dangerous SQL operations
deny {
    input.tool_name == "execute_query"
    contains(lower(input.arguments.sql), "drop")
}

deny {
    input.tool_name == "execute_query"
    contains(lower(input.arguments.sql), "truncate")
}

deny {
    input.tool_name == "execute_query"
    contains(lower(input.arguments.sql), "delete from")
}

# Block path traversal
deny {
    some key
    input.arguments[key]
    contains(input.arguments[key], "../")
}
