import type {
  DossierItem,
  DossierSection,
  DossierStatus,
  LandDossier,
} from "../lib/land-dossier-types";

const STATUS_META: Record<
  DossierStatus,
  { label: string; symbol: string }
> = {
  avoid: { label: "回避", symbol: "×" },
  review: { label: "要確認", symbol: "!" },
  current_clear: { label: "接続資料では該当なし", symbol: "○" },
  available: { label: "収録あり", symbol: "●" },
  context: { label: "参考", symbol: "i" },
  unknown: { label: "資料不足", symbol: "—" },
};

const PRIORITY_LABELS = {
  high: "優先して補う",
  medium: "次に補う",
  low: "補足候補",
} as const;

const SECTION_META: Record<
  DossierSection["id"],
  { label: string; icon: string }
> = {
  terrain: { label: "地形", icon: "地" },
  water: { label: "水", icon: "水" },
  ground: { label: "地盤", icon: "盤" },
  history: { label: "歴史", icon: "史" },
  facilities: { label: "周辺施設", icon: "周" },
};

const STATUS_ORDER: Record<DossierStatus, number> = {
  avoid: 0,
  review: 1,
  unknown: 2,
  current_clear: 3,
  available: 4,
  context: 5,
};

function detailValue(item: DossierItem, label: string) {
  return item.details.find((detail) => detail.label === label)?.value ?? null;
}

function itemCounts(items: DossierItem[]) {
  return items.reduce(
    (counts, item) => {
      counts[item.status] += 1;
      return counts;
    },
    {
      avoid: 0,
      review: 0,
      current_clear: 0,
      available: 0,
      context: 0,
      unknown: 0,
    } satisfies Record<DossierStatus, number>,
  );
}

