"use strict";

let withdrawalMode = "fixed_infl";
let deflMode = "keep";
let chartPortfolio = null;
let chartSurvival = null;
let chartFailureTiming = null;
let simulationCancelRequested = false;
let simulationWasCancelled = false;
let progressHideTimer = null;

function cancelSimulation() {
  simulationCancelRequested = true;
  const button = document.getElementById("cancelSimulation");
  if (button) button.disabled = true;
  const text = document.getElementById("progressText");
  if (text) text.textContent = "中止処理中…";
}

function setDeflMode(mode) {
  deflMode = mode;
  document.getElementById("btn-defl-keep").classList.toggle("active", mode === "keep");
  document.getElementById("btn-defl-reduce").classList.toggle("active", mode === "reduce");
}

function setMode(mode) {
  withdrawalMode = mode;
  document.getElementById("btn-fixed-infl").classList.toggle("active", mode === "fixed_infl");
  document.getElementById("btn-dynamic").classList.toggle("active", mode === "dynamic");
  document.getElementById("field-withdrawal-amount").style.display = mode === "fixed_infl" ? "" : "none";
  document.getElementById("field-withdrawal-rate").style.display = mode === "dynamic" ? "" : "none";
  document.getElementById("field-min-wd").style.display = mode === "dynamic" ? "" : "none";
  updateWdHint();
}

function syncWithdrawalDefault() {
  const initial = parseFloat(document.getElementById("initialPortfolio").value) || 0;
  const el = document.getElementById("withdrawalAmount");
  if (el) el.value = Math.round(initial * 0.04);
  updateWdHint();
}

function updateWdHint() {
  if (withdrawalMode === "fixed_infl") {
    const amount = parseFloat(document.getElementById("withdrawalAmount").value) || 0;
    const el = document.getElementById("wd-hint");
    if (el) el.textContent = amount.toLocaleString() + "万円を毎年の年初に一括取崩し。以降はインフレ分を調整";
  } else {
    const initial = parseFloat(document.getElementById("initialPortfolio").value) || 0;
    const rate = parseFloat(document.getElementById("withdrawalRate").value) || 0;
    const el = document.getElementById("wd-hint-rate");
    if (el) el.textContent = "毎年の年初残高 × " + rate + "% を一括して取り崩します";
  }
  updateCashHint();
}

function updateInflHint() {
  const mean = parseFloat(document.getElementById("inflationRate").value) || 0;
  const std = parseFloat(document.getElementById("inflationStdDev").value) || 0;
  const el = document.getElementById("infl-hint");
  if (!el) return;
  if (std === 0) {
    el.textContent = "固定インフレ率（毎年一定）";
    el.className = "small-hint";
  } else {
    el.textContent = "68%確率で " + (mean - std).toFixed(1) + "%〜" + (mean + std).toFixed(1) + "% の範囲でランダム変動";
    el.className = "small-hint blue";
  }
}

function updateCashHint() {
  const bufYears = parseFloat(document.getElementById("cashBufferYears").value) || 0;
  const dropPct = parseFloat(document.getElementById("dropThreshold").value) || 0;
  let annualWd;
  if (withdrawalMode === "fixed_infl") {
    annualWd = parseFloat(document.getElementById("withdrawalAmount").value) || 0;
  } else {
    const initial = parseFloat(document.getElementById("initialPortfolio").value) || 0;
    const rate = parseFloat(document.getElementById("withdrawalRate").value) || 0;
    annualWd = Math.round(initial * rate / 100);
  }
  const initPortfolio = parseFloat(document.getElementById("initialPortfolio").value) || 0;
  const cashAmt = Math.round(annualWd * bufYears);
  const triggerAmt = Math.round(initPortfolio * (1 - dropPct / 100));
  const el = document.getElementById("cash-hint");
  if (!el) return;
  if (bufYears === 0) {
    el.textContent = "現金バッファが0年分のため、初年度から投資資産を取り崩します。";
    el.style.borderLeftColor = "#1d2430";
  } else if (dropPct === 0) {
    el.innerHTML = "現金バッファ <strong>" + bufYears + "年分（" + cashAmt.toLocaleString() +
      "万円）</strong>：投資資産が初期額を<strong>少しでも</strong>下回れば現金を使用。";
    el.style.borderLeftColor = "#f59e0b";
  } else {
    el.innerHTML = "現金バッファ <strong>" + bufYears + "年分（" + cashAmt.toLocaleString() +
      "万円）</strong>：投資資産が初期（" +
      initPortfolio.toLocaleString() + "万円）から <strong style=\"color:#c53030\">" +
      dropPct + "%を超えて下落</strong>（" + triggerAmt.toLocaleString() +
      "万円未満）で現金を優先使用。現金枯渇後は通常取崩しに戻ります。";
    el.style.borderLeftColor = "#ef4444";
  }
}

document.addEventListener("DOMContentLoaded", function () {
  syncWithdrawalDefault();
  updateInflHint();
  updateCashHint();
});

function randNorm2() {
  let u1;
  do { u1 = Math.random(); } while (u1 === 0);
  const r = Math.sqrt(-2 * Math.log(u1));
  const th = 2 * Math.PI * Math.random();
  return [r * Math.cos(th), r * Math.sin(th)];
}

function randNorm(mean, std) {
  const z = randNorm2()[0];
  return mean + std * z;
}

function percentile(sorted, p) {
  if (!sorted.length) return 0;
  return sorted[Math.min(Math.floor(p / 100 * sorted.length), sorted.length - 1)];
}

function fmtMan(val) {
  if (!Number.isFinite(val)) return "—";
  if (val < 0) return "−" + fmtMan(-val);
  if (val >= 10000) return (val / 10000).toFixed(2) + "億円";
  return Math.round(val).toLocaleString() + "万円";
}

function fmtPct(val, digits) {
  if (!Number.isFinite(val)) return "—";
  return (val * 100).toFixed(digits == null ? 1 : digits) + "%";
}

function updateReservoir(reservoir, item, seen, limit) {
  if (reservoir.length < limit) {
    reservoir.push(item);
    return;
  }
  const j = Math.floor(Math.random() * seen);
  if (j < limit) reservoir[j] = item;
}

function chooseReservoirSlot(reservoirLength, seen, limit) {
  if (reservoirLength < limit) return reservoirLength;
  const j = Math.floor(Math.random() * seen);
  return j < limit ? j : -1;
}

function quantileFromCounts(counts, total, q) {
  if (!total) return null;
  const target = Math.ceil(total * q);
  let cumulative = 0;
  for (let i = 0; i < counts.length; i++) {
    cumulative += counts[i];
    if (cumulative >= target) return i;
  }
  return counts.length - 1;
}

const PRIMARY_FAILURE_FEATURE_KEYS = [
  "earlyDownturn",
  "deepDrawdown",
  "longSlump",
  "highInflation",
  "slowRecovery"
];

const FAILURE_FEATURE_KEYS = PRIMARY_FAILURE_FEATURE_KEYS.concat("none");

const EARLY_DOWNTURN_MARKET_INDEX_THRESHOLD = 0.70;
const MARKET_DEEP_DRAWDOWN_THRESHOLD = 0.50;

const FAILURE_FEATURE_LABELS = {
  earlyDownturn: "開始5年以内の大幅不振",
  deepDrawdown: "市場の大幅下落",
  longSlump: "10年間の長期低迷",
  highInflation: "高インフレの継続",
  slowRecovery: "暴落後の回復遅延",
  none: "上記特徴なし"
};

