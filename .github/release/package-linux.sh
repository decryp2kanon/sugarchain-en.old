#!/usr/bin/env bash
# Run from the release source checkout on a fresh Ubuntu GitHub Actions runner.
set -euo pipefail
export LC_ALL=C

host=${RELEASE_HOST:?}
emulator=${RELEASE_EMULATOR:?}
[[ $(git rev-parse HEAD) == "${SOURCE_REVISION:?}" ]]
jobs=$(nproc)
if (( jobs > 4 )); then jobs=4; fi
depends_host=$host
if [[ "$emulator" == native ]]; then
    depends_host=$(cd depends && ./config.guess)
    [[ ${depends_host%%-*} == "${host%%-*}" ]]
fi
prefix="$PWD/depends/$depends_host"
make -C depends -j"$jobs" HOST="$depends_host" NO_IPC=1
cmake -S . -B build -G Ninja --toolchain "$prefix/toolchain.cmake" \
    -DCMAKE_BUILD_TYPE=Release -DBUILD_GUI=ON -DENABLE_WALLET=ON -DENABLE_IPC=OFF \
    -DBUILD_TESTS=OFF -DBUILD_GUI_TESTS=OFF -DBUILD_TX=ON -DBUILD_UTIL=ON \
    -DBUILD_WALLET_TOOL=ON -DBUILD_BENCH=OFF -DBUILD_FUZZ_BINARY=OFF -DINSTALL_MAN=ON \
    '-DCMAKE_INSTALL_RPATH=$ORIGIN/../lib' \
    '-DCMAKE_EXE_LINKER_FLAGS=-static-libgcc -static-libstdc++ -Wl,--disable-new-dtags'
cmake --build build --parallel "$jobs"

package="sugarchain-en-31.1.0-$host"
stage="$PWD/stage/$package"
docs="$stage/share/doc/SugarchainEn"
mkdir -p "$stage" out
cmake --install build --strip --prefix "$stage"
install -m644 README.md doc/sugarchain-en-{linux-release,draft-release-notes}.md "$docs/"
install -m644 share/examples/sugarchain.conf "$stage/sugarchain.conf"
cp -R share/rpcauth "$stage/share/"
# Qt is static. Its font backends are shared in the project's depends recipes.
mkdir -p "$stage/lib"
for lib in libfreetype.so.6 libfontconfig.so.1; do
    install -m644 "$prefix/lib/$lib" "$stage/lib/$lib"
done

python3 "$(dirname "$0")/linux-notices.py" depends/sources "$docs/dependency-notices"

programs=(sugarchain sugarchaind sugarchain-cli sugarchain-qt sugarchain-tx sugarchain-util sugarchain-wallet)
[[ $(find "$stage/bin" -mindepth 1 -maxdepth 1 | wc -l) -eq ${#programs[@]} ]]
for program in "${programs[@]}"; do
    [[ -x "$stage/bin/$program" && -s "$stage/share/man/man1/$program.1" ]]
done
[[ -s "$docs/COPYING" && -s "$docs/copyright" ]]
[[ -s "$stage/share/applications/org.sugarchain.SugarchainEn.desktop" ]]
[[ -s "$stage/share/metainfo/org.sugarchain.SugarchainEn.metainfo.xml" ]]
compgen -G "$stage/share/icons/hicolor/*/apps/sugarchain.png" > /dev/null

case "$host" in
    x86_64-linux-gnu)     machine='Advanced Micro Devices X86-64'; endian=little; bits=64 ;;
    aarch64-linux-gnu)    machine=AArch64; endian=little; bits=64 ;;
    arm-linux-gnueabihf)  machine=ARM; endian=little; bits=32 ;;
    riscv64-linux-gnu)    machine=RISC-V; endian=little; bits=64 ;;
    powerpc64-linux-gnu)  machine=PowerPC64; endian=big; bits=64 ;;
    *) exit 1 ;;
