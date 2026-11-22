/** Review could not run for an infrastructure reason (no token, clone failed): retried later, never waived into a merge. */
export class ReviewInfraError extends Error {
  constructor(message: string) { super(message); this.name = "ReviewInfraError"; }
}
