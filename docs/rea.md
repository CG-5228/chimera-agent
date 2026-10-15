# rea reverse-engineering MCP server

The MCP catalogue offers **rea** (`rea-agents`), a server for inspecting binaries, processes, and applications through reverse-engineering tools. The catalogue pins the package to **`rea-agents@6.4.0`**; the command uses that exact version rather than a floating `latest` tag. See the [`rea-agents` package](https://www.npmjs.com/package/rea-agents).

## Prerequisites

The catalogue declares these requirements and options:

- **Node.js 22 or newer**, because the server runs through `npx`.
- **Ghidra**, which is free. The catalogue states that Ghidra requires both `GHIDRA_INSTALL_DIR` and `JAVA_HOME` to run.
- **IDA, Hopper, and JEB** are optional paid engines. They are opt-in through environment variables.

## Add and test the server

Use the command and arguments from the `rea` catalogue entry:

```bash
chimera mcp add rea --command npx --arg=-y --arg=--package=rea-agents@6.4.0 --arg=rea --arg=mcp
```

The command saves the server configuration; it does not connect to the server. Live-test the configured server and inspect the tools it exposes with:

```bash
chimera mcp test rea
```

This test connects to the server, lists its tools, and closes the session. To make configured MCP servers available through the shared pool, enable autoload with `CHIMERA_MCP_AUTOLOAD=1`. Autoload is off by default.

## Target-changing tools and alerts

The `rea` catalogue entry marks target-changing or code-executing tools in `exec_tools`. Those tools remain available on every surface, including messaging, cron, A2A, MCP, and GitHub-issue jobs; they are not removed simply because a surface cannot request approval. The matching uses the configured server name (`rea`) or the catalogue's `rea-agents` command match, and prefixes tool names with the configured server name.

Each invocation of a matching tool records a `rea_tool_executed` event in `audit.jsonl`, including the tool name, surface, and UTC timestamp. Chimera also sends an owner notification through the configured approval webhook; when no webhook is configured, the durable audit event remains available in the existing audit log. This is additional to any approval governance a surface already provides.

The `exec_tools` names are:

```text
annotate_native_function
capture_browser_scenario
capture_electron_scenario
capture_native_ui_scenario
capture_process_scenario
close_frida_session
install_adb_package
instrument_with_frida
load_frida_script
observe_native_calls
observe_web_execution
push_adb_file
resume_frida_session
set_address_name
set_addresses_names
set_bookmark
set_comment
set_inline_comment
start_adb_activity
start_adb_app
start_frida_session
stop_adb_app
uninstall_adb_package
unload_frida_script
unset_bookmark
```

## Long analyses

`call_timeout` in `mcp.json` sets the per-call timeout in seconds. MCP calls default to 120 seconds when the field is absent. For analyses that take longer, set a larger value in the `rea` server entry, for example:

```json
[
  {
    "name": "rea",
    "command": "npx",
    "args": ["-y", "--package=rea-agents@6.4.0", "rea", "mcp"],
    "call_timeout": 600
  }
]
```

The value shown is an example configuration, not a catalogue default.
