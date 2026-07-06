import http from "node:http";

const port = Number(process.env.PORT || 3000);
const token = process.env.WEB_TO_CODEX_TOKEN || "";

const body = JSON.stringify({ prompt: "Return a short mock response." });

const request = http.request(
  {
    hostname: "127.0.0.1",
    port,
    path: "/api/codex",
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Content-Length": Buffer.byteLength(body),
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    }
  },
  (response) => {
    let data = "";
    response.setEncoding("utf8");
    response.on("data", (chunk) => {
      data += chunk;
    });
    response.on("end", () => {
      console.log(`status=${response.statusCode}`);
      console.log(data);
      if (response.statusCode !== 200) process.exitCode = 1;
    });
  }
);

request.on("error", (error) => {
  console.error(error.message);
  process.exitCode = 1;
});

request.end(body);
