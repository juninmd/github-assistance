/** Classify PR authors for the advisory review: Jules fixes itself; only the owner's own PRs get automated corrections. */
export const JULES_LOGINS = new Set(["google-labs-jules", "google-labs-jules[bot]", "jules da google"]);
export const isJules = (login?: string | null) => JULES_LOGINS.has((login ?? "").trim().toLowerCase());
export const defaultOwner = () => process.env.GITHUB_OWNER ?? "juninmd";
export const isOwner = (login?: string | null, owner?: string | null) => (login ?? "").trim().toLowerCase() === (owner ?? defaultOwner()).trim().toLowerCase();
export const shouldAutofix = (login?: string | null, owner?: string | null) => !isJules(login) && isOwner(login, owner);
