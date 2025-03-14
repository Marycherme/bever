# bever - Cross-Chain Bridge Event Listener Simulation

This repository contains a Python script that simulates a critical component of a cross-chain bridge: an event listener. This script is designed as an architectural showcase, demonstrating a robust, modular, and fault-tolerant approach to monitoring on-chain events on a source chain to trigger actions on a destination chain.

## Concept

In a typical cross-chain bridge, users lock assets (e.g., ERC20 tokens) in a smart contract on a source blockchain (e.g., Ethereum). This action emits an event, like `TokensLocked`. A network of off-chain nodes, often called relayers or validators, listens for this specific event.

Upon detecting a `TokensLocked` event, a relayer validates it and then initiates a transaction on the destination blockchain (e.g., Polygon) to mint or unlock a corresponding amount of a pegged asset for the user.

This `bever` script simulates the role of such a relayer node. It connects to a source chain, listens for `TokensLocked` events from a specified bridge contract, processes them, and simulates the subsequent action on the destination chain. Key features include replay protection (to prevent double-spending) and a modular architecture.

## Code Architecture

The script is built with a clear separation of concerns, using several distinct classes:

*   `BlockchainConnector`:
    *   **Responsibility**: Manages the connection to the source blockchain's RPC endpoint using `web3.py`.
    *   **Features**: Handles initial connection logic, provides connection status checks, and includes a retry mechanism for robustness.

*   `StateDB`:
    *   **Responsibility**: Provides a simple, file-based persistent state to prevent event replay attacks.
    *   **Features**: It records the transaction hashes of successfully processed events in a JSON file. Before processing a new event, it checks this database to ensure the event is unique.

*   `TransactionProcessor`:
    *   **Responsibility**: Encapsulates the business logic for handling a new event.
    *   **Features**: It receives event data, validates it, checks with the `StateDB` for replays, and then simulates the creation and signing of a transaction for the destination chain.

*   `BridgeEventListener`:
    *   **Responsibility**: The main orchestrator class.
    *   **Features**: It initializes all other components, sets up the smart contract and the event filter using `web3.py`, and runs the primary polling loop to listen for new events.

This modular design makes the system easier to understand, maintain, and test. For instance, the `BlockchainConnector` could be extended to support WebSocket providers, or the `StateDB` could be replaced with a more robust database like Redis or PostgreSQL without altering the core listening logic.

## How it Works

The script executes the following sequence of operations:

1.  **Initialization**: The `main` function loads configuration from a `.env` file, including the source chain RPC URL and the bridge contract address.
2.  **Connection**: The `BridgeEventListener` instantiates the `BlockchainConnector`, which establishes a connection to the specified RPC URL.
3.  **Contract Setup**: A `web3.py` contract object is created using the provided address and ABI, allowing the script to interact with the smart contract.
4.  **Filter Creation**: An event filter is created specifically for the `TokensLocked` event on the bridge contract. This filter will watch for new events from the latest block onwards.
5.  **Listening Loop**: The script enters an infinite loop where it periodically polls the blockchain for new events captured by the filter.
6.  **Event Processing**: When one or more new events are detected:
    a. Each event is passed to the `TransactionProcessor`.
    b. The processor extracts the transaction hash and checks the `StateDB` to see if it has been processed before. If so, it's skipped.
    c. The event data is validated (e.g., ensuring the lock amount is positive).
    d. The processor then *simulates* the process of creating, signing, and sending a transaction to the destination chain to mint the corresponding tokens.
    e. Upon successful simulation, the event's transaction hash is saved to the `StateDB` to prevent future reprocessing.
7.  **Error Handling**: The loop includes error handling for potential connection drops or other exceptions, ensuring the listener can run continuously.

## Usage Example

Follow these steps to run the event listener simulation.

**1. Clone the Repository**

```bash
git clone <repository-url>
cd bever
```

**2. Create a Virtual Environment**

It's highly recommended to use a virtual environment.

```bash
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
```

**3. Install Dependencies**

Install the required Python libraries from the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

**4. Configure Environment Variables**

Create a file named `.env` in the root of the project directory. This file will store your sensitive configuration.

```
# .env file

# RPC URL for the source blockchain (e.g., Ethereum Sepolia testnet)
# You can get one for free from services like Infura, Alchemy, or Chainstack.
RPC_URL="https://sepolia.infura.io/v3/YOUR_INFURA_PROJECT_ID"

# The address of the deployed bridge smart contract on the source chain.
# For this simulation, you can use any valid contract address on that network.
BRIDGE_CONTRACT_ADDRESS="0x1234567890123456789012345678901234567890"

# (Optional) A placeholder for a private key used for signing transactions on the destination chain.
# The script does not actually use this for signing, it's for demonstration.
DESTINATION_SIGNER_KEY="0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
```

**5. Run the Script**

Execute the Python script to start the listener.

```bash
python script.py
```

**Expected Output**

The script will start logging its activities to the console. You will see messages indicating a successful connection, initialization of the contract, and the start of the listening loop. Every few seconds, it will log a message indicating whether new events were found.

```
2023-10-27 10:30:00 - INFO - [script.main] - StateDB initialized with path: processed_events_db.json
2023-10-27 10:30:00 - INFO - [script._connect] - Attempting to connect to RPC: https://sepolia.infura.io/v3/xxx (Attempt 1/3)
2023-10-27 10:30:01 - INFO - [script._connect] - Successfully connected to chain ID: 11155111
2023-10-27 10:30:01 - INFO - [script._setup_contract] - Successfully initialized contract instance at 0x1234567890123456789012345678901234567890
2023-10-27 10:30:01 - INFO - [script.start_listening] - Starting event listener loop... polling for 'TokensLocked' events.
2023-10-27 10:30:11 - INFO - [script.start_listening] - No new events found. Waiting...
2023-10-27 10:30:21 - INFO - [script.start_listening] - No new events found. Waiting...
...
```

If a `TokensLocked` event is emitted by the target contract while the script is running, it will detect and process it, logging the details of the simulated destination transaction.