# Copyright (c) 2026 The Sugarchain En developers
# Distributed under the MIT software license, see the accompanying file COPYING.
"""Native 0.16 wallet migration and signed-message compatibility.

Only fresh, unfunded, offline mainnet wallets are used. Generated private keys
and passwords stay in memory; summaries contain counts and booleans only.
Imported/watch-only/multisig wallets and historical funded rescans are outside
this probe; their existing upstream tests are retained separately.
"""

import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil

from test_framework.native_node import Node

MESSAGE = 'Sugarchain En unfunded disposable wallet compatibility probe v1'
WALLET_NAME = 'legacy'
RESTORED_NAME = 'restored'


class ProbeFailure(Exception):
    """Intentionally contains no RPC arguments, key material, or passwords."""


def require(condition):
    if not condition:
        raise ProbeFailure('A probe assertion failed')


def private_dir(path):
    path.mkdir(parents=True, exist_ok=False, mode=0o700)
    return path


def inside(path, root):
    path = Path(path).resolve()
    require(path.is_relative_to(root.resolve()))
    return path


def file_digest(path, root):
    # This function is used only on files created during this particular run.
    path = inside(path, root)
    require(path.is_file() and not path.is_symlink())
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.digest()


def public_key(info):
    if 'pubkey' in info:
        return info['pubkey']
    embedded = info.get('embedded')
    if isinstance(embedded, dict):
        return public_key(embedded)
    raise ProbeFailure('Generated address does not expose its public key')


def hd_path(value):
    require(isinstance(value, str) and value.startswith('m/'))
    return value.replace("'", 'h').replace('H', 'h')


def zero_balance(node):
    require(node.rpc('getbalance') == 0)
    require(node.rpc('getwalletinfo')['txcount'] == 0)


def own_unfunded_chain(node):
    # Explicitly disable networking again after the private helper starts.
    node.rpc('setnetworkactive', False)
    chain = node.rpc('getblockchaininfo')
    require(chain['chain'] == 'main' and chain['blocks'] == 0)
    require(node.rpc('getconnectioncount') == 0)


def old_node(binary, directory, timeout):
    return Node(binary, directory, chain='main', legacy=True, timeout=timeout,
                extra=(f'-walletdir={directory / "wallets"}',
                       '-wallet=wallet.dat', '-keypool=8'))


def new_node(binary, directory, coverage_dir, timeout):
    return Node(binary, directory, chain='main', coverage_dir=coverage_dir, timeout=timeout,
                extra=(f'-walletdir={directory / "wallets"}',
                       '-nowallet', '-keypool=8'))


def capture_addresses(node, phase):
    records = []
    for address_type in ('legacy', 'p2sh-segwit', 'bech32'):
        label = f'probe-{phase}-{address_type}'
        address = node.rpc('getnewaddress', label, address_type)
        records.append(capture_address(node, address, label, False,
                                       address_type == 'legacy'))
    address = node.rpc('getrawchangeaddress', 'legacy')
    records.append(capture_address(node, address, None, True, True))
    return records


def capture_address(node, address, label, change, signable):
    info = node.rpc('validateaddress', address)
    require(info['isvalid'] is True and info['ismine'] is True)
    require(info.get('iswatchonly', False) is False)
    path = hd_path(info['hdkeypath'])
    seed_id = info['hdmasterkeyid']
    require(isinstance(seed_id, str) and len(seed_id) == 40)
    require(path.startswith('m/0h/1h/' if change else 'm/0h/0h/'))
    record = {
        'address': address, 'pubkey': public_key(info),
        'script': info['scriptPubKey'], 'path': path, 'seed_id': seed_id,
        'label': label, 'change': change,
    }
    if signable:
        # These values are held in memory only; no JSON fixture manifest is made.
        record['wif'] = node.rpc('dumpprivkey', address)
        record['old_signature'] = node.rpc('signmessage', address, MESSAGE)
        require(node.rpc('verifymessage', address,
                         record['old_signature'], MESSAGE) is True)
    return record


def unlock(node, password):
    if password is not None:
        node.rpc('walletpassphrase', password, 600)


def lock(node, password):
    if password is not None:
        node.rpc('walletlock')


def fixture_summary():
    return {
        'ok': False, 'failure_count': 0, 'old_version': 0, 'new_version': 0,
        'fixture_created': False, 'old_shutdown_clean': False,
        'address_count': 0, 'hd_seed_count': 0,
        'migration_complete': False, 'migration_backup_matches': False,
        'descriptor_sqlite': False, 'encryption_preserved': False,
        'ownership_pubkeys_scripts_match': False, 'hd_metadata_matches': False,
        'checked_address_count': 0, 'signature_case_count': 0,
        'bidirectional_signatures': False, 'reload_matches': False,
        'backup_restore_matches': False, 'unfunded': False,
        'source_snapshot_unchanged': False,
    }


