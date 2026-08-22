import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { classifyRequestOrigin } from "../app/lib/integration-api/origin-safety.mjs";

const base = {
  requestUrl: "http://localhost:3100/api/v3/assess",
  host: "127.0.0.1:3100",
  forwardedHost: null,
  forwardedProto: null,
  vercel: null,
};

test("request URL and strict Host candidates both permit genuine same-origin posts", () => {
  assert.equal(classifyRequestOrigin({ ...base, origin: "http://localhost:3100" }), "allowed");
  assert.equal(classifyRequestOrigin({ ...base, origin: "http://127.0.0.1:3100" }), "allowed");
  assert.equal(classifyRequestOrigin({ ...base, host: null, origin: "http://localhost:3100" }), "allowed");
});

test("foreign, opaque and structurally invalid origins fail closed", () => {
  for (const origin of [
    "",
    "null",
    "http://user:pass@127.0.0.1:3100",
    "http://127.0.0.1:3100/",
    "http://127.0.0.1:3100/path",
    "http://127.0.0.1:3100?query=1",
    "http://127.0.0.1:3100#fragment",
    "http://local\thost:3100",
    "http://local\rhost:3100",
    "http://local\nhost:3100",
    "ftp://127.0.0.1:3100",
    "http://127.0.0.1:3100,https://evil.example",
  ]) assert.equal(classifyRequestOrigin({ ...base, origin }), "invalid", origin);
  assert.equal(classifyRequestOrigin({ ...base, origin: "https://evil.example" }), "rejected");
});

test("present but invalid Host evidence fails closed even when request URL matches", () => {
  for (const host of [
    "",
    "localhost:3100,evil.example",
    "localhost:3100/path",
    "user@localhost:3100",
    " localHost:3100",
    "local\thost:3100",
    "local\rhost:3100",
    "local\nhost:3100",
  ]) {
    assert.equal(classifyRequestOrigin({
      ...base,
      origin: "http://localhost:3100",
      host,
    }), "invalid", host);
  }
});

test("forwarded host evidence is ignored outside Vercel", () => {
  const evidence = {
    ...base,
    origin: "http://localhost:3100",
    forwardedHost: "preview.example,evil.example",
    forwardedProto: "https,http",
  };
  assert.equal(classifyRequestOrigin(evidence), "allowed");
  assert.equal(classifyRequestOrigin({
    ...evidence,
    origin: "https://preview.example",
    forwardedHost: "preview.example",
    forwardedProto: "https",
  }), "rejected");
});

test("a complete canonical Vercel forwarded pair adds its HTTPS origin", () => {
  assert.equal(classifyRequestOrigin({
    ...base,
    origin: "https://preview.example",
    forwardedHost: "preview.example",
    forwardedProto: "https",
    vercel: "1",
  }), "allowed");
});

test("ambiguous, partial or malformed Vercel forwarded evidence fails closed", () => {
  for (const [forwardedHost, forwardedProto] of [
    [null, "https"],
    ["preview.example", null],
    ["preview.example,evil.example", "https"],
    ["preview.example", "https,http"],
    ["preview.example/path", "https"],
    ["user@preview.example", "https"],
    ["preview.example", "javascript"],
    [" preview.example", "https"],
    ["preview.\rexample", "https"],
    ["preview.example", "https\nhttp"],
  ]) {
    assert.equal(classifyRequestOrigin({
      ...base,
      origin: "http://localhost:3100",
      forwardedHost,
      forwardedProto,
      vercel: "1",
    }), "invalid", String(forwardedHost) + " / " + String(forwardedProto));
  }
});

test("validation boundary keeps cross-site rejection and empty-Origin classification wired", async () => {
  const source = await readFile(new URL("../app/lib/integration-api/validation.ts", import.meta.url), "utf8");
  assert.match(source, /sec-fetch-site/);
  assert.match(source, /=== "cross-site"/);
  assert.match(source, /if \(origin !== null\)/);
  assert.match(source, /classifyRequestOrigin/);
});
