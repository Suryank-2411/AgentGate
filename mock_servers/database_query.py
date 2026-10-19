"""Mock Database Query MCP Server for testing and demo."""

from __future__ import annotations

import argparse
import json

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

mcp = MCPServer("DatabaseQuery", instructions="A mock database query tool for testing.")

# Fake databases
MOCK_TABLES = {
    "app_db": {
        "users": {
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "username", "type": "VARCHAR(255)"},
                {"name": "email", "type": "VARCHAR(255)"},
                {"name": "created_at", "type": "TIMESTAMP"},
            ],
            "rows": [
                {"id": 1, "username": "alice", "email": "alice@example.com"},
                {"id": 2, "username": "bob", "email": "bob@example.com"},
                {"id": 3, "username": "charlie", "email": "charlie@example.com"},
            ],
        },
        "orders": {
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "user_id", "type": "INTEGER"},
                {"name": "total", "type": "DECIMAL(10,2)"},
                {"name": "status", "type": "VARCHAR(50)"},
            ],
            "rows": [
                {"id": 101, "user_id": 1, "total": 59.99, "status": "completed"},
                {"id": 102, "user_id": 2, "total": 129.50, "status": "pending"},
            ],
        },
    }
}


@mcp.tool(
    title="Execute a SQL query",
    annotations=ToolAnnotations(read_only_hint=False, open_world_hint=False),
)
def execute_query(sql: str, database: str = "app_db") -> str:
    """Execute a SQL query against the specified database and return results."""
    if database not in MOCK_TABLES:
        raise ToolError(f"Database not found: {database}")

    sql_lower = sql.strip().lower()
    if sql_lower.startswith("select"):
        # Mock: return first matching table's rows
        for table_name, table_data in MOCK_TABLES[database].items():
            if table_name in sql_lower:
                return json.dumps({
                    "query": sql,
                    "database": database,
                    "rows": table_data["rows"],
                    "row_count": len(table_data["rows"]),
                })
        return json.dumps({
            "query": sql,
            "database": database,
            "rows": [],
            "row_count": 0,
            "message": "No matching table found in mock data",
        })

    # For non-SELECT, return an "affected rows" response
    return json.dumps({
        "query": sql,
        "database": database,
        "affected_rows": 0,
        "message": "Query executed (mock)",
    })


@mcp.tool(
    title="List database tables",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
def list_tables(database: str = "app_db") -> str:
    """List all tables in the specified database."""
    if database not in MOCK_TABLES:
        raise ToolError(f"Database not found: {database}")
    tables = list(MOCK_TABLES[database].keys())
    return json.dumps({"database": database, "tables": tables, "count": len(tables)})


@mcp.tool(
    title="Describe table schema",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
def describe_table(table: str, database: str = "app_db") -> str:
    """Describe the schema of a table in the specified database."""
    if database not in MOCK_TABLES:
        raise ToolError(f"Database not found: {database}")
    if table not in MOCK_TABLES[database]:
        raise ToolError(f"Table not found: {table} in {database}")
    columns = MOCK_TABLES[database][table]["columns"]
    return json.dumps({"database": database, "table": table, "columns": columns})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mock Database Query MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
    )
    parser.add_argument("--port", type=int, default=9002)
    args = parser.parse_args()

    if args.transport == "streamable-http":
        mcp.run(transport="streamable-http", host="0.0.0.0", port=args.port)
    else:
        mcp.run()
