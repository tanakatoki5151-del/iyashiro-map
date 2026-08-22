"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";
import { requestAssessment, requestComparison } from "./api";
import {
  AssessmentResult,
  CandidateShelf,
  ComparisonResult,
} from "./result-views";
import {
  emptyAssessmentForm,
  type AssessRequest,
  type AssessmentFormState,
  type CompareView,
  type DistanceThreshold,
  type HclInput,
  type ManualPropertyInput,
  type SavedCandidate,
} from "./types";
import styles from "@/app/integrated/integrated.module.css";

const directions = ["北", "北東", "東", "南東", "南", "南西", "西", "北西"];
const ageBands = ["不明", "1981年以前", "1981〜2000年", "2001〜2010年", "2011〜2020年", "2021年以降"];

function freshForm(): AssessmentFormState {
  return {
    ...emptyAssessmentForm,
    manual: { ...emptyAssessmentForm.manual },
    policy: { ...emptyAssessmentForm.policy },
    hcl: { ...emptyAssessmentForm.hcl },
  };
}

function compactManual(manual: ManualPropertyInput): AssessRequest["manual"] | undefined {
  const entries = {
    name: manual.name.trim(),
    address: manual.address.trim(),
    station: manual.station.trim(),
    areaM2: manual.areaM2.trim(),
    layout: manual.layout.trim(),
    memo: manual.memo.trim(),
  };
  return Object.values(entries).some(Boolean) ? entries : undefined;
}

function compactHcl(hcl: HclInput): AssessRequest["hcl"] | undefined {
  if (!hcl.enabled) return undefined;
  return {
    entranceDirection: hcl.entranceDirection.trim(),
    bedroomDirection: hcl.bedroomDirection.trim(),
    workDeskDirection: hcl.workDeskDirection.trim(),
    kitchenDirection: hcl.kitchenDirection.trim(),
    headDirection: hcl.headDirection.trim(),
    buildingAgeBand: hcl.buildingAgeBand.trim(),
    concerns: hcl.concerns.trim(),
  };
}

function parseRequest(form: AssessmentFormState): AssessRequest {
  const address = form.address.trim();
  const propertyUrl = form.propertyUrl.trim();
  const manual = compactManual(form.manual);
  const latitudeEntered = Boolean(form.latitude.trim());
  const longitudeEntered = Boolean(form.longitude.trim());
  if (latitudeEntered !== longitudeEntered) {
    throw new Error("緯度と経度は両方入力してください。");
  }

  let lat: number | undefined;
  let lon: number | undefined;
  if (latitudeEntered && longitudeEntered) {
    lat = Number(form.latitude);
    lon = Number(form.longitude);
    if (!Number.isFinite(lat) || lat < -90 || lat > 90) {
      throw new Error("緯度は -90〜90 の数値で入力してください。");
    }
    if (!Number.isFinite(lon) || lon < -180 || lon > 180) {
      throw new Error("経度は -180〜180 の数値で入力してください。");
    }
  }

  if (propertyUrl) {
    let parsed: URL;
    try {
      parsed = new URL(propertyUrl);
    } catch {
      throw new Error("物件URLの形式を確認してください。");
    }
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
      throw new Error("物件URLは http または https のURLを入力してください。");
    }
  }

  if (!address && lat === undefined && !propertyUrl && !manual?.address) {
    throw new Error("住所、緯度・経度、物件URL、または手動補正住所のいずれかを入力してください。");
  }

  return {
    candidateLabel: form.candidateLabel.trim() || undefined,
    address: address || undefined,
    lat,
    lon,
    propertyUrl: propertyUrl || undefined,
    manual,
    policy: { ...form.policy },
    hcl: compactHcl(form.hcl),
  };
}

function candidateLabel(form: AssessmentFormState, request: AssessRequest, resolvedLabel: string): string {
  if (form.candidateLabel.trim()) return form.candidateLabel.trim();
  if (request.manual?.name) return request.manual.name;
  if (resolvedLabel) return resolvedLabel;
  if (request.address) return request.address;
  return "候補地点";
}

function localId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : "candidate-" + Date.now() + "-" + Math.random().toString(16).slice(2);
}

function DirectionSelect({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className={styles.field} htmlFor={id}>
      <span>{label}</span>
      <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">不明・未確認</option>
        {directions.map((direction) => <option value={direction} key={direction}>{direction}</option>)}
      </select>
    </label>
  );
}

