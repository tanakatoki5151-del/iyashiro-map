import type {
  DossierItem,
  DossierStatus,
  LandDossier,
} from "../lib/land-dossier-types";

const STATUS_LABELS: Record<DossierStatus, string> = {
  avoid: "回避条件に該当",
  review: "要確認",
  current_clear: "現在の資料では該当なし",
  available: "情報あり",
  context: "参考情報",
  unknown: "情報不足",
};

const PRIORITY_LABELS = {
  high: "優先して補う",
  medium: "次に補う",
  low: "補足候補",
} as const;

const SECTION_LABELS = {
  terrain: "地形",
  water: "水",
  ground: "地盤",
  history: "歴史",
  facilities: "周辺施設",
} as const;

function DossierItemCard({
  item,
  testId,
  modelVersion,
}: {
  item: DossierItem;
  testId?: string;
  modelVersion?: string;
}) {
  return (
    <article
      className="dossier-item"
      data-status={item.status}
      data-testid={testId ?? "dossier-item-" + item.id}
      data-model-version={modelVersion}
    >
      <div className="dossier-item-heading">
        <h4>{item.title}</h4>
        <span className="dossier-status">{STATUS_LABELS[item.status]}</span>
      </div>
      <p className="dossier-item-summary">{item.summary}</p>
      <p className="dossier-item-explanation">{item.explanation}</p>
      {item.details.length > 0 && (
        <dl className="dossier-detail-grid">
          {item.details.map((detail, index) => (
            <div key={detail.label + "-" + index}>
              <dt>{detail.label}</dt>
              <dd>{detail.value}</dd>
            </div>
          ))}
        </dl>
      )}
      <div className="dossier-evidence-note">
        <span>確認範囲：{item.coverage}</span>
        <span>根拠：{item.source}</span>
      </div>
    </article>
  );
}