def make_fixture(root, password, result, legacy_binary, timeout):
    directory = private_dir(root / 'old')
    private_dir(directory / 'wallets')
    records = []
    with old_node(legacy_binary, directory, timeout) as node:
        own_unfunded_chain(node)
        result['old_version'] = int(node.rpc('getnetworkinfo')['version'])
        require(result['old_version'] == 160502)
        zero_balance(node)
        records.extend(capture_addresses(node, 'before'))
        if password is not None:
            node.rpc('encryptwallet', password)
            # 0.16 encryptwallet requests a normal daemon shutdown. Wait for it
            # before the helper's context exit can attempt a redundant stop.
            require(node.process.wait(timeout=60) == 0)
    result['old_shutdown_clean'] = True

    if password is not None:
        with old_node(legacy_binary, directory, timeout) as node:
            own_unfunded_chain(node)
            unlock(node, password)
            records.extend(capture_addresses(node, 'after'))
            zero_balance(node)
            lock(node, password)
            snapshot = root / 'old-checkpointed.dat'
            require(not snapshot.exists())
            node.rpc('backupwallet', str(snapshot))
    else:
        # Reopen only our generated wallet so both fixture paths take their
        # snapshots through the old checkpointing backupwallet implementation.
        with old_node(legacy_binary, directory, timeout) as node:
            own_unfunded_chain(node)
            zero_balance(node)
            snapshot = root / 'old-checkpointed.dat'
            require(not snapshot.exists())
            node.rpc('backupwallet', str(snapshot))

    snapshot.chmod(0o600)
    result['address_count'] = len(records)
    result['hd_seed_count'] = len({r['seed_id'] for r in records})
    require(result['hd_seed_count'] == (2 if password is not None else 1))
    result['fixture_created'] = True
    return directory, snapshot, file_digest(snapshot, root), records


def wallet_state(node, password):
    info = node.rpc('getwalletinfo')
    require(info['descriptors'] is True and info['format'] == 'sqlite')
    if password is not None:
        require('unlocked_until' in info and info['unlocked_until'] == 0)
    else:
        require('unlocked_until' not in info)
    zero_balance(node)


def verify_addresses(node, records, fingerprint_groups, result):
    for record in records:
        info = node.rpc('getaddressinfo', record['address'])
        require(info['address'] == record['address'])
        require(info['ismine'] is True and info['iswatchonly'] is False)
        require(info['solvable'] is True)
        require(public_key(info) == record['pubkey'])
        require(info['scriptPubKey'] == record['script'])
        require(info['ischange'] is record['change'])
        if record['label'] is not None:
            require(record['label'] in info['labels'])
        require(hd_path(info['hdkeypath']) == record['path'])
        fingerprint = info['hdmasterfingerprint']
        require(isinstance(fingerprint, str) and len(fingerprint) == 8)
        int(fingerprint, 16)
        old_seed = record['seed_id']
        if old_seed in fingerprint_groups:
            require(fingerprint_groups[old_seed] == fingerprint)
        else:
            fingerprint_groups[old_seed] = fingerprint
        # Descriptor metadata leaves hdseedid unset in the current source.
        # Comparing it to legacy hdmasterkeyid would assert an invalid contract.
        result['checked_address_count'] += 1
    require(len(fingerprint_groups) == len({r['seed_id'] for r in records}))


def signatures(old, new, records, result):
    prior_count = result['signature_case_count']
    for record in records:
        if 'wif' not in record:
            continue
        address = record['address']
        old_sig = old.rpc('signmessage', address, MESSAGE)
        require(new.rpc('verifymessage', address,
                        record['old_signature'], MESSAGE) is True)
        require(new.rpc('verifymessage', address, old_sig, MESSAGE) is True)
        new_sig = new.rpc('signmessage', address, MESSAGE)
        require(old.rpc('verifymessage', address, new_sig, MESSAGE) is True)
        old_key_sig = old.rpc('signmessagewithprivkey', record['wif'], MESSAGE)
        require(new.rpc('verifymessage', address, old_key_sig, MESSAGE) is True)
        new_key_sig = new.rpc('signmessagewithprivkey', record['wif'], MESSAGE)
        require(old.rpc('verifymessage', address, new_key_sig, MESSAGE) is True)
        require(old.rpc('verifymessage', address, new_sig,
                        MESSAGE + ' changed') is False)
        require(new.rpc('verifymessage', address, old_sig,
                        MESSAGE + ' changed') is False)
        result['signature_case_count'] += 1
    require(result['signature_case_count'] - prior_count == sum('wif' in r for r in records))


