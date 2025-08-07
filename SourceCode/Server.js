






// Server.js
const http = require('http');
const PORT = 3000;

let players = {};

// Clean up disconnected players every 5 seconds
setInterval(() => {
  const now = Date.now();
  for (const id in players) {
    if (now - players[id].time > 5000) {
      delete players[id];
    }
  }
}, 1000);

const server = http.createServer((req, res) => {
  if (req.method === 'POST') {
    let body = '';
    req.on('data', chunk => (body += chunk));
    req.on('end', () => {
      try {
        const data = JSON.parse(body);

        // ✅ Use client-sent ID (IP or UUID)
        const id = typeof data.id === 'string' ? data.id : req.socket.remoteAddress.replace(/^.*:/, '');

        players[id] = {
          x: data.x,
          y: data.y,
          z: data.z,
          time: Date.now()
        };

        res.writeHead(200);
        res.end('Position Updated');
      } catch (e) {
        res.writeHead(400);
        res.end('Invalid JSON');
      }
    });
  } else if (req.method === 'GET') {
    const result = {};
    for (const id in players) {
      result[id] = {
        x: players[id].x,
        y: players[id].y,
        z: players[id].z
      };
    }

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(result));
  } else {
    res.writeHead(405);
    res.end('Method Not Allowed');
  }
});

server.listen(PORT, () => {
  console.log(`🟢 Server running at http://localhost:${PORT}`);
});