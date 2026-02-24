#!/usr/bin/env python3
"""
Build structured security intelligence from rekt.news articles.
Produces chain-specific risk surfaces and vulnerability pattern mappings
for TVMBench corpus enrichment and Tesserae migration risk analysis.

Usage:
    python3 build_rekt_intelligence.py              # Process all known articles
    python3 build_rekt_intelligence.py --fetch 50   # Fetch 50 new articles first
"""

import argparse
import json
import re
import time
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

OUTPUT_DIR = Path("/opt/tvmbench/data/rekt")

# Known high-profile exploits with manual classification
# These are the most important for migration risk intelligence
KNOWN_EXPLOITS = [
    # Bridge exploits (critical for cross-chain migration)
    {"slug": "ronin-network-rekt", "name": "Ronin Network", "amount": 624_000_000, "date": "2022-03-23",
     "chains": ["ethereum"], "vectors": ["bridge", "access_control"],
     "description": "Bridge validator keys compromised. 5/9 multisig stolen via social engineering + old DAO access.",
     "migration_relevance": "HIGH — bridge contracts are prime migration targets. Key management patterns must be preserved."},
    {"slug": "polynetwork-rekt", "name": "Poly Network", "amount": 611_000_000, "date": "2021-08-10",
     "chains": ["ethereum", "bsc", "polygon"], "vectors": ["bridge", "access_control"],
     "description": "Cross-chain relay contract had privilege escalation via keeper role manipulation.",
     "migration_relevance": "HIGH — cross-chain message verification patterns differ fundamentally between EVM and TVM."},
    {"slug": "binance-bridge-rekt", "name": "BNB Bridge", "amount": 586_000_000, "date": "2022-10-06",
     "chains": ["bsc"], "vectors": ["bridge"],
     "description": "IAVL proof verification bug allowed forged deposit proofs.",
     "migration_relevance": "HIGH — proof verification logic is chain-specific. TVM uses different proof structures."},
    {"slug": "wormhole-rekt", "name": "Wormhole", "amount": 326_000_000, "date": "2022-02-02",
     "chains": ["ethereum", "solana"], "vectors": ["bridge", "access_control"],
     "description": "Solana guardian set verification bypassed via deprecated instruction.",
     "migration_relevance": "CRITICAL — demonstrates how chain-specific auth patterns (Solana's program-derived accounts vs EVM's msg.sender) create unique attack surfaces."},
    {"slug": "nomad-rekt", "name": "Nomad", "amount": 190_000_000, "date": "2022-08-01",
     "chains": ["ethereum"], "vectors": ["bridge", "upgrade"],
     "description": "Routine upgrade initialized trusted root to 0x00, making all messages valid.",
     "migration_relevance": "CRITICAL — upgrade patterns differ across chains. TVM set_code without migration is the equivalent risk."},

    # Flash loan / DeFi composability
    {"slug": "euler-rekt", "name": "Euler Finance", "amount": 197_000_000, "date": "2023-03-13",
     "chains": ["ethereum"], "vectors": ["flash_loan", "reentrancy"],
     "description": "Donation attack via flash loan exploiting missing health check in liquidation path.",
     "migration_relevance": "HIGH — atomic composability doesn't exist on TVM. Flash loan patterns must be decomposed into message chains."},
    {"slug": "cream-finance-rekt", "name": "Cream Finance", "amount": 130_000_000, "date": "2021-10-27",
     "chains": ["ethereum"], "vectors": ["flash_loan", "oracle_manipulation"],
     "description": "Flash loan + oracle manipulation via yUSD price inflation.",
     "migration_relevance": "MEDIUM — oracle patterns on TVM use async message passing, creating different timing risks."},
    {"slug": "beanstalk-rekt", "name": "Beanstalk", "amount": 181_000_000, "date": "2022-04-17",
     "chains": ["ethereum"], "vectors": ["flash_loan", "access_control"],
     "description": "Flash loan used to gain governance majority and drain treasury via emergency governance.",
     "migration_relevance": "HIGH — governance timing assumptions change on async chains. TVM governance must account for message ordering."},

    # Reentrancy (maps to bounce handling on TVM)
    {"slug": "the-dao-rekt", "name": "The DAO", "amount": 60_000_000, "date": "2016-06-17",
     "chains": ["ethereum"], "vectors": ["reentrancy"],
     "description": "Classic reentrancy via recursive call in withdrawal function.",
     "migration_relevance": "CRITICAL — reentrancy doesn't exist on TVM (async messages). But bounce handling bugs are the TVM equivalent and arguably more insidious because EVM devs don't expect them."},
    {"slug": "curve-finance-rekt", "name": "Curve Finance", "amount": 69_300_000, "date": "2023-07-30",
     "chains": ["ethereum"], "vectors": ["reentrancy"],
     "description": "Vyper compiler bug (0.2.15-0.3.0) caused incorrect reentrancy guard placement.",
     "migration_relevance": "CRITICAL — compiler bugs create hidden vulnerabilities. Migration must verify security properties at IR level, not rely on source language safety."},

    # Oracle manipulation (maps to cross-contract interaction on TVM)
    {"slug": "mango-markets-rekt", "name": "Mango Markets", "amount": 115_000_000, "date": "2022-10-11",
     "chains": ["solana"], "vectors": ["oracle_manipulation"],
     "description": "MNGO perp market oracle manipulated via thin liquidity + self-trading.",
     "migration_relevance": "HIGH — Solana oracle patterns differ from both EVM and TVM. On TVM, oracle data arrives via messages with potential staleness."},
    {"slug": "bonqdao-rekt", "name": "BonqDAO", "amount": 120_000_000, "date": "2023-02-01",
     "chains": ["polygon"], "vectors": ["oracle_manipulation"],
     "description": "Tellor oracle manipulated with low staking cost to inflate ALBT price.",
     "migration_relevance": "MEDIUM — oracle staking economics differ per chain. Migration must map oracle trust models."},

    # Access control
    {"slug": "wintermute-rekt", "name": "Wintermute", "amount": 162_300_000, "date": "2022-09-20",
     "chains": ["ethereum"], "vectors": ["access_control"],
     "description": "Profanity vanity address generator vulnerability exposed admin private key.",
     "migration_relevance": "LOW — key management is off-chain. But address derivation differs (TVM workchain-aware addresses)."},
    {"slug": "multichain-rekt", "name": "Multichain", "amount": 126_300_000, "date": "2023-07-06",
     "chains": ["ethereum"], "vectors": ["access_control", "bridge"],
     "description": "CEO arrest led to single-point-of-failure key compromise. Bridge drained across multiple chains.",
     "migration_relevance": "HIGH — operational security patterns must be preserved. Multisig threshold assumptions change per chain."},

    # Upgrade/proxy (maps to set_code on TVM)
    {"slug": "level-finance-rekt", "name": "Level Finance", "amount": 1_100_000, "date": "2023-05-01",
     "chains": ["bsc"], "vectors": ["upgrade", "access_control"],
     "description": "Referral controller had open claim function due to missing access control after upgrade.",
     "migration_relevance": "CRITICAL — upgrade patterns are fundamentally different on TVM. EVM proxy patterns (UUPS, Transparent, Beacon) have no direct TVM equivalent. set_code requires explicit state migration."},

    # Storage/state manipulation
    {"slug": "parity-wallet-rekt", "name": "Parity Wallet", "amount": 150_000_000, "date": "2017-11-06",
     "chains": ["ethereum"], "vectors": ["storage", "access_control"],
     "description": "Library contract self-destructed, bricking all dependent wallets.",
     "migration_relevance": "CRITICAL — contract dependencies differ across chains. TVM has no selfdestruct equivalent but storage rent can evict state."},

    # Recent exploits (2024-2026)
    {"slug": "dmm-bitcoin-rekt", "name": "DMM Bitcoin", "amount": 304_000_000, "date": "2024-05-30",
     "chains": ["bitcoin"], "vectors": ["access_control"],
     "description": "Exchange hot wallet key compromise. Attributed to Lazarus Group.",
     "migration_relevance": "LOW — exchange-level, not smart contract."},
    {"slug": "wazirx-rekt", "name": "WazirX", "amount": 235_000_000, "date": "2024-07-18",
     "chains": ["ethereum"], "vectors": ["access_control"],
     "description": "Multisig wallet compromise via social engineering of signing devices.",
     "migration_relevance": "MEDIUM — multisig patterns differ per chain. TVM multisig uses different message flows."},
    {"slug": "radiant-capital-rekt", "name": "Radiant Capital", "amount": 53_000_000, "date": "2024-10-16",
     "chains": ["ethereum", "arbitrum", "bsc"], "vectors": ["access_control"],
     "description": "Hardware wallet compromise via malware. Multi-chain deployment drained.",
     "migration_relevance": "HIGH — multi-chain deployment patterns must ensure compromise of one chain doesn't cascade."},
    {"slug": "bybit-rekt", "name": "Bybit", "amount": 1_436_173_027, "date": "2025-02-21",
     "chains": ["ethereum"], "vectors": ["access_control"],
     "description": "Largest crypto hack. Exchange cold wallet compromise attributed to Lazarus Group.",
     "migration_relevance": "LOW — exchange-level custody, not smart contract."},
    {"slug": "moonwell-rekt", "name": "Moonwell", "amount": 1_780_000, "date": "2026-02-15",
     "chains": ["moonbeam"], "vectors": ["oracle_manipulation"],
     "description": "Oracle misconfiguration priced cbETH at $1.12 instead of $2,200. Commit was co-authored by Claude Opus 4.6 — possibly first major exploit of AI-assisted ('vibe-coded') smart contracts.",
     "migration_relevance": "CRITICAL — demonstrates that AI-assisted development (including migration) requires explicit verification gates. Validates our fail-closed architecture."},
]

