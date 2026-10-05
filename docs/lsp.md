# Language server and VS Code extension (experimental)

`odoo-doctor lsp` runs a [Language Server Protocol](https://microsoft.github.io/language-server-protocol/)
server on stdio, so any LSP editor can show Odoo Doctor findings and offer fixes. A VS Code
extension in [`editors/vscode`](../editors/vscode) wires it up.

> Status: **experimental** in 0.7.0. It is not covered by the
> [stability contract](stability.md) yet; flags, settings and behaviour may change.

## Install

```bash
pip install 'odoo-doctor[lsp]'
```

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
- Each refresh scans the whole workspace folder, because cross-module rules need every
  addon. A scan takes roughly 0.06 s per addon. Scans never overlap; saves that arrive
  during a scan are merged into one rerun.
- Findings are published for every file in the project, not only the open ones.
- The server only speaks LSP on stdout. Rule crashes are logged to stderr and do not stop
  the server.

## VS Code

Build and install the extension from source (it is not published to the Marketplace yet):

```bash
cd editors/vscode
npm ci
npm run package                      # odoo-doctor-<version>.vsix
code --install-extension odoo-doctor-*.vsix
```

Settings: `odooDoctor.enable` (default `true`) and `odooDoctor.path` (default
`odoo-doctor`; set it to the full path when the executable is in a virtualenv VS Code does
not see). Commands: *Odoo Doctor: Rescan workspace*, *Odoo Doctor: Restart language server*.

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
- *No findings*: check `odoo-doctor scan <folder>` on the same folder, and that
  `[ignore]` in `odoo-doctor.toml` does not exclude the files.
- *Stale findings after a branch switch*: run *Odoo Doctor: Rescan workspace*.
