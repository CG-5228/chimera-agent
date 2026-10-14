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

## Running it in the desktop app on Windows

These notes describe what was measured on 14 October 2026 with rea in Chimera Desktop 0.67.0.

Ghidra 12.1.4 requires Java 21 or newer (`application.java.min=21` in
`Ghidra/application.properties`). The official ZIP releases of both Ghidra and the JDK work without
an installer; the JDK MSI asks for administrator rights.

Put `GHIDRA_INSTALL_DIR` and `JAVA_HOME` in the rea server's own `env` entry in `mcp.json`, using
`--env GHIDRA_INSTALL_DIR=... --env JAVA_HOME=...` when adding it. Variables set elsewhere may not
reach the server process: the app's MCP pool starts the server with its own environment. The rea
session reported "GHIDRA_INSTALL_DIR is not configured" until both variables were in the server
entry.

rea took 6–13 seconds to start, while the app's **Test** button waits 12 seconds by default. Set
`--connect-timeout 60`; analyses can take a long time, so set `--call-timeout 600` as well. For
example:

```powershell
chimera mcp add rea --command npx --arg=-y --arg=--package=rea-agents@6.4.0 --arg=rea --arg=mcp --call-timeout 600 --connect-timeout 60 --env GHIDRA_INSTALL_DIR=C:\path\to\ghidra_12.1.4_PUBLIC --env JAVA_HOME=C:\path\to\jdk-21
```

The server exposes about 170 tools. Sending all their schemas at once made the first model step
need about 95k prompt tokens and stop with `context_stuck`. Turn on `CHIMERA_MCP_DEFER` so the model
looks tools up on demand.

Responses can be very large: one `rea_analyze_function` call returned about 430k characters, and
`rea_binary_session` returned about 240k characters. For routine work, prefer `rea_open_binary`,
`rea_binary_overview`, `rea_list_procedures`, and `rea_analyze_function` on a few procedures; avoid
`rea_binary_session`.

The server connects once when the app starts. Restart the app after adding it.

## Tools on unattended surfaces

The `rea` catalogue entry marks target-changing or code-executing tools in `exec_tools`. `chimera/governance/mcp_readonly.py` uses that list to build denied tool names for configured `rea` servers. It matches a server when its configured name is `rea`, or when the command line contains the entry's `rea-agents` match string, and prefixes each denied tool name with the configured server name.

The helper classifies these surfaces as unattended: names beginning with `app-messaging` or `cron:`, and the exact names `a2a`, `mcp`, and `github-issue`. On those surfaces, the matching `rea` tools are denied by name rather than offered for approval. Other surface names are not classified as unattended by this helper.

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