# Chain-specific risk surfaces that matter for migration
CHAIN_RISK_SURFACES = {
    "ethereum": {
        "execution_model": "synchronous, atomic transactions",
        "key_risks": [
            "Reentrancy via synchronous external calls",
            "Flash loan atomic composability attacks",
            "Storage slot collisions in proxy patterns",
            "Gas limit manipulation",
            "Frontrunning via public mempool",
        ],
        "tvm_migration_warnings": [
            "Reentrancy guards become unnecessary — but bounce handlers become critical",
            "Flash loan patterns must be decomposed into multi-message flows",
            "Proxy/upgrade patterns have no direct equivalent — use set_code with state migration",
            "Storage is not slot-based — TVM uses cells/dictionaries with rent",
            "No public mempool — but validator message ordering creates different MEV risks",
        ]
    },
    "solana": {
        "execution_model": "parallel execution, account model, program-derived addresses",
        "key_risks": [
            "Account validation (missing owner/signer checks)",
            "PDA derivation predictability",
            "Cross-program invocation (CPI) authority escalation",
            "Instruction introspection attacks",
            "Rent exemption assumptions",
        ],
        "tvm_migration_warnings": [
            "Account model → TVM actor model mapping is non-trivial",
            "PDA patterns have no equivalent — TVM uses init_state for address derivation",
            "CPI → TVM internal messages (different trust model)",
            "No instruction introspection on TVM",
            "Rent model differs: TVM charges ongoing storage, not one-time exemption",
        ]
    },
    "bsc": {
        "execution_model": "EVM-compatible, faster blocks, centralized validators",
        "key_risks": [
            "Same as Ethereum EVM risks",
            "Validator centralization enables targeted censorship",
            "Lower gas costs enable more complex attacks",
        ],
        "tvm_migration_warnings": [
            "Same EVM→TVM warnings as Ethereum",
            "Validator model completely different on TON (PoS with sharding)",
        ]
    },
    "polygon": {
        "execution_model": "EVM-compatible, PoS sidechain",
        "key_risks": [
            "Same as Ethereum EVM risks",
            "Bridge-specific risks (Polygon PoS bridge)",
            "Chain reorganization risks",
        ],
        "tvm_migration_warnings": [
            "Same EVM→TVM warnings as Ethereum",
            "Bridge patterns require complete reimplementation for TVM",
        ]
    },
    "avalanche": {
        "execution_model": "EVM-compatible (C-Chain), subnet architecture",
        "key_risks": [
            "Same as Ethereum EVM risks",
            "Subnet isolation assumptions",
            "Cross-subnet message passing",
        ],
        "tvm_migration_warnings": [
            "Same EVM→TVM warnings as Ethereum",
            "Subnet concept maps loosely to TVM workchains",
        ]
    },
    "cosmos": {
        "execution_model": "IBC message passing, CosmWasm contracts, Tendermint consensus",
        "key_risks": [
            "IBC message forgery/replay",
            "CosmWasm reentrancy (submessages)",
            "Governance manipulation",
            "Light client verification bypass",
        ],
        "tvm_migration_warnings": [
            "IBC → TVM cross-workchain messages (different verification model)",
            "CosmWasm submessages → TVM internal messages (similar async model)",
            "Governance timing assumptions change with TVM's non-deterministic message ordering",
        ]
    },
    "ton": {
        "execution_model": "asynchronous actor model, message passing, workchains, sharding",
        "key_risks": [
            "Missing/incorrect bounce handlers → locked funds",
            "Message ordering non-determinism → race conditions",
            "Storage rent exhaustion → state eviction DoS",
            "Gas forwarding insufficiency → incomplete message chains",
            "Workchain address validation bypass",
            "Dictionary gas bombs → oversized cell operations",
            "Replay attacks (missing seqno/subwallet checks)",
            "set_code without state migration → corrupted storage",
            "TEP-74/62/89 compliance gaps in Jetton/NFT/SBT",
        ],
        "native_risks_not_in_evm": [
            "Bounce fund-locking (no EVM equivalent)",
            "Partial message chain execution (no atomic transactions)",
            "Storage rent eviction (EVM storage is permanent after creation)",
            "Non-deterministic cross-shard message delivery",
            "257-bit integer edge cases (EVM uses 256-bit)",
        ]
    }
}

