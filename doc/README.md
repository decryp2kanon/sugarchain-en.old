Sugarchain En
=============

Setup
---------------------
Sugarchain En is based on Bitcoin Core v31.1 and implements Sugarchain mainnet networking and consensus. Its mainnet downloads and validates Sugarchain blocks and transactions, not the Bitcoin blockchain. The current mainnet parameters are defined in [`src/kernel/chainparams.cpp`](../src/kernel/chainparams.cpp). Initial synchronization time and storage depend on the chain size, pruning settings, hardware, and network connection. This candidate exposes mainnet and isolated regtest. Inherited testnet and Signet modes are disabled until native parameters are ported and verified.

The Sugarchain homepage is https://sugarchain.org/.

Current release preparation targets Linux first; Windows and macOS are deferred.
See the [Linux candidate build/package guide](sugarchain-en-linux-release.md) and
[En draft release notes](sugarchain-en-draft-release-notes.md). No public En release
or download is announced by these preparation documents. See the [native validation record](sugarchain-en-native-validation-2026-11-18.md) for local coverage and explicit exclusions, and the [native benchmark record](sugarchain-en-native-benchmarks-2026-11-18.md) for bounded component observations.

This directory also retains upstream Bitcoin Core technical references, BIPs,
example transactions, and historical release notes. Their Bitcoin names,
addresses, and external service links identify the upstream material; they
do not describe Sugarchain En releases or guarantee support by an external tool.

Running
---------------------
The following notes describe source builds and private candidates. See the Linux candidate guide for validation and package scope.

### Linux

After building or staging a candidate, run:

- `bin/sugarchain-qt` (GUI) or
- `bin/sugarchaind` (headless)
- `bin/sugarchain` (wrapper command)

The `sugarchain` command supports subcommands like `sugarchain gui`, `sugarchain node`, and `sugarchain rpc` exposing different functionality. Subcommands can be listed with `sugarchain help`.

### Windows

Native execution and installation are deferred. The Windows build notes are retained for follow-up work; no current En Windows release support is claimed.

### macOS

Native execution and packaging are deferred. The macOS build notes are retained for follow-up work; no current En macOS release support is claimed.

### Need Help?

* Contact/community: https://t.me/sugarchain
* Bug reports: https://github.com/decryp2kanon/sugarchain-en/issues

Building
---------------------
The following are developer notes on how to build Sugarchain En on your native platform. They are not complete guides, but include notes on the necessary libraries, compile flags, etc.

- [Dependencies](dependencies.md)
- [macOS Build Notes](build-osx.md)
- [Unix Build Notes](build-unix.md)
- [Windows Build Notes](build-windows-msvc.md)
- [FreeBSD Build Notes](build-freebsd.md)
- [OpenBSD Build Notes](build-openbsd.md)
- [NetBSD Build Notes](build-netbsd.md)

Development
---------------------
See this repository's [contribution guide](/CONTRIBUTING.md) for the development process and testing expectations.

- [Developer Notes](developer-notes.md)
- [Productivity Notes](productivity.md)
- [Release Process](release-process.md)
- [Upstream Bitcoin Core Source Documentation (External Link)](https://doxygen.bitcoincore.org/)
- [Translation Process](translation_process.md)
- [Translation Strings Policy](translation_strings_policy.md)
- [JSON-RPC Interface](JSON-RPC-interface.md)
- [Unauthenticated REST Interface](REST-interface.md)
- [BIPS](bips.md)
- [Dnsseed Policy](dnsseed-policy.md)
- [Benchmarking](benchmarking.md)
- [Internal Design Docs](design/)

### Resources
* Discuss Sugarchain En changes in the [project issues](https://github.com/decryp2kanon/sugarchain-en/issues) and pull requests.
* Upstream Bitcoin Core technical discussions remain useful references; they are not Sugarchain En support channels.

### Miscellaneous
- [Assets Attribution](assets-attribution.md)
- [sugarchain.conf Configuration File](bitcoin-conf.md)
- [CJDNS Support](cjdns.md)
- [Files](files.md)
- [Fuzz-testing](fuzzing.md)
- [I2P Support](i2p.md)
- [Init Scripts (systemd/upstart/openrc)](init.md)
- [Managing Wallets](managing-wallets.md)
- [Multisig Tutorial](multisig-tutorial.md)
- [Offline Signing Tutorial](offline-signing-tutorial.md)
- [P2P bad ports definition and list](p2p-bad-ports.md)
- [PSBT support](psbt.md)
- [Reduce Memory](reduce-memory.md)
- [Reduce Traffic](reduce-traffic.md)
- [Tor Support](tor.md)
- [Transaction Relay Policy](policy/README.md)
- [ZMQ](zmq.md)

License
---------------------
Distributed under the [MIT software license](/COPYING).
