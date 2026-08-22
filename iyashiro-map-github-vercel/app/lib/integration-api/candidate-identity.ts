import { createHash } from "node:crypto";

export function createCandidateId(identity: unknown): string {
  return "candidate_" + createHash("sha256")
    .update(JSON.stringify(identity))
    .digest("hex")
    .slice(0, 16);
}
