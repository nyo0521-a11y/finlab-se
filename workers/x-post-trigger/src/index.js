/**
 * x-post-trigger: Cloudflare Workers Scheduled
 *
 * 指定時刻に GitHub Actions の x-post-scheduled.yml を workflow_dispatch でトリガーする。
 * slot（morning / night）を inputs として渡し、GH 側の重複投稿防止ロジックに委譲する。
 *
 * 必要なシークレット:
 *   GITHUB_PAT: GitHub Personal Access Token（workflow スコープのみで OK）
 */

const REPO     = "nyo0521-a11y/finlab-se";
const WORKFLOW = "x-post-scheduled.yml";
const GH_API   = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;

/** cron 文字列からスロット名を返す */
function slotFromCron(cron) {
  if (cron === "17 22 * * *" || cron === "37 22 * * *") return "morning";
  if (cron === "53 11 * * *" || cron === "13 12 * * *") return "night";
  return "morning"; // fallback
}

export default {
  async scheduled(event, env, ctx) {
    const slot = slotFromCron(event.cron);
    const ts   = new Date().toISOString();

    const res = await fetch(GH_API, {
      method: "POST",
      headers: {
        "Authorization":        `Bearer ${env.GITHUB_PAT}`,
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type":         "application/json",
        "User-Agent":           "finlab-se-x-post-trigger/1.0",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: { slot },
      }),
    });

    if (res.ok) {
      // GitHub は 204 No Content を返す
      console.log(`[${ts}] OK: triggered slot="${slot}" cron="${event.cron}" HTTP=${res.status}`);
    } else {
      const body = await res.text();
      console.error(`[${ts}] ERROR: slot="${slot}" HTTP=${res.status} body=${body}`);
      // Workers の scheduled handler では例外を投げると自動リトライされない（設計上 no-op）
    }
  },
};
