const { app, BrowserWindow, screen } = require('electron');

let mainWindow;

app.whenReady().then(() => {
    // Pega o tamanho da tela principal do seu monitor
    const primaryDisplay = screen.getPrimaryDisplay();
    const { width, height } = primaryDisplay.bounds;

    mainWindow = new BrowserWindow({
        width: 400,
        height: 600,
        x: width - 450, // Posiciona o pet perto do canto inferior direito da tela
        y: height - 650,
        transparent: true,    // Fundo transparente
        frame: false,         // Sem barra de título, sem bordas
        alwaysOnTop: true,    // Fica sempre por cima dos outros programas
        skipTaskbar: true,    // Não aparece na barra de tarefas/painel do BigLinux
        resizable: false,     // Impede redimensionamento manual
        type: 'toolbar',      // Dica para gerenciadores de janela do Linux entenderem que é um widget flutuante
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false
        }
    });

    // IMPORTANTE:
    // Se você quiser que o pet seja APENAS visual e o mouse "atravesse" ele para clicar no que está atrás, 
    // descomente a linha abaixo. (Se quiser clicar nele ou arrastá-lo, deixe comentada):
    // mainWindow.setIgnoreMouseEvents(true);

    mainWindow.loadURL('http://127.0.0.1:8765/o/5kt9GMi9yv-NFTAo/');

    // Garante que o pet flutue acima de tudo no ambiente KDE Plasma do BigLinux
    mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
