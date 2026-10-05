import * as vscode from 'vscode';
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from 'vscode-languageclient/node';

let client: LanguageClient | undefined;

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

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  context.subscriptions.push(
    vscode.commands.registerCommand('odooDoctor.restart', async () => {
      await stopClient();
      await startClient();
    }),
    vscode.workspace.onDidChangeConfiguration(async (event) => {
      if (event.affectsConfiguration('odooDoctor')) {
        await stopClient();
        await startClient();
      }
    }),
  );
  await startClient();
}

export async function deactivate(): Promise<void> {
  await stopClient();
}