function classifyFailure(r) {
  const tags = [];
  if (r.earlyDownturn) tags.push("earlyDownturn");
  if (r.maxDrawdown >= MARKET_DEEP_DRAWDOWN_THRESHOLD) tags.push("deepDrawdown");
  if (r.longSlump) tags.push("longSlump");
  if (r.highInflation) tags.push("highInflation");
  if (r.slowRecovery) tags.push("slowRecovery");
  if (!tags.length) tags.push("none");
  return tags;
}

function createFeatureOutcomeStats() {
  const result = {};
  FAILURE_FEATURE_KEYS.forEach(function (key) {
    result[key] = {
      withTotal: 0,
      withSuccesses: 0,
      withoutTotal: 0,
      withoutSuccesses: 0
    };
  });
  return result;
}

function updateFeatureOutcomeStats(stats, tags, succeeded) {
  FAILURE_FEATURE_KEYS.forEach(function (key) {
    const hasFeature = tags.indexOf(key) >= 0;
    const target = stats[key];
    if (hasFeature) {
      target.withTotal++;
      if (succeeded) target.withSuccesses++;
    } else {
      target.withoutTotal++;
      if (succeeded) target.withoutSuccesses++;
    }
  });
}

function summarizeFeatureOutcomes(stats) {
  const result = {};
  FAILURE_FEATURE_KEYS.forEach(function (key) {
    const s = stats[key];
    const withRate = s.withTotal ? s.withSuccesses / s.withTotal : null;
    const withoutRate = s.withoutTotal ? s.withoutSuccesses / s.withoutTotal : null;
    result[key] = {
      withRate: withRate,
      withoutRate: withoutRate,
      difference: withRate !== null && withoutRate !== null ? withRate - withoutRate : null,
      reliable: s.withTotal >= 30 && s.withoutTotal >= 30,
      withTotal: s.withTotal,
      withSuccesses: s.withSuccesses,
      withoutTotal: s.withoutTotal,
      withoutSuccesses: s.withoutSuccesses
    };
  });
  return result;
}

function combinationKey(tags) {
  const primary = PRIMARY_FAILURE_FEATURE_KEYS.filter(function (key) { return tags.indexOf(key) >= 0; });
  return primary.length ? primary.join("+") : "none";
}

function summarizeFailureCombinations(counts, failureCount) {
  return Object.keys(counts).map(function (key) {
    const tags = key === "none" ? ["none"] : key.split("+");
    return {
      key: key,
      label: tags.map(function (tag) { return FAILURE_FEATURE_LABELS[tag]; }).join("＋"),
      count: counts[key],
      share: failureCount ? counts[key] / failureCount : 0
    };
  }).sort(function (a, b) { return b.count - a.count || a.label.localeCompare(b.label, "ja"); }).slice(0, 5);
}

const WITHDRAWAL_SENSITIVITY_FACTORS = [0.80, 0.90, 1.00, 1.10, 1.20];

function createWithdrawalSensitivityStates(initialPortfolio, initialCash, initialWithdrawal) {
  return WITHDRAWAL_SENSITIVITY_FACTORS.map(function (factor) {
    return {
      factor: factor,
      portfolio: initialPortfolio,
      cash: initialCash,
      withdrawal: initialWithdrawal * factor,
      failed: false
    };
  });
}

function updateWithdrawalSensitivity(states, grossReturn, withdrawalInflationFactor,
    triggerLevel, successThreshold) {
  if (!states) return;
  states.forEach(function (state) {
    if (state.failed) return;
    const wdThisYear = state.withdrawal;
    const useCash = state.cash > 0 && state.portfolio < triggerLevel;
    if (useCash) {
      const fromCash = Math.min(state.cash, wdThisYear);
      state.cash -= fromCash;
      state.portfolio -= wdThisYear - fromCash;
    } else {
      state.portfolio -= wdThisYear;
      if (state.portfolio < 0 && state.cash > 0) {
        const fromCash = Math.min(state.cash, -state.portfolio);
        state.cash -= fromCash;
        state.portfolio += fromCash;
      }
    }
    state.portfolio = Math.max(state.portfolio, 0) * grossReturn;
    const total = state.portfolio + state.cash;
    if (total <= 0 || total < successThreshold) {
      state.failed = true;
      if (total <= 0) {
        state.portfolio = 0;
        state.cash = 0;
      }
    }
    state.withdrawal *= withdrawalInflationFactor;
  });
}

function chooseCombinationRepresentative(records, years) {
  if (!records || !records.length) return null;
  const metrics = [
    { key: "failureYear", scale: Math.max(years / 4, 1) },
    { key: "earlyMinReturn", scale: 0.20 },
    { key: "maxDrawdown", scale: 0.20 },
    { key: "worstTenYearReal", scale: 0.05 },
    { key: "maxFiveYearAppliedInflation", scale: 0.03 },
    { key: "maxUnderwaterYears", scale: 5 }
  ];
  metrics.forEach(function (metric) {
    const values = records.map(function (r) { return r[metric.key]; })
      .filter(Number.isFinite).sort(function (a, b) { return a - b; });
    metric.median = values.length ? percentile(values, 50) : null;
  });
  function score(r) {
    return metrics.reduce(function (total, metric) {
      if (metric.median === null) return total;
      return total + (Number.isFinite(r[metric.key])
        ? Math.abs(r[metric.key] - metric.median) / metric.scale
        : 1);
    }, 0);
  }
  return records.slice().sort(function (a, b) { return score(a) - score(b); })[0];
}

function chooseCombinationExamples(combinations, sampledByCombination, years) {
  return combinations.slice(0, 3).map(function (combo, index) {
    const record = chooseCombinationRepresentative(sampledByCombination[combo.key], years);
    return record ? {
      type: "combination",
      title: "第" + (index + 1) + "位の組み合わせ・代表例",
      combination: combo,
      record: record
    } : null;
  }).filter(Boolean);
}

