import os
import json
import time
import logging
from typing import Dict, Any, Optional

import requests
from web3 import Web3
from web3.contract import Contract
from web3.logs import DISCARD
from web3.exceptions import MismatchedABI
from dotenv import load_dotenv

# --- Configuration & Setup ---

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- Constants ---

# This is a sample ABI for a hypothetical bridge contract.
# It includes a 'TokensLocked' event which the listener will monitor.
BRIDGE_CONTRACT_ABI = json.dumps([
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "sender", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "token", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "destinationChainId", "type": "uint256"},
            {"indexed": False, "internalType": "bytes", "name": "recipient", "type": "bytes"}
        ],
        "name": "TokensLocked",
        "type": "event"
    }
])

# --- Classes ---

class StateDB:
    """
    A simple file-based state manager to prevent event replay attacks.

    This class simulates a persistent database by storing the transaction hashes
    of processed events in a local JSON file. Before processing a new event,
    the system checks this database to ensure the event hasn't been handled before.
    """
    def __init__(self, db_path: str = 'processed_events_db.json'):
        """Initializes the StateDB instance.

        Args:
            db_path (str): The file path for the persistent state database.
        """
        self.db_path = db_path
        self._db = self._load_db()
        logging.info(f"StateDB initialized with path: {self.db_path}")

    def _load_db(self) -> Dict[str, Any]:
        """Loads the database from the JSON file."""
        try:
            with open(self.db_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logging.warning("Database file not found or invalid. Starting with an empty state.")
            return {}

    def _save_db(self):
        """Saves the current state to the JSON file."""
        try:
            with open(self.db_path, 'w') as f:
                json.dump(self._db, f, indent=4)
        except IOError as e:
            logging.error(f"Failed to save state database: {e}")

    def has_processed(self, tx_hash: str) -> bool:
        """Checks if a transaction hash has already been processed."""
        return tx_hash in self._db

    def mark_as_processed(self, tx_hash: str, event_data: Dict[str, Any]):
        """Marks a transaction hash as processed and saves its details."""
        if self.has_processed(tx_hash):
            logging.warning(f"Attempted to re-process transaction hash: {tx_hash}")
            return
        self._db[tx_hash] = {
            'timestamp': int(time.time()),
            'event_data': str(event_data) # Convert event data to string for JSON compatibility
        }
        self._save_db()
        logging.info(f"Marked transaction {tx_hash} as processed.")


class BlockchainConnector:
    """
    Manages the connection to a blockchain node via Web3.py.

    This class abstracts the logic of connecting to an RPC endpoint, checking the
    connection status, and providing a Web3 instance for interactions.
    It supports retries for initial connection failures.
    """
    def __init__(self, rpc_url: str, connection_retries: int = 3, retry_delay: int = 5):
        """
        Initializes the connector.

        Args:
            rpc_url (str): The URL of the blockchain RPC endpoint.
            connection_retries (int): Number of retries for the initial connection.
            retry_delay (int): Delay in seconds between retries.
        """
        self.rpc_url = rpc_url
        self.web3: Optional[Web3] = None
        self._connect(connection_retries, retry_delay)

    def _connect(self, retries: int, delay: int):
        """Establishes the connection to the RPC endpoint."""
        for attempt in range(retries):
            try:
                logging.info(f"Attempting to connect to RPC: {self.rpc_url} (Attempt {attempt + 1}/{retries})")
                self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
                if self.web3.is_connected():
                    logging.info(f"Successfully connected to chain ID: {self.web3.eth.chain_id}")
                    return
                else:
                    raise ConnectionError("Web3 provider failed to connect.")
            except (requests.exceptions.ConnectionError, ConnectionError) as e:
                logging.error(f"Connection attempt failed: {e}")
                if attempt < retries - 1:
                    logging.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    logging.critical("All connection attempts failed. Exiting.")
                    raise

    def get_contract(self, address: str, abi: str) -> Optional[Contract]:
        """Returns a Web3 contract instance if connected."""
        if not self.is_connected() or not self.web3:
            logging.error("Cannot get contract, not connected to blockchain.")
            return None
        try:
            return self.web3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)
        except MismatchedABI as e:
             logging.error(f"ABI mismatch for contract at {address}: {e}")
             return None
        except Exception as e:
            logging.error(f"Failed to instantiate contract at {address}: {e}")
            return None

    def is_connected(self) -> bool:
        """Checks the current connection status."""
        return self.web3 is not None and self.web3.is_connected()


