Remember: Fix Memory Correctness Without Redesigning the Architecture

Work on the existing "Remember" repository, specifically "memory-gateway".

The latest benchmark shows:

- Remember answer accuracy: 70%
- Full context: 100%
- Recent-N: 40%
- Token reduction at 100 turns: 92%
- Gateway overhead: ~23ms p50
- Isolation: 0 leaks
- Streaming: PASS
- Fail-open behavior: PASS

Do NOT redesign the gateway architecture or optimize token reduction further. The main problem is memory correctness.

Goal

Improve the deterministic memory engine so that it can correctly handle:

1. Natural-language facts
2. Corrections
3. Revocations/resets
4. Questions/interrogative noise
5. Stale memory
6. Contradictory information

Target:

Memory correctness: >=95%
Correction accuracy: >=95%
False-memory rate: ~0%
Interrogative noise: 0%
Cross-conversation leakage: 0%

Keep the existing OpenAI-compatible proxy, context compiler, storage architecture, streaming, and fail-open behavior intact.

---

1. Fix Interrogative Noise

Currently questions such as:

What is my name?
What is the deployment target?
When is the beta launch?
What is the demo password?

can become memories such as:

What = my name?

This must never happen.

Add robust detection so interrogative/user-question messages are not stored as factual memories.

Test:

What is my name?
Why did we choose PostgreSQL?
When is the launch?
Where is the project deployed?
How does Cloudisy work?

Expected:

No memory extracted.

Do not accidentally reject legitimate declarative statements containing question-like words.

---

2. Expand Deterministic Fact Extraction

Support the existing patterns while adding natural language forms such as:

I am building Cloudisy.
Cloudisy uses Neon PostgreSQL.
Cloudisy uses self-hosted PostgreSQL.
Cloudisy's beta launch is scheduled for next month.
I prefer TypeScript.
I prefer MUI over shadcn.
The deployment target is AWS Lambda.

The extractor should normalize these into structured memory where possible.

Do not create a huge brittle regex system. Keep extraction modular and testable.

---

3. Implement Correction Semantics

Support corrections such as:

Cloudisy changed from Neon PostgreSQL to self-hosted PostgreSQL.

Cloudisy now uses self-hosted PostgreSQL instead of Neon.

We no longer use Neon.

The database was changed to self-hosted PostgreSQL.

Actually, the deployment target changed to AWS Lambda.

I changed my preference from X to Y.

Represent corrections explicitly rather than simply creating another independent fact.

Use the existing memory/versioning architecture where possible.

A correction should establish:

target
old_value
new_value
timestamp/source
status

For example:

{
  "type": "correction",
  "target": "Cloudisy database",
  "old_value": "Neon PostgreSQL",
  "new_value": "self-hosted PostgreSQL"
}

The context compiler must prefer the current value and avoid presenting superseded values as active facts.

---

4. Implement Revocation / Reset Semantics

Handle statements such as:

The demo password was reset.
Ignore the previous password.
That password is no longer valid.
We no longer use X.
Forget the previous value.
X has been revoked.

Introduce or reuse a memory state model such as:

ACTIVE
SUPERSEDED
REVOKED
EXPIRED

Do not delete historical records unnecessarily. Preserve history, but prevent invalid memories from being selected as current context.

Example:

Temporary password = temp1234

The temporary password was reset.

Expected state:

temp1234 -> REVOKED

A later query:

What is the demo password?

must NOT cause "temp1234" to be returned as the current password.

---

5. Improve Conflict Resolution

When multiple memories describe the same entity/property:

Cloudisy uses Neon.
Cloudisy uses self-hosted PostgreSQL.

the context compiler must select the latest valid state.

Prefer:

latest valid correction
>
latest active fact
>
older superseded fact

Do not inject both conflicting values into the final context unless historical context is explicitly required.

Use timestamps/version/source metadata already present in the project.

---

6. Protect Against False Memories

Do not store:

- Questions
- Empty/low-information messages
- Pure acknowledgements
- Random conversational filler
- Model-generated answers as user facts
- Unsupported assumptions
- Automatically inferred facts that were never stated

Existing low-information filtering must continue working.

Add tests for:

ok
thanks
yes
no
continue
sure
What?
Why?
How?

Expected:

No memory extraction.

---

7. Update Context Compilation

The compiler should receive only currently valid, relevant memories.

For example, after:

Cloudisy uses Neon PostgreSQL.

Actually, Cloudisy changed to self-hosted PostgreSQL.

compiled context should contain:

Cloudisy database: self-hosted PostgreSQL

and should not contain:

Cloudisy database: Neon PostgreSQL

as an active fact.

Likewise:

password = temp1234
password was reset

must result in no active password memory.

Do not increase the context budget just to hide correctness problems.

---

8. Add Comprehensive Regression Tests

Extend the existing test suite.

Minimum cases:

Basic facts

I am building Cloudisy.
Cloudisy uses PostgreSQL.
I prefer TypeScript.

Corrections

Cloudisy uses Neon.
Actually, Cloudisy uses self-hosted PostgreSQL.

Revocation

The temporary password is temp1234.
The password was reset.

Questions

What is my name?
What database do we use?

Contradictions

I prefer React.
Actually, I prefer Vue.

Stale information

Create an old fact and later update it.

Unrelated information

Ensure unrelated memories are not injected into the compiled context.

Isolation

Verify that memories from conversation A never appear in conversation B.

---

9. Re-run the Existing Comprehensive Benchmark

After implementation, run the existing benchmark without changing its methodology.

Compare:

Before
After

for:

- Recall accuracy
- Correction accuracy
- False memory rate
- Interrogative noise
- Token usage
- p50 latency
- p95 latency
- Memory write overhead
- Isolation
- Streaming
- Fail-open behavior

Do NOT modify the benchmark to make the new implementation look better.

---

10. Regression Requirements

The following must remain passing:

78+ existing tests
OpenAI SDK compatibility
/v1/models
/v1/chat/completions
streaming
malformed request handling
oversized request handling
fail-open behavior
conversation isolation

Do not introduce a dependency on the Memory-AI compressor.

Keep the deterministic engine independently correct.

Do not enable the Memory-AI compressor yet. We will benchmark deterministic vs AI-assisted extraction separately after this work.

---

11. Final Report

Create/update:

benchmarks/COMPREHENSIVE_RESULTS.md

with the new results.

Clearly report:

Before:
Memory correctness = 70%

After:
Memory correctness = X%

Correction accuracy = X%
False memory rate = X%
Interrogative noise = X%
Token reduction = X%
Gateway overhead = X ms

Also list any remaining failures honestly.

Important Engineering Constraints

- Preserve existing architecture.
- Prefer small, composable changes.
- Do not rewrite the memory system unnecessarily.
- Do not sacrifice isolation or fail-open behavior.
- Do not optimize for benchmark scores by hardcoding benchmark phrases.
- Tests must use varied natural-language wording.
- Do not treat LLM-generated answers as user facts.
- Historical memories may remain stored, but superseded/revoked memories must not be presented as current.
- Run the full test suite before finishing.

At the end, provide:

Implementation summary
Files changed
Tests added
Existing tests: PASS/FAIL
Memory correctness: X%
Correction accuracy: X%
False memory rate: X%
Token reduction: X%
Latency overhead: X ms
Isolation: PASS/FAIL
Final verdict: PASS/PARTIAL/FAIL
