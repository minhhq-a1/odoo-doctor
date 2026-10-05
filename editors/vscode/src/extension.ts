import * as vscode from 'vscode';
import {
  ExecuteCommandRequest,
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from 'vscode-languageclient/node';

// Command the language server registers (see odoo_doctor/lsp/server.py).
const SERVER_RESCAN_COMMAND = 'odooDoctor.rescan';

let client: LanguageClient | undefined;

// Start, stop and restart requests run one after another, so two quick events (a
// settings change and the restart command, say) can never start two servers.
let pending: Promise<void> = Promise.resolve();
function enqueue(task: () => Promise<void>): Promise<void> {
  pending = pending.then(task).catch(() => undefined);
  return pending;
}

async function startClient(): Promise<void> {
  const config = vscode.workspace.getConfiguration('odooDoctor');
  if (!config.get<boolean>('enable', true)) {
    return;
  }
  const command = config.get<string>('path', 'odoo-doctor');

  const serverOptions: ServerOptions = { command, args: ['lsp'] };
  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: 'file', language: 'python' },
      { scheme: 'file', language: 'xml' },
      { scheme: 'file', pattern: '**/*.csv' },
    ],
  };

  const next = new LanguageClient(
    'odooDoctor',
    'Odoo Doctor',
    serverOptions,
    clientOptions,
  );
  try {
    await next.start();
    client = next;
  } catch (error) {
    client = undefined;
    void vscode.window.showErrorMessage(
      `Odoo Doctor could not start "${command} lsp" (${String(error)}). ` +
        `Install it with: pip install 'odoo-doctor[lsp]', or set odooDoctor.path.`,
    );
  }
}

async function stopClient(): Promise<void> {
  const current = client;
  client = undefined;
  if (current) {
    await current.stop();
  }
}

function restart(): Promise<void> {
  return enqueue(async () => {
    await stopClient();
    await startClient();
  });
}

async function rescan(): Promise<void> {
  if (!client) {
    void vscode.window.showInformationMessage('Odoo Doctor is not running.');
    return;
  }
  await client.sendRequest(ExecuteCommandRequest.type, {
    command: SERVER_RESCAN_COMMAND,
  });
}

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  context.subscriptions.push(
    vscode.commands.registerCommand('odooDoctor.restart', restart),
    vscode.commands.registerCommand('odooDoctor.rescanWorkspace', rescan),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration('odooDoctor')) {
        void restart();
      }
    }),
  );
  await enqueue(startClient);
}

export function deactivate(): Promise<void> {
  return enqueue(stopClient);
}
