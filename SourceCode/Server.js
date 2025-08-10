


const http = require('http');
const PORT = 3000;

let players = {};
let containers = {}; // { "cx,cz": [ {x,y,z}, ... ] }

const CHUNK_SIZE = 50;
const CONTAINERS_PER_CHUNK = 5;
const MIN_DISTANCE = 5;

// Generate spaced container positions for a chunk
function generateContainersForChunk(cx, cz) {
  const positions = [];
  let tries = 0;
  const maxTries = 100;

  while (positions.length < CONTAINERS_PER_CHUNK && tries < maxTries) {
    const x = (cx * CHUNK_SIZE) + Math.random() * CHUNK_SIZE;
    const z = (cz * CHUNK_SIZE) + Math.random() * CHUNK_SIZE;
    let tooClose = false;

    for (const pos of positions) {
      const dist = Math.sqrt((x - pos.x) ** 2 + (z - pos.z) ** 2);
      if (dist < MIN_DISTANCE) {
        tooClose = true;
        break;
      }
    }

    if (!tooClose) {
      positions.push({ x, y: 0.5, z });
    }
    tries++;
  }

  return positions;
}

// Periodically generate containers for chunks around players
function updateContainers() {
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
      containers[key] = generateContainersForChunk(cx, cz);
    }
  });
}

setInterval(updateContainers, 5000);

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

        // Use client-sent ID
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
    if (req.url === '/containers') {
      // Return all container positions
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(containers));
    } else {
      // Return player positions
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
    }
  } else {
    res.writeHead(405);
    res.end('Method Not Allowed');
  }
});

server.listen(PORT, () => {
  console.log(`🟢 Server running at http://localhost:${PORT}`);
});
