#!/usr/bin/env python3
"""Parse rekt.news leaderboard from text dump and save structured JSON."""

import json
import re
from pathlib import Path

OUTPUT_DIR = Path("/opt/tvmbench/data/rekt")

# Raw leaderboard text (concatenated format from web_fetch)
RAW = """1.$14,847,374,246 | 12/20/20202.$1,436,173,027 | 2/21/20253.$624,000,000 | 03/23/20224.$611,000,000 | 08/10/20215.$586,000,000 | 10/06/20226.$477,000,000 | 11/12/227.$326,000,000 | 02/02/20228.$304,000,000 | 05/30/20249.$235,000,000 | 07/18/202410.$223,000,000 | 5/22/202511.$216,000,000 | 05/20/202412.$200,000,000 | 09/23/202313.$197,000,000 | 03/13/202314.$196,000,000 | 12/04/202115.$190,000,000 | 08/01/202216.$181,000,000 | 04/17/202217.$162,300,000 | 09/20/202218.$147,000,000 | 09/29/202119.$140,000,000 | 12/13/202120.$130,000,000 | 10/27/202121.$128,000,000 | 11/3/202522.$126,300,000 | 07/06/202323.$126,000,000 | 11/10/202324.$120,000,000 | 02/01/202325.$120,000,000 | 12/02/202126.$115,000,000 | 10/11/202227.$100,000,000 | 06/02/202328.$100,000,000 | 06/23/202229.$99,100,000 | 11/22/202330.$92,000,000 | 10/08/202131.$85,000,000 | 03/05/202432.$81,500,000 | 12/31/202333.$80,000,000 | 05/01/202234.$80,000,000 | 01/28/202235.$77,700,000 | 12/12/202136.$73,540,297 | 01/23/202537.$69,300,000 | 07/30/202338.$62,500,000 | 03/26/202439.$60,000,000 | 07/22/202340.$59,000,000 | 04/19/202141.$57,200,000 | 04/28/202142.$55,470,000 | 08/20/202443.$55,000,000 | 11/05/202144.$54,300,000 | 09/12/202345.$53,000,000 | 10/16/202446.$51,700,000 | 8/14/202547.$49,500,000 | 2/24/202448.$48,000,000 | 11/22/202349.$48,000,000 | 03/23/202250.$45,000,000 | 05/19/202151.$45,000,000 | 09/29/202052.$44,700,000 | 09/19/202453.$44,700,000 | 04/19/202454.$44,300,000 | 7/18/202555.$42,000,000 | 7/9/202556.$41,600,000 | 09/04/202357.$41,500,000 | 9/8/202558.$41,000,000 | 9/22/202559.$37,500,000 | 02/13/202160.$37,000,000 | 12/14/202261.$34,000,000 | 09/21/202162.$33,700,000 | 01/18/202263.$33,000,000 | 04/20/202464.$32,000,000 | 03/04/202165.$31,400,000 | 11/30/202166.$30,500,000 | 05/02/202167.$30,000,000 | 12/18/202168.$28,000,000 | 11/01/202269.$27,600,000 | 06/05/202270.$27,300,000 | 1/31/202671.$27,000,000 | 7/15/202572.$27,000,000 | 09/03/202473.$27,000,000 | 06/23/202174.$27,000,000 | 03/05/202175.$26,200,000 | 1/8/202676.$26,000,000 | 11/18/202377.$25,220,000 | 09/10/202478.$25,000,000 | 10/26/202079.$24,000,000 | 9/24/202580.$24,000,000 | 12/02/202281.$24,000,000 | 05/12/202182.$23,000,000 | 07/31/202383.$22,200,000 | 04/12/202184.$21,800,000 | 05/13/202285.$21,200,000 | 10/02/202286.$21,000,000 | 03/08/202487.$20,000,000 | 05/15/202488.$20,000,000 | 08/03/202189.$19,700,000 | 11/22/202090.$19,400,000 | 06/10/202491.$18,800,000 | 08/30/202192.$18,100,000 | 11/25/202193.$18,000,000 | 05/17/202194.$16,180,000 | 6/6/202595.$16,000,000 | 03/23/202495.$16,000,000 | 10/14/202196.$15,800,000 | 10/27/202297.$15,600,000 | 04/02/202298.$15,000,000 | 09/28/202099.$14,000,000 | 7/24/2025100.$14,000,000 | 02/27/2021"""