async function runSimulation() {
  document.querySelectorAll(".panel-left > details").forEach(function (d) { d.open = true; });

  let allValid = true;
  document.querySelectorAll(".panel-left input[type=\"number\"]").forEach(function (el) {
    el.setCustomValidity("");
    if (el.offsetParent !== null && !el.reportValidity()) allValid = false;
  });
  if (!allValid) return;

  const initialPortfolio = parseFloat(document.getElementById("initialPortfolio").value) * 10000;
  const wdRate = parseFloat(document.getElementById("withdrawalRate").value) / 100;
  const wdAmount = parseFloat(document.getElementById("withdrawalAmount").value || 0) * 10000;
  const minWithdrawal = parseFloat(document.getElementById("minWithdrawal").value || 0) * 10000;
  const mu = parseFloat(document.getElementById("expectedReturn").value) / 100;
  const sigma = parseFloat(document.getElementById("stdDev").value) / 100;
  const inflMean = parseFloat(document.getElementById("inflationRate").value) / 100;
  const inflStd = parseFloat(document.getElementById("inflationStdDev").value) / 100;
  const successThreshold = parseFloat(document.getElementById("successThreshold").value) * 10000;
  const cashBufferYears = parseFloat(document.getElementById("cashBufferYears").value) || 0;
  const dropThreshold = parseFloat(document.getElementById("dropThreshold").value) / 100;
  const fxRatio = parseFloat(document.getElementById("fxRatio").value) / 100;
  const fxMean = parseFloat(document.getElementById("fxMean").value) / 100;
  const fxStd = parseFloat(document.getElementById("fxStd").value) / 100;
  const fxCorr = parseFloat(document.getElementById("fxCorr").value);
  const years = parseInt(document.getElementById("simYears").value, 10);
  const numSims = parseInt(document.getElementById("numSims").value, 10);

  const sigmaLog = Math.sqrt(Math.log(1 + sigma * sigma / ((1 + mu) * (1 + mu))));
  const muLog = Math.log(1 + mu) - 0.5 * sigmaLog * sigmaLog;
  const fxStdLog = Math.sqrt(Math.log(1 + fxStd * fxStd / ((1 + fxMean) * (1 + fxMean))));
  const muFxLog = Math.log(1 + fxMean) - 0.5 * fxStdLog * fxStdLog;
  const fxActive = fxRatio > 0;
  const sqrtRho2 = Math.sqrt(Math.max(0, 1 - fxCorr * fxCorr));

  const initialWd = withdrawalMode === "fixed_infl" ? wdAmount : initialPortfolio * wdRate;
  const cashBuffer = cashBufferYears * initialWd;
  const triggerLevel = initialPortfolio * (1 - dropThreshold);
  const initialTotal = initialPortfolio + cashBuffer;

  simulationCancelRequested = false;
  simulationWasCancelled = false;
  if (progressHideTimer !== null) {
    clearTimeout(progressHideTimer);
    progressHideTimer = null;
  }
  document.querySelectorAll(".run-btn:not(#cancelSimulation)").forEach(function (b) { b.disabled = true; });
  const cancelButton = document.getElementById("cancelSimulation");
  if (cancelButton) cancelButton.disabled = false;
  document.getElementById("progressArea").style.display = "";

  const CHUNK = 2000;
  const PATH_SAMPLE_LIMIT = 20000;
  const FAILURE_COMBINATION_SAMPLE_LIMIT = 200;
  const sampledPaths = [];
  const sampledFailuresByCombination = {};
  const failureYearCounts = new Int32Array(years + 1);
  const failureTypeCounts = {
    earlyDownturn: 0,
    deepDrawdown: 0,
    longSlump: 0,
    highInflation: 0,
    slowRecovery: 0,
    none: 0
  };
  const featureOutcomeStats = createFeatureOutcomeStats();
  const failureCombinationCounts = {};
  const sensitivitySampleSize = withdrawalMode === "fixed_infl" ? Math.min(numSims, 20000) : 0;
  const sensitivitySuccessCounts = new Int32Array(WITHDRAWAL_SENSITIVITY_FACTORS.length);
  let sampledPathSeen = 0;
  let failureSeen = 0;
  let successCount = 0;
  let totalCashPeriods = 0;
  let totalCashCoverRatio = 0;

  await new Promise(function (resolve) { setTimeout(resolve, 30); });

  try {
    for (let s = 0; s < numSims; s++) {
      let portfolio = initialPortfolio;
      let cash = cashBuffer;
      let wd = initialWd;
      let currentMinWd = minWithdrawal;
      let failed = false;
      let failureYear = null;
      let depleted = false;
      let marketIndex = 1;
      let marketPeak = 1;
      let maxDrawdown = 0;
      let negativeStreak = 0;
      let longestNegative = 0;
      let inflationProduct = 1;
      let appliedInflationSum = 0;
      let appliedInflationYears = 0;
      let firstFiveGrowth = 1;
      let firstTenGrowth = 1;
      let firstTenAnnualized = 0;
      const firstTenReturns = [];
      let earlyDownturn = false;
      let earlyMinReturn = 0;
      let longSlump = false;
      let worstTenYearReal = null;
      const rollingRealReturns = [];
      let rollingRealProduct = 1;
      let highInflation = false;
      let maxFiveYearAppliedInflation = null;
      const rollingAppliedInflation = [];
      let rollingAppliedInflationSum = 0;
      let underwaterYears = 0;
      let maxUnderwaterYears = 0;
      let severeDrawdownInEpisode = false;
      let yearsSinceSevereDrawdown = 0;
      let slowRecovery = false;
      let finalFeatureTags = null;
      const sensitivityStates = s < sensitivitySampleSize
        ? createWithdrawalSensitivityStates(initialPortfolio, cashBuffer, initialWd)
        : null;

      sampledPathSeen++;
      const pathSlot = chooseReservoirSlot(sampledPaths.length, sampledPathSeen, PATH_SAMPLE_LIMIT);
      const path = pathSlot >= 0 ? [(portfolio + cash) / 10000] : null;
      const realPath = pathSlot >= 0 ? [(portfolio + cash) / 10000] : null;

      for (let y = 0; y < years; y++) {
        const wasAtRisk = !failed;
        const inflThisYear = inflStd > 0 ? randNorm(inflMean, inflStd) : inflMean;
        const withdrawalInflation = (inflThisYear > 0 || deflMode === "reduce") ? inflThisYear : 0;
        const withdrawalInflationFactor = Math.max(0.01, 1 + withdrawalInflation);
        const z = randNorm2();
        const stockLogReturn = muLog + sigmaLog * z[0];
        const stockGross = Math.exp(stockLogReturn);
        let fxGross = 1;
        if (fxActive) {
          const zfx = fxCorr * z[0] + sqrtRho2 * z[1];
          fxGross = Math.exp(muFxLog + fxStdLog * zfx);
        }
        const grossReturn = stockGross * ((1 - fxRatio) + fxRatio * fxGross);
        const simpleReturn = grossReturn - 1;

        updateWithdrawalSensitivity(sensitivityStates, grossReturn, withdrawalInflationFactor,
          triggerLevel, successThreshold);

        if (depleted) {
          if (path) {
            path.push(0);
            realPath.push(0);
          }
          continue;
        }

        const wdThisYear = withdrawalMode === "dynamic"
          ? Math.max(portfolio * wdRate, currentMinWd)
          : wd;

        const useCash = cash > 0 && portfolio < triggerLevel;
        if (useCash) {
          totalCashPeriods++;
          const fromCash = Math.min(cash, wdThisYear);
          totalCashCoverRatio += wdThisYear > 0 ? fromCash / wdThisYear : 1;
          cash -= fromCash;
          portfolio -= wdThisYear - fromCash;
        } else {
          portfolio -= wdThisYear;
          if (portfolio < 0 && cash > 0) {
            const fromCash = Math.min(cash, -portfolio);
            cash -= fromCash;
            portfolio += fromCash;
          }
        }

        if (firstTenReturns.length < 10) {
          firstTenReturns.push(simpleReturn);
          firstTenGrowth *= grossReturn;
          if (firstTenReturns.length <= 5) firstFiveGrowth *= grossReturn;
          if (firstTenReturns.length === 10) firstTenAnnualized = Math.pow(firstTenGrowth, 0.1) - 1;
        }

        if (simpleReturn < 0) {
          negativeStreak++;
          longestNegative = Math.max(longestNegative, negativeStreak);
        } else {
          negativeStreak = 0;
        }

        marketIndex *= grossReturn;
        if (wasAtRisk) {
          if (marketIndex >= marketPeak) {
            marketPeak = marketIndex;
            underwaterYears = 0;
            severeDrawdownInEpisode = false;
            yearsSinceSevereDrawdown = 0;
          } else {
            const currentDrawdown = 1 - marketIndex / marketPeak;
            maxDrawdown = Math.max(maxDrawdown, currentDrawdown);
            underwaterYears++;
            maxUnderwaterYears = Math.max(maxUnderwaterYears, underwaterYears);
            if (currentDrawdown >= 0.20 && !severeDrawdownInEpisode) {
              severeDrawdownInEpisode = true;
              yearsSinceSevereDrawdown = 1;
            } else if (severeDrawdownInEpisode) {
              yearsSinceSevereDrawdown++;
            }
            if (yearsSinceSevereDrawdown >= 8) slowRecovery = true;
          }
        }
        inflationProduct *= Math.max(0.01, 1 + inflThisYear);
        if (wasAtRisk) {
          if (y < 5) {
            earlyMinReturn = Math.min(earlyMinReturn, marketIndex - 1);
            if (marketIndex <= EARLY_DOWNTURN_MARKET_INDEX_THRESHOLD) earlyDownturn = true;
          }
          const realGrossReturn = grossReturn / Math.max(0.01, 1 + inflThisYear);
          rollingRealReturns.push(realGrossReturn);
          rollingRealProduct *= realGrossReturn;
          if (rollingRealReturns.length > 10) rollingRealProduct /= rollingRealReturns.shift();
          if (rollingRealReturns.length === 10) {
            const rollingAnnualized = Math.pow(rollingRealProduct, 0.1) - 1;
            worstTenYearReal = worstTenYearReal === null
              ? rollingAnnualized
              : Math.min(worstTenYearReal, rollingAnnualized);
            if (rollingAnnualized < 0) longSlump = true;
          }
        }

        portfolio = Math.max(portfolio, 0) * grossReturn;

        const total = portfolio + cash;
        const first5Years = Math.min(5, firstTenReturns.length);
        const failedThisYear = wasAtRisk && (total <= 0 || total < successThreshold);

        if (failedThisYear) {
          failed = true;
          failureYear = y + 1;
          failureYearCounts[failureYear]++;
          const first10Years = firstTenReturns.length;
          const record = {
            annualReturns: firstTenReturns.slice(),
            failureYear: failureYear,
            first5Years: first5Years,
            first5Return: firstFiveGrowth - 1,
            first10Years: first10Years,
            first10Annualized: first10Years >= 10
              ? firstTenAnnualized
              : (first10Years > 0 ? Math.pow(firstTenGrowth, 1 / first10Years) - 1 : 0),
            earlyDownturn: earlyDownturn,
            earlyMinReturn: earlyMinReturn,
            maxDrawdown: maxDrawdown,
            longestNegative: longestNegative,
            longSlump: longSlump,
            worstTenYearReal: worstTenYearReal,
            highInflation: highInflation,
            maxFiveYearAppliedInflation: maxFiveYearAppliedInflation,
            slowRecovery: slowRecovery,
            maxUnderwaterYears: maxUnderwaterYears,
            avgAppliedInflation: appliedInflationYears > 0 ? appliedInflationSum / appliedInflationYears : null,
            appliedInflationYears: appliedInflationYears,
            assumedInflation: inflMean,
            assumedInflationStd: inflStd
          };
          record.tags = classifyFailure(record);
          finalFeatureTags = record.tags.slice();
          failureSeen++;
          record.tags.forEach(function (tag) { failureTypeCounts[tag]++; });
          const combo = combinationKey(record.tags);
          failureCombinationCounts[combo] = (failureCombinationCounts[combo] || 0) + 1;
          if (!sampledFailuresByCombination[combo]) sampledFailuresByCombination[combo] = [];
          updateReservoir(sampledFailuresByCombination[combo], record,
            failureCombinationCounts[combo], FAILURE_COMBINATION_SAMPLE_LIMIT);
        }

        if (withdrawalMode === "fixed_infl") {
          wd *= withdrawalInflationFactor;
        } else {
          currentMinWd *= withdrawalInflationFactor;
        }
        appliedInflationSum += withdrawalInflation;
        appliedInflationYears++;
        if (wasAtRisk && !failedThisYear && y + 1 < years) {
          rollingAppliedInflation.push(withdrawalInflation);
          rollingAppliedInflationSum += withdrawalInflation;
          if (rollingAppliedInflation.length > 5) {
            rollingAppliedInflationSum -= rollingAppliedInflation.shift();
          }
          if (rollingAppliedInflation.length === 5) {
            const rollingInflationAverage = rollingAppliedInflationSum / 5;
            maxFiveYearAppliedInflation = maxFiveYearAppliedInflation === null
              ? rollingInflationAverage
              : Math.max(maxFiveYearAppliedInflation, rollingInflationAverage);
            if (rollingInflationAverage >= inflMean + Math.max(inflStd, 0.01)) highInflation = true;
          }
        }

        if (total <= 0) {
          portfolio = 0;
          cash = 0;
          depleted = true;
        }
        if (path) {
          path.push((portfolio + cash) / 10000);
          realPath.push((portfolio + cash) / 10000 / inflationProduct);
        }
      }

      if (!failed) {
        successCount++;
        finalFeatureTags = classifyFailure({
          earlyDownturn: earlyDownturn,
          maxDrawdown: maxDrawdown,
          longSlump: longSlump,
          highInflation: highInflation,
          slowRecovery: slowRecovery
        });
      }
      updateFeatureOutcomeStats(featureOutcomeStats, finalFeatureTags || ["none"], !failed);
      if (sensitivityStates) {
        sensitivityStates.forEach(function (state, index) {
          if (!state.failed) sensitivitySuccessCounts[index]++;
        });
      }
      if (pathSlot >= 0) sampledPaths[pathSlot] = { path: path, realPath: realPath, failed: failed };

      if ((s + 1) % CHUNK === 0) {
        const pct = Math.round((s + 1) / numSims * 100);
        document.getElementById("progressFill").style.width = pct + "%";
        document.getElementById("progressText").textContent =
          "計算中… " + pct + "% (" + (s + 1).toLocaleString() + " / " + numSims.toLocaleString() + " 回)";
        await new Promise(function (resolve) { setTimeout(resolve, 0); });
        if (simulationCancelRequested) {
          simulationWasCancelled = true;
          document.getElementById("progressText").textContent = "計算を中止しました。結果は更新していません。";
          return;
        }
      }
    }

    document.getElementById("progressFill").style.width = "100%";
    document.getElementById("progressText").textContent = "完了！";

    const successRate = successCount / numSims * 100;
    const labels = Array.from({ length: years + 1 }, function (_, i) { return i + "年"; });
    const pctLines = { p10: [], p25: [], p50: [], p75: [], p90: [] };
    const realP50 = [];
    const survivalRates = [];

    for (let y = 0; y <= years; y++) {
      const vals = sampledPaths.map(function (p) { return p.path[y]; }).sort(function (a, b) { return a - b; });
      const realVals = sampledPaths.map(function (p) { return p.realPath[y]; }).sort(function (a, b) { return a - b; });
      pctLines.p10.push(percentile(vals, 10));
      pctLines.p25.push(percentile(vals, 25));
      pctLines.p50.push(percentile(vals, 50));
      pctLines.p75.push(percentile(vals, 75));
      pctLines.p90.push(percentile(vals, 90));
      realP50.push(percentile(realVals, 50));

      let aliveAtYear = numSims;
      for (let fy = 1; fy <= y; fy++) aliveAtYear -= failureYearCounts[fy];
      survivalRates.push(aliveAtYear / numSims * 100);
    }

    const finalVals = sampledPaths.map(function (p) { return p.path[years]; }).sort(function (a, b) { return a - b; });
    const medianFinalRaw = percentile(finalVals, 50);
    const p10FinalRaw = percentile(finalVals, 10);
    const p25FinalRaw = percentile(finalVals, 25);
    const p90FinalRaw = percentile(finalVals, 90);
    const finalRealVals = sampledPaths.map(function (p) { return p.realPath[years]; }).sort(function (a, b) { return a - b; });
    const realMedianRaw = percentile(finalRealVals, 50);
    const realP10Raw = percentile(finalRealVals, 10);
    const realP90Raw = percentile(finalRealVals, 90);

    const failureCombinations = summarizeFailureCombinations(failureCombinationCounts, failureSeen);
    const failureExampleSampleSize = Object.keys(sampledFailuresByCombination).reduce(function (total, key) {
      return total + sampledFailuresByCombination[key].length;
    }, 0);
    const failureSummary = {
      count: failureSeen,
      q25Year: quantileFromCounts(failureYearCounts, failureSeen, 0.25),
      medianYear: quantileFromCounts(failureYearCounts, failureSeen, 0.50),
      q75Year: quantileFromCounts(failureYearCounts, failureSeen, 0.75),
      counts: Array.from(failureYearCounts),
      types: failureTypeCounts,
      comparisons: summarizeFeatureOutcomes(featureOutcomeStats),
      combinations: failureCombinations,
      examples: chooseCombinationExamples(failureCombinations, sampledFailuresByCombination, years),
      sampleSize: failureExampleSampleSize,
      combinationSampleLimit: FAILURE_COMBINATION_SAMPLE_LIMIT
    };

    const avgCashPeriods = totalCashPeriods / numSims;
    const avgCashCoverRate = totalCashPeriods > 0 ? totalCashCoverRatio / totalCashPeriods * 100 : null;
    const withdrawalSensitivity = sensitivitySampleSize ? WITHDRAWAL_SENSITIVITY_FACTORS.map(function (factor, index) {
      return {
        factor: factor,
        annualWithdrawal: initialWd * factor,
        successRate: sensitivitySuccessCounts[index] / sensitivitySampleSize * 100
      };
    }) : [];

    renderResults({
      successRate: successRate,
      successCount: successCount,
      numSims: numSims,
      labels: labels,
      years: years,
      pctLines: pctLines,
      realP50: realP50,
      survivalRates: survivalRates,
      medianFinal: fmtMan(medianFinalRaw),
      p10Final: fmtMan(p10FinalRaw),
      p25Final: fmtMan(p25FinalRaw),
      p90Final: fmtMan(p90FinalRaw),
      realMedian: fmtMan(realMedianRaw),
      realP10: fmtMan(realP10Raw),
      realP90: fmtMan(realP90Raw),
      inflMean: inflMean,
      inflStd: inflStd,
      successThreshold: successThreshold,
      mu: mu,
      sigma: sigma,
      initialPortfolio: initialPortfolio,
      initialWd: initialWd,
      wdRate: wdRate,
      minWithdrawal: minWithdrawal,
      wdMode: withdrawalMode,
      cashBuffer: cashBuffer,
      dropThreshold: dropThreshold,
      avgCashPeriods: avgCashPeriods,
      avgCashCoverRate: avgCashCoverRate,
      fxRatio: fxRatio,
      fxMean: fxMean,
      fxStd: fxStd,
      fxCorr: fxCorr,
      failureSummary: failureSummary,
      withdrawalSensitivity: withdrawalSensitivity,
      sensitivitySampleSize: sensitivitySampleSize,
      percentileSampleSize: sampledPaths.length
    });
  } finally {
    document.querySelectorAll(".run-btn:not(#cancelSimulation)").forEach(function (b) { b.disabled = false; });
    const cancelButton = document.getElementById("cancelSimulation");
    if (cancelButton) cancelButton.disabled = true;
    progressHideTimer = setTimeout(function () {
      document.getElementById("progressArea").style.display = "none";
      progressHideTimer = null;
    }, simulationWasCancelled ? 5000 : 2000);
  }
}