export default function LandDossierPanel({
  dossier,
  onClose,
}: {
  dossier: LandDossier;
  onClose: () => void;
}) {
  const placeNameItem = dossier.sections
    .flatMap((section) => section.items)
    .find((item) =>
      /place[-_ ]?name|nomen|地名|町名|土地名|由来/i.test(
        item.id + " " + item.title,
      ),
    );
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
          <p className="dossier-kicker">この地点の土地情報</p>
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

      <div className="dossier-coverage" data-testid="dossier-coverage">
        <strong>{dossier.location.coverageStatus}</strong>
        <span>{dossier.location.coverageNote}</span>
        <small>
          100m区画 {dossier.location.cellId} ・ {dossier.location.cellStability}
        </small>
      </div>

      <nav className="dossier-index" aria-label="土地情報の項目">
        <a href="#dossier-hard-avoid">絶対に避けたい条件</a>
        <a href="#dossier-iyashiroji">イヤシロジ</a>
        <a href="#dossier-ryumyak">龍脈</a>
        {dossier.sections.map((section) => (
          <a key={section.id} href={"#dossier-" + section.id}>
            {SECTION_LABELS[section.id]}
          </a>
        ))}
        <a href="#dossier-place-name">地名の由来</a>
        <a href="#dossier-missing">足りない情報</a>
      </nav>

      <p className="dossier-reading-guide">
        最初に回避条件を確認し、次に「イヤシロジ」と「龍脈」の二本柱を見ます。そのあと、地形・水・地盤・歴史・周辺施設の根拠を順に読めます。
      </p>

      <section
        id="dossier-hard-avoid"
        className="dossier-section dossier-stage-one"
        data-section="hard-avoid"
        data-dossier-section="hard-avoid"
      >
        <div className="dossier-section-heading">
          <span>第一段階</span>
          <h3>{dossier.stageOne.title}</h3>
        </div>
        <div
          className="dossier-stage-verdict"
          data-status={dossier.stageOne.status}
          data-testid="hard-avoid-verdict"
        >
          <strong>{STATUS_LABELS[dossier.stageOne.status]}</strong>
          <span>{dossier.stageOne.thresholdM}mを基準に確認</span>
        </div>
        <p className="dossier-section-intro">{dossier.stageOne.summary}</p>
        <div className="dossier-item-list">
          {dossier.stageOne.items.length > 0 ? (
            dossier.stageOne.items.map((item) => (
              <DossierItemCard key={item.id} item={item} />
            ))
          ) : (
            <p className="dossier-empty">
              回避条件の確認結果がまだ接続されていません。該当なしとは扱いません。
            </p>
          )}
        </div>
      </section>

      <section
        id="dossier-iyashiroji"
        className="dossier-section dossier-pillar"
        data-section="iyashiroji"
        data-dossier-section="iyashiroji"
        data-pillar="1"
      >
        <div className="dossier-section-heading">
          <span>土地そのもの・一本目</span>
          <h3>{dossier.axes.iyashiroji.title}</h3>
        </div>
        <p className="dossier-section-intro">
          {dossier.axes.iyashiroji.summary}
        </p>
        <div className="dossier-version-grid">
          <div>
            <p className="dossier-version-label">現在の判定</p>
            <DossierItemCard
              item={dossier.axes.iyashiroji.current}
              testId="iyashiroji-v15-3"
              modelVersion="V15.3"
            />
          </div>
          <div>
            <p className="dossier-version-label">過去版との比較</p>
            <DossierItemCard
              item={dossier.axes.iyashiroji.legacy}
              testId="iyashiroji-v10"
              modelVersion="V10"
            />
          </div>
        </div>
        <p className="dossier-comparison-note">
          {dossier.axes.iyashiroji.comparisonNote}
        </p>
      </section>

      <section
        id="dossier-ryumyak"
        className="dossier-section dossier-pillar"
        data-section="ryumyak"
        data-dossier-section="ryumyak"
        data-pillar="2"
      >
        <div className="dossier-section-heading">
          <span>土地そのもの・二本目</span>
          <h3>{dossier.axes.ryumyak.title}</h3>
        </div>
        <p className="dossier-section-intro">{dossier.axes.ryumyak.summary}</p>
        <DossierItemCard
          item={dossier.axes.ryumyak.current}
          testId="ryumyak-current"
        />
      </section>

      {dossier.sections.map((section) => {
        const items = placeNameItem
          ? section.items.filter((item) => item.id !== placeNameItem.id)
          : section.items;
        return (
          <section
            key={section.id}
            id={"dossier-" + section.id}
            className="dossier-section"
            data-section={section.id}
            data-dossier-section={section.id}
          >
            <div className="dossier-section-heading">
              <span>根拠を詳しく見る</span>
              <h3>{section.title}</h3>
            </div>
            <p className="dossier-section-intro">{section.intro}</p>
            <div className="dossier-item-list">
              {items.length > 0 ? (
                items.map((item) => (
                  <DossierItemCard key={item.id} item={item} />
                ))
              ) : (
                <p className="dossier-empty">
                  この項目で表示できる追加情報は、現在の統合資料にはありません。
                </p>
              )}
            </div>
          </section>
        );
      })}

      <section
        id="dossier-place-name"
        className="dossier-section"
        data-section="place-name"
        data-dossier-section="place-name"
      >
        <div className="dossier-section-heading">
          <span>土地の背景</span>
          <h3>地名・土地名の由来</h3>
        </div>
        {placeNameItem ? (
          <DossierItemCard item={placeNameItem} testId="place-name-origin" />
        ) : (
          <div className="dossier-empty" data-testid="place-name-origin-missing">
            <strong>現在の統合資料では、由来を確認できていません。</strong>
            <span>
              「由来がない」という意味ではなく、根拠資料がまだこの地点に結び付いていない状態です。推測で補わず、追加探索の対象にします。
            </span>
          </div>
        )}
      </section>

      <section
        id="dossier-missing"
        className="dossier-section dossier-missing"
        data-section="missing-information"
        data-dossier-section="missing-information"
        data-testid="missing-information"
      >
        <div className="dossier-section-heading">
          <span>情報の穴を見える化</span>
          <h3>まだ足りない情報</h3>
        </div>
        <p className="dossier-section-intro">
          未取得・未接続・確認範囲外を、安全や問題なしとは扱いません。次に何を調べるかまで表示します。
        </p>
        <div className="dossier-missing-list">
          {dossier.missingInformation.length > 0 ? (
            dossier.missingInformation.map((missing) => (
              <article key={missing.id} data-priority={missing.priority} data-missing-for={missing.id}>
                <span>{PRIORITY_LABELS[missing.priority]}</span>
                <h4>{missing.title}</h4>
                <p>{missing.currentState}</p>
                <strong>次にすること</strong>
                <p>{missing.nextAction}</p>
              </article>
            ))
          ) : (
            <p className="dossier-empty">
              今回の統合結果では、個別に列挙された未取得情報はありません。
            </p>
          )}
        </div>
      </section>

      <details className="dossier-sources" data-section="sources" data-dossier-section="sources">
        <summary>使った資料と版を確認する</summary>
        <div>
          {dossier.sources.map((source, index) => (
            <article key={source.title + "-" + index}>
              <strong>{source.title}</strong>
              <span>{source.project}</span>
              <small>
                {source.version ? "版：" + source.version : "版情報なし"}
                {source.pointer ? " ・ 保存先：" + source.pointer : ""}
              </small>
            </article>
          ))}
        </div>
      </details>

      {dossier.cautions.length > 0 && (
        <div className="dossier-cautions" data-section="cautions">
          <strong>判断するときの注意</strong>
          <ul>
            {dossier.cautions.map((caution) => (
              <li key={caution}>{caution}</li>
            ))}
          </ul>
        </div>
      )}

      <footer className="dossier-actions">
        <a href={jsonUrl} target="_blank" rel="noreferrer">
          AI・JSON用の公開結果を開く
        </a>
        <button type="button" onClick={onClose}>
          閉じる
        </button>
      </footer>
    </div>
  );
}
