// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-present The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <primitives/block.h>

#include <crypto/yespower-1.0.1/yespower.h>
#include <hash.h>
#include <streams.h>
#include <tinyformat.h>

#include <algorithm>
#include <iterator>
#include <memory>
#include <span>
#include <sstream>
#include <stdexcept>

#ifdef WIN32
#include <windows.h>
#ifdef SUGARCHAIN_WINDOWS_KERNEL_DLL
#include <atomic>
#endif
#else
#include <pthread.h>
#endif

namespace {
// Each verification worker owns its scratch allocation. Unlike yespower_tls,
// release it when the thread exits, including when a worker pool is destroyed.
struct YespowerLocal {
    yespower_local_t memory;
    YespowerLocal()
    {
        if (yespower_init_local(&memory)) throw std::runtime_error("YespowerSugar: failed to initialize scratch memory");
    }
    ~YespowerLocal() { yespower_free_local(&memory); }
    YespowerLocal(const YespowerLocal&) = delete;
    YespowerLocal& operator=(const YespowerLocal&) = delete;
};

#ifdef WIN32
void NTAPI FreeYespowerLocal(void* value)
#else
void FreeYespowerLocal(void* value)
#endif
{
    delete static_cast<YespowerLocal*>(value);
}

#ifdef SUGARCHAIN_WINDOWS_KERNEL_DLL
// A host can unload the shared kernel while the threads that used it still exist.
constinit std::atomic<DWORD> g_kernel_fls_key{FLS_OUT_OF_INDEXES};
#endif

YespowerLocal& GetYespowerLocal()
{
#ifdef WIN32
    // Keep the callback registered for the lifetime of the executable. Worker
    // threads release their own scratch when they exit.
    static const DWORD key{[] {
        const DWORD index{FlsAlloc(FreeYespowerLocal)};
        if (index == FLS_OUT_OF_INDEXES) throw std::runtime_error("YespowerSugar: failed to create scratch key");
#ifdef SUGARCHAIN_WINDOWS_KERNEL_DLL
        g_kernel_fls_key.store(index, std::memory_order_relaxed);
#endif
        return index;
    }()};
    auto* value{static_cast<YespowerLocal*>(FlsGetValue(key))};
#else
    // A POSIX key must remain available to workers until their thread exit.
    static const pthread_key_t key{[] {
        pthread_key_t created;
        if (pthread_key_create(&created, FreeYespowerLocal)) throw std::runtime_error("YespowerSugar: failed to create scratch key");
        return created;
    }()};
    auto* value{static_cast<YespowerLocal*>(pthread_getspecific(key))};
#endif
    if (value) return *value;
    auto local{std::make_unique<YespowerLocal>()};
#ifdef WIN32
    if (!FlsSetValue(key, local.get())) throw std::runtime_error("YespowerSugar: failed to set scratch memory");
#else
    if (pthread_setspecific(key, local.get())) throw std::runtime_error("YespowerSugar: failed to set scratch memory");
#endif
    return *local.release();
}
} // namespace

#ifdef SUGARCHAIN_WINDOWS_KERNEL_DLL
extern "C" BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID reserved)
{
    if (reason == DLL_PROCESS_DETACH && reserved == nullptr) {
        // FreeLibrary: release populated slots before the callback code unloads.
        // At process termination Windows reclaims the entire address space.
        const DWORD index{g_kernel_fls_key.load(std::memory_order_relaxed)};
        if (index != FLS_OUT_OF_INDEXES) FlsFree(index);
    }
    return TRUE;
}
#endif

uint256 CBlockHeader::GetHash() const
{
    return (HashWriter{} << *this).GetHash();
}

// Official Sugarchain YespowerSugar parameters. The block identifier remains SHA256d.
uint256 CBlockHeader::GetPoWHash() const
{
    static_assert(YESPOWER_SUGAR_VERSION == YESPOWER_1_0);
    static constexpr yespower_params_t params{YESPOWER_1_0, YESPOWER_SUGAR_N, YESPOWER_SUGAR_R,
        YESPOWER_SUGAR_PERSONALIZATION, sizeof(YESPOWER_SUGAR_PERSONALIZATION) - 1};
    DataStream serialized;
    serialized << *this;
    yespower_binary_t result;
    auto& local{GetYespowerLocal()};
    if (yespower(&local.memory, reinterpret_cast<const uint8_t*>(serialized.data()), serialized.size(), &params, &result)) {
        throw std::runtime_error("YespowerSugar: failed to compute proof of work");
    }
    uint256 hash;
    std::copy(std::begin(result.uc), std::end(result.uc), hash.begin());
    return hash;
}

std::string CBlock::ToString() const
{
    std::stringstream s;
    s << strprintf("CBlock(hash=%s, ver=0x%08x, hashPrevBlock=%s, hashMerkleRoot=%s, nTime=%u, nBits=%08x, nNonce=%u, vtx=%u)\n",
        GetHash().ToString(),
        nVersion,
        hashPrevBlock.ToString(),
        hashMerkleRoot.ToString(),
        nTime, nBits, nNonce,
        vtx.size());
    for (const auto& tx : vtx) {
        s << "  " << tx->ToString() << "\n";
    }
    return s.str();
}