function failureExampleHtml(example) {
  const r = example.record;
  const combo = example.combination;
  const longSlumpText = Number.isFinite(r.worstTenYearReal)
    ? fmtPct(r.worstTenYearReal, 1)
    : "10年間に未到達";
  const inflationText = Number.isFinite(r.maxFiveYearAppliedInflation)
    ? fmtPct(r.maxFiveYearAppliedInflation, 1)
    : "5年間の判定期間なし";
  const returns = r.annualReturns.slice(0, 10).map(function (v, i) {
    return v == null ? "" : "<span style=\"white-space:nowrap\">" + (i + 1) + "年目 " + fmtPct(v, 1) + "</span>";
  }).filter(Boolean).join(" / ");
  return [
    "<div class=\"metric-card\" style=\"min-width:0\">",
    "<div class=\"metric-label\">" + example.title + "</div>",
    "<div style=\"font-weight:700;line-height:1.5;margin:5px 0\">" + combo.label + "</div>",
    "<div class=\"metric-sub\">" + combo.count.toLocaleString() + "シナリオ／失敗群の" +
      (combo.share * 100).toFixed(1) + "%</div>",
    "<div style=\"font-family:var(--hand);font-size:1.35rem;font-weight:700;color:var(--danger);margin:5px 0\">",
    r.failureYear + "年目に基準割れ</div>",
    "<div class=\"metric-sub\" style=\"line-height:1.7;text-align:left\">",
    "開始5年以内の最低累積リターン：<strong>" + fmtPct(r.earlyMinReturn, 1) + "</strong><br>",
    "市場の最大下落率：<strong>−" + fmtPct(r.maxDrawdown, 1) + "</strong><br>",
    "最悪の10年間・実質年率：<strong>" + longSlumpText + "</strong><br>",
    "最も高い5年間の平均反映インフレ率：<strong>" + inflationText + "</strong><br>",
    "最長の回復待ち期間：<strong>" + r.maxUnderwaterYears + "年</strong>",
    "</div>",
    "<details style=\"margin-top:8px\"><summary style=\"cursor:pointer;font-size:12px\">最初の10年の市場リターン</summary>",
    "<div style=\"font-size:11px;line-height:1.8;margin-top:6px;color:var(--muted)\">" + returns + "</div></details>",
    "</div>"
  ].join("");
}