esac
binaries=("$stage"/bin/* "$stage"/lib/*)
# Carry any additional GCC runtimes needed by the installed ELF objects.
for lib in libatomic.so.1 libstdc++.so.6 libgcc_s.so.1; do
    if readelf -d "${binaries[@]}" | grep -F "[$lib]" > /dev/null; then
        runtime=$("$host-g++" -print-file-name="$lib")
        install -m644 "$runtime" "$stage/lib/$lib"
        binaries+=("$stage/lib/$lib")
        gcc_major=$("$host-g++" -dumpversion | cut -d. -f1)
        install -m644 "/usr/share/doc/gcc-$gcc_major-base/copyright" "$docs/dependency-notices/GCC-runtime-copyright"
    fi
done
report="$docs/linux-runtime.txt"
{
    echo "Sugarchain En 31.1.0 ($host)"
    echo "Source: $SOURCE_REVISION"
    echo "Build OS: $(. /etc/os-release && echo "$PRETTY_NAME")"
    "$host-g++" -dumpfullversion | sed 's/^/GCC: /'
    echo "Build: Release, wallet and static Qt, IPC disabled."
    echo "Runtime verification: $emulator on $(uname -m)."
    echo "The GUI uses X11 or XWayland and the system's font configuration."
    echo "A matching Linux kernel and glibc are required. Each file's highest imported glibc version follows."
} > "$report"
for binary in "${binaries[@]}"; do
    header=$(readelf -h "$binary")
    grep -Eq "Machine: +$machine$" <<< "$header"
    grep -Fq "$endian endian" <<< "$header"
    grep -Eq "Class: +ELF$bits$" <<< "$header"
    if [[ $host == arm-linux-gnueabihf ]]; then grep -Fq 'hard-float ABI' <<< "$header"; fi
    needed=$(readelf -d "$binary" | sed -n 's/.*(NEEDED).*\[\([^]]*\)\].*/\1/p')
    for lib in $needed; do
        case "$lib" in
            libc.so.6|libm.so.6|libdl.so.2|libpthread.so.0|librt.so.1|ld-linux*.so.*|ld64.so.1|libresolv.so.2) ;;
            *) [[ -f "$stage/lib/$lib" ]] || { echo "Missing library $lib for $binary"; exit 1; } ;;
        esac
    done
    glibc=$(readelf -VW "$binary" | grep -oE 'GLIBC_[0-9.]*[0-9]' | sort -Vu | tail -1)
    printf '%s: %s; %s\n' "${binary#"$stage"/}" "$glibc" "$(xargs <<< "$needed")" >> "$report"
done

epoch=$(git show -s --format=%ct HEAD)
tar --sort=name --mtime="@$epoch" --owner=0 --group=0 --numeric-owner -C stage -cf - "$package" |
    gzip -n -9 > "out/$package.tar.gz"
(cd out && sha256sum "$package.tar.gz" > "$package.tar.gz.sha256" && sha256sum -c "$package.tar.gz.sha256")
sandbox=$(mktemp -d "${RUNNER_TEMP:?}/linux-check.XXXXXX")
tar -xzf "out/$package.tar.gz" -C "$sandbox"
bindir="$sandbox/$package/bin"
export XDG_DATA_HOME="$sandbox/data" XDG_CONFIG_HOME="$sandbox/config" XDG_CACHE_HOME="$sandbox/cache"
export XDG_RUNTIME_DIR="$sandbox/run" FONTCONFIG_FILE=/etc/fonts/fonts.conf
export QT_QPA_PLATFORM=xcb
mkdir -m700 "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_RUNTIME_DIR" "$sandbox/node"
run=()
if [[ "$emulator" != native ]]; then run=("$emulator" -L "/usr/$host"); fi
for program in "${programs[@]}"; do
    opts=(-version)
    case "$program" in
        sugarchain) opts=(--version) ;;
        sugarchaind) opts=("-datadir=$sandbox/node" -version) ;;
    esac
    timeout 90 "${run[@]}" "$bindir/$program" "${opts[@]}" > "$sandbox/$program.version"
    grep -F 'Sugarchain En' "$sandbox/$program.version" > /dev/null
done
cli=("${run[@]}" "$bindir/sugarchain-cli" "-datadir=$sandbox/node" -rpcport=26443)
"${run[@]}" "$bindir/sugarchaind" "-datadir=$sandbox/node" -rpcport=26443 -server=1 \
    -listen=0 -connect=0 -dnsseed=0 -discover=0 -networkactive=0 -maxconnections=0 -keypool=4 \
    > "$sandbox/node.log" 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || true' EXIT
actual=$(timeout 120 "${cli[@]}" -rpcwait -rpcwaittimeout=100 getblockhash 0)
[[ $actual == 7d5eaec2dbb75f99feadfa524c78b7cabc1d8c8204f79d4f3a83381b811b0adc ]]
"${cli[@]}" createwallet en_package_check > /dev/null
address=$("${cli[@]}" -rpcwallet=en_package_check getnewaddress '' bech32)
[[ $address == sugar1q* ]]
"${cli[@]}" stop > /dev/null
wait "$pid"
trap - EXIT
cat "$report"
