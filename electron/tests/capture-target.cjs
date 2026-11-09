const { app, BrowserWindow } = require('electron');
app.whenReady().then(async () => {
  // Keep original data inside the isolated process, never in test logs.

  const win = new BrowserWindow({
    width: 640,
    height: 320,
    title: 'Sado isolated input verification',
  });
  await win.loadURL(
    'data:text/html,<title>Sado isolated input verification</title><textarea autofocus style="width:90vw;height:70vh" aria-label="Test destination"></textarea>',
  );
});
app.on('window-all-closed', () => app.quit());