function renderFailureAnalysis(d) {
  const f = d.failureSummary;
  if (!f.count) {
    return [
      "<div class=\"sketch-card\">",
      "<h3><span class=\"num\">D</span> 失敗シナリオ分析</h3>",
      "<div class=\"note accent\">今回の条件では失敗シナリオがありませんでした。取崩額や期間を変えると、失敗シナリオの特徴が表示されます。</div>",
      "</div>"
    ].join("");
  }

  const examples = f.examples.map(failureExampleHtml).join("");
  const typeTotal = Math.max(f.count, 1);
  function typePct(key) { return (f.types[key] / typeTotal * 100).toFixed(1) + "%"; }
  function comparisonCells(key) {
    const c = f.comparisons[key];
    const withRate = c && c.withRate !== null ? (c.withRate * 100).toFixed(1) + "%" : "—";
    const withoutRate = c && c.withoutRate !== null ? (c.withoutRate * 100).toFixed(1) + "%" : "—";
    let difference = "—";
    if (c && c.difference !== null) {
      const points = c.difference * 100;
      difference = (points > 0 ? "+" : points < 0 ? "−" : "±") + Math.abs(points).toFixed(1) + "ポイント";
      if (!c.reliable) difference += "（参考）";
    }
    const detail = c ? "特徴あり：" + c.withSuccesses.toLocaleString() + "成功／" +
      c.withTotal.toLocaleString() + "シナリオ、特徴なし：" + c.withoutSuccesses.toLocaleString() + "成功／" +
      c.withoutTotal.toLocaleString() + "シナリオ" : "";
    return "<td style=\"text-align:right\" title=\"" + detail + "\">" + withRate +
      "</td><td style=\"text-align:right\" title=\"" + detail + "\">" + withoutRate +
      "</td><td style=\"text-align:right\">" + difference + "</td>";
  }
  function featureRow(label, key) {
    return "<tr><td>" + label + "</td><td style=\"text-align:right\">" + typePct(key) + "</td>" + comparisonCells(key) + "</tr>";
  }

  return [
    "<div class=\"sketch-card\">",
    "<h3><span class=\"num\">D</span> 失敗シナリオ分析</h3>",
    "<div class=\"note orange\" style=\"margin-bottom:12px\">",
    "<strong>成功率と中央値は別の指標です。</strong> 成功率は基準割れの有無、中央値は全シナリオの真ん中を示します。",
    "成功率が50%を超えると、中央値が大きくても矛盾ではありません。",
    "</div>",
    "<div class=\"failure-summary-grid\" style=\"margin-bottom:14px\">",
    "<div class=\"metric-card\"><div class=\"metric-label\">失敗シナリオ</div><div class=\"metric-value small\" style=\"color:var(--danger)\">",
    f.count.toLocaleString(), "</div><div class=\"metric-sub\">全", d.numSims.toLocaleString(), "回中</div></div>",
    "<div class=\"metric-card\"><div class=\"metric-label\">失敗年・中央値</div><div class=\"metric-value small\">",
    f.medianYear, "年目</div><div class=\"metric-sub\">失敗群の真ん中</div></div>",
    "<div class=\"metric-card\"><div class=\"metric-label\">失敗の中央50%</div><div class=\"metric-value small\">",
    f.q25Year, "〜", f.q75Year, "年目</div><div class=\"metric-sub\">早い25%〜遅い25%</div></div>",
    "<div class=\"metric-card\"><div class=\"metric-label\">代表例の抽出候補</div><div class=\"metric-value small\">",
    f.sampleSize.toLocaleString(), "件</div><div class=\"metric-sub\">各組み合わせから最大", f.combinationSampleLimit,
    "件を無作為抽出</div></div>",
    "</div>",
    "<div class=\"charts-row\" style=\"grid-template-columns:1fr\">",
    "<div class=\"chart-card\"><div class=\"chart-title\"><span class=\"num\">D1</span> 失敗した年の分布</div>",
    "<div class=\"chart-wrap\"><canvas id=\"chartFailureTiming\"></canvas></div></div></div>",
    "<div style=\"overflow-x:auto;margin-top:14px\"><table class=\"stats-table\" style=\"min-width:900px\">",
    "<tr><th>失敗シナリオの特徴（複数該当可）</th><th>失敗群内</th><th>特徴あり<br>成功率</th><th>特徴なし<br>成功率</th><th>成功率差</th></tr>",
    featureRow("開始5年以内の大幅不振（累積リターンが一度でも−30%以下）", "earlyDownturn"),
    featureRow("市場の大幅下落（最高値から50%以上下落）", "deepDrawdown"),
    featureRow("10年間の長期低迷（任意の10年間の実質年率リターン0%未満）", "longSlump"),
    featureRow("高インフレの継続（任意の5年間が設定平均＋基準以上）", "highInflation"),
    featureRow("暴落後の回復遅延（20%以上下落後、8年以上最高値を回復せず）", "slowRecovery"),
    featureRow("上記特徴なし", "none"),
    "</table></div>",
    f.combinations.length ? [
      "<h4 style=\"font-family:var(--hand);margin:16px 0 8px\">失敗群で多かった特徴の組み合わせ</h4>",
      "<div style=\"overflow-x:auto\"><table class=\"stats-table\" style=\"min-width:620px\">",
      "<tr><th>特徴の組み合わせ（上位5件）</th><th>失敗シナリオ数</th><th>失敗群内</th></tr>",
      f.combinations.map(function (combo) {
        return "<tr><td>" + combo.label + "</td><td style=\"text-align:right\">" +
          combo.count.toLocaleString() + "</td><td style=\"text-align:right\">" +
          (combo.share * 100).toFixed(1) + "%</td></tr>";
      }).join(""),
      "</table></div>"
    ].join("") : "",
    examples ? [
      "<h4 style=\"font-family:var(--hand);margin:16px 0 8px\">上位3組の代表的な失敗シナリオ</h4>",
      "<div class=\"failure-example-grid\">",
      examples,
      "</div>"
    ].join("") : "",
    "<div class=\"note\" style=\"margin-top:12px\">",
    "<strong>成功率差：</strong>「特徴あり成功率 − 特徴なし成功率」です。マイナスほど、その特徴があるシナリオで最終年まで残った割合が低かったことを示します。率にカーソルを合わせるとシナリオ数を確認できます。比較群が30シナリオ未満の場合は参考値と表示します。<br>",
    "<strong>注意：</strong>特徴は原因を断定するものではなく、成功率差も因果的な寄与度ではありません。1つのシナリオに複数付くため「失敗群内」の合計は100%にならないことがあります。",
    "10年間の長期低迷など、一定期間を完了しないと付かない特徴もあります。このため、特徴ありの高い成功率は『その期間を耐えたシナリオの特徴』を表す場合があります。組み合わせと併せて複合的に読んでください。<br>",
    "<strong>代表例：</strong>上位3つの組み合わせごとに、抽出候補の中から失敗年と各特徴指標が中央値に近いシナリオを表示しています。極端な最悪例ではなく、過去の実例でもありません。",
    "</div>",
    "</div>"
  ].join("");
}

