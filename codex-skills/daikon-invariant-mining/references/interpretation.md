# Interpreting Daikon Invariants For Performance Repair

Use mined invariants only when they are close to the candidate edit.

Useful invariant categories:

- **Identity fast path**: `result_is_same_object == 1`, `return == input`.
- **Value preservation**: `float_value == result_float_value`.
- **Type stability**: input/output type facts such as `is_int == result_is_int`.
- **Shape or length stability**: array/list/string dimensions that can avoid repeated validation or allocation.
- **Branch stability**: observed branch preconditions that justify a guarded fast path.

Risky categories:

- Generic arity facts such as `arg_count == 2`.
- Exact constants from a small test unless they express a real domain precondition.
- Invariants from unrelated hot functions.
- Zero-coverage reports.

Recommended agent behavior:

1. Treat Daikon output as likely evidence, not proof.
2. Convert a useful invariant into an explicit precondition.
3. Check whether the precondition is likely relevant to the measured hot path.
4. Match the precondition to a rewrite opportunity:
   - `conditional_identity_return` -> guarded fast path.
   - identity-return evidence in `validate`/`check`/`ensure` functions -> consider splitting validation from normalization.
   - value-preserving evidence -> avoid redundant numeric conversion.
   - shape-preserving evidence -> avoid redundant shape/size work.
5. Preserve fallback logic for inputs outside the precondition.
6. Validate with correctness tests and performance evaluation.

Important distinction:

- Invariant evidence answers whether a cheaper rewrite may be semantically safe.
- Hot-path evidence answers whether the rewrite is likely to matter.
- Rewrite opportunities tell the agent what family of optimization to attempt.
