/**
 * x-post-trigger: Cloudflare Workers Scheduled
 *
 * 指定時刻に GitHub Actions のワークフローを workflow_dispatch でトリガーする。
 * GitHub Actions の built-in cron は遅延が常態化しているため、こちらを正とする。
 *
 * 設計（2026-06-13 簡素化版・救済枠なし）:
 *   JST 05:35 → deploy.yml（5:30公開予約の反映ビルド＋Xエンキュー）
 *   JST 06:35 → deploy.yml 救済枠（7:05のX投稿前にビルドを保証）
 *   JST 07:05 → x-post-scheduled (morning): 新着優先・なければ既存記事紹介
 *   JST 21:05 → x-post-scheduled (night):   朝の積み残し優先・なければ既存記事紹介
 *
 * 必要なシークレット:
 *   GITHUB_PAT: GitHub Personal Access Token（workflow スコープのみで OK）
 */

const REPO = "nyo0521-a11y/finlab-se";
const GH_API_BASE = `https://api.github.com/repos/${REPO}/actions/workflows`;

function dispatchParamsFromCron(cron) {
  switch (cron) {
    case "35 20 * * *":
    case "35 21 * * *":
      return { workflow: "deploy.yml", inputs: {} };
    case "5 22 * * *":
      return { workflow: "x-post-scheduled.yml", inputs: { slot: "morning" } };
    case "5 12 * * *":
      return { workflow: "x-post-scheduled.yml", inputs: { slot: "night" } };
    default:
      return null;
  }
}

export default {
  async scheduled(event, env, ctx) {
    const params = dispatchParamsFromCron(event.cron);
    const ts = new Date().toISOString();
    if (!params) {
      console.error(`[${ts}] ERROR: unknown cron "${event.cron}"`);
      return;
    }
    const { workflow, inputs } = params;
    const url = `${GH_API_BASE}/${workflow}/dispatches`;
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Authorization":        `Bearer ${env.GITHUB_PAT}`,
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type":         "application/json",
        "User-Agent":           "finlab-se-x-post-trigger/1.0",
      },
      body: JSON.stringify({ ref: "main", inputs }),
    });
    if (res.ok) {
      console.log(`[${ts}] OK: workflow="${workflow}" cron="${event.cron}" HTTP=${res.status}`);
    } else {
      const body = await res.text();
      console.error(`[${ts}] ERROR: workflow="${workflow}" HTTP=${res.status} body=${body}`);
    }
  },
};