class TransactionProcessor:
    """
    Processes events captured by the listener.

    This class is responsible for the business logic of what to do when a valid
    'TokensLocked' event is detected. It simulates the creation and signing of a
    transaction for the destination chain.
    """
    def __init__(self, state_db: StateDB):
        """
        Initializes the processor.

        Args:
            state_db (StateDB): An instance of the state database to prevent replays.
        """
        self.state_db = state_db
        # In a real-world scenario, this would be a private key for the destination chain validator/relayer
        self.destination_chain_signer_key = os.getenv("DESTINATION_SIGNER_KEY", "0x_placeholder_key")

    def process_lock_event(self, event: Dict[str, Any]):
        """
        Handles a single 'TokensLocked' event.

        This method performs validation, checks for replays, and then simulates
        the action on the destination chain.
        """
        tx_hash = event['transactionHash'].hex()
        log_index = event['logIndex']
        event_identifier = f"{tx_hash}-{log_index}"

        logging.info(f"Processing event from transaction: {tx_hash}")

        # 1. Replay Protection: Check if this event has been processed before.
        if self.state_db.has_processed(event_identifier):
            logging.warning(f"Event {event_identifier} has already been processed. Skipping.")
            return

        # 2. Validation (example)
        event_args = event['args']
        if not all(k in event_args for k in ['sender', 'token', 'amount', 'destinationChainId']):
            logging.error(f"Malformed event {event_identifier}: missing required arguments. Skipping.")
            return
        
        if event_args['amount'] <= 0:
            logging.error(f"Invalid event {event_identifier}: lock amount must be positive. Skipping.")
            return

        # 3. Simulate Destination Chain Transaction
        logging.info(f"Event valid. Simulating minting transaction on chain {event_args['destinationChainId']}.")
        self._simulate_destination_tx(event_args)

        # 4. Mark as processed
        self.state_db.mark_as_processed(event_identifier, event_args)
        logging.info(f"Successfully processed and marked event {event_identifier}.")

    def _simulate_destination_tx(self, event_args: Dict[str, Any]):
        """
        Simulates creating, signing, and sending a transaction on the destination chain.
        
        In a real bridge, this would involve:
        - Connecting to the destination chain's RPC.
        - Crafting a transaction to call a 'mint' or 'unlock' function on a destination contract.
        - Signing it with a secure key.
        - Sending it and waiting for confirmation.
        """
        tx_details = {
            'from': Web3.to_checksum_address(event_args['sender']),
            'to_contract': '0xDestinationContractAddress...',
            'function': 'mintBridgedTokens',
            'args': {
                'recipient': event_args['recipient'],
                'amount': event_args['amount'],
                'token': event_args['token']
            },
            'signed_by': self.destination_chain_signer_key[:10] + '...'
        }
        logging.info(f"[SIMULATION] Creating destination transaction: {tx_details}")
        # Simulate a network delay for the transaction
        time.sleep(1)
        logging.info(f"[SIMULATION] Destination transaction for amount {event_args['amount']} sent and confirmed.")


class BridgeEventListener:
    """
    The main orchestrator class for the cross-chain bridge event listener.
    
    It sets up connections, initializes event filters, and runs an infinite loop
    to poll for new events from the source chain bridge contract.
    """
    def __init__(self, config: Dict[str, Any]):
        """
        Initializes the event listener.
        
        Args:
            config (Dict[str, Any]): A dictionary containing configuration parameters.
        """
        self.config = config
        self.connector = BlockchainConnector(rpc_url=config['rpc_url'])
        self.state_db = StateDB()
        self.processor = TransactionProcessor(self.state_db)
        self.contract: Optional[Contract] = self._setup_contract()
        self.event_filter = None

    def _setup_contract(self) -> Optional[Contract]:
        """Initializes the contract object to listen to."""
        if not self.connector.is_connected():
            logging.critical("Cannot setup contract, blockchain connector is not available.")
            return None
        
        contract = self.connector.get_contract(
            address=self.config['contract_address'],
            abi=self.config['contract_abi']
        )
        if not contract:
            logging.critical("Failed to initialize bridge contract instance. Exiting.")
            return None

        logging.info(f"Successfully initialized contract instance at {self.config['contract_address']}")
        return contract

    def start_listening(self, poll_interval: int = 5):
        """
        Starts the main event listening loop.

        Args:
            poll_interval (int): The interval in seconds to poll for new events.
        """
        if not self.contract or not self.connector.web3:
            logging.error("Cannot start listening, contract or web3 instance not available.")
            return
        
        # Create a filter for the 'TokensLocked' event
        try:
            self.event_filter = self.contract.events.TokensLocked.create_filter(fromBlock='latest')
        except Exception as e:
            logging.critical(f"Failed to create event filter: {e}")
            return

        logging.info("Starting event listener loop... polling for 'TokensLocked' events.")
        while True:
            try:
                if not self.connector.is_connected():
                    logging.error("Connection lost. Attempting to reconnect...")
                    # In a real app, you would implement a robust reconnection strategy.
                    # For this simulation, we will exit.
                    break

                events = self.event_filter.get_new_entries()
                if not events:
                    logging.info("No new events found. Waiting...")
                else:
                    for event in events:
                        self.processor.process_lock_event(event)
                
                time.sleep(poll_interval)

            except Exception as e:
                logging.error(f"An error occurred in the listening loop: {e}")
                time.sleep(poll_interval * 2) # Wait longer after an error
            except KeyboardInterrupt:
                logging.info("Shutdown signal received. Exiting listener loop.")
                break

# --- Main Execution ---

def main():
    """Main function to configure and run the listener."""
    # Load configuration from environment variables
    # Example: a public RPC for Ethereum Sepolia testnet
    rpc_url = os.getenv("RPC_URL")
    # Example: a hypothetical bridge contract address on Sepolia
    contract_address = os.getenv("BRIDGE_CONTRACT_ADDRESS")

    if not rpc_url or not contract_address:
        logging.critical("Missing required environment variables: RPC_URL and/or BRIDGE_CONTRACT_ADDRESS")
        logging.critical("Please create a .env file with these values.")
        return

    config = {
        "rpc_url": rpc_url,
        "contract_address": contract_address,
        "contract_abi": BRIDGE_CONTRACT_ABI
    }

    listener = BridgeEventListener(config)
    listener.start_listening(poll_interval=10)

if __name__ == "__main__":
    main()
# @-internal-utility-start
def format_timestamp_8462(ts: float):
    """Formats a unix timestamp into ISO format. Updated on 2025-10-26 22:42:45"""
    import datetime
    dt_object = datetime.datetime.fromtimestamp(ts)
    return dt_object.isoformat()
# @-internal-utility-end

