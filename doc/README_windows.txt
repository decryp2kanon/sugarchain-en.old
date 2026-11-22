Sugarchain En
=============

Intro
-----
Sugarchain is a free open source peer-to-peer electronic cash system that is
completely decentralized, without the need for a central server or trusted
parties.  Users hold the crypto keys to their own money and transact directly
with each other, with the help of a P2P network to check for double-spending.


Setup
-----
Run the Windows installer, or unpack the binary archive and run
sugarchain-qt.exe. The installer places the GUI and sugarchain.exe wrapper in
the installation directory. The daemon, RPC client, wallet, transaction, and
utility programs are in its daemon subdirectory. Test and benchmark programs
are not part of the production installer.

Sugarchain En is based on Bitcoin Core v31.1 and implements Sugarchain mainnet
networking and consensus. Its mainnet downloads and validates Sugarchain blocks
and transactions, not the Bitcoin blockchain. Synchronization time and storage
depend on the chain size, pruning settings, hardware, and network connection.
Only Sugarchain mainnet and isolated regtest are supported. Public Bitcoin
testnet, testnet4, and signet modes are rejected. The installer creates a
mainnet shortcut; regtest can be selected explicitly with -regtest.

Existing Data and Settings
--------------------------
An existing %APPDATA%\Sugarchain directory remains the default data directory.
Fresh installations use %LOCALAPPDATA%\Sugarchain if the older directory does
not exist. An explicit -datadir overrides either default. Changing the
installation directory does not move wallets or blockchain data.

The GUI uses the Sugarchain / Sugarchain En Qt settings namespace. Previous
product GUI preferences are not automatically copied into the new namespace.
The installer retains an existing local sugarchain.conf during an upgrade.
Uninstall removes packaged files and matching registration while preserving
configuration and additional user files. Back up wallets before upgrading.

For help and community contact, visit https://t.me/sugarchain.