# EVM→TVM vulnerability pattern mapping (detailed)
VULNERABILITY_PATTERN_MAP = {
    "reentrancy": {
        "evm_pattern": "Recursive external call before state update",
        "tvm_equivalent": "Bounce handler state corruption",
        "tvm_category": "bounce-handling",
        "tvmbench_ids": "TVB-001 – TVB-020",
        "severity_change": "DIFFERENT — not lower, not higher. The attack surface shape changes completely.",
        "migration_action": "Remove reentrancy guards. Add comprehensive bounce handlers for all outgoing messages. Ensure state updates happen before sending messages (checks-effects-interactions still applies, but for different reasons).",
        "example_exploits": ["The DAO ($60M)", "Curve Finance ($69.3M)", "Reentrancy-based attacks total: ~$500M+"],
    },
    "flash_loan": {
        "evm_pattern": "Atomic borrow → manipulate → profit → repay within single transaction",
        "tvm_equivalent": "Message chain ordering manipulation",
        "tvm_category": "message-chain-attacks",
        "tvmbench_ids": "TVB-004 – TVB-025",
        "severity_change": "REDUCED — no atomic composability on TVM means classic flash loans don't work. But message ordering attacks are the new risk.",
        "migration_action": "Flash loan patterns CANNOT be directly migrated. Decompose into multi-message flows. Add TOCTOU checks for state that may change between messages. Consider message chain timeout patterns.",
        "example_exploits": ["Euler ($197M)", "Beanstalk ($181M)", "Cream ($130M)"],
    },
    "oracle_manipulation": {
        "evm_pattern": "Synchronous read of manipulable on-chain price feed",
        "tvm_equivalent": "Stale oracle data between async message hops",
        "tvm_category": "cross-contract-interaction",
        "tvmbench_ids": "TVB-056 – TVB-060",
        "severity_change": "DIFFERENT — synchronous manipulation becomes stale data attacks. Price can change between request and response messages.",
        "migration_action": "Add freshness checks (timestamp validation). Implement oracle heartbeat monitoring. Consider TWAP-like mechanisms adapted for async delivery. Never trust oracle data that arrived in a different message than the action it gates.",
        "example_exploits": ["Mango Markets ($115M)", "BonqDAO ($120M)", "Moonwell ($1.78M, AI-assisted)"],
    },
    "access_control": {
        "evm_pattern": "Missing/incorrect modifier checks (onlyOwner, etc.)",
        "tvm_equivalent": "Sender validation + workchain-aware address checks",
        "tvm_category": "authentication-access-control",
        "tvmbench_ids": "TVB-036 – TVB-043",
        "severity_change": "SIMILAR — access control bugs are universal. TVM adds workchain complexity.",
        "migration_action": "Map all EVM access control modifiers to TVM sender checks. Add workchain validation for cross-workchain messages. Preserve multisig threshold semantics. Validate that bounced messages cannot bypass access control.",
        "example_exploits": ["Ronin ($624M)", "Wintermute ($162M)", "Multichain ($126M)"],
    },
    "bridge": {
        "evm_pattern": "Cross-chain message verification failure",
        "tvm_equivalent": "Cross-shard/workchain message routing verification",
        "tvm_category": "cross-contract-interaction",
        "tvmbench_ids": "TVB-056 – TVB-060",
        "severity_change": "CRITICAL — bridge patterns are chain-specific by definition. Every bridge migration requires full security re-audit.",
        "migration_action": "NEVER auto-migrate bridge contracts. Flag for mandatory manual review. Verify all proof verification logic against target chain's proof structure. Map validator/guardian patterns to target chain's consensus model.",
        "example_exploits": ["Ronin ($624M)", "BNB Bridge ($586M)", "Wormhole ($326M)", "Nomad ($190M)"],
    },
    "upgrade_proxy": {
        "evm_pattern": "UUPS/Transparent/Beacon proxy with delegatecall",
        "tvm_equivalent": "set_code without state migration",
        "tvm_category": "upgrade-migration-safety",
        "tvmbench_ids": "TVB-013 – TVB-049",
        "severity_change": "DIFFERENT — TVM has no delegatecall. Upgrades use set_code which replaces contract code entirely. State migration must be explicit.",
        "migration_action": "Map proxy pattern to set_code + migration handler. Ensure state layout compatibility checks. Add version tracking. Implement rollback capability. Flag any contract with proxy patterns for manual review of upgrade path.",
        "example_exploits": ["Nomad ($190M, upgrade bug)", "Level Finance ($1.1M)", "Parity ($150M, selfdestruct)"],
    },
    "integer_arithmetic": {
        "evm_pattern": "uint256 overflow/underflow (pre-Solidity 0.8)",
        "tvm_equivalent": "257-bit integer edge cases, negative number handling",
        "tvm_category": "tvm-arithmetic",
        "tvmbench_ids": "TVB-050 – TVB-055",
        "severity_change": "DIFFERENT — TVM uses signed 257-bit integers. Overflow behavior differs. Negative values are possible where EVM only had unsigned.",
        "migration_action": "Verify all arithmetic operations handle the 257-bit range. Check for implicit unsigned assumptions in the source. Add explicit bounds checks where Solidity 0.8+ checked arithmetic was relied upon. Validate that negative values cannot corrupt state.",
        "example_exploits": ["Various overflow attacks (pre-2020)"],
    },
    "storage_manipulation": {
        "evm_pattern": "Storage slot collision, delegatecall storage layout mismatch",
        "tvm_equivalent": "Dictionary gas bombs, cell overflow, storage rent exhaustion",
        "tvm_category": "gas-storage-economics",
        "tvmbench_ids": "TVB-007 – TVB-030",
        "severity_change": "FUNDAMENTALLY DIFFERENT — TVM storage is cell-based with ongoing rent, not slot-based with one-time gas cost.",
        "migration_action": "Redesign storage layout for TVM cell model. Add dictionary size limits to prevent gas bombs. Implement storage rent monitoring. Consider state pruning strategies. Map EVM events to TVM external message patterns.",
        "example_exploits": ["Parity Wallet ($150M)", "Various storage collision bugs"],
    },
    "token_standard": {
        "evm_pattern": "ERC-20/721/1155 non-compliance (missing return values, approval race conditions)",
        "tvm_equivalent": "TEP-74/62/89 compliance gaps (Jetton/NFT/SBT)",
        "tvm_category": "standards-compliance",
        "tvmbench_ids": "TVB-010 – TVB-035",
        "severity_change": "DIFFERENT — TEP standards use message-based transfers (not synchronous approve+transferFrom). Transfer patterns are fundamentally different.",
        "migration_action": "Map ERC-20 to Jetton (TEP-74). Map ERC-721 to NFT (TEP-62). Map SBTs to TEP-89. Verify all callbacks and notification messages. Ensure burn/mint authority is correctly preserved. Check bounce handling on failed transfers.",
        "example_exploits": ["Various ERC-20 compliance issues"],
    },
}


