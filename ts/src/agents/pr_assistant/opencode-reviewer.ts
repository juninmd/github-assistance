/** opencode advisory review: enable flag and idempotency marker. */
import { enabled } from "./review-flags.ts";
import { REVIEW_MARKER } from "./review-verdict.ts";

export const OPENCODE_REVIEW_MARKER = REVIEW_MARKER;
export const opencodeReviewEnabled = () => enabled("OPENCODE_REVIEW_ENABLED", false);
export const hasExistingOpencodeReviewComment = (comments: any[]) => comments.some((c) => (c.body ?? "").includes(OPENCODE_REVIEW_MARKER));