function renderWithdrawalPlanAnalysis(d) {
  const initialTotal = d.initialPortfolio + d.cashBuffer;
  const actualInitialWithdrawal = d.wdMode === "fixed_infl"
    ? d.initialWd
    : Math.max(d.initialPortfolio * d.wdRate, d.minWithdrawal);
  const totalRate = initialTotal > 0 ? actualInitialWithdrawal / initialTotal : null;
  const investmentRate = d.initialPortfolio > 0 ? actualInitialWithdrawal / d.initialPortfolio : null;
  const coverageYears = actualInitialWithdrawal > 0 ? initialTotal / actualInitialWithdrawal : null;
  const sensitivityRows = d.withdrawalSensitivity.map(function (row) {
    const difference = Math.round((row.factor - 1) * 100);
    const differenceLabel = difference === 0 ? "現在額" : (difference > 0 ? "+" : "−") + Math.abs(difference) + "%";
    return "<tr" + (difference === 0 ? " style=\"font-weight:700;background:rgba(72,213,137,.10)\"" : "") + ">" +
      "<td>" + fmtMan(row.annualWithdrawal / 10000) + "/年</td><td style=\"text-align:right\">" +
      differenceLabel + "</td><td style=\"text-align:right\">" + row.successRate.toFixed(1) + "%</td></tr>";
  }).join("");

  return [
    "<div class=\"sketch-card\">",
    "<h3><span class=\"num\">P</span> 取崩し計画の負担確認</h3>",
    "<div class=\"failure-summary-grid\" style=\"margin-bottom:14px\">",
    "<div class=\"metric-card\"><div class=\"metric-label\">当初取崩率（総資産ベース）</div><div class=\"metric-value small\">",
    fmtPct(totalRate, 2), "</div><div class=\"metric-sub\">投資資産＋現金バッファを分母</div></div>",
    "<div class=\"metric-card\"><div class=\"metric-label\">当初取崩率（投資資産のみ）</div><div class=\"metric-value small\">",
    fmtPct(investmentRate, 2), "</div><div class=\"metric-sub\">現金バッファを除く参考値</div></div>",
    "<div class=\"metric-card\"><div class=\"metric-label\">初期総資産は何年分か</div><div class=\"metric-value small\">",
    coverageYears === null ? "—" : coverageYears.toFixed(1) + "年分", "</div><div class=\"metric-sub\">運用益・インフレを考慮しない単純比率</div></div>",
    "<div class=\"metric-card\"><div class=\"metric-label\">設定期間</div><div class=\"metric-value small\">",
    d.years, "年間</div><div class=\"metric-sub\">成功判定までの期間</div></div>",
    "</div>",
    d.withdrawalSensitivity.length ? [
      "<h4 style=\"font-family:var(--hand);margin:0 0 8px\">取崩額を変えた場合の成功率</h4>",
      "<div style=\"overflow-x:auto\"><table class=\"stats-table\" style=\"min-width:520px\">",
      "<tr><th>初年度の年間取崩額</th><th>現在額との差</th><th>成功率</th></tr>",
      sensitivityRows,
      "</table></div>",
      "<div class=\"note\" style=\"margin-top:10px\">5つの取崩額を<strong>同じ市場・インフレ・為替シナリオ</strong>で比較しています。",
      "初期の投資資産と現金バッファ額は現在の設定で固定し、各取崩額は同じインフレ率で増減します。比較標本は",
      d.sensitivitySampleSize.toLocaleString(), "シナリオです。固定的な安全率を示すものではなく、現在額付近で成功率がどの程度変わるかを見るための感応度です。</div>"
    ].join("") : "<div class=\"note\">取崩額別の成功率比較は、定額取崩しモードで表示します。</div>",
    "</div>"
  ].join("");
}

