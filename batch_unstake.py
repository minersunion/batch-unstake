import argparse
import os
import bittensor
from bittensor.utils.balance import Balance
from typing import List, Optional, Tuple


def get_hotkey_wallets_for_wallet(wallet) -> List["bittensor.wallet"]:
    hotkey_wallets = []
    hotkeys_path = os.path.expanduser("~/.bittensor/wallets") + "/" + wallet.name + "/hotkeys"
    try:
        hotkey_files = next(os.walk(os.path.expanduser(hotkeys_path)))[2]
    except StopIteration:
        hotkey_files = []
    for hotkey_file_name in hotkey_files:
        try:
            hotkey_for_name = bittensor.wallet(
                path=wallet.path, name=wallet.name, hotkey=hotkey_file_name
            )
            if (
                hotkey_for_name.hotkey_file.exists_on_device()
                and not hotkey_for_name.hotkey_file.is_encrypted()
            ):
                hotkey_wallets.append(hotkey_for_name)
        except Exception:
            pass
    return hotkey_wallets

def batch_unstake():
    parser = argparse.ArgumentParser(description="Subnet registration script.")
    parser.add_argument("--coldkey", required=True, default="default")
    args = parser.parse_args()

    subtensor = bittensor.subtensor(network="finney")

    wallet = bittensor.wallet(name=args.coldkey)

    old_balance = subtensor.get_balance(wallet.coldkeypub.ss58_address)

    # Unstake from all hotkeys.
    all_hotkeys: List[bittensor.wallet] = get_hotkey_wallets_for_wallet(
        wallet=wallet
    )

    hotkeys_to_unstake_from: List[str] = [
        wallet.hotkey.ss58_address for wallet in all_hotkeys
    ]  # definitely wallets

    final_hotkeys_ss58: List[str] = []
    final_amounts: List[Balance] = []  # In raos

    for hotkey_ss58 in hotkeys_to_unstake_from:
        hotkey_stake: Balance = subtensor.get_stake_for_coldkey_and_hotkey(
            hotkey_ss58=hotkey_ss58, coldkey_ss58=wallet.coldkeypub.ss58_address
        )
        unstake_amount_tao: float = hotkey_stake.tao  # The amount specified to unstake.

        if unstake_amount_tao:
            # There is a specified amount to unstake.
            final_amounts.append(bittensor.Balance.from_tao(unstake_amount_tao))
            final_hotkeys_ss58.append(hotkey_ss58)  # add the ss58 address.

    if not len(final_amounts):
        print("No taos staked to this wallet's coldkeys")
        return

    hotkeys_ss58_and_amounts = zip(final_hotkeys_ss58, final_amounts)

    unstake_calls = [subtensor.substrate.compose_call(
        call_module="SubtensorModule",
        call_function="remove_stake",
        call_params={"hotkey": hotkey_ss58, "amount_unstaked": rao_amount},
    ) for hotkey_ss58, rao_amount in hotkeys_ss58_and_amounts]

    # Prepare batch call
    batch_call = subtensor.substrate.compose_call(
        call_module='Utility',
        call_function='batch',
        call_params={
            'calls': unstake_calls  # List of calls to batch
        }
    )

    extrinsic = subtensor.substrate.create_signed_extrinsic(
        call=batch_call, keypair=wallet.coldkey
    )

    response = subtensor.substrate.submit_extrinsic(
        extrinsic,
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )

    response.process_events()
    if response.is_success:
        print("Successfully unstaked from all hotkeys with a non-zero staked amount")
    else:
        print("Failed to unstake")

    new_balance = subtensor.get_balance(wallet.coldkeypub.ss58_address)
        
    print(f"Balance: {old_balance} ==> {new_balance}")

if __name__ == "__main__":
    batch_unstake()
