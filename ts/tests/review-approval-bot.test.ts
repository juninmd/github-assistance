import { expect, test } from "bun:test";
import { PRAssistantAgent } from "../src/agents/pr_assistant/agent.ts";
import { approvalState } from "../src/agents/pr_assistant/review-approval.ts";
import { OPENCODE_REVIEW_MARKER } from "../src/agents/pr_assistant/opencode-reviewer.ts";

const SHA = "31b9fc096619bd60d6e8932b41810430e0e780c3";
const review = (login: string) => ({ user: { login }, body: `${OPENCODE_REVIEW_MARKER}\n**Veredito:** \`APPROVE\`\nSHA \`${SHA.slice(0, 8)}\`` });

test("approval from the renamed app identity juninmd-bot[bot] counts as approved", () => {
  const reviewers = Object.getOwnPropertyDescriptor(PRAssistantAgent.prototype, "reviewers")!.get!.call({ targetOwner: "juninmd" });
  expect(approvalState([review("juninmd-bot[bot]")], SHA, reviewers)).toBe("approved");
  expect(approvalState([review("gh-assistance[bot]")], SHA, reviewers)).toBe("approved");
  expect(approvalState([review("stranger")], SHA, reviewers)).toBe("missing");
});
