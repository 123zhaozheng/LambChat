# Codebase Analysis Priority
- ALWAYS use codebase-memory-mcp tools (search_graph, trace_path, get_code_snippet) to search the codebase first
- Fallback to standard Grep/Glob/Read only if MCP returns insufficient results
- Use list_projects first to get the exact project name before querying