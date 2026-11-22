/** Classify PR authors for the advisory review: only the owner's own PRs get automated corrections. */
export const defaultOwner = () => process.env.GITHUB_OWNER ?? "juninmd";
export const isOwner = (login?: string | null, owner?: string | null) => (login ?? "").trim().toLowerCase() === (owner ?? defaultOwner()).trim().toLowerCase();
export const shouldAutofix = (login?: string | null, owner?: string | null) => isOwner(login, owner);