function renderResults(d) {
  const rateClass = d.successRate >= 80 ? "success-rate" : d.successRate >= 60 ? "success-rate warn" : "success-rate danger";
  const thresholdLabel = fmtMan(d.successThreshold / 10000);
  const succSymbol = d.successThreshold > 0 ? "≥" : "&gt;";
  const failSymbol = d.successThreshold > 0 ? "&lt;" : "≤";
  const succWord = d.successThreshold > 0 ? thresholdLabel + " 以上" : thresholdLabel + " を上回っている状態";
  const inflNote = d.inflStd > 0
    ? "平均 " + (d.inflMean * 100).toFixed(1) + "%・標準偏差 " + (d.inflStd * 100).toFixed(1) + "%（変動）"
    : (d.inflMean * 100).toFixed(1) + "%（固定）";
  const fxNote = d.fxRatio > 0
    ? "外貨比率" + (d.fxRatio * 100).toFixed(0) + "%・平均" + (d.fxMean * 100).toFixed(1) +
      "%・標準偏差" + (d.fxStd * 100).toFixed(1) + "%・相関" + d.fxCorr
    : "為替影響なし（外貨比率0%）";
  const markerPos = Math.max(0, Math.min(100, d.successRate));

  const html = [
    "<div class=\"mode-banner annual\">年次シミュレーション（年初に1年分を一括取崩し）</div>",
    "<div class=\"success-row\">",
    "<div class=\"metric-card hero\"><div class=\"metric-label\">成功率</div><div class=\"metric-value " + rateClass + "\">",
    d.successRate.toFixed(1), "<span style=\"font-size:1.5rem\">%</span></div><div class=\"metric-sub\">",
    d.successCount.toLocaleString(), " / ", d.numSims.toLocaleString(), " 回が成功</div>",
    "<div class=\"band\"><div class=\"seg s-danger\" style=\"flex:60\"></div>",
    "<div class=\"seg s-warn\" style=\"flex:20\"></div>",
    "<div class=\"seg s-ok\" style=\"flex:20\"></div>",
    "<div class=\"marker\" style=\"left:" + markerPos + "%\"></div></div>",
    "<div class=\"band-legend\"><span style=\"left:0\">0%</span>",
    "<span style=\"left:60%;transform:translateX(-50%)\">60%</span>",
    "<span style=\"left:80%;transform:translateX(-50%)\">80%</span>",
    "<span style=\"right:0\">100%</span></div></div>",
    "<div class=\"metric-card\"><div class=\"metric-label\">失敗率</div><div class=\"metric-value small\" style=\"color:var(--danger)\">",
    (100 - d.successRate).toFixed(1), "<span style=\"font-size:.85rem\">%</span></div><div class=\"metric-sub\">残高 ", failSymbol, " ", thresholdLabel, "</div></div>",
    "<div class=\"metric-card\"><div class=\"metric-label\">名目中央値</div><div class=\"metric-value small\">", d.medianFinal,
    "</div><div class=\"metric-sub\">最終時点・額面</div></div>",
    "<div class=\"metric-card\"><div class=\"metric-label\">実質中央値</div><div class=\"metric-value small\" style=\"color:#7c3aed\">",
    d.realMedian, "</div><div class=\"metric-sub\">最終時点・購買力ベース</div></div></div>",
    renderWithdrawalPlanAnalysis(d),
    "<div class=\"charts-row\">",
    "<div class=\"chart-card\"><div class=\"chart-title\"><span class=\"num\">A</span> 資産推移（パーセンタイル帯）</div><div class=\"chart-wrap\"><canvas id=\"chartPortfolio\"></canvas></div></div>",
    "<div class=\"chart-card\"><div class=\"chart-title\"><span class=\"num\">B</span> 年別成功状態率（残高 ", succSymbol, " ", thresholdLabel,
    "）</div><div class=\"chart-wrap\"><canvas id=\"chartSurvival\"></canvas></div></div></div>",
    "<div class=\"sketch-card\"><h3><span class=\"num\">C</span> シミュレーション統計サマリー</h3>",
    "<table class=\"stats-table\"><tr><th>指標</th><th style=\"text-align:right\">値</th></tr>",
    "<tr><td>成功率（総資産が毎年末に " + succWord + "）</td><td>" + d.successRate.toFixed(2) + "%</td></tr>",
    "<tr><td>失敗率</td><td>" + (100 - d.successRate).toFixed(2) + "%</td></tr>",
    "<tr class=\"section-row\"><td colspan=\"2\">── 最終資産分布（名目）──</td></tr>",
    "<tr><td>上位10%</td><td>" + d.p90Final + "</td></tr><tr><td>中央値</td><td>" + d.medianFinal + "</td></tr>",
    "<tr><td>下位25%</td><td>" + d.p25Final + "</td></tr><tr><td>下位10%</td><td>" + d.p10Final + "</td></tr>",
    "<tr class=\"section-row\"><td colspan=\"2\">── 実質額（各シナリオで発生した累積インフレで換算）──</td></tr>",
    "<tr><td>上位10%（実質）</td><td>" + d.realP90 + "</td></tr><tr><td>中央値（実質）</td><td>" + d.realMedian + "</td></tr>",
    "<tr><td>下位10%（実質）</td><td>" + d.realP10 + "</td></tr>",
    d.cashBuffer > 0 ? [
      "<tr class=\"section-row\"><td colspan=\"2\">── 現金バッファ ──</td></tr>",
      "<tr><td>初期現金バッファ</td><td>" + fmtMan(d.cashBuffer / 10000) + "</td></tr>",
      "<tr><td>発動閾値</td><td>" + fmtMan(d.initialPortfolio * (1 - d.dropThreshold) / 10000) + " 未満</td></tr>",
      "<tr><td>平均現金使用期間</td><td>" + d.avgCashPeriods.toFixed(1) + " 年</td></tr>",
      d.avgCashCoverRate !== null ? "<tr><td>現金使用年の平均カバー率</td><td>" + d.avgCashCoverRate.toFixed(1) + "%</td></tr>" : ""
    ].join("") : "",
    "<tr><td>計算モード</td><td>年次（年初取崩し・年間リターン）</td></tr>",
    "<tr><td>シミュレーション回数</td><td>" + d.numSims.toLocaleString() + " 回</td></tr>",
    "<tr><td>資産分布の計算標本</td><td>" + d.percentileSampleSize.toLocaleString() + " 回</td></tr></table></div>",
    renderFailureAnalysis(d),
    "<div class=\"note accent\"><strong>計算条件：</strong><br>",
    "• 年初に1年分を一括取崩し、その後に年間リターンを適用<br>",
    "• 株式リターン " + (d.mu * 100).toFixed(2) + "%（年率算術平均）・リスク " + (d.sigma * 100).toFixed(2) + "%（年率）<br>",
    "• 為替：" + fxNote + "<br>• インフレ率：" + inflNote + "（年末に調整）<br>",
    d.wdMode === "fixed_infl"
      ? "• 取崩額：初年度 " + fmtMan(d.initialWd / 10000) + "/年、以降インフレ時に増額、デフレ時は" + (deflMode === "reduce" ? "減額" : "変更なし") + "<br>"
      : "• 取崩額：毎年の年初残高 × " + (d.wdRate * 100).toFixed(1) + "%、最低額はインフレ連動<br>",
    "• 成功基準：各年末の総資産（投資＋現金）", succSymbol, " <strong>", thresholdLabel, "</strong>",
    d.successThreshold === 0 ? "（ちょうど0円は失敗扱い）" : "", "<br>",
    d.cashBuffer > 0 ? "• 現金バッファ " + fmtMan(d.cashBuffer / 10000) + "：発動ライン割れ時に優先使用<br>" : "",
    "• 各年のリターンは独立と仮定。過去に存在したかや発生頻度を判定する機能ではありません。</div>"
  ].join("");

  const resultPanel = document.getElementById("resultPanel");
  resultPanel.innerHTML = html;
  resultPanel.style.display = "flex";
  resultPanel.style.flexDirection = "column";
  resultPanel.style.gap = "16px";
  drawPortfolioChart(d.labels, d.pctLines, d.realP50);
  drawSurvivalChart(d.labels, d.survivalRates);
  if (d.failureSummary.count) drawFailureTimingChart(d.labels, d.failureSummary.counts);
}

