/**
 * x-post-trigger: Cloudflare Workers Scheduled
 *
 * 指定時刻に GitHub Actions の x-post-scheduled.yml を workflow_dispatch でトリガーする。
 * slot（morning / night）を inputs として渡し、GH 側の重複投稿防止ロジックに委譲する。
 *
 * 必要なシークレット:
 *   GITHUB_PAT: GitHub Personal Access Token（workflow スコープのみで OK）
 */

const REPO = "nyo0521-a11y/finlab-se";
const GH_API_BASE = `https://api.github.com/repos/${REPO}/actions/workflows`;

/**
 * cron 文字列から { workflow, inputs } を返す。
 *   "5 12 * * *"  → x-rotation.yml（inputs なし）
 *   それ以外       → x-post-scheduled.yml（slot を inputs で渡す）
 */
function dispatchParamsFromCron(cron) {
  if (cron === "5 12 * * *") {
    return { workflow: "x-rotation.yml", inputs: {} };
  }
  const slot =
    cron === "17 22 * * *" || cron === "37 22 * * *" ? "morning" : "night";
  return { workflow: "x-post-scheduled.yml", inputs: { slot } };
}

export default {
  async scheduled(event, env, ctx) {
    const { workflow, inputs } = dispatchParamsFromCron(event.cron);
    const ts  = new Date().toISOString();
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
