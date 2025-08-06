










// Server.js
const http = require('http');

let players = {};

const server = http.createServer((req, res) => {
  const ip = req.socket.remoteAddress.replace(/^.*:/, ''); // Extract IPv4
  if (req.method === 'POST') {
    let body = '';
    req.on('data', chunk => (body += chunk));
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        players[ip] = {
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
    for (const ip in players) {
      result[ip] = {
        x: players[ip].x,
        y: players[ip].y,
        z: players[ip].z
      };
    }

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(result));
  } else {
    res.writeHead(405);
    res.end('Method Not Allowed');
  }
});

const PORT = 3000;
server.listen(PORT, () => {
  console.log(`🟢 Server running at http://localhost:${PORT}`);
});
