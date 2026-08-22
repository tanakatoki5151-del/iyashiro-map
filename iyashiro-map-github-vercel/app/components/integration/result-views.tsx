import type {
  AssessmentView,
  CompareView,
  DecisionStatus,
  LayerView,
  SavedCandidate,
} from "./types";
import styles from "@/app/integrated/integrated.module.css";

const statusLabels: Record<DecisionStatus, string> = {
  hard_veto: "HARD-VETO / 除外",
  review: "要確認",
  pass: "候補に残す",
  out_of_scope: "対象範囲外 / 判定不能",
  unknown: "UNKNOWN / 未判定",
};

const availabilityLabels: Record<LayerView["availability"], string> = {
  available: "接続済み",
  partial: "部分接続",
  unavailable: "API未提供",
  unknown: "接続状態不明",
};

function statusClass(status: DecisionStatus): string {
  if (status === "hard_veto") return styles.statusVeto;
  if (status === "review") return styles.statusReview;
  if (status === "pass") return styles.statusPass;
  return styles.statusUnknown;
}

function StatusPill({ status }: { status: DecisionStatus }) {
  return <span className={styles.statusPill + " " + statusClass(status)}>{statusLabels[status]}</span>;
}

function displayCoordinate(value: number | undefined): string {
  return typeof value === "number" ? value.toFixed(6) : "未提供";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function displayText(value: unknown): string | undefined {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return undefined;
}

type HclTrack = {
  id: string;
  name: string;
  verdict: string;
  detail: string;
  action: string;
};

function hclTracks(assessment: AssessmentView): HclTrack[] {
  const houseCompass = isRecord(assessment.raw.houseCompass) ? assessment.raw.houseCompass : undefined;
  const report = houseCompass && isRecord(houseCompass.report) ? houseCompass.report : houseCompass;
  const tracks = report && Array.isArray(report.tracks) ? report.tracks : [];
  return tracks.flatMap((track, index) => {
    if (!isRecord(track)) return [];
    return [{
      id: displayText(track.track) ?? displayText(track.id) ?? String(index),
      name: displayText(track.name) ?? displayText(track.track) ?? "HCL確認項目",
      verdict: displayText(track.verdict) ?? "未判定",
      detail: displayText(track.thisCase) ?? displayText(track.explanation) ?? "",
      action: displayText(track.action) ?? "",
    }];
  });
}

type HclContext = {
  items: Array<{ label: string; value: string }>;
  notes: string[];
};

const hclContextLabels: Record<string, string> = {
  bedroomDirection: "\u5bdd\u5ba4\u65b9\u4f4d",
  workDeskDirection: "\u4ed5\u4e8b\u673a\u65b9\u4f4d",
  headDirection: "\u5c31\u5bdd\u6642\u306e\u982d\u65b9\u4f4d",
  buildingAgeBand: "\u7bc9\u5e74\u5e2f",
  concerns: "\u6c17\u306b\u306a\u308b\u70b9",
};

function hclContext(assessment: AssessmentView): HclContext {
  const houseCompass = isRecord(assessment.raw.houseCompass) ? assessment.raw.houseCompass : undefined;
  const adapter = houseCompass && isRecord(houseCompass.adapter) ? houseCompass.adapter : undefined;
  const context = adapter && isRecord(adapter.contextOnly) ? adapter.contextOnly : undefined;
  const items = context ? Object.entries(hclContextLabels).flatMap(([key, label]) => {
    const raw = context[key];
    const value = Array.isArray(raw)
      ? raw.map(displayText).filter((item): item is string => Boolean(item)).join(" / ")
      : displayText(raw);
    return value ? [{ label, value }] : [];
  }) : [];
  const notes = adapter && Array.isArray(adapter.notes)
    ? adapter.notes.map(displayText).filter((item): item is string => Boolean(item))
    : [];
  return { items, notes };
}

function LayerCard({ layer }: { layer: LayerView }) {
  const unavailable = layer.availability === "unavailable";
  return (
    <article className={styles.layerCard}>
      <div className={styles.cardHeader}>
        <div>
          <p className={styles.cardKicker}>{availabilityLabels[layer.availability]}</p>
          <h3>{layer.label}</h3>
        </div>
        <StatusPill status={layer.status} />
      </div>
      <p className={styles.layerHeadline}>{layer.headline}</p>
      {unavailable && (
        <p className={styles.unknownInline}>
          未取得・未接続は、安全や問題の不存在を意味しません。
        </p>
      )}
      {layer.details.length > 0 && (
        <dl className={styles.factGrid}>
          {layer.details.map((detail) => (
            <div key={detail.label + detail.value}>
              <dt>{detail.label}</dt>
              <dd>{detail.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {layer.warnings.length > 0 && (
        <div className={styles.cardWarning}>
          <strong>注意・不足</strong>
          <ul>
            {[...new Set(layer.warnings)].map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        </div>
      )}
      {layer.evidence.length > 0 && (
        <details className={styles.evidenceDetails}>
          <summary>根拠・出典を確認</summary>
          <ul>
            {[...new Set(layer.evidence)].map((item) => <li key={item}>{item}</li>)}
          </ul>
        </details>
      )}
    </article>
  );
}

export function AssessmentResult({
  assessment,
  thresholdM,
  includeShrines,
}: {
  assessment: AssessmentView;
  thresholdM: number;
  includeShrines: boolean;
}) {
  const tracks = hclTracks(assessment);
  const context = hclContext(assessment);
  return (
    <div className={styles.resultStack} aria-live="polite">
      <section className={styles.decisionCard + " " + statusClass(assessment.status)}>
        <div className={styles.decisionTop}>
          <div>
            <p className={styles.cardKicker}>統合ゲート判定</p>
            <h2>{assessment.label}</h2>
          </div>
          <StatusPill status={assessment.status} />
        </div>
        <p className={styles.decisionRule}>
          寺・墓地・大病院の距離閾値 {thresholdM}m ／ 神社ゲート {includeShrines ? "ON" : "OFF"}
        </p>
        {assessment.reasons.length > 0 && (
          <ul className={styles.reasonList}>
            {assessment.reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        )}
        {(assessment.status === "unknown" || assessment.status === "out_of_scope") && (
          <p className={styles.unknownCallout}>
            {assessment.status === "out_of_scope"
              ? "対象範囲内の有効セルを確定できないため判定していません。"
              : "判定に必要な事実が不足しています。UNKNOWNは安全判定ではありません。"}
          </p>
        )}
      </section>

      <section className={styles.locationCard} aria-labelledby="integrated-location-title">
        <div>
          <p className={styles.cardKicker}>解析地点</p>
          <h2 id="integrated-location-title">{assessment.location.label}</h2>
          {assessment.location.address && assessment.location.address !== assessment.location.label && (
            <p>{assessment.location.address}</p>
          )}
          {assessment.location.coverageNote && (
            <p className={styles.helpText}>{assessment.location.coverageNote}</p>
          )}
        </div>
        <dl className={styles.locationFacts}>
          <div><dt>100mセル</dt><dd>{assessment.location.cellId ?? "未提供"}</dd></div>
          <div><dt>緯度</dt><dd>{displayCoordinate(assessment.location.lat)}</dd></div>
          <div><dt>経度</dt><dd>{displayCoordinate(assessment.location.lon)}</dd></div>
          <div><dt>位置誤差</dt><dd>{assessment.location.uncertaintyM !== undefined ? assessment.location.uncertaintyM + "m" : "未提供"}</dd></div>
          <div><dt>位置coverage</dt><dd>{assessment.location.coverageStatus ?? "未提供"}</dd></div>
          <div><dt>収容確率</dt><dd>{assessment.location.coveredWeight !== undefined ? (assessment.location.coveredWeight * 100).toFixed(1) + "%" : "未提供"}</dd></div>
        </dl>
      </section>

      <section aria-labelledby="ranking-views-title">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.cardKicker}>独立ビュー</p>
            <h2 id="ranking-views-title">順位を混ぜずに見る</h2>
          </div>
          <p>総合点・多数決は作りません。</p>
        </div>
        <div className={styles.rankingGrid}>
          {assessment.rankings.map((ranking) => (
            <article className={styles.rankingCard} key={ranking.id}>
              <p>{ranking.label}</p>
              <strong>{ranking.status === "available" ? ranking.value : ranking.status === "unknown" ? "UNKNOWN" : "API未提供"}</strong>
              <span>{ranking.detail ?? (ranking.status === "available" ? "正本の独立ビュー" : ranking.status === "unknown" ? "正本順位は未確定。安全扱いにしません" : "未取得＝安全ではありません")}</span>
            </article>
          ))}
        </div>
      </section>

      <section aria-labelledby="hard-gates-title">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.cardKicker}>非補償型</p>
            <h2 id="hard-gates-title">距離・履歴のgate</h2>
          </div>
          <p>別レイヤーの良さで相殺しません。</p>
        </div>
        {assessment.gates.length > 0 ? (
          <div className={styles.gateList}>
            {assessment.gates.map((gate) => (
              <article key={gate.id} className={statusClass(gate.status)}>
                <div>
                  <strong>{gate.label}</strong>
                  {gate.nearestName && <span>{gate.nearestName}</span>}
                </div>
                <div className={styles.gateMeasure}>
                  <StatusPill status={gate.status} />
                  {gate.distanceM !== undefined && (
                    <b>{Math.round(gate.distanceM)}m{gate.thresholdM !== undefined ? " / 閾値" + gate.thresholdM + "m" : ""}</b>
                  )}
                </div>
                <p>{gate.detail}</p>
              </article>
            ))}
          </div>
        ) : (
          <p className={styles.emptyState}>
            API応答に該当したhard gate・要確認gateはありません。これは未取得項目の安全を保証する表示ではありません。
          </p>
        )}
      </section>

      <section aria-labelledby="fact-layers-title">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.cardKicker}>FACT ENVELOPE</p>
            <h2 id="fact-layers-title">プロジェクト別の事実</h2>
          </div>
          <p>各レイヤーの結論と欠測を分離します。</p>
        </div>
        <div className={styles.layerGrid}>
          {assessment.layers.map((layer) => <LayerCard key={layer.id} layer={layer} />)}
        </div>
      </section>

      {(tracks.length > 0 || context.items.length > 0) && (
        <section aria-labelledby="hcl-tracks-title">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.cardKicker}>BOUNDED FAIL-CLOSED</p>
              <h2 id="hcl-tracks-title">HCLの個別トラック</h2>
            </div>
            <p>家相・方位を土地ゲートへ加算しません。</p>
          </div>
          {context.items.length > 0 && (
            <>
              <p className={styles.unknownInline}>{"\u5bdd\u5ba4\u30fb\u673a\u30fb\u982d\u65b9\u4f4d\u30fb\u7bc9\u5e74\u5e2f\u30fb\u81ea\u7531\u8a18\u8ff0\u306fcontext only\u3067\u3059\u3002\u73fe\u884cHCL\u898f\u5247\u306e\u7d50\u8ad6\u3078\u81ea\u52d5\u52a0\u7b97\u3057\u307e\u305b\u3093\u3002"}</p>
              <dl className={styles.factGrid}>
                {context.items.map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}
              </dl>
              {context.notes.length > 0 && <ul className={styles.reasonList}>{context.notes.map((note) => <li key={note}>{note}</li>)}</ul>}
            </>
          )}
          {tracks.length > 0 && <div className={styles.hclTracks}>
            {tracks.map((track) => (
              <article key={track.id}>
                <div><strong>{track.id} {track.name}</strong><span>{track.verdict}</span></div>
                {track.detail && <p>{track.detail}</p>}
                {track.action && <small>次の確認: {track.action}</small>}
              </article>
            ))}
          </div>}
        </section>
      )}

      {(assessment.warnings.length > 0 || assessment.nextActions.length > 0) && (
        <section className={styles.followupGrid} aria-label="不足と次の確認">
          <article>
            <h2>不足・注意</h2>
            {assessment.warnings.length > 0
              ? <ul>{[...new Set(assessment.warnings)].map((item) => <li key={item}>{item}</li>)}</ul>
              : <p>APIから注意事項は提供されていません。</p>}
          </article>
          <article>
            <h2>次に確認すること</h2>
            {assessment.nextActions.length > 0
              ? <ol>{[...new Set(assessment.nextActions)].map((item) => <li key={item}>{item}</li>)}</ol>
              : <p>APIから次アクションは提供されていません。</p>}
          </article>
        </section>
      )}

      {assessment.sources.length > 0 && (
        <details className={styles.sourceDetails}>
          <summary>正本・出典参照</summary>
          <ul>
            {[...new Set(assessment.sources)].map((source) => (
              <li key={source}>
                {/^https?:\/\//.test(source)
                  ? <a href={source} target="_blank" rel="noreferrer">{source}</a>
                  : source}
              </li>
            ))}
          </ul>
        </details>
      )}

      <p className={styles.globalCaution}>
        本画面は土地・物件選びの確認支援です。研究上の仮説、取得済み事実、欠測を分けて表示し、
        健康・資産価値・将来結果を保証しません。現地確認、公的資料、契約前調査を併用してください。
      </p>
    </div>
  );
}

export function CandidateShelf({
  candidates,
  activeId,
  comparing,
  onSelect,
  onRemove,
  onCompare,
}: {
  candidates: SavedCandidate[];
  activeId?: string;
  comparing: boolean;
  onSelect: (candidate: SavedCandidate) => void;
  onRemove: (localId: string) => void;
  onCompare: () => void;
}) {
  return (
    <section className={styles.candidateShelf} aria-labelledby="saved-candidates-title">
      <div className={styles.sectionHeading}>
        <div>
          <p className={styles.cardKicker}>SESSION CANDIDATES</p>
          <h2 id="saved-candidates-title">保存した候補</h2>
        </div>
        <button
          className={styles.secondaryButton}
          type="button"
          onClick={onCompare}
          disabled={candidates.length < 2 || comparing}
        >
          {comparing ? "比較中…" : "候補を比較"}
        </button>
      </div>
      {candidates.length === 0 ? (
        <p className={styles.emptyState}>判定が完了した候補だけ、このセッション内に保持します。</p>
      ) : (
        <div className={styles.candidateList}>
          {candidates.map((candidate) => (
            <article key={candidate.localId} className={candidate.localId === activeId ? styles.activeCandidate : undefined}>
              <div>
                <strong>{candidate.label}</strong>
                <span>{candidate.assessment.location.cellId ?? "セル未提供"}</span>
                <StatusPill status={candidate.assessment.status} />
              </div>
              <div className={styles.candidateActions}>
                <button type="button" onClick={() => onSelect(candidate)}
                  aria-label={candidate.label + "の判定結果を表示"}
                  aria-pressed={candidate.localId === activeId}>
                  {candidate.localId === activeId ? "表示中" : "表示"}
                </button>
                <button type="button" onClick={() => onRemove(candidate.localId)} aria-label={candidate.label + "を候補から外す"}>
                  外す
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      <p className={styles.sessionNote}>候補はブラウザの再読み込みで消えます。物件情報を端末へ永続保存しません。</p>
    </section>
  );
}

export function ComparisonResult({ comparison }: { comparison: CompareView }) {
  return (
    <section className={styles.comparisonCard} aria-labelledby="comparison-title" aria-live="polite">
      <div className={styles.sectionHeading}>
        <div>
          <p className={styles.cardKicker}>SERVER COMPARISON</p>
          <h2 id="comparison-title">{comparison.title}</h2>
        </div>
        <p>tier → 正本sourceRank</p>
      </div>
      {comparison.summary.length > 0 && (
        <ul className={styles.comparisonNotes}>
          {comparison.summary.map((note) => <li key={note}>{note}</li>)}
        </ul>
      )}
      {comparison.failures.length > 0 && (
        <div className={styles.errorBox} role="status">
          <p>比較できなかった候補があります。</p>
          <ul>
            {comparison.failures.map((failure) => (
              <li key={failure.id}>
                {failure.label}: {failure.message}
                {failure.error ? "（" + failure.error + "）" : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
      {comparison.rows.length > 0 ? (
        <div className={styles.comparisonTableWrap}>
          <table className={styles.comparisonTable}>
            <thead>
              <tr><th>入力順</th><th>候補</th><th>tier</th><th>正本順位</th><th>理由</th></tr>
            </thead>
            <tbody>
              {comparison.rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.displayOrder ?? "—"}</td>
                  <th scope="row">{row.label}</th>
                  <td><StatusPill status={row.status} /></td>
                  <td>{row.sourceRank === undefined ? "UNKNOWN / 順位なし" : String(row.sourceRank) + (row.tie ? "（同順位）" : "")}</td>
                  <td>{row.notes.length > 0 ? row.notes.join(" / ") : "APIから理由未提供"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className={styles.emptyState}>比較APIはorderingを返しませんでした。ローカルで順位を推測しません。</p>
      )}
      <p className={styles.globalCaution}>HARD-VETOは他の順位やレイヤーで相殺しません。UNKNOWNは安全扱いにしません。</p>
    </section>
  );
}
