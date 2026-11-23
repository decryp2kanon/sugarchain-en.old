// Copyright (c) 2015-present The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_TEST_UTIL_POW_H
#define BITCOIN_TEST_UTIL_POW_H

#include <arith_uint256.h>
#include <consensus/params.h>

#include <algorithm>
#include <cstdint>

/** Bitcoin mainnet parameters for the historical interval retarget tests. */
inline Consensus::Params BitcoinMainnetPowParams()
{
    Consensus::Params params{};
    params.powLimit = uint256{"00000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"};
    params.nPowTargetTimespan = 14 * 24 * 60 * 60;
    params.nPowTargetSpacing = 10 * 60;
    return params;
}

/** Reference SugarShield target using generic 256-bit arithmetic. */
inline uint32_t ReferenceSugarShieldWorkRequired(const arith_uint256& total, int64_t span, const Consensus::Params& params)
{
    const int64_t target_span{params.AveragingWindowTimespan()};
    const int64_t damped{target_span + (span - target_span) / 4};
    const auto adjusted{std::clamp(damped, params.MinActualTimespan(), params.MaxActualTimespan())};
    arith_uint256 reference{total / arith_uint256{uint64_t(params.nPowAveragingWindow)}};
    reference /= arith_uint256{uint64_t(target_span)};
    reference *= arith_uint256{uint64_t(adjusted)};
    return std::min(reference, UintToArith256(params.powLimit)).GetCompact();
}

#endif // BITCOIN_TEST_UTIL_POW_H
