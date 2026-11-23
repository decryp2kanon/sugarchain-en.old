# Sugarchain En draft release notes

Linux is the first distribution target. This draft records candidate validation for Linux, Windows and macOS. Publication and the supported Linux distribution and architecture matrix require separate approval.

## Version

The current client metadata is 31.1.0, based on Bitcoin Core 31.1 (`CLIENT_VERSION_RC=0`, `CLIENT_VERSION_IS_RELEASE=false`). The upstream base version and RC values are retained; En is marked as a prerelease candidate rather than an approved release. En release approval, final artifact provenance, and any future version/tag policy are separate decisions.

## Native compatibility

- Restore official Sugarchain mainnet address encodings: SegWit `sugar1...`, legacy P2PKH `S...`, and P2SH `s...`. These prefixes replace the inherited Bitcoin mainnet address domain in En. Check any addresses obtained from an earlier En build before reusing them.
- Restore the native message-signature prefix, `Sugarchain Signed Message:` followed by a newline, for legacy address-based signatures. This aligns native Sugarchain message hashing; signatures made under the Bitcoin message domain are a different domain. The address/script support of the legacy signature API is unchanged.
- Keep the legacy-wallet migration path: migration-only Berkeley DB reading converts legacy wallets to descriptor/SQLite wallets through `migratewallet`. The operation creates a `.legacy.bak` backup and may return separate watch-only/solvable wallets. Ordinary legacy-wallet loading is not a substitute for migration. Retain the original backup, compare the migrated contents, and create fresh backups afterward. This draft does not claim validation of every legacy script configuration or production transaction history.
- Reject unsupported public testnet3, testnet4, and signet startup modes in En applications. Mainnet and isolated regtest are supported application modes; regtest is a development fixture, not an official public Sugarchain testnet.
- Respect the native mainnet no-Taproot deployment policy in wallet generation. Mainnet automatic receive/change selection and configured `bech32m` generation are rejected rather than advertised as deployed. Existing descriptor import/generic derivation and regtest behavior remain available. No Taproot deployment or new mainnet consensus rule is introduced.
- Repair production proof-cache lock annotations and common application linking while retaining native consensus selection.

## Linux candidate scope

The [Linux candidate guide](sugarchain-en-linux-release.md) defines the production build recipe and required package manifest. The current validated Linux configuration is monolithic (`ENABLE_IPC=OFF`) with seven installed executables. IPC-enabled packaging is not validated by that candidate; the product default is unchanged. Candidate integration includes the Sugarchain executable names, application/URI entry and AppStream ID `org.sugarchain.SugarchainEn`, installed icons, and project/bundled-asset notices under `share/doc/SugarchainEn`.

Four Korean/Japanese translation gaps in the encryption, address-signing, Tor-proxy, and fee explanations are filled. Autostart setup rejects executable paths containing `%` or `=`.

GUI settings migration retains the previous Komorebi profile and avoids overwriting an existing En profile. Wallet-format migration is separate. Packaging and message work must be reviewed at the integrated candidate revision before these notes become final.

Host-built Linux candidates may require matching shared libraries and Qt platform plugins.

## Windows and macOS package checks

### Integration candidate `108163098c18`

Windows Server 2022 ran the mainnet Qt wallet from the build directory and the installation directory for each x86_64 package. Both installers passed fresh installation, in-place upgrade, and removal with user files preserved. The following hashes identify the installer executables inside the Actions archives.