# EVM→TVM mapping (from scrape_rekt.py)
EVM_TO_TVM_MAPPING = {
    "reentrancy": {
        "tvm_equivalent": "bounce-handling",
        "explanation": "EVM reentrancy → TVM bounce handler manipulation",
        "tvmbench_categories": ["TVB-001 – TVB-020"]
    },
    "flash_loan": {
        "tvm_equivalent": "message-chain-attacks",
        "explanation": "Flash loan atomic composability → TVM message chain ordering attacks",
        "tvmbench_categories": ["TVB-004 – TVB-025"]
    },
    "oracle_manipulation": {
        "tvm_equivalent": "cross-contract-interaction",
        "explanation": "Synchronous oracle reads → TVM stale state between message hops",
        "tvmbench_categories": ["TVB-056 – TVB-060"]
    },
    "access_control": {
        "tvm_equivalent": "authentication-access-control",
        "explanation": "Missing onlyOwner → TVM sender validation + workchain-aware address checks",
        "tvmbench_categories": ["TVB-036 – TVB-043"]
    },
    "bridge": {
        "tvm_equivalent": "cross-contract-interaction",
        "explanation": "Cross-chain message verification → TVM cross-shard/workchain routing",
        "tvmbench_categories": ["TVB-056 – TVB-060"]
    },
    "upgrade": {
        "tvm_equivalent": "upgrade-migration-safety",
        "explanation": "Proxy upgrade bugs → TVM set_code without state migration",
        "tvmbench_categories": ["TVB-013 – TVB-049"]
    },
    "integer_overflow": {
        "tvm_equivalent": "tvm-arithmetic",
        "explanation": "EVM uint256 overflow → TVM 257-bit integer edge cases",
        "tvmbench_categories": ["TVB-050 – TVB-055"]
    },
    "storage": {
        "tvm_equivalent": "gas-storage-economics",
        "explanation": "Storage collision/slot manipulation → TVM dict attacks, storage rent exhaustion",
        "tvmbench_categories": ["TVB-007 – TVB-030"]
    },
    "token_standard": {
        "tvm_equivalent": "standards-compliance",
        "explanation": "ERC-20/721 compliance gaps → TEP-74/62/89 compliance issues",
        "tvmbench_categories": ["TVB-010 – TVB-035"]
    }
}


def parse():
    entries = []
    # Match: N.$AMOUNT | DATE
    for m in re.finditer(r'(\d+)\.\$([0-9,]+)\s*\|\s*(\d{1,2}/\d{1,2}/\d{2,4})', RAW):
        rank = int(m.group(1))
        amount = int(m.group(2).replace(",", ""))
        date = m.group(3)
        entries.append({"rank": rank, "amount_usd": amount, "date": date})
    return entries


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    entries = parse()
    total = sum(e["amount_usd"] for e in entries)
    
    # Save
    (OUTPUT_DIR / "leaderboard.json").write_text(json.dumps(entries, indent=2))
    (OUTPUT_DIR / "evm_to_tvm_mapping.json").write_text(json.dumps(EVM_TO_TVM_MAPPING, indent=2))
    
    stats = {
        "total_entries": len(entries),
        "total_lost_usd": total,
        "total_lost_formatted": f"${total:,.0f}",
        "top_10_total_usd": sum(e["amount_usd"] for e in entries[:10]),
        "scraped_at": "2026-02-24T07:05:00Z",
        "source": "rekt.news/leaderboard",
        "note": "Leaderboard only (top 100). Full scrape with article details requires --full mode in scrape_rekt.py"
    }
    (OUTPUT_DIR / "stats.json").write_text(json.dumps(stats, indent=2))
    
    print(f"Parsed {len(entries)} entries, total lost: ${total:,.0f}")
    print(f"Top 10 alone: ${stats['top_10_total_usd']:,.0f}")
    print(f"Saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
