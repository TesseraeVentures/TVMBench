#!/usr/bin/env python3
"""Expand rekt intelligence to cover ALL Tesserae target chains and all→all migration matrix."""

import json
from pathlib import Path

OUTPUT_DIR = Path("/opt/tvmbench/data/rekt")

# Load existing data
existing_surfaces = json.loads((OUTPUT_DIR / "chain_risk_surfaces.json").read_text())
existing_exploits = json.loads((OUTPUT_DIR / "classified_exploits.json").read_text())
existing_patterns = json.loads((OUTPUT_DIR / "vulnerability_pattern_map.json").read_text())

# Add missing chain risk surfaces
NEW_CHAIN_SURFACES = {
    "sui": {
        "execution_model": "parallel execution, object-centric model, Move language, shared objects via consensus",
        "key_risks": [
            "Shared object contention and ordering attacks",
            "Object wrapping/unwrapping privilege escalation",
            "Dynamic field manipulation (unbounded growth, type confusion)",
            "Capability pattern misuse (missing cap checks, cap leaking)",
            "Clock/epoch manipulation in time-dependent logic",
            "Module upgrade compatibility (backward compat not enforced by runtime)",
            "Sponsored transaction abuse (gas sponsor draining)",
            "Transfer-to-object bugs (objects sent to non-store types)",
        ],
        "native_risks_not_in_evm": [
            "Object ownership model has no EVM equivalent",
            "Shared vs owned objects create unique concurrency risks",
            "Dynamic fields can create unbounded storage without gas limits",
            "Move's type system prevents some EVM bugs but introduces new categories",
        ],
        "migration_warnings_from_evm": [
            "EVM storage slots → Sui objects (fundamentally different data model)",
            "msg.sender → tx_context::sender() + capability pattern",
            "Reentrancy impossible (Move borrow checker) but shared object races exist",
            "No delegatecall — module upgrades use package upgrade policies",
            "Events are structured (not just logged bytes)",
        ],
        "migration_warnings_to_evm": [
            "Object ownership has no EVM mapping — flatten to storage slots",
            "Capability pattern → onlyOwner/role modifiers (weaker enforcement)",
            "Shared objects → global state (loses concurrency properties)",
        ]
    },
    "polkadot": {
        "execution_model": "substrate runtime, ink! smart contracts on Wasm, parachain model, XCM cross-chain",
        "key_risks": [
            "ink! reentrancy (call_flags::ALLOW_REENTRY must be explicit)",
            "Cross-contract call failure handling (ink! returns Result, not revert)",
            "XCM message manipulation (cross-parachain message forgery)",
            "Weight/gas estimation errors (Substrate weight system differs from EVM gas)",
            "Storage deposit exhaustion (callers pay for storage, not contract)",
            "Delegate call in ink! (call_builder with delegate flag)",
            "Lazy storage attacks (unbounded lazy maps, iteration gas bombs)",
            "Chain extension privilege escalation",
        ],
        "native_risks_not_in_evm": [
            "Storage deposit model (caller pays, not deployer)",
            "Weight system is fundamentally different from gas",
            "XCM cross-chain messages have unique trust assumptions",
            "ink! uses Rust's type system but runs on Wasm (different execution model)",
        ],
        "migration_warnings_from_evm": [
            "Solidity revert → ink! Result<T, Error> (must handle explicitly)",
            "EVM gas → Substrate weight (different cost model)",
            "msg.value → ink! transferred_value() (same concept, different API)",
            "EVM events → ink! #[ink(event)] (similar but structured)",
            "Proxy patterns → ink! delegate_call (exists but different)",
        ],
        "migration_warnings_to_evm": [
            "ink! Result error handling → Solidity require/revert",
            "Storage deposits → no EVM equivalent (deployer pays for storage on EVM)",
        ]
    },
    "near": {
        "execution_model": "sharded PoS, Wasm smart contracts (Rust/AssemblyScript), async cross-contract calls, storage staking",
        "key_risks": [
            "Cross-contract callback reentrancy (promise chains)",
            "Storage staking exhaustion (account must stake NEAR for storage)",
            "Serde deserialization panics (malformed input crashes contract)",
            "Access key manipulation (function-call keys with incorrect allowances)",
            "Promise chain ordering attacks (non-deterministic resolution)",
            "Upgrade without state migration (contract deploy overwrites code)",
            "Gas prepaid vs attached splits (insufficient gas for callbacks)",
        ],
        "native_risks_not_in_evm": [
            "Promise-based async execution (similar to TVM but different API)",
            "Storage staking model (NEAR tokens locked for bytes stored)",
            "Access key system (function-call keys, full-access keys)",
            "Account model with named accounts (not just addresses)",
        ],
        "migration_warnings_from_evm": [
            "Synchronous calls → NEAR promises (async, may fail independently)",
            "EVM storage → NEAR collections (LookupMap, UnorderedMap, Vector)",
            "msg.sender → predecessor_account_id (similar concept)",
            "No atomic composability — promise chains can partially fail",
            "Solidity constructor → NEAR init method (#[init])",
        ],
        "migration_warnings_to_evm": [
            "Promise chains → synchronous calls (loses async properties)",
            "Storage staking → no EVM equivalent",
            "Named accounts → address-only (loses readability)",
        ]
    },
    "starknet": {
        "execution_model": "ZK-rollup on Ethereum, Cairo language, Sierra intermediate, STARK proofs",
        "key_risks": [
            "Felt252 overflow (native type is field element, not integer)",
            "Storage slot collision in upgradeable contracts (similar to EVM)",
            "Sierra gas metering manipulation",
            "L1↔L2 message bridge attacks (Starknet↔Ethereum messaging)",
            "Contract class hash manipulation during upgrades",
            "Missing access control on external functions (no default private)",
            "Reentrancy via L1 handler callbacks",
            "Prover/verifier trust assumptions",
        ],
        "native_risks_not_in_evm": [
            "Felt252 arithmetic (not uint256 — different overflow behavior)",
            "STARK proof system trust model",
            "Sierra compilation (an extra compilation step that can introduce bugs)",
            "Contract classes vs instances (deploy_syscall creates instances from classes)",
        ],
        "migration_warnings_from_evm": [
            "uint256 → felt252/u256 (different arithmetic, need explicit handling)",
            "Solidity inheritance → Cairo components/traits",
            "EVM opcodes → Sierra/Cairo builtins",
            "Proxy pattern → replace_class_hash (native upgrade mechanism)",
            "Events → Cairo events (similar but with felt252 serialization)",
        ],
        "migration_warnings_to_evm": [
            "felt252 → uint256 (expanding type, generally safe but verify ranges)",
            "Cairo components → Solidity inheritance (loses composability model)",
        ]
    },
    "aptos": {
        "execution_model": "parallel execution, Move language (Aptos variant), resource-oriented, Block-STM concurrency",
        "key_risks": [
            "Resource duplication (copy/drop abilities misuse)",
            "Module upgrade attacks (compatibility checking has edge cases)",
            "Signer capability forgery (signer_capability extraction)",
            "Coin module vs fungible asset confusion (two token standards coexist)",
            "Object model confusion (Aptos objects ≠ Sui objects)",
            "Aggregator manipulation (concurrent data structure attacks)",
            "Block-STM speculative execution side effects",
        ],
        "native_risks_not_in_evm": [
            "Move resource model (no EVM equivalent — resources cannot be copied/dropped without abilities)",
            "Dual token standards (legacy Coin module + new Fungible Asset)",
            "Block-STM parallel execution (speculative execution model)",
            "Global storage (modules own their storage, not a flat key-value store)",
        ],
        "migration_warnings_from_evm": [
            "EVM storage → Move global storage + resources (fundamentally different)",
            "msg.sender → signer (Move has first-class signer type)",
            "ERC-20 → Coin module OR Fungible Asset (must choose which standard)",
            "Reentrancy guards unnecessary (Move borrow checker prevents it)",
            "Proxy patterns → module upgrades (compatibility-checked by VM)",
        ],
        "migration_warnings_to_evm": [
            "Move resources → EVM storage (loses resource safety guarantees)",
            "Signer type → msg.sender (loses type-level authentication)",
        ]
    },
    "bitcoin": {
        "execution_model": "UTXO model, Bitcoin Script (limited), no smart contracts (Ordinals/BRC-20 via inscriptions)",
        "key_risks": [
            "Script complexity limits (very constrained computation)",
            "UTXO double-spend (transaction malleability)",
            "Ordinal/inscription-based token manipulation",
            "Timelock bypass attacks",
            "Multi-sig key management",
        ],
        "native_risks_not_in_evm": [
            "UTXO model (fundamentally different from account model)",
            "No smart contract state (all state is in UTXOs)",
            "Limited scripting capability",
        ],
        "migration_warnings_from_evm": [
            "Smart contracts CANNOT be meaningfully migrated to Bitcoin Script",
            "Only simple custody/multisig/timelock patterns can be represented",
            "BRC-20/Ordinals are inscription-based, not contract-based",
        ],
        "migration_warnings_to_evm": [
            "UTXO patterns → account model (fundamental paradigm shift)",
            "Bitcoin Script → Solidity (massive capability expansion)",
        ]
    }
}

