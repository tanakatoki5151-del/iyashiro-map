export interface ComparisonOrderingCandidate {
  candidateId: string;
  clientCandidateId: string | null;
  candidateOrdinal: number | null;
  sourceRank: number | null;
  tier: string;
  summary: string;
  hardGateCount: number;
  reviewCount: number;
}

export function buildComparisonOrdering(candidates: ComparisonOrderingCandidate[]) {
  return candidates.map((candidate) => ({
    candidateId: candidate.candidateId,
    clientCandidateId: candidate.clientCandidateId,
    candidateOrdinal: candidate.candidateOrdinal,
    displayOrder: (candidate.candidateOrdinal ?? 0) + 1,
    rank: candidate.sourceRank,
    tie: candidate.sourceRank === null ||
      candidates.filter((other) => other.sourceRank === candidate.sourceRank).length > 1,
    rankingBasis: candidate.sourceRank === null
      ? "none_no_cell_addressable_source_first"
      : "source_first_area_explicit",
    tier: candidate.tier,
    sourceRank: candidate.sourceRank,
    reasons: [
      candidate.summary,
      ...(candidate.hardGateCount ? ["hard gate " + candidate.hardGateCount + "件"] : []),
      ...(candidate.reviewCount ? ["要確認 " + candidate.reviewCount + "件"] : []),
    ],
  }));
}