| Windows runtime | Installer bytes | Installer SHA-256 | Evidence |
| --- | ---: | --- | --- |
| MSVCRT | 28,680,752 | `5868c7c4c11cacece755012c65d042b4d8ce7a798dcca9b233d67cc7335bda7d` | [Archive](https://github.com/decryp2kanon/sugarchain-en/actions/runs/44872574212/artifacts/14700071881) · [Windows lifecycle](https://github.com/decryp2kanon/sugarchain-en/actions/runs/44872574212/job/136792252778#step:10:1) |
| UCRT | 28,669,310 | `dd71d06b25e6aa845c548f96f3d2c04db076f4c2fe82693b32ec2cb7ee368772` | [Archive](https://github.com/decryp2kanon/sugarchain-en/actions/runs/44872574212/artifacts/14699393704) · [Windows lifecycle](https://github.com/decryp2kanon/sugarchain-en/actions/runs/44872574212/job/136792252836#step:10:1) |

On Apple Silicon, the packaged Cocoa app reopened a regtest wallet and restored its backup. The confirmed transaction survived both operations. All 161 CTest cases passed. The functional suite passed 443 cases and skipped 19 conditionally. Cross-builds verified the ARM64 and Intel x86_64 application archives and their executable architectures. Native execution was verified on Apple Silicon. [Native macOS](https://github.com/decryp2kanon/sugarchain-en/actions/runs/44872574212/job/136750153354) · [ARM64 archive check](https://github.com/decryp2kanon/sugarchain-en/actions/runs/44872574212/job/136750184392) · [Intel archive check](https://github.com/decryp2kanon/sugarchain-en/actions/runs/44872574212/job/136750184346)

An earlier MSVCRT package at `267f3688ff72` exited with `0xc0000005` after returning from `GuiMain` in two Windows checks. A subsequent instrumented run of the same executable exited successfully. The faulting module remains unknown. [Original native check](https://github.com/decryp2kanon/sugarchain-en/actions/runs/44864273197/job/136760866312) · [Native-shell check](https://github.com/decryp2kanon/sugarchain-en/actions/runs/44878691390/job/136768988990) · [Source observation](https://github.com/decryp2kanon/sugarchain-en/actions/runs/44882494063/job/136780612041)

### Earlier packaged artifacts

The following candidate files were built from `20f63ff768a8`. On Windows Server 2022, both installers passed installation, in-place upgrade, installed Qt wallet startup and shutdown, and uninstall with user files preserved. On Apple Silicon, the packaged Qt application started with Cocoa, backed up a wallet and passed the bundle signature check.

| Candidate file | SHA-256 | Native validation |
| --- | --- | --- |
| Windows x86_64 MSVCRT installer | `dc8f423565b552c5f1ef0749ed6ebddae1806c3d7e11559276a693b562b94121` | [Windows job](https://github.com/decryp2kanon/sugarchain-en/actions/runs/44790544547/job/136521017767) |
| Windows x86_64 UCRT installer | `ffe2924588f742ad705bfdfb9cbb609b44befb83ca1d1816043551c612732328` | [Windows job](https://github.com/decryp2kanon/sugarchain-en/actions/runs/44790544547/job/136521017725) |
| macOS arm64 application ZIP | `d2f89a4df5d946aaf25582d65f33dc4168580790423acf9f20f3606e43ad7ea1` | [macOS job](https://github.com/decryp2kanon/sugarchain-en/actions/runs/44790812935/job/136477657681) |

The Intel macOS cross-build at `4d16aa069e09` verified the archive layout and x86_64 executable on Linux. The native macOS results above cover Apple Silicon. [Intel cross-build](https://github.com/decryp2kanon/sugarchain-en/actions/runs/44753835460/job/136348360337)

## Validation and publication gates

- Complete the integrated production build and isolated installed-runtime/package checks.
- Adapt and run broad native regression coverage against the finished core; closed PR #20 is reference material, not a completed validation result for the final source.
- Reuse earlier IBD/startup evidence only where its source and scope still apply; repeat affected mainnet-scale and performance measurements separately. No new speedup or throughput figure is announced here.
- Record exact source/environment/options, inspected package contents, and private candidate checksums after validation.
- Require `CI` and `En Linux Qt` to pass on the integrated source and on the final `en` commit. Tagging and publication require separate approval.

Upstream [Bitcoin Core 31.1 release notes](release-notes.md) are preserved as history. Their download links, external infrastructure, supported platforms, and upgrade claims are not an En release announcement.
