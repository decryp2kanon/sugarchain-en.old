# Sugarchain En final CI

The final CI phase follows the native Linux implementation and the Windows and
macOS packaging changes. Both workflows can be dispatched manually. The
`SKIP_BRANCH_PUSH` variable suppresses duplicate branch runs without suppressing
an explicit workflow dispatch.

## Coverage

The existing matrix is retained:

- Fourteen Linux/container configurations: include analysis, 32-bit ARM,
  address/leak/undefined/integer sanitizers, macOS cross-builds for both
  architectures, no-wallet, i686 without IPC, fuzzing, native legacy wallet
  compatibility, Alpine/musl, clang-tidy, thread sanitizer, and two memory
  sanitizer configurations.
- macOS arm64 native applications and fuzzing. The standard job verifies the
  deployed application before unit/functional tests, including actual offline
  GUI/RPC/wallet operation in an isolated data directory.
- Windows native Visual Studio applications and fuzzing; both MinGW CRT
  cross-builds execute their unit/functional tests on native Windows runners.
  Runtime smoke checks exercise all seven production binaries, native addresses,
  wallet behavior, and offline mainnet/regtest operation. Cross-built NSIS
  installers are installed, upgraded, exercised, and uninstalled on fresh runners.
- Repository lint, two metadata jobs, and the conditional ancestor-commit check.
- A separate Linux GUI/wallet/IPC workflow builds all configured targets,
  installs applications, verifies native runtime behavior, and runs all configured
  CTest suites, including Qt, IPC, and recovery tests.

Cross-build success is not reported as native execution. Native platform jobs
provide the corresponding runtime evidence. Test runners retain their existing
feature and environment requirements; an unavailable component is reported as a
skip rather than counted as a passed assertion.

## Genuine previous-release compatibility

The legacy job uses Sugarchain Yumekawa 0.16.5.2 Visioneye from the
[official release](https://github.com/sugarchain-project/sugarchain/releases/tag/v0.16.5.2-visioneye).
The Linux x86_64 archive is pinned to SHA-256
`2cfebb1af0436de90f8c142de6de710decc3713802800d1f7d7c9ab258e5900c`.
Only its regular daemon executable is extracted. A mismatched archive fails
before execution.

`wallet_sugarchain_legacy.py` creates fresh plaintext and encrypted, unfunded
mainnet wallets with networking disabled. It checks BDB-to-descriptor-SQLite
migration, ownership, scripts, public keys, HD metadata, native signed-message
interoperability in both directions, backup identity, unload/reload, and restore.
Only successful RPC calls made to the current daemon enter functional RPC
coverage. Private keys and passwords are not logged.

The earlier Bitcoin 0.20-28 fixtures remain available in the upstream tests, but
are not downloaded or presented as earlier Sugarchain releases. Their version
dependent checks are unavailable in the native profile. Imported/watch-only and
multisig legacy migration, funded historical rescans, and backward compatibility
with unsupported future Sugarchain releases are not established by this probe.

The local targeted test passed against the pinned legacy archive and the current
native daemon. Actual remote CI conclusions are recorded by GitHub Actions for
the tested commit; this document does not declare unexecuted jobs successful.

## Recovery timeouts

The recovery harness retains all genuine Yespower boundaries, repeated crashes,
damaged-record repair, and invalid-header checks. The existing
`TEST_RUNNER_TIMEOUT_FACTOR` sets the overall deadline and scales the initial
idle budget for instrumented builds. Only new, validated structured events reset
the idle watchdog. Diagnostic noise cannot extend the overall deadline.

## Repository lint boundaries

The vendored Yespower C directory retains upstream formatting and include guards,
matching the existing third-party lint policy. Native integration code and all
runtime/hash tests remain checked. The Boost integer-sort public header is an
explicit dependency of block-index reconstruction.

The historical standalone allocation fixture
`doc/benchmarks/post-ibd-cache-probe.cpp` has one documented exception to the
implementation-file include rule. Its synthetic allocation store requires
private cache admission; it is never linked into a production node. No production
API exposes that bypass. Its remaining style and numeric parsing checks apply.
Draft En release notes live directly under `doc/`, leaving `doc/release-notes/`
reserved for archived releases.
