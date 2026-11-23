# Linux-first candidate build and package guide

This guide covers the Linux candidate. Windows and macOS native execution, installation, and packaging are covered by their platform guides and the final cross-platform CI. No public En release, download, tag, release date, or Linux support matrix is announced here. Private candidate artifacts and checksums follow validation; public release approval is a separate decision.

## Version and scope

The current source is based on Bitcoin Core 31.1 and identifies itself as Sugarchain En 31.1.0. `CMakeLists.txt` sets major/minor/build to `31/1/0`, RC to `0`, and `CLIENT_VERSION_IS_RELEASE` to `false`. The upstream version numbers are retained, while the false release flag identifies this En build as a prerelease candidate. These values are not an En publication announcement. Do not assign an En tag or release date from the upstream version.

Record the exact source commit, compiler, build options, Linux distribution, architecture, dependency versions, and validation results for each private candidate. An existing local build or an older measurement does not validate a later source revision. The [En draft notes](sugarchain-en-draft-release-notes.md) describe the current compatibility scope; [upstream release notes](release-notes.md) remain historical references.

## Build a production candidate

Use a clean checkout and fresh build/staging directories on disk. Follow [Linux dependencies](build-unix.md) and the [dependency requirements](dependencies.md). The GUI needs Qt 6 and its translation tools; the wallet needs SQLite. QR encoding is enabled by default and needs libqrencode unless explicitly disabled. The current validated candidate is monolithic (`ENABLE_IPC=OFF`). The product's Linux IPC default is unchanged; an IPC-enabled candidate needs Cap'n Proto and remains a separate, unvalidated configuration.

Run from the source root, replacing the two absolute paths. Choose build parallelism for the host. This production recipe excludes test/benchmark executables; it does not replace a separate validation build.

```sh
en_release_build=/absolute/path/to/en-release-build
en_release_stage=/absolute/path/to/en-release-stage
cmake -S . -B "$en_release_build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_GUI=ON -DENABLE_WALLET=ON -DENABLE_IPC=OFF \
  -DBUILD_TESTS=OFF -DBUILD_GUI_TESTS=OFF \
  -DBUILD_TX=ON -DBUILD_UTIL=ON -DBUILD_WALLET_TOOL=ON \
  -DBUILD_BENCH=OFF -DBUILD_FUZZ_BINARY=OFF \
  -DINSTALL_MAN=ON
cmake --build "$en_release_build" --parallel 2
cmake --install "$en_release_build" --prefix "$en_release_stage"
```

The explicit TX, utility, and wallet-tool settings matter because their defaults depend on `BUILD_TESTS`. The package layout below assumes the default GNUInstallDirs relative paths. The current candidate installs seven executables in `bin` and has no IPC executables in `libexec`.

CMake's internal target/component names retain the `bitcoin` prefix; installed product names use `sugarchain`:

| CMake target/component | Installed path |
|---|---|
| `bitcoin`, `bitcoind`, `bitcoin-qt` | `bin/sugarchain`, `bin/sugarchaind`, `bin/sugarchain-qt` |
| `bitcoin-cli`, `bitcoin-tx`, `bitcoin-util`, `bitcoin-wallet` | Corresponding `bin/sugarchain-*` tools |
| `bitcoin-node`, `bitcoin-gui` (optional IPC; excluded from the current candidate) | `libexec/sugarchain-node`, `libexec/sugarchain-gui` |

## Stage and inspect the package

Require the Linux packaging integration before creating a candidate. In addition to the seven monolithic executables above, the staged manifest must contain:

| Content | Default path |
|---|---|
| Seven command manpages | `share/man/man1/sugarchain*.1` |
| Application/URI entry | `share/applications/org.sugarchain.SugarchainEn.desktop` |
| AppStream metadata | `share/metainfo/org.sugarchain.SugarchainEn.metainfo.xml` |
| Application icons | `share/icons/hicolor/*/apps/sugarchain.png` |
| Project license and bundled-asset notices | `share/doc/SugarchainEn/COPYING`, `share/doc/SugarchainEn/copyright` |
| README, this guide, and En draft notes | `share/doc/SugarchainEn/` |
| Configuration example and RPC-authentication helper | `sugarchain.conf`, `share/rpcauth/` |

The CMake install provides binaries, manpages, desktop metadata, icons, and license notices. Stage the candidate documentation, populated configuration example, and RPC helper explicitly:

```sh
install -m 644 README.md doc/sugarchain-en-linux-release.md \
  doc/sugarchain-en-draft-release-notes.md "$en_release_stage/share/doc/SugarchainEn/"
install -m 644 share/examples/sugarchain.conf "$en_release_stage/sugarchain.conf"
cp -R share/rpcauth "$en_release_stage/share/"
```

Adjust paths if GNUInstallDirs was overridden. Use a fresh stage so copied files from an older build cannot enter the candidate. Do not include wallets, node data, credentials, build caches, test fixtures, or private logs.

The desktop entry declares `sugarchain:` URI handling and uses `sugarchain-qt` from PATH. Put a nonstandard staging prefix's `bin` directory on a task-local PATH for isolated launcher checks. Merely installing the file does not select the user's default URI handler. Autostart setup rejects executable paths containing `%` or `=`; use an installation path without these characters when enabling autostart.

A normal host build can depend on host shared libraries and Qt platform plugins. It is not automatically a static, portable, or reproducible Linux distribution. Inspect the candidate's dynamic dependencies and plugin availability on every intended target environment; record the tested environment before stating support. If bundling additional libraries/plugins, include their required notices and validate that deployment separately.

## Compatibility checks before packaging

- Mainnet uses native `sugar1...` SegWit, `S...` legacy P2PKH, and `s...` P2SH address encodings. These are prefixes, not example payment destinations. Old Bitcoin-encoded En addresses are not the native Sugarchain encoding.
- Native mainnet has no Taproot deployment. Automatic wallet receive/change generation and configured `bech32m` generation are rejected there. Imported descriptors and generic derivation remain available; their presence does not activate Taproot on mainnet. Isolated regtest retains its existing development behavior.
- Applications support mainnet and isolated regtest. Public testnet3, testnet4, and signet modes are rejected; inherited parameter definitions or examples do not make them supported En networks.
- Legacy address-based message signing/verifying uses the native `Sugarchain Signed Message:` prefix followed by a newline. This does not add legacy message-signature support to every script/address type.
- Legacy Berkeley DB wallets require the `migratewallet` path before ordinary loading. Cleanly shut down the old node and retain a backup; use a working copy for migration. Inspect all returned wallets, including optional watch-only/solvable wallets, then create new descriptor-wallet backups. En descriptor/SQLite backup restoration and migration of an old Berkeley DB backup are distinct paths; consult the candidate's `help migratewallet` and [wallet documentation](managing-wallets.md). GUI profile migration from the former Komorebi name remains separate from wallet-format migration.

Verify installed wrapper/tool version output, isolated GUI startup/shutdown, URI handoff, autostart paths containing spaces/special characters, desktop/AppStream metadata, notices, and the exact staged manifest. Regenerate the example configuration/manpages from the final candidate where required and review their network/version text. Never use production wallet/profile paths for these checks.

Production build/runtime checks, broad native regression coverage, mainnet-scale checks, and benchmark work are separate validation stages. Historical IBD/startup measurements retain their original source/scope limits. CI remains disabled until separate explicit instruction; a local candidate build does not authorize CI or public publication.

Only after the applicable validation gates pass, create private candidate archives from the inspected stage and record their SHA-256 checksums together with the exact source revision and environment. Candidate naming must distinguish version, source revision, Linux architecture, and candidate status without inventing a public release tag.
