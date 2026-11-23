# Sugarchain En implementation and PR plan

Updated: 2026-11-18. Base branch: `en`.

Prioritize production core functionality. Defer broad test maintenance, benchmarks, and CI until the implementation is complete. Sequence numbers are work items, not GitHub PR numbers. Create a PR only when changes are needed; validation-only work may produce a report.

Priority: **3: Mandatory; 2: Required; 1: Important; 0: Optional.**

## Current state

- Branding is merged in PR #17; Qt expectations are fixed in PR #18.
- CI setup is merged in PR #19. The owner authorized re-enabling both GitHub workflows and running the complete cross-platform CI after the remaining implementation on 2026-11-18.
- [PR #20](https://github.com/decryp2kanon/sugarchain-en/pull/20) is closed without merge. Preserve its branch and commits as reference material for item 9.
- Native mainnet addresses and legacy signed-message compatibility are merged in PRs #22 and #23. Generated plain/encrypted legacy wallets passed migration, ownership, signing and backup/restore checks.
- Required build prerequisites, unsupported public-network rejection and native wallet output policy are merged in PRs #21, #24 and #25.
- Linux desktop/package integration and four key-flow translations are merged in PRs #26 and #27. Strict local production builds and isolated runtime checks passed.
- Linux prerelease metadata, candidate guidance and generated command manuals are merged in PR #28.
- The owner expanded this execution to include the remaining Windows and macOS support and the complete CI matrix on 2026-11-18. Public release publication and signing remain separate actions.
- Native regression coverage and bounded persistent-proof recovery are complete; see the [validation record](sugarchain-en-native-validation-2026-11-18.md). Historical full-chain evidence remains explicitly historical. All 173 benchmark sanity cases and bounded native component measurements are complete; see the [benchmark record](sugarchain-en-native-benchmarks-2026-11-18.md). No additional optimization is proposed without a justified comparison. CI stays disabled.

## PR sequence

| Order | Proposed PR or work item | Priority | Scope and completion criteria |
|---|---|---|---|
| 1 | Restore native address compatibility | **3** | Restore official mainnet encodings: SegWit `sugar1...`, legacy `S...`, and P2SH `s...`. Align address generation, parsing, and related RPC behavior. |
| 2 | Complete existing-wallet compatibility and recovery | **3** | Provide a compatible wallet or migration path preserving keys, addresses, and transaction information. Complete signing, sending, receiving, backup recovery, and upgrade handling. |
| 3 | Separate required production-core fixes | **2** | Assess PR #20's Yespower workspace lifetime, proof-cache locking, and related runtime changes. Extract only justified fixes into focused PRs. Preserve existing consensus rules. |
| 4 | Complete Linux packaging | **2** | Finish executable paths, desktop integration, settings migration, package metadata, and license information. |
| 5 | Complete Windows execution and installation | **2, conditional** | Complete native execution, installation, and settings migration if Windows is a release target. Otherwise record the exclusion. |
| 6 | Complete macOS execution and packaging | **2, conditional** | Complete native execution, packaging, and settings migration if macOS is a release target. Validate the native deployed app and both cross-compilation targets before claiming completion. |
| 7 | Improve important user-facing messages | **1** | Resolve incomplete or incorrect messages and translations on commonly used screens. |
| 8 | Prepare the En release configuration | **2** | Prepare version metadata, release notes, supported platforms, and package contents. Final artifacts and checksums follow final validation. |
| 9 | Reintroduce native regression coverage using closed PR #20 | **2** | Prepare a fresh PR against the then-current `en` branch. Adapt the preserved native fixtures and tests to the finished core. Include remaining test expectation repairs, including IBD output formatting. |
| 10 | Validate operation at mainnet scale | **2** | Reuse applicable completed IBD evidence. Check large-index startup, synchronization, restart, CPU, and memory behavior affected by subsequent changes. |
| 11 | Align benchmarks and measure performance | **1** | Reuse applicable benchmark work from PR #20. Preserve representative workloads and measure runtime, CPU, and memory. |
| 12 | Improve measured bottlenecks | **1** | Create a separate PR for each justified optimization. Compare correctness and resource use against its baseline. Omit this item if no improvement is justified. |
| 13 | Restore and complete final CI | **2** | Authorized on 2026-11-18. Re-enable workflows after implementation, execute every configured platform and analysis job, and resolve failures before merging the final changes. |

## Closed PR #20 reference

Preserved branch: `test/core-consensus-regressions-20261118`.

Preserved head: `490f73fe4a4a5ef644fe61d07652048466fcb957`.

Use its [validation record](https://github.com/decryp2kanon/sugarchain-en/blob/490f73fe4a4a5ef644fe61d07652048466fcb957/doc/core-consensus-validation.md), fixtures, and implementation history. Do not merge or cherry-pick the entire old PR as a prerequisite for item 1. Remove changes already extracted in item 3 from the new item-9 PR. Keep benchmark work in item 11. Reassess prior passing results against the final source; they do not establish that future changes pass.

## Execution and review policy

- Run no automatic CI, manual dispatches, or remote CI jobs in this execution. Keep `CI` and `En Linux Qt` disabled until the owner separately instructs otherwise, including after local verification is finished.
- Keep core PRs focused on implementation. Use necessary local compilation and basic runtime checks; broad test maintenance starts at item 9 and benchmark work at item 11.
- The current owner authorization permits sequential implementation, focused PR creation and merge after appropriate local build and isolated runtime verification. Continue through applicable work without requesting per-PR approval. Public release still requires separate approval.
- Preserve operating nodes, original wallets, existing changes, and reference branches. Use isolated copies for wallet and mainnet-scale work.
- Announce intentional crash or memory-exhaustion experiments before running them.
- Document supported platforms and exclusions. An earlier CI failure does not itself block an intermediate PR merge under the owner's current instruction; supported-platform final validation remains required before release.
- Public release requires separate owner approval after final validation.

## Priority 0: no scheduled PR required

No PR is planned for Doxygen generation, bulk renaming of internal Bitcoin identifiers, or complete translation of every supported language. Preserve original copyright notices and historical records.

## Final cross-platform execution

Windows and macOS follow-ups are tracked in PRs #31 and #32. The final integration PR adds the required native runtime and installer/bundle checks and restores the full CI matrix. Their source changes must not be considered validated on Windows or macOS until the corresponding hosted-runner jobs pass. The final Actions run is the authoritative execution record; local Linux checks are supplementary. No original wallet or operating-node data is used.
