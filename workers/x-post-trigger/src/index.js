/**
 * x-post-trigger: Cloudflare Workers Scheduled
 *
 * 指定時刻に GitHub Actions のワークフローを workflow_dispatch でトリガーする。
 * 無料プランは cron 5本までのため、1つの cron から複数ワークフローを起動できる設計。
 *
 * 必要なシークレット:
 *   GITHUB_PAT: GitHub Personal Access Token（workflow スコープのみで OK）
 */

const REPO = "nyo0521-a11y/finlab-se";
const GH_API_BASE = `https://api.github.com/repos/${REPO}/actions/workflows`;

/**
 * cron 文字列から起動するワークフローの配列を返す。
 *   20:35 UTC (JST 05:35) → deploy.yml（5:30公開予約の反映ビルド＋Xエンキュー）
 *   22:17 UTC (JST 07:17) → 朝のX投稿 ＋ deploy.yml 保険ビルド
 *   22:37 UTC (JST 07:37) → 朝のX投稿（救済枠）
 *   11:53 UTC (JST 20:53) → 夜のX投稿
 *   12:13 UTC (JST 21:13) → 夜のX投稿（救済枠）＋ x-rotation
 */
function dispatchListFromCron(cron) {
  switch (cron) {
    case "35 20 * * *":
      return [{ workflow: "deploy.yml", inputs: {} }];
    case "17 22 * * *":
      return [
        { workflow: "x-post-scheduled.yml", inputs: { slot: "morning" } },
        { workflow: "deploy.yml", inputs: {} },
      ];
    case "37 22 * * *":
      return [{ workflow: "x-post-scheduled.yml", inputs: { slot: "morning" } }];
    case "53 11 * * *":
      return [{ workflow: "x-post-scheduled.yml", inputs: { slot: "night" } }];
    case "13 12 * * *":
      return [
        { workflow: "x-post-scheduled.yml", inputs: { slot: "night" } },
        { workflow: "x-rotation.yml", inputs: {} },
      ];
    default:
      return [];
  }
}

async function dispatch(env, workflow, inputs) {
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
    console.log(`[${ts}] OK: workflow="${workflow}" HTTP=${res.status}`);
  } else {
    const body = await res.text();
    console.error(`[${ts}] ERROR: workflow="${workflow}" HTTP=${res.status} body=${body}`);
  }
}

export default {
  async scheduled(event, env, ctx) {
    for (const { workflow, inputs } of dispatchListFromCron(event.cron)) {
      await dispatch(env, workflow, inputs);
    }
  },
};
