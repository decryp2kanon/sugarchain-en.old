#!/usr/bin/env python3
# Copyright (c) 2026 The Sugarchain En developers
# Distributed under the MIT software license, see the accompanying file COPYING.
"""Migrate genuine Sugarchain 0.16 plaintext/encrypted wallets without peers."""

import os
from pathlib import Path

from test_framework.legacy_wallet import run_compatibility
from test_framework.test_framework import BitcoinTestFramework, SkipTest


class SugarchainLegacyWalletTest(BitcoinTestFramework):
    def set_test_params(self):
        self.num_nodes = 0
        self.setup_clean_chain = True

    def skip_test_if_missing_module(self):
        self.skip_if_no_wallet()
        if not os.environ.get("SUGARCHAIN_LEGACY_BINARY"):
            raise SkipTest("Genuine Sugarchain 0.16 binary not provided; upstream Bitcoin releases are incompatible")

    def setup_network(self):
        # The probe controls independent mainnet children, without any P2P links.
        pass

    def run_test(self):
        summary = run_compatibility(
            os.environ["SUGARCHAIN_LEGACY_BINARY"], self.binary_paths.bitcoind,
            Path(self.options.tmpdir) / "native-legacy-wallets",
            coverage_dir=self.options.coveragedir,
            timeout=90 * self.options.timeout_factor,
        )
        for result in summary.values():
            assert result["ok"] and not result["failure_count"]
        self.log.info("Native legacy wallet migration passed: %s", {
            name: {key: result[key] for key in ("old_version", "address_count",
                   "checked_address_count", "signature_case_count")}
            for name, result in summary.items()
        })


if __name__ == "__main__":
    SugarchainLegacyWalletTest(__file__).main()
