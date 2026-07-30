const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("smoke", `${process.pid}-${Date.now()}`);
const { default: worker } = await import(workerUrl.href);
const lat = Number(process.argv[2] ?? "35.681236");
const lng = Number(process.argv[3] ?? "139.767125");

const response = await worker.fetch(
  new Request(`http://localhost/api/diagnose?lat=${lat}&lng=${lng}`, {
    headers: { accept: "application/json" },
  }),
  {
    ASSETS: {
      fetch: async () => new Response("Not found", { status: 404 }),
    },
  },
  { waitUntil() {}, passThroughOnException() {} },
);

const payload = await response.json();
console.log(
  JSON.stringify(
    {
      status: response.status,
      scope: payload.scope?.name,
      theory: payload.theory
        ? {
            score: payload.theory.score,
            label: payload.theory.label,
            confidence: payload.theory.internalConfidence,
            highEvidence: payload.theory.highEvidence,
            lowEvidence: payload.theory.lowEvidence,
            scales: payload.theory.scales,
          }
        : null,
      modern: payload.modern
        ? {
            score: payload.modern.score,
            label: payload.modern.label,
            completeness: payload.modern.completeness,
          }
        : null,
      combined: payload.combined
        ? {
            score: payload.combined.score,
            label: payload.combined.label,
          }
        : null,
      error: payload.message ?? null,
    },
    null,
    2,
  ),
);

if (!response.ok) process.exitCode = 1;
