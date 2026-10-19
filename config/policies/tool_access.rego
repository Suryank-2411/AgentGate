package agentgateway.tool_access

# Default: deny all access
default allow = false

# Admins can access everything
allow {
    input.user.roles[_] == "admin"
}

# Developers can access non-destructive tools
allow {
    input.user.roles[_] == "developer"
    not deny
}

# Analysts can access database tools only
allow {
    input.user.roles[_] == "analyst"
    input.server_name == "database-query"
}

# Deny rules
deny {
    input.tool_name == "delete_file"
    not input.user.roles[_] == "admin"
}
