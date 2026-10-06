# Language server and VS Code extension (experimental)

`odoo-doctor lsp` runs a [Language Server Protocol](https://microsoft.github.io/language-server-protocol/)
server on stdio, so any LSP editor can show Odoo Doctor findings and offer fixes. A VS Code
extension in [`editors/vscode`](../editors/vscode) wires it up.

> Status: **experimental** in 0.7.0. It is not covered by the
> [stability contract](stability.md) yet; flags, settings and behaviour may change.

## Install

```bash
uv tool install 'odoo-doctor[lsp]'     # or: pipx install 'odoo-doctor[lsp]'
```

Needs Python 3.10 or newer. On macOS the system `python3` / `pip3` from Xcode is 3.9, so
plain `pip3 install` fails with `No matching distribution found`; `uv tool install
--python 3.12 'odoo-doctor[lsp]'` fetches a suitable Python for you. Inside a virtualenv,
`pip install 'odoo-doctor[lsp]'` works too. Upgrade with `uv tool upgrade odoo-doctor`.
Check the install with `odoo-doctor --help` (there is no `--version` flag).

Without the extra, `odoo-doctor lsp` exits with code 3 and tells you what to install.

## What it does

- **Diagnostics** for the whole workspace folder: every finding `odoo-doctor scan` reports,
  as squiggles and in the Problems panel, with the rule name as the code and a link to its
  documentation.
- **Quick fixes** on a finding (lightbulb, Ctrl+. / Cmd+.):
  - *fix*: the deterministic auto-fix, when the rule has one (the same fixers as
    `odoo-doctor fix`);
  - *disable on this line*: adds `# odoo-doctor: disable=<rule>` above the line (an XML
    comment in XML files); an existing `disable=` comment above is extended;
  - *disable in this file*: adds `disable-file=<rule>` at the top (after a shebang or XML
    declaration);
  - *disable in odoo-doctor.toml*: adds the rule to `[ignore] rules` and rescans.
- **Command** `odooDoctor.rescan`: scan again now.

Configuration (addons paths, `[ignore]`, `[severity]`, plugins, ...) comes from
`odoo-doctor.toml` in the workspace folder, exactly as for the command line.

## How it behaves

- Analysis reads files **from disk**. Findings are computed when the workspace opens, when
  a file is **saved**, and on `odooDoctor.rescan`; not while you type. Quick fixes are
  applied to the editor buffer.
- **Unsaved edits:** a finding's line number comes from the last save. If the flagged line
  moved or changed in the buffer since then, the actions that depend on that line (the
  auto-fix and *disable on this line*) are not offered until you save; *disable in this
  file* and *disable in odoo-doctor.toml* always are.
- *Disable on this line* is offered only where a comment is safe: not inside a multi-line
  string, not after a backslash continuation, not inside an XML tag, and not in a file that
  cannot be tokenized.
- Each refresh scans the whole workspace folder, because cross-module rules need every
  addon. A scan takes roughly 0.06 s per addon. Scans never overlap; saves that arrive
  during a scan are merged into one rerun, and a failed scan is logged and does not stop
  the next one.
- Findings are published for every file in the project, not only the open ones, under the
  path the editor opened the folder with (so symlinked folders work). A folder nested in
  another workspace folder is covered by the outer one and not scanned twice; folders
  added or removed while the editor is open are picked up.
- Limitation: an addon that is a symlink pointing **outside** the workspace folder is
  scanned, but its diagnostics are published under the real path, so the editor may not
  show them on the file you opened through the link.
- The server only speaks LSP on stdout. Rule crashes are logged to stderr and do not stop
  the server.

## VS Code

Install **Odoo Doctor** (`MinhHong.odoo-doctor`, preview) from the Extensions view, or:

```bash
code --install-extension MinhHong.odoo-doctor
```

It also needs the server (see [Install](#install)). To build the
extension from source instead:

```bash
cd editors/vscode
npm ci
npm run package                      # odoo-doctor-<version>.vsix
code --install-extension odoo-doctor-*.vsix
```

Settings: `odooDoctor.enable` (default `true`) and `odooDoctor.path` (default
`odoo-doctor`; set it to the full path when the executable is in a virtualenv VS Code does
not see). Commands: *Odoo Doctor: Rescan workspace*, *Odoo Doctor: Restart language server*.

The extension does not run in an untrusted workspace (Restricted Mode): it launches
`odoo-doctor` on the folder, which reads that folder's configuration and plugins. Trust the
workspace to enable it.

## Other editors

Any client that can start `odoo-doctor lsp` over stdio works. Examples:

Neovim (0.10+):

```lua
vim.api.nvim_create_autocmd("FileType", {
  pattern = { "python", "xml" },
  callback = function(args)
    vim.lsp.start({
      name = "odoo-doctor",
      cmd = { "odoo-doctor", "lsp" },
      root_dir = vim.fs.root(args.buf, { "odoo-doctor.toml", "__manifest__.py", ".git" }),
    })
  end,
})
```

Helix (`languages.toml`; add `odoo-doctor` next to the language servers you already use):

```toml
[language-server.odoo-doctor]
command = "odoo-doctor"
args = ["lsp"]
```

## Troubleshooting

- *"could not start odoo-doctor lsp"*: the executable is not on VS Code's `PATH` or was
  installed without the extra. Run `odoo-doctor lsp` in a terminal; set `odooDoctor.path`.
  VS Code started from the Dock does not read your shell `PATH`, so an executable in
  `~/.local/bin` (where `uv tool` and `pipx` put it) may not be found: use the full path,
  e.g. `/Users/you/.local/bin/odoo-doctor`.
- *`pip install` says "No matching distribution found"*: your Python is older than 3.10
  (the Xcode `python3` on macOS is 3.9). Use `uv tool install` or `pipx` as above.
- *No findings*: check `odoo-doctor scan <folder>` on the same folder, and that
  `[ignore]` in `odoo-doctor.toml` does not exclude the files.
- *Stale findings after a branch switch*: run *Odoo Doctor: Rescan workspace*.
