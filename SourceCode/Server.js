
// Server.js

const http = require('http');
const PORT = 3000;

let players = {};
let containers = {}; // { "cx,cz": [ {x,y,z}, ... ] }
let coins = {};      // { "cx,cz": [ {x,y,z}, ... ] }

const CHUNK_SIZE = 50;
const CONTAINERS_PER_CHUNK = 5;
const COINS_PER_CHUNK = 1;  
const MIN_DISTANCE = 5;

// Generate spaced positions (for containers or coins)
function generatePositionsForChunk(cx, cz, count, yValue) {
  const positions = [];
  let tries = 0;
  while (positions.length < count && tries < 100) {
    const x = (cx * CHUNK_SIZE) + Math.random() * CHUNK_SIZE;
    const z = (cz * CHUNK_SIZE) + Math.random() * CHUNK_SIZE;
    if (!positions.some(pos => Math.hypot(x - pos.x, z - pos.z) < MIN_DISTANCE)) {
      positions.push({ x, y: yValue, z });
    }
    tries++;
  }
  return positions;
}

// Periodically generate containers & coins for chunks around players
function updateEntities() {
  const activeChunks = new Set();

  for (const id in players) {
    const p = players[id];
    const cx = Math.floor(p.x / CHUNK_SIZE);
    const cz = Math.floor(p.z / CHUNK_SIZE);

    for (let dx = -2; dx <= 2; dx++) {
      for (let dz = -2; dz <= 2; dz++) {
        activeChunks.add(`${cx + dx},${cz + dz}`);
      }
    }
  }

  activeChunks.forEach(key => {
    if (!containers[key]) {
      const [cx, cz] = key.split(',').map(Number);
      containers[key] = generatePositionsForChunk(cx, cz, CONTAINERS_PER_CHUNK, 0.5);
    }
    if (!coins[key]) {
      const [cx, cz] = key.split(',').map(Number);
      coins[key] = generatePositionsForChunk(cx, cz, COINS_PER_CHUNK, 1);
    }
  });
}

setInterval(updateEntities, 5000);

// Clean up disconnected players
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
        const id = typeof data.id === 'string' ? data.id : req.socket.remoteAddress.replace(/^.*:/, '');

        players[id] = {
          x: data.x,
          y: data.y,
          z: data.z,
          time: Date.now()
        };

        res.writeHead(200);
        res.end('Position Updated');
      } catch {
        res.writeHead(400);
        res.end('Invalid JSON');
      }
    });
  } 
  else if (req.method === 'GET') {
    if (req.url === '/containers') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(containers));
    }
    else if (req.url === '/coins') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(coins));
    }
    else {
      const result = {};
      for (const id in players) {
        result[id] = { x: players[id].x, y: players[id].y, z: players[id].z };
      }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(result));
    }
  } 
  else {
    res.writeHead(405);
    res.end('Method Not Allowed');
  }
});

server.listen(PORT, () => {
  console.log(`🟢 Server running at http://localhost:${PORT}`);
});