# Merge with existing
all_surfaces = {**existing_surfaces, **NEW_CHAIN_SURFACES}
(OUTPUT_DIR / "chain_risk_surfaces.json").write_text(json.dumps(all_surfaces, indent=2))
print(f"Chain risk surfaces: {len(existing_surfaces)} → {len(all_surfaces)} chains")

# Build full all→all migration matrix
ALL_CHAINS = list(all_surfaces.keys())
# Map generator names to chain names
GEN_TO_CHAIN = {
    "solidity": "ethereum", "vyper": "ethereum", "tact": "ton",
    "move": "sui", "anchor": "solana", "ink": "polkadot",
    "cosmwasm": "cosmos", "near": "near", "cairo": "starknet", "aptos": "aptos"
}
TARGET_CHAINS = ["ton", "sui", "solana", "polkadot", "cosmos", "near", "starknet", "aptos", "ethereum"]
SOURCE_CHAINS = ["ethereum", "solana", "bsc", "polygon", "avalanche", "cosmos", "sui", "polkadot", "near", "starknet", "aptos", "ton"]

matrix = {}
for source in SOURCE_CHAINS:
    for target in TARGET_CHAINS:
        if source == target:
            continue
        # Skip EVM→EVM (trivial, not our market)
        evm_chains = {"ethereum", "bsc", "polygon", "avalanche"}
        if source in evm_chains and target in evm_chains:
            continue

        key = f"{source}→{target}"
        source_surface = all_surfaces.get(source, {})
        target_surface = all_surfaces.get(target, {})

        # Find relevant exploits
        relevant_exploits = [
            e for e in existing_exploits
            if source in e.get("chains", [])
        ]

        # Find relevant patterns
        relevant_patterns = []
        for pattern_name, pattern in existing_patterns.items():
            matched_exploits = [
                e for e in relevant_exploits
                if pattern_name in e.get("vectors", [])
            ]
            if matched_exploits:
                relevant_patterns.append({
                    "pattern": pattern_name,
                    "severity_change": pattern.get("severity_change", "UNKNOWN"),
                    "example_losses": sum(e["amount"] for e in matched_exploits),
                    "exploit_count": len(matched_exploits),
                })

        # Determine risk level
        if any("CRITICAL" in p.get("severity_change", "") for p in relevant_patterns):
            risk = "CRITICAL"
        elif relevant_patterns:
            risk = "HIGH"
        elif source_surface or target_surface:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        warnings = source_surface.get("migration_warnings_from_evm", []) if target != "ethereum" else source_surface.get("migration_warnings_to_evm", [])
        if not warnings:
            warnings = source_surface.get("tvm_migration_warnings", [])

        matrix[key] = {
            "source_execution_model": source_surface.get("execution_model", "unknown"),
            "target_execution_model": target_surface.get("execution_model", "unknown"),
            "relevant_vulnerability_patterns": relevant_patterns,
            "total_historical_losses_on_source": sum(e["amount"] for e in relevant_exploits),
            "migration_warnings": warnings[:5],  # Cap at 5 for readability
            "risk_level": risk,
        }

(OUTPUT_DIR / "migration_risk_matrix.json").write_text(json.dumps(matrix, indent=2))
print(f"Migration risk matrix: {len(matrix)} routes (was 6)")

# Update stats
total_losses = sum(e["amount"] for e in existing_exploits)
stats = {
    "generated_at": "2026-02-24T07:30:00Z",
    "total_classified_exploits": len(existing_exploits),
    "total_losses_usd": total_losses,
    "total_losses_formatted": f"${total_losses:,.0f}",
    "chain_risk_profiles": len(all_surfaces),
    "migration_routes_covered": len(matrix),
    "vulnerability_patterns": len(existing_patterns),
    "source_chains": sorted(set(k.split("→")[0] for k in matrix)),
    "target_chains": sorted(set(k.split("→")[1] for k in matrix)),
}
(OUTPUT_DIR / "intelligence_stats.json").write_text(json.dumps(stats, indent=2))
print(f"Stats updated: {stats['chain_risk_profiles']} chains, {stats['migration_routes_covered']} routes")


if __name__ == "__main__":
    main() if False else None  # just run module-level code