function drawPortfolioChart(labels, pct, realP50Line) {
  const ctx = document.getElementById("chartPortfolio").getContext("2d");
  if (chartPortfolio) chartPortfolio.destroy();
  const ymax = Math.max.apply(null, pct.p90.concat([1]));
  chartPortfolio = new Chart(ctx, {
    type: "line",
    data: { labels: labels, datasets: [
      { label: "上位10%", data: pct.p90, borderColor: "#16a34a", borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.3 },
      { label: "上位25%", data: pct.p75, borderColor: "#86efac", backgroundColor: "rgba(134,239,172,0.18)", borderWidth: 1.5, pointRadius: 0, fill: "+1", tension: 0.3 },
      { label: "中央値（名目）", data: pct.p50, borderColor: "#1d2430", borderWidth: 2.5, pointRadius: 0, fill: false, tension: 0.3 },
      { label: "実質中央値", data: realP50Line, borderColor: "#7c3aed", borderWidth: 2, borderDash: [6, 4], pointRadius: 0, fill: false, tension: 0.3 },
      { label: "下位25%", data: pct.p25, borderColor: "#fca5a5", borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.3 },
      { label: "下位10%", data: pct.p10, borderColor: "#ef4444", borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.3 }
    ]},
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { font: { family: "JetBrains Mono", size: 10 }, boxWidth: 14 } },
        tooltip: { callbacks: { label: function (c) { return " " + c.dataset.label + ": " + fmtMan(c.parsed.y); } } } },
      scales: {
        x: { ticks: { maxTicksLimit: 10, font: { family: "JetBrains Mono", size: 10 } }, grid: { display: false } },
        y: { max: ymax, ticks: { callback: function (v) { return fmtMan(v); } }, grid: { color: "rgba(29,36,48,0.06)" } }
      }
    }
  });
}

function drawSurvivalChart(labels, rates) {
  const ctx = document.getElementById("chartSurvival").getContext("2d");
  if (chartSurvival) chartSurvival.destroy();
  chartSurvival = new Chart(ctx, {
    type: "line",
    data: { labels: labels, datasets: [
      { label: "成功状態率", data: rates, borderColor: "#16a34a", backgroundColor: "rgba(74,222,128,0.18)", fill: true, borderWidth: 2.5, pointRadius: 0, tension: 0.3 },
      { label: "80%ライン", data: Array(labels.length).fill(80), borderColor: "#22c55e", borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0, fill: false },
      { label: "60%ライン", data: Array(labels.length).fill(60), borderColor: "#f59e0b", borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0, fill: false }
    ]},
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { font: { family: "JetBrains Mono", size: 10 }, boxWidth: 14 } },
        tooltip: { callbacks: { label: function (c) { return " " + c.dataset.label + ": " + c.parsed.y.toFixed(1) + "%"; } } } },
      scales: {
        x: { ticks: { maxTicksLimit: 10, font: { family: "JetBrains Mono", size: 10 } }, grid: { display: false } },
        y: { min: 0, max: 100, ticks: { callback: function (v) { return v + "%"; } }, grid: { color: "rgba(29,36,48,0.06)" } }
      }
    }
  });
}

function drawFailureTimingChart(labels, counts) {
  const canvas = document.getElementById("chartFailureTiming");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (chartFailureTiming) chartFailureTiming.destroy();
  chartFailureTiming = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels.slice(1),
      datasets: [{ label: "その年に初めて失敗した回数", data: counts.slice(1), backgroundColor: "rgba(239,68,68,0.45)", borderColor: "#ef4444", borderWidth: 1 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { font: { family: "JetBrains Mono", size: 10 } } } },
      scales: {
        x: { ticks: { maxTicksLimit: 12, font: { family: "JetBrains Mono", size: 10 } }, grid: { display: false } },
        y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "rgba(29,36,48,0.06)" } }
      }
    }
  });
}