function DossierItemCard({
  item,
  testId,
  modelVersion,
  summaryLabel,
  htmlId,
}: {
  item: DossierItem;
  testId?: string;
  modelVersion?: string;
  summaryLabel?: string;
  htmlId?: string;
}) {
  const meta = STATUS_META[item.status];
  return (
    <details
      id={htmlId}
      className="dossier-item"
      data-status={item.status}
      data-testid={testId ?? "dossier-item-" + item.id}
      data-model-version={modelVersion}
    >
      <summary>
        <span className="dossier-status-icon" aria-hidden="true">
          {meta.symbol}
        </span>
        <span className="dossier-item-copy">
          <strong>{summaryLabel ?? item.title}</strong>
          {summaryLabel ? null : (
            <small>{item.summary}</small>
          )}
        </span>
        <span className="dossier-status">{meta.label}</span>
        <span className="dossier-disclosure" aria-hidden="true">
          ＋
        </span>
      </summary>
      <div className="dossier-item-body">
        <p className="dossier-item-explanation">{item.explanation}</p>
        {item.details.length > 0 ? (
          <dl className="dossier-detail-grid">
            {item.details.map((detail, index) => (
              <div key={detail.label + "-" + index}>
                <dt>{detail.label}</dt>
                <dd>{detail.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        <div className="dossier-evidence-note">
          <span>確認範囲</span>
          <strong>{item.coverage}</strong>
          <span>根拠</span>
          <strong>{item.source}</strong>
        </div>
      </div>
    </details>
  );
}

function AxisMetrics({
  item,
  labels,
}: {
  item: DossierItem;
  labels: string[];
}) {
  const metrics = labels.flatMap((label) => {
    const value = detailValue(item, label);
    return value ? [{ label, value }] : [];
  });
  return (
    <dl className="axis-metrics">
      {metrics.map((metric) => (
        <div key={metric.label}>
          <dt>{metric.label.replace("主区画の", "")}</dt>
          <dd>{metric.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function LandDossierPanel({
  dossier,
  onClose,
  onOpenDetails,
}: {
  dossier: LandDossier;
  onClose: () => void;
  onOpenDetails: () => void;
}) {
  const placeNameItem = dossier.sections
    .flatMap((section) => section.items)
    .find((item) =>
      /place[-_ ]?name|nomen|地名|町名|土地名|由来/i.test(
        item.id + " " + item.title,
      ),
    );
  const alreadyShownIds = new Set([
    ...dossier.stageOne.items.map((item) => item.id),
    dossier.axes.iyashiroji.current.id,
    dossier.axes.iyashiroji.legacy.id,
    dossier.axes.ryumyak.current.id,
    ...(placeNameItem ? [placeNameItem.id] : []),
  ]);
  const detailSections = dossier.sections.map((section) => ({
    ...section,
    items: section.items.filter((item) => !alreadyShownIds.has(item.id)),
  }));
  const stageCounts = itemCounts(dossier.stageOne.items);
  const importantFindings = [...dossier.stageOne.items]
    .filter((item) => item.status !== "current_clear")
    .sort((left, right) => STATUS_ORDER[left.status] - STATUS_ORDER[right.status])
    .slice(0, 3);
  const verdict =
    dossier.stageOne.status === "avoid"
      ? {
          label: "候補から外す条件あり",
          symbol: "×",
          next: "該当した条件の距離と根拠を先に確認してください。後段の評価では相殺しません。",
        }
      : dossier.stageOne.status === "review"
        ? {
            label: "保留して追加確認",
            symbol: "!",
            next: "資料不足や境界付近の項目を補ってから、次の判断へ進みます。",
          }
        : {
            label: "二本柱の比較へ進む",
            symbol: "→",
            next: "イヤシロジと龍脈を別々に見て、土地の詳しい根拠を確認します。",

          };
  const openHardAvoid = (itemId: string) => {
    onOpenDetails();
    window.requestAnimationFrame(() => {
      const target = document.getElementById("hard-avoid-" + itemId);
      if (target instanceof HTMLDetailsElement) target.open = true;
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  const jsonUrl =
    "/api/v3/dossier?lat=" +
    encodeURIComponent(dossier.location.lat) +
    "&lng=" +
    encodeURIComponent(dossier.location.lng) +
    "&label=" +
    encodeURIComponent(dossier.location.label);

  return (
    <div
      className="dossier-panel"
      data-testid="land-dossier"
      data-primary-label={dossier.location.label}
      role="region"
      aria-labelledby="land-dossier-title"
    >
      <header className="dossier-hero">
        <div>
          <p className="dossier-kicker">選択した地点</p>
          <h2 id="land-dossier-title">{dossier.location.label}</h2>
          <p className="dossier-coordinate">{dossier.location.coordinate}</p>
        </div>
        <button
          className="dossier-close"
          type="button"
          aria-label="土地情報を閉じる"
          onClick={onClose}
        >
          ×
        </button>
      </header>

      <section
        id="dossier-overview"
        className="dossier-decision"
        data-status={dossier.stageOne.status}
        aria-labelledby="dossier-decision-title"
      >
        <div className="decision-heading">
          <span className="decision-symbol" aria-hidden="true">
            {verdict.symbol}
          </span>
          <div>
            <p>第一段階の結論</p>
            <h3 id="dossier-decision-title">{verdict.label}</h3>
          </div>
        </div>
        <p className="decision-summary">{dossier.stageOne.summary}</p>
        <ul className="decision-counts" aria-label="回避条件の集計">
          <li data-status="avoid">
            <strong>{stageCounts.avoid}</strong>
            <span>回避</span>
          </li>
          <li data-status="review">
            <strong>{stageCounts.review}</strong>
            <span>要確認</span>
          </li>
          <li data-status="unknown">
            <strong>{stageCounts.unknown}</strong>
            <span>資料不足</span>
          </li>
        </ul>
        {importantFindings.length > 0 ? (
          <div className="decision-findings" aria-label="先に見る項目">
            <span>先に見る項目</span>
            <ul>
              {importantFindings.map((item) => {
                const nearest = detailValue(item, "最寄り名称");
                const distance = detailValue(item, "最短距離（セル中心基準）");
                return (
                  <li key={item.id} data-status={item.status}>
                    <a
                      href={"#hard-avoid-" + item.id}
                      onClick={(event) => {
                        event.preventDefault();
                        openHardAvoid(item.id);
                      }}
                    >
                      <span aria-hidden="true">{STATUS_META[item.status].symbol}</span>
                      <strong>{item.title}</strong>
                      <small>
                        {[nearest, distance].filter(Boolean).join("・") || item.coverage}
                      </small>
                    </a>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : (
          <p className="decision-clear-note">
            5つの回避条件は、接続済み資料では500m以内の該当が確認されませんでした。
          </p>
        )}
        <p className="decision-next">
          <strong>次にすること</strong>
          {verdict.next}
        </p>
        <div className="decision-coverage" data-testid="dossier-coverage">
          <strong>{dossier.location.coverageStatus}</strong>
          <span>詳しい収録範囲と100m区画は「使った資料」で確認できます。</span>
        </div>
      </section>

      <section className="dossier-axis-overview" aria-labelledby="axis-overview-title">
        <div className="dossier-group-heading">
          <span>土地そのものを別々に見る</span>
          <h3 id="axis-overview-title">二本柱</h3>
          <p>順位表が異なるため、イヤシロジと龍脈は合算しません。</p>
        </div>
        <div className="dossier-axis-grid">
          <article
            id="dossier-iyashiroji"
            className="dossier-axis-card"
            data-status={dossier.axes.iyashiroji.current.status}
            data-section="iyashiroji"
            data-dossier-section="iyashiroji"
            data-pillar="1"
          >
            <div className="axis-card-heading">
              <div>
                <span>土地そのもの・一本目</span>
                <h4>イヤシロジ</h4>
              </div>
              <span className="dossier-status">
                {STATUS_META[dossier.axes.iyashiroji.current.status].label}
              </span>
            </div>
            <p className="axis-version">V15.3 現在の判定</p>
            <p className="axis-summary">{dossier.axes.iyashiroji.current.summary}</p>
            <AxisMetrics
              item={dossier.axes.iyashiroji.current}
              labels={["主区画の正本順位", "地形・地勢区分"]}
            />
            <DossierItemCard
              summaryLabel="詳しい根拠・全数値を見る"
              item={dossier.axes.iyashiroji.current}
              testId="iyashiroji-v15-3"
              modelVersion="V15.3"
            />
            <div className="dossier-legacy-block">
              <span>過去版との比較</span>
              <DossierItemCard
                item={dossier.axes.iyashiroji.legacy}
                testId="iyashiroji-v10"
                modelVersion="V10"
              />
            </div>
            <p className="dossier-comparison-note">
              {dossier.axes.iyashiroji.comparisonNote}
            </p>
          </article>

          <article
            id="dossier-ryumyak"
            className="dossier-axis-card"
            data-status={dossier.axes.ryumyak.current.status}
            data-section="ryumyak"
            data-dossier-section="ryumyak"
            data-pillar="2"
          >
            <div className="axis-card-heading">
              <div>
                <span>土地そのもの・二本目</span>
                <h4>{dossier.axes.ryumyak.title}</h4>
              </div>
              <span className="dossier-status">
                {STATUS_META[dossier.axes.ryumyak.current.status].label}
              </span>
            </div>
            <p className="axis-version">現行正本</p>
            <p className="axis-summary">{dossier.axes.ryumyak.current.summary}</p>
            <AxisMetrics
              item={dossier.axes.ryumyak.current}
              labels={["主区画の正本順位", "龍脈ゾーン", "確度"]}
            />
            <DossierItemCard
              summaryLabel="詳しい根拠・全数値を見る"
              item={dossier.axes.ryumyak.current}
              testId="ryumyak-current"
            />
          </article>
        </div>
      </section>

      <nav className="dossier-index" aria-label="土地カルテの項目">
        <a href="#dossier-overview">結論</a>
        <a href="#dossier-hard-avoid">回避条件</a>
        <a href="#dossier-land-details">土地の詳細</a>
        <a href="#dossier-missing">不足・資料</a>
      </nav>

      <section
        id="dossier-hard-avoid"
        className="dossier-section dossier-stage-one"
        data-section="hard-avoid"
        data-dossier-section="hard-avoid"
      >
        <div className="dossier-group-heading">
          <span>500m以内を先に確認</span>
          <h3>絶対に避けたい条件</h3>
          <p>寺院・墓地・大規模病院・強い歴史・P8を、後段の点数とは別に確認します。</p>
        </div>
        <div
          className="dossier-stage-verdict"
          data-status={dossier.stageOne.status}
          data-testid="hard-avoid-verdict"
        >
          <strong>{verdict.label}</strong>
          <span>{dossier.stageOne.thresholdM}mを基準に確認</span>
        </div>
        <div className="dossier-item-list">
          {dossier.stageOne.items.length > 0 ? (
            dossier.stageOne.items.map((item) => (
              <DossierItemCard
                key={item.id}
                item={item}
                htmlId={"hard-avoid-" + item.id}
              />
            ))
          ) : (
            <p className="dossier-empty">
              回避条件の確認結果がまだ接続されていません。該当なしとは扱いません。
            </p>
          )}
        </div>
      </section>

      <section id="dossier-land-details" className="dossier-land-details">
        <div className="dossier-group-heading">
          <span>必要なところだけ開く</span>
          <h3>土地の詳しい根拠</h3>
          <p>地形・水・地盤・歴史・周辺施設を、要点から順に確認できます。</p>
        </div>
        <div className="dossier-category-list">
          {detailSections.map((section) => {
            const counts = itemCounts(section.items);
            const representative = [...section.items].sort(
              (left, right) => STATUS_ORDER[left.status] - STATUS_ORDER[right.status],
            )[0];
            return (
              <details
                key={section.id}
                id={"dossier-" + section.id}
                className="dossier-category"
                data-section={section.id}
                data-dossier-section={section.id}
              >
                <summary>
                  <span className="category-icon" aria-hidden="true">
                    {SECTION_META[section.id].icon}
                  </span>
                  <span className="category-copy">
                    <strong>{SECTION_META[section.id].label}</strong>
                    <small>{representative?.summary ?? "主要情報は上の判定で確認済みです。"}</small>
                  </span>
                  <span className="category-counts">
                    {counts.avoid + counts.review > 0 ? (
                      <b data-status="review">注意 {counts.avoid + counts.review}</b>
                    ) : null}
                    {counts.unknown > 0 ? <b data-status="unknown">未確認 {counts.unknown}</b> : null}
                  </span>
                  <span className="dossier-disclosure" aria-hidden="true">＋</span>
                </summary>
                <div className="dossier-category-body">
                  <p>{section.intro}</p>
                  <div className="dossier-item-list">
                    {section.items.length > 0 ? (
                      section.items.map((item) => (
                        <DossierItemCard key={item.id} item={item} />
                      ))
                    ) : (
                      <p className="dossier-empty">
                        この分類の主要項目は、上の回避条件または二本柱で確認済みです。
                      </p>
                    )}
                  </div>
                </div>
              </details>
            );
          })}

          <details
            id="dossier-place-name"
            className="dossier-category"
            data-section="place-name"
            data-dossier-section="place-name"
          >
            <summary>
              <span className="category-icon" aria-hidden="true">名</span>
              <span className="category-copy">
                <strong>地名・土地名の由来</strong>
                <small>
                  {placeNameItem?.summary ?? "由来資料はまだこの地点に結び付いていません。"}
                </small>
              </span>
              <span className="category-counts">
                {!placeNameItem || placeNameItem.status === "unknown" ? (
                  <b data-status="unknown">未確認</b>
                ) : null}
              </span>
              <span className="dossier-disclosure" aria-hidden="true">＋</span>
            </summary>
            <div className="dossier-category-body">
              {placeNameItem ? (
                <DossierItemCard item={placeNameItem} testId="place-name-origin" />
              ) : (
                <div className="dossier-empty" data-testid="place-name-origin-missing">
                  <strong>現在の統合資料では、由来を確認できていません。</strong>
                  <span>
                    「由来がない」という意味ではありません。推測で補わず、追加探索の対象にします。
                  </span>
                </div>
              )}
            </div>
          </details>
        </div>
      </section>

      <details
        id="dossier-missing"
        className="dossier-missing"
        data-section="missing-information"
        data-dossier-section="missing-information"
        data-testid="missing-information"
      >
        <summary>
          <span>
            <small>情報の穴を見える化</small>
            <strong>まだ足りない情報</strong>
          </span>
          <b>{dossier.missingInformation.length}件</b>
          <span className="dossier-disclosure" aria-hidden="true">＋</span>
        </summary>
        <div className="dossier-missing-body">
          <p>
            未取得・未接続・確認範囲外を、安全や問題なしとは扱いません。次に何を調べるかまで表示します。
          </p>
          <div className="dossier-missing-list">
            {dossier.missingInformation.length > 0 ? (
              dossier.missingInformation.map((missing) => (
                <details key={missing.id} data-priority={missing.priority} data-missing-for={missing.id}>
                  <summary>
                    <span>{PRIORITY_LABELS[missing.priority]}</span>
                    <strong>{missing.title}</strong>
                    <span className="dossier-disclosure" aria-hidden="true">＋</span>
                  </summary>
                  <div>
                    <p>{missing.currentState}</p>
                    <strong>次にすること</strong>
                    <p>{missing.nextAction}</p>
                  </div>
                </details>
              ))
            ) : (
              <p className="dossier-empty">
                今回の統合結果では、個別に列挙された未取得情報はありません。
              </p>
            )}
          </div>
        </div>
      </details>

      <details className="dossier-sources" data-section="sources" data-dossier-section="sources">
        <summary>
          <span>
            <small>版・根拠・注意事項</small>
            <strong>使った資料</strong>
          </span>
          <b>{dossier.sources.length}件</b>
          <span className="dossier-disclosure" aria-hidden="true">＋</span>
        </summary>
        <div className="dossier-sources-body">
          <div
            className="dossier-location-record"
            data-testid="dossier-coverage-detail"
          >
            <strong>この地点の収録範囲</strong>
            <p>{dossier.location.coverageNote}</p>
            <dl>
              <div>
                <dt>収録状態</dt>
                <dd>{dossier.location.coverageStatus}</dd>
              </div>
              <div>
                <dt>100m区画</dt>
                <dd>{dossier.location.cellId}</dd>
              </div>
              <div>
                <dt>区画の安定性</dt>
                <dd>{dossier.location.cellStability}</dd>
              </div>
            </dl>
          </div>
          <div className="dossier-source-list">
            {dossier.sources.map((source, index) => (
              <article key={source.title + "-" + index}>
                <strong>{source.title}</strong>
                <span>{source.project}</span>
                <small>{source.version ? "版：" + source.version : "版情報なし"}</small>
                {source.pointer ? (
                  <a href={source.pointer} target="_blank" rel="noreferrer">
                    公開元を開く
                  </a>
                ) : null}
              </article>
            ))}
          </div>
          {dossier.cautions.length > 0 ? (
            <div className="dossier-cautions" data-section="cautions">
              <strong>判断するときの注意</strong>
              <ul>
                {dossier.cautions.map((caution) => (
                  <li key={caution}>{caution}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </details>

      <footer className="dossier-actions">
        <a href={jsonUrl} target="_blank" rel="noreferrer">
          AI用データを開く
        </a>
        <button type="button" onClick={onClose}>閉じる</button>
      </footer>
    </div>
  );
}