export default function IntegratedCopilot() {
  const [form, setForm] = useState<AssessmentFormState>(freshForm);
  const [candidates, setCandidates] = useState<SavedCandidate[]>([]);
  const [active, setActive] = useState<SavedCandidate | null>(null);
  const [comparison, setComparison] = useState<CompareView | null>(null);
  const [assessmentError, setAssessmentError] = useState<string | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [comparing, setComparing] = useState(false);

  const setTop = <K extends keyof AssessmentFormState>(key: K, value: AssessmentFormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const setManual = <K extends keyof ManualPropertyInput>(key: K, value: ManualPropertyInput[K]) => {
    setForm((current) => ({ ...current, manual: { ...current.manual, [key]: value } }));
  };

  const setHcl = <K extends keyof HclInput>(key: K, value: HclInput[K]) => {
    setForm((current) => ({ ...current, hcl: { ...current.hcl, [key]: value } }));
  };

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAssessmentError(null);
    setComparisonError(null);
    setComparison(null);

    const candidateLocalId = localId();
    let request: AssessRequest;
    try {
      request = { ...parseRequest(form), clientCandidateId: candidateLocalId };
    } catch (error) {
      setAssessmentError(error instanceof Error ? error.message : "入力内容を確認してください。");
      return;
    }

    setLoading(true);
    try {
      const assessment = await requestAssessment(request);
      const saved: SavedCandidate = {
        localId: candidateLocalId,
        savedAt: new Date().toISOString(),
        label: candidateLabel(form, request, assessment.location.label),
        request,
        assessment,
      };
      setCandidates((current) => [saved, ...current].slice(0, 20));
      setActive(saved);
    } catch (error) {
      setAssessmentError(
        error instanceof Error
          ? error.message
          : "統合判定APIを利用できません。結果は作成されていません。",
      );
    } finally {
      setLoading(false);
    }
  }

  async function compareCandidates() {
    if (candidates.length < 2) return;
    setComparing(true);
    setComparisonError(null);
    try {
      setComparison(await requestComparison(candidates));
    } catch (error) {
      setComparison(null);
      setComparisonError(
        error instanceof Error
          ? error.message
          : "比較APIを利用できません。ローカルで順位は推測しません。",
      );
    } finally {
      setComparing(false);
    }
  }

  function removeCandidate(id: string) {
    setCandidates((current) => current.filter((candidate) => candidate.localId !== id));
    setActive((current) => {
      if (!current || current.localId !== id) return current;
      return null;
    });
    setComparison(null);
    setComparisonError(null);
  }

  return (
    <main className={styles.page}>
      <header className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>IYASHIRO LAND DECISION COPILOT</p>
          <h1>土地選び・物件判定コパイロット</h1>
          <p className={styles.heroLead}>
            住所・座標・物件URLから、R3、V15.3、RYUMYAK、ORBIT、歴史、HCLを同じ画面で確認します。
            結論は混ぜず、hard-vetoと欠測を先に示します。
          </p>
        </div>
        <nav className={styles.nav} aria-label="関連画面">
          <Link href="/">地図</Link>
          <Link href="/profile">土地カルテ</Link>
          <Link href="/nexus">NEXUS</Link>
        </nav>
      </header>

      <div className={styles.unknownBanner} role="note">
        <strong>UNKNOWNは安全ではありません。</strong>
        <span>データ未取得、対象外、位置の曖昧さを「問題なし」へ置き換えません。</span>
      </div>

      <div className={styles.workspace}>
        <aside className={styles.inputColumn}>
          <form className={styles.formCard} onSubmit={submit} noValidate>
            <div className={styles.formHeading}>
              <div>
                <p className={styles.cardKicker}>NEW CANDIDATE</p>
                <h2>候補を調べる</h2>
              </div>
              <span>最大20件比較</span>
            </div>

            <label className={styles.field} htmlFor="candidate-label">
              <span>候補名 <small>任意</small></span>
              <input
                id="candidate-label"
                value={form.candidateLabel}
                onChange={(event) => setTop("candidateLabel", event.target.value)}
                placeholder="例：目白 A物件"
              />
            </label>

            <fieldset className={styles.fieldset}>
              <legend>場所の指定</legend>
              <label className={styles.field} htmlFor="candidate-address">
                <span>住所</span>
                <input
                  id="candidate-address"
                  autoComplete="street-address"
                  value={form.address}
                  onChange={(event) => setTop("address", event.target.value)}
                  placeholder="東京都・川崎市・横浜市の住所"
                />
              </label>
              <div className={styles.twoColumns}>
                <label className={styles.field} htmlFor="candidate-latitude">
                  <span>緯度</span>
                  <input
                    id="candidate-latitude"
                    inputMode="decimal"
                    value={form.latitude}
                    onChange={(event) => setTop("latitude", event.target.value)}
                    placeholder="35.681236"
                  />
                </label>
                <label className={styles.field} htmlFor="candidate-longitude">
                  <span>経度</span>
                  <input
                    id="candidate-longitude"
                    inputMode="decimal"
                    value={form.longitude}
                    onChange={(event) => setTop("longitude", event.target.value)}
                    placeholder="139.767125"
                  />
                </label>
              </div>
              <p className={styles.helpText}>住所と座標を両方入力した場合、APIが解決結果と曖昧さを返します。</p>
            </fieldset>

            <label className={styles.field} htmlFor="property-url">
              <span>物件URL <small>任意</small></span>
              <input
                id="property-url"
                type="url"
                inputMode="url"
                value={form.propertyUrl}
                onChange={(event) => setTop("propertyUrl", event.target.value)}
                placeholder="https://..."
              />
              <small>取得できないサイトでは、下の手動補正を使えます。</small>
            </label>

            <details className={styles.formDetails}>
              <summary>物件情報を手動で補正</summary>
              <div className={styles.detailsBody}>
                <div className={styles.twoColumns}>
                  <label className={styles.field} htmlFor="manual-name">
                    <span>物件名</span>
                    <input id="manual-name" value={form.manual.name} onChange={(event) => setManual("name", event.target.value)} />
                  </label>
                  <label className={styles.field} htmlFor="manual-station">
                    <span>最寄駅</span>
                    <input id="manual-station" value={form.manual.station} onChange={(event) => setManual("station", event.target.value)} />
                  </label>
                </div>
                <label className={styles.field} htmlFor="manual-address">
                  <span>補正住所</span>
                  <input id="manual-address" value={form.manual.address} onChange={(event) => setManual("address", event.target.value)} />
                </label>
                <div className={styles.twoColumns}>
                  <label className={styles.field} htmlFor="manual-area">
                    <span>面積 m2</span>
                    <input id="manual-area" inputMode="decimal" value={form.manual.areaM2} onChange={(event) => setManual("areaM2", event.target.value)} />
                  </label>
                  <label className={styles.field} htmlFor="manual-layout">
                    <span>間取り</span>
                    <input id="manual-layout" value={form.manual.layout} onChange={(event) => setManual("layout", event.target.value)} />
                  </label>
                </div>
                <label className={styles.field} htmlFor="manual-memo">
                  <span>補正メモ</span>
                  <textarea id="manual-memo" rows={3} value={form.manual.memo} onChange={(event) => setManual("memo", event.target.value)} />
                </label>
              </div>
            </details>

            <fieldset className={styles.fieldset}>
              <legend>距離ゲート</legend>
              <div className={styles.radioGroup} aria-describedby="threshold-help">
                {([300, 500, 650] as DistanceThreshold[]).map((value) => (
                  <label key={value}>
                    <input
                      type="radio"
                      name="distanceThreshold"
                      value={value}
                      checked={form.policy.distanceThresholdM === value}
                      onChange={() => setForm((current) => ({
                        ...current,
                        policy: { ...current.policy, distanceThresholdM: value },
                      }))}
                    />
                    <span>{value}m</span>
                  </label>
                ))}
              </div>
              <p id="threshold-help" className={styles.helpText}>
                寺・墓地・大病院を同じ閾値で確認します。既定は500mです。
              </p>
              <label className={styles.checkRow}>
                <input
                  type="checkbox"
                  checked={form.policy.includeShrines}
                  onChange={(event) => setForm((current) => ({
                    ...current,
                    policy: { ...current.policy, includeShrines: event.target.checked },
                  }))}
                />
                <span><strong>神社も距離ゲートへ含める</strong><small>既定OFF。ONにした場合だけ同じ閾値で確認します。</small></span>
              </label>
            </fieldset>

            <details className={styles.formDetails}>
              <summary>
                <span>HOUSE COMPASS LAB 入力</span>
                <small>{form.hcl.enabled ? "ON" : "任意"}</small>
              </summary>
              <div className={styles.detailsBody}>
                <label className={styles.checkRow}>
                  <input type="checkbox" checked={form.hcl.enabled} onChange={(event) => setHcl("enabled", event.target.checked)} />
                  <span><strong>HCLを同時に確認する</strong><small>土地判定とは合算しません。</small></span>
                </label>
                <div className={styles.twoColumns}>
                  <DirectionSelect id="hcl-entrance" label="玄関方位" value={form.hcl.entranceDirection} onChange={(value) => setHcl("entranceDirection", value)} />
                  <DirectionSelect id="hcl-bedroom" label="寝室方位" value={form.hcl.bedroomDirection} onChange={(value) => setHcl("bedroomDirection", value)} />
                  <DirectionSelect id="hcl-desk" label="仕事机方位" value={form.hcl.workDeskDirection} onChange={(value) => setHcl("workDeskDirection", value)} />
                  <DirectionSelect id="hcl-kitchen" label="台所方位" value={form.hcl.kitchenDirection} onChange={(value) => setHcl("kitchenDirection", value)} />
                  <DirectionSelect id="hcl-head" label="就寝時の頭方位" value={form.hcl.headDirection} onChange={(value) => setHcl("headDirection", value)} />
                  <label className={styles.field} htmlFor="hcl-age">
                    <span>築年帯</span>
                    <select id="hcl-age" value={form.hcl.buildingAgeBand} onChange={(event) => setHcl("buildingAgeBand", event.target.value)}>
                      <option value="">未入力</option>
                      {ageBands.map((age) => <option key={age} value={age}>{age}</option>)}
                    </select>
                  </label>
                </div>
                <label className={styles.field} htmlFor="hcl-concerns">
                  <span>気になる点</span>
                  <textarea
                    id="hcl-concerns"
                    rows={3}
                    value={form.hcl.concerns}
                    onChange={(event) => setHcl("concerns", event.target.value)}
                    placeholder="玄関、寝室、水回り、道路との関係など"
                  />
                </label>
              </div>
            </details>

            {assessmentError && (
              <div className={styles.errorBox} role="alert">
                <strong>判定できませんでした</strong>
                <p>{assessmentError}</p>
                <small>API未接続・取得失敗時に代替の架空結果は表示しません。</small>
              </div>
            )}

            <button className={styles.primaryButton} type="submit" disabled={loading}>
              {loading ? "正本と事実レイヤーを確認中…" : "統合判定を実行"}
            </button>
          </form>

          <CandidateShelf
            candidates={candidates}
            activeId={active?.localId}
            comparing={comparing}
            onSelect={setActive}
            onRemove={removeCandidate}
            onCompare={() => { void compareCandidates(); }}
          />
        </aside>

        <section className={styles.outputColumn} aria-label="判定結果">
          {comparisonError && (
            <div className={styles.errorBox} role="alert">
              <strong>比較できませんでした</strong>
              <p>{comparisonError}</p>
              <small>ローカル推測による順位は表示しません。</small>
            </div>
          )}
          {comparison && <ComparisonResult comparison={comparison} />}
          {loading && (
            <div className={styles.loadingBox} role="status">
              <span aria-hidden="true" />
              <div><strong>判定中</strong><p>住所解決、正本セル、距離ゲート、各レイヤーを確認しています。</p></div>
            </div>
          )}
          {!loading && active && (
            <AssessmentResult
              assessment={active.assessment}
              thresholdM={active.request.policy.distanceThresholdM}
              includeShrines={active.request.policy.includeShrines}
            />
          )}
          {!loading && !active && (
            <div className={styles.welcomeCard}>
              <p className={styles.cardKicker}>HOW TO READ</p>
              <h2>候補地点を入力してください</h2>
              <ol>
                <li>住所・座標・物件URLのいずれかで地点を特定</li>
                <li>hard-vetoとUNKNOWNを先に確認</li>
                <li>4つの順位ビューと6つの事実レイヤーを個別に確認</li>
                <li>候補を2件以上保存し、サーバー比較を実行</li>
              </ol>
              <p>結果を作るためのモックデータは使いません。APIが利用できない場合は、その状態を明示します。</p>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
