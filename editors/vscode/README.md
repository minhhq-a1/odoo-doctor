# Odoo Doctor for VS Code (experimental)

Health findings for Odoo custom addons, in your editor. This extension starts the
`odoo-doctor lsp` language server and shows what `odoo-doctor scan` would report:

- findings as diagnostics (squiggles and the Problems panel), each with a link to the
  rule's documentation;
- quick fixes (Ctrl+. / Cmd+.): apply the deterministic auto-fix when the rule has one, or
  disable the rule on this line, in this file, or in `odoo-doctor.toml`.

## Requirements

Install Odoo Doctor with the language server extra (Python 3.10 or newer):

```bash
uv tool install 'odoo-doctor[lsp]'     # or: pipx install 'odoo-doctor[lsp]'
```

On macOS the system `pip3` is Python 3.9 and cannot install it; use `uv` or `pipx` as
above. The extension runs `odoo-doctor lsp`. If VS Code cannot find the executable (it
does not read your shell `PATH` when started from the Dock), set `odooDoctor.path` to its
full path, e.g. `~/.local/bin/odoo-doctor`.

## Settings and commands

| Setting | Default | Meaning |
|---|---|---|
| `odooDoctor.enable` | `true` | Run the language server for this workspace |
| `odooDoctor.path` | `odoo-doctor` | Path to the `odoo-doctor` executable |

Commands: **Odoo Doctor: Rescan workspace**, **Odoo Doctor: Restart language server**.

Project settings (addons paths, ignores, severity, plugins) come from `odoo-doctor.toml`,
exactly as for the command line.

## Good to know

- Analysis reads files from disk, so findings refresh when the workspace opens and when
  you **save** a file, not while typing.
- Each refresh scans the whole workspace folder (cross-module rules need every addon).
- This is the first, experimental release of the language server. See
  [docs/lsp.md](https://github.com/minhhq-a1/odoo-doctor/blob/main/docs/lsp.md).

## Build from source

```bash
cd editors/vscode
npm ci
npm run package        # writes odoo-doctor-<version>.vsix
code --install-extension odoo-doctor-*.vsix
```
