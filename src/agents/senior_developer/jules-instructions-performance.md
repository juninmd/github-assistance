# Task: Performance Optimization for {{repository}}

## Identified Bottlenecks
{{details}}

## Instructions
You are a performance engineer. Your goal is to identify, measure, and mitigate performance bottlenecks in the codebase.

### 1. Identify and Measure
- Run existing benchmarks or profiling tools if available.
- Identify the slowest functions, endpoints, or database queries.

### 2. Algorithmic Improvements
- Replace inefficient algorithms or data structures with more optimized versions.
- Optimize loops and recursion.

### 3. Caching & Resource Management
- Implement caching strategies where appropriate.
- Optimize resource allocation and usage (memory, database connections, file handles).

### 4. Concurrency & Parallelism
- Identify opportunities for parallel execution (e.g., using `Promise.all` in Node.js or `multiprocessing`/`threading` in Python).

## Constraints
- **Do not break existing functionality.** All tests must pass.
- **Do not change public API contracts** unless absolutely necessary and documented.

## Deliverables
Create a PR with:
- Optimized code changes.
- Comparison metrics showing the performance improvement (if measurable).
- Detailed explanation of the optimization techniques used.
