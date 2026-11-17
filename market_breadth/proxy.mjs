import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const RUNTIME_DIR = path.join(HERE, 'runtime');
const DATA_DIR = path.join(RUNTIME_DIR, 'data');
const SEED_DIR = path.join(HERE, 'seed-data');
const CORE_PORT = 3210;
const GATEWAY_PORT = Number(process.env.GATEWAY_PORT) || 3211;

fs.mkdirSync(DATA_DIR, { recursive: true });
for (const name of ['codes.json', 'daily.json', 'backtest-result.json']) {
  const source = path.join(SEED_DIR, name);
  const destination = path.join(DATA_DIR, name);
  if (!fs.existsSync(destination) && fs.existsSync(source)) {
    fs.copyFileSync(source, destination);
  }
}

let stopping = false;
const child = spawn(process.execPath, [path.join(RUNTIME_DIR, 'breadth.mjs')], {
  cwd: RUNTIME_DIR,
  env: { ...process.env, PORT: String(CORE_PORT) },
  stdio: 'inherit',
});

child.on('exit', (code, signal) => {
  if (!stopping) {
    console.error(`breadth core exited unexpectedly (code=${code}, signal=${signal})`);
    process.exit(code || 1);
  }
});

function jsonError(response, status, message) {
  const body = Buffer.from(JSON.stringify({ error: message }));
  response.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': String(body.length),
    'Cache-Control': 'no-store',
  });
  response.end(body);
}

function forwardState(response) {
  const upstream = http.get(
    { hostname: '127.0.0.1', port: CORE_PORT, path: '/api/state', timeout: 5000 },
    (upstreamResponse) => {
      const chunks = [];
      upstreamResponse.on('data', (chunk) => chunks.push(chunk));
      upstreamResponse.on('end', () => {
        const body = Buffer.concat(chunks);
        response.writeHead(upstreamResponse.statusCode || 502, {
          'Content-Type': 'application/json; charset=utf-8',
          'Content-Length': String(body.length),
          'Cache-Control': 'no-store',
        });
        response.end(body);
      });
    },
  );
  upstream.on('timeout', () => upstream.destroy(new Error('breadth core timed out')));
  upstream.on('error', () => jsonError(response, 503, 'market breadth service unavailable'));
}

const server = http.createServer((request, response) => {
  if (request.method === 'GET' && request.url === '/health') {
    const body = Buffer.from(JSON.stringify({ status: child.exitCode === null ? 'ok' : 'error' }));
    response.writeHead(child.exitCode === null ? 200 : 503, {
      'Content-Type': 'application/json; charset=utf-8',
      'Content-Length': String(body.length),
      'Cache-Control': 'no-store',
    });
    return response.end(body);
  }
  if (request.method === 'GET' && request.url === '/api/state') {
    return forwardState(response);
  }
  return jsonError(response, 404, 'not found');
});

server.listen(GATEWAY_PORT, '0.0.0.0', () => {
  console.log(`market breadth internal gateway listening on ${GATEWAY_PORT}`);
});

function shutdown(signal) {
  if (stopping) return;
  stopping = true;
  server.close(() => {
    if (child.exitCode === null) child.kill(signal);
  });
  setTimeout(() => process.exit(0), 5000).unref();
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
