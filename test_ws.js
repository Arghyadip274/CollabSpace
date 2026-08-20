const WebSocket = require('ws');
const ws = new WebSocket('wss://collabspace-backend-c26l.onrender.com/realtime/ws?token=invalid_token');

ws.on('open', () => {
    console.log('Connected!');
    process.exit(0);
});

ws.on('error', (err) => {
    console.log('Error:', err.message);
    process.exit(1);
});

ws.on('close', (code, reason) => {
    console.log('Closed:', code, reason.toString());
    process.exit(1);
});