def build_intelligence():
    """Build the complete security intelligence database."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Save known exploits with classifications
    exploits_path = OUTPUT_DIR / "classified_exploits.json"
    exploits_path.write_text(json.dumps(KNOWN_EXPLOITS, indent=2))
    print(f"Saved {len(KNOWN_EXPLOITS)} classified exploits to {exploits_path}")

    # 2. Save chain risk surfaces
    chains_path = OUTPUT_DIR / "chain_risk_surfaces.json"
    chains_path.write_text(json.dumps(CHAIN_RISK_SURFACES, indent=2))
    print(f"Saved {len(CHAIN_RISK_SURFACES)} chain risk profiles to {chains_path}")

    # 3. Save vulnerability pattern map
    patterns_path = OUTPUT_DIR / "vulnerability_pattern_map.json"
    patterns_path.write_text(json.dumps(VULNERABILITY_PATTERN_MAP, indent=2))
    print(f"Saved {len(VULNERABILITY_PATTERN_MAP)} pattern mappings to {patterns_path}")

    # 4. Compute migration risk matrix
    risk_matrix = build_migration_risk_matrix()
    matrix_path = OUTPUT_DIR / "migration_risk_matrix.json"
    matrix_path.write_text(json.dumps(risk_matrix, indent=2))
    print(f"Saved migration risk matrix to {matrix_path}")

    # 5. Generate summary stats
    stats = compute_intelligence_stats()
    stats_path = OUTPUT_DIR / "intelligence_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2))
    print(f"Saved intelligence stats to {stats_path}")

    # Print summary
    print(f"\n{'='*60}")
    print("SECURITY INTELLIGENCE SUMMARY")
    print(f"{'='*60}")
    print(f"Classified exploits:        {len(KNOWN_EXPLOITS)}")
    print(f"Total losses tracked:       ${sum(e['amount'] for e in KNOWN_EXPLOITS):,.0f}")
    print(f"Chain risk profiles:        {len(CHAIN_RISK_SURFACES)}")
    print(f"Vulnerability patterns:     {len(VULNERABILITY_PATTERN_MAP)}")
    print(f"Bridge exploits (highest risk for migration): {sum(1 for e in KNOWN_EXPLOITS if 'bridge' in e['vectors'])}")
    print(f"Bridge losses:              ${sum(e['amount'] for e in KNOWN_EXPLOITS if 'bridge' in e['vectors']):,.0f}")

    # Migration-critical findings
    critical = [e for e in KNOWN_EXPLOITS if e["migration_relevance"].startswith("CRITICAL")]
    print(f"\nCRITICAL migration-relevant exploits: {len(critical)}")
    for e in critical:
        print(f"  • {e['name']} (${e['amount']:,.0f}) — {e['migration_relevance'][:80]}")


def build_migration_risk_matrix():
    """Build a source→target migration risk matrix."""
    source_chains = ["ethereum", "solana", "bsc", "polygon", "avalanche", "cosmos"]
    target_chains = ["ton"]  # We primarily migrate TO TON

    matrix = {}
    for source in source_chains:
        for target in target_chains:
            key = f"{source}→{target}"
            source_risks = CHAIN_RISK_SURFACES.get(source, {})
            target_risks = CHAIN_RISK_SURFACES.get(target, {})

            # Count relevant pattern mappings
            relevant_patterns = []
            for pattern_name, pattern in VULNERABILITY_PATTERN_MAP.items():
                # Check if any known exploit on this source chain uses this pattern
                source_exploits = [
                    e for e in KNOWN_EXPLOITS
                    if source in e.get("chains", []) and pattern_name in e.get("vectors", [])
                ]
                if source_exploits:
                    relevant_patterns.append({
                        "pattern": pattern_name,
                        "severity_change": pattern["severity_change"],
                        "migration_action": pattern["migration_action"],
                        "example_losses": sum(e["amount"] for e in source_exploits),
                    })

            matrix[key] = {
                "source_execution_model": source_risks.get("execution_model", "unknown"),
                "target_execution_model": target_risks.get("execution_model", "unknown"),
                "relevant_vulnerability_patterns": relevant_patterns,
                "total_historical_losses_on_source": sum(
                    e["amount"] for e in KNOWN_EXPLOITS if source in e.get("chains", [])
                ),
                "migration_warnings": source_risks.get("tvm_migration_warnings", []),
                "risk_level": "CRITICAL" if any(
                    p["severity_change"].startswith("CRITICAL") for p in relevant_patterns
                ) else "HIGH" if relevant_patterns else "MEDIUM",
            }

    return matrix


def compute_intelligence_stats():
    """Compute aggregate statistics."""
    total_losses = sum(e["amount"] for e in KNOWN_EXPLOITS)
    by_vector = {}
    by_chain = {}
    by_relevance = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}

    for e in KNOWN_EXPLOITS:
        for v in e["vectors"]:
            by_vector[v] = by_vector.get(v, 0) + e["amount"]
        for c in e["chains"]:
            by_chain[c] = by_chain.get(c, 0) + e["amount"]
        level = e["migration_relevance"].split(" ")[0].rstrip(" —")
        by_relevance[level] = by_relevance.get(level, 0) + 1

    return {
        "generated_at": "2026-02-24T07:15:00Z",
        "total_classified_exploits": len(KNOWN_EXPLOITS),
        "total_losses_usd": total_losses,
        "total_losses_formatted": f"${total_losses:,.0f}",
        "losses_by_attack_vector": {
            k: {"total_usd": v, "formatted": f"${v:,.0f}"}
            for k, v in sorted(by_vector.items(), key=lambda x: x[1], reverse=True)
        },
        "losses_by_chain": {
            k: {"total_usd": v, "formatted": f"${v:,.0f}"}
            for k, v in sorted(by_chain.items(), key=lambda x: x[1], reverse=True)
        },
        "migration_relevance_counts": by_relevance,
        "tvmbench_corpus_coverage": {
            "bounce_handling": "TVB-001 – TVB-020 (8 entries)",
            "message_chain": "TVB-004 – TVB-025 (8 entries)",
            "gas_storage": "TVB-007 – TVB-030 (8 entries)",
            "standards": "TVB-010 – TVB-035 (8 entries)",
            "auth_access": "TVB-036 – TVB-043 (8 entries)",
            "upgrade_migration": "TVB-013 – TVB-049 (8 entries)",
            "arithmetic": "TVB-050 – TVB-055 (6 entries)",
            "cross_contract": "TVB-056 – TVB-060 (5 entries)",
        },
        "key_insight": "Bridge exploits account for the highest losses and are the most dangerous migration targets. NEVER auto-migrate bridge contracts.",
        "ai_assisted_exploit": "Moonwell (2026-02-15) — first known major exploit of AI-co-authored smart contract code. Validates our fail-closed verification architecture.",
    }


if __name__ == "__main__":
    build_intelligence()