def probe_fixture(root, password, result, legacy_binary, current_binary, coverage_dir, timeout):
    old_directory, snapshot, snapshot_hash, records = make_fixture(root, password, result, legacy_binary, timeout)
    new_directory = private_dir(root / 'new')
    wallet_directory = private_dir(new_directory / 'wallets')
    migration_directory = private_dir(wallet_directory / WALLET_NAME)
    target = migration_directory / 'wallet.dat'
    require(not target.exists())
    shutil.copyfile(snapshot, target)
    target.chmod(0o600)
    require(file_digest(target, root) == snapshot_hash)

    # Both helpers control only datadirs created above. The old independent
    # signer is reopened after the clean snapshot, never on the copy migrated.
    with old_node(legacy_binary, old_directory, timeout) as old:
        own_unfunded_chain(old)
        unlock(old, password)
        zero_balance(old)
        with new_node(current_binary, new_directory, coverage_dir, timeout) as new:
            own_unfunded_chain(new)
            result['new_version'] = int(new.rpc('getnetworkinfo')['version'])
            require(new.rpc('listwallets') == [])
            if password is None:
                migration = new.rpc('migratewallet', WALLET_NAME)
            else:
                migration = new.rpc('migratewallet', WALLET_NAME, password)
            require(migration['wallet_name'] == WALLET_NAME)
            require('watchonly_name' not in migration and 'solvables_name' not in migration)
            require(new.rpc('listwallets') == [WALLET_NAME])
            result['migration_complete'] = True
            migration_backup = inside(migration['backup_path'], wallet_directory)
            require(file_digest(migration_backup, root) == snapshot_hash)
            result['migration_backup_matches'] = True
            wallet_state(new, password)
            result['descriptor_sqlite'] = True
            result['encryption_preserved'] = True
            unlock(new, password)
            groups = {}
            verify_addresses(new, records, groups, result)
            result['ownership_pubkeys_scripts_match'] = True
            result['hd_metadata_matches'] = True
            signatures(old, new, records, result)
            result['bidirectional_signatures'] = True
            zero_balance(new)
            lock(new, password)

            descriptor_backup = root / 'descriptor-backup.dat'
            require(not descriptor_backup.exists())
            new.rpc('backupwallet', str(descriptor_backup))
            descriptor_backup.chmod(0o600)
            descriptor_hash = file_digest(descriptor_backup, root)
            new.rpc('unloadwallet', WALLET_NAME, False)
            require(new.rpc('listwallets') == [])
            loaded = new.rpc('loadwallet', WALLET_NAME, False)
            require(loaded['name'] == WALLET_NAME)
            wallet_state(new, password)
            unlock(new, password)
            verify_addresses(new, records, groups, result)
            result['reload_matches'] = True
            lock(new, password)
            new.rpc('unloadwallet', WALLET_NAME, False)
            require(new.rpc('listwallets') == [])

            restored = new.rpc('restorewallet', RESTORED_NAME,
                               str(descriptor_backup), False)
            require(restored['name'] == RESTORED_NAME)
            require(new.rpc('listwallets') == [RESTORED_NAME])
            wallet_state(new, password)
            unlock(new, password)
            verify_addresses(new, records, groups, result)
            signatures(old, new, records, result)
            lock(new, password)
            new.rpc('unloadwallet', RESTORED_NAME, False)
            require(file_digest(descriptor_backup, root) == descriptor_hash)
            result['backup_restore_matches'] = True
            result['unfunded'] = True
        zero_balance(old)
        lock(old, password)
    require(file_digest(snapshot, root) == snapshot_hash)
    result['source_snapshot_unchanged'] = True
    result['ok'] = True



def run_compatibility(legacy_binary, current_binary, output_dir, *, coverage_dir=None, timeout=90):
    """Create and validate independent plaintext and encrypted legacy fixtures."""
    legacy_binary = Path(legacy_binary).resolve(strict=True)
    current_binary = Path(current_binary).resolve(strict=True)
    for binary in (legacy_binary, current_binary):
        require(binary.is_file() and os.access(binary, os.X_OK))
    root = private_dir(Path(output_dir))
    summary = {name: fixture_summary() for name in ('plain', 'encrypted')}
    for name, result in summary.items():
        password = secrets.token_urlsafe(32) if name == 'encrypted' else None
        fixture = private_dir(root / name)
        try:
            probe_fixture(fixture, password, result, legacy_binary, current_binary,
                          coverage_dir, timeout)
        except Exception:
            # RPC error text or exception arguments can contain key material.
            result['failure_count'] += 1
            (root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
            raise ProbeFailure(f'Native legacy {name} wallet compatibility failed') from None
        finally:
            password = None
    (root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary
