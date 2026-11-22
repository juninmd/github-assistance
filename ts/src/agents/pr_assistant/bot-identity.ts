/** Single source of the bot's GitHub identity: a rename of the App must not silently break the merge gate (PR #287). */
export const DEFAULT_BOT_LOGIN = "juninmd-bot[bot]";
/** Former App names whose review comments must keep counting until those PRs are re-reviewed. */
export const LEGACY_BOT_LOGINS = ["gh-assistance[bot]"];
export const configuredBotLogin = () => process.env.GITHUB_BOT_LOGIN?.trim() || DEFAULT_BOT_LOGIN;

/**
 * Logins whose review comment is the verdict. With App auth the owner is left out: the bot comments as the App, so an
 * owner comment carrying the verdict markers would be a hand-made approval (`/merge` is the explicit owner path).
 */
export function reviewerLogins(owner: string, live: string | null = null, appAuth = false): string[] {
  const all = [live, configuredBotLogin(), DEFAULT_BOT_LOGIN, ...LEGACY_BOT_LOGINS, appAuth ? null : owner].filter((x): x is string => !!x);
  return [...new Set(all.map((x) => x.trim()))];
}
/** Commit identity for pushes made by the bot (conflict resolution, fixes). */
export function gitIdentity(login = configuredBotLogin()): { name: string; email: string } {
  return { name: process.env.GIT_AUTHOR_NAME ?? login, email: process.env.GIT_AUTHOR_EMAIL ?? `${login}@users.noreply.github.com` };
}
