/**
 * TVMBench Baseline Agent
 *
 * Simple pattern-matching agent for detect mode. No LLM — uses regex and
 * AST-like heuristics to find common TVM vulnerability patterns.
 * Serves as a floor benchmark: any serious agent should beat this.
 */

import type { Agent, AgentTask, AgentResponse, DetectResponse, VulnerabilityFinding } from './interface';

// ---------------------------------------------------------------------------
// Pattern Rules
// ---------------------------------------------------------------------------

interface PatternRule {
  id: string;
  category: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  pattern: RegExp;
  antiPattern?: RegExp; // If present, vuln only fires when antiPattern is NOT found
  description: string;
  recommendation: string;
}

const RULES: PatternRule[] = [
  {
    id: 'BOUNCE_MISSING',
    category: 'bounce-handling',
    severity: 'high',
    pattern: /send\s*\(/,
    antiPattern: /bounced\s*\(|receive\s*\(\s*bounced\b|recv_internal.*bounced/s,
    description: 'Contract sends messages but has no bounce handler. Funds sent to a contract that rejects will be lost.',
    recommendation: 'Add a bounced() receiver to handle failed message deliveries.',
  },
  {
    id: 'NO_ADMIN_CHECK_SETCODE',
    category: 'upgrade-safety',
    severity: 'critical',
    pattern: /set_code\s*\(|setCode\s*\(/,
    antiPattern: /require\s*\(.*(?:sender|ctx\.sender|admin|owner)/s,
    description: 'set_code called without visible admin/owner authorization check.',
    recommendation: 'Gate code upgrades behind admin address verification.',
  },
  {
    id: 'NO_SEQNO',
    category: 'replay-protection',
    severity: 'critical',
    pattern: /recv_external|onExternalMessage/,
    antiPattern: /seqno|seq_no|sequence/,
    description: 'External message handler without sequence number check. Replay attacks possible.',
    recommendation: 'Add seqno verification to all external message handlers.',
  },
  {
    id: 'INSUFFICIENT_GAS_FORWARD',
    category: 'gas-economics',
    severity: 'medium',
    pattern: /SendRemainingValue|mode:\s*64/,
    antiPattern: /SendRemainingBalance|mode:\s*128/,
    description: 'Uses SendRemainingValue (mode 64) which may not forward enough gas for complex child operations.',
    recommendation: 'Verify gas forwarding is sufficient for all child message processing.',
  },
  {
    id: 'UNBOUNDED_DICT',
    category: 'gas-economics',
    severity: 'medium',
    pattern: /\.set\s*\(|dict_set|udict_set|idict_set/,
    antiPattern: /\.size|require.*(?:length|count|size)\s*[<≤]/s,
    description: 'Dictionary set operation without bounds check. Attacker can bloat storage causing gas exhaustion.',
    recommendation: 'Add size limits on dictionary entries.',
  },
  {
    id: 'MISSING_TRANSFER_NOTIFICATION',
    category: 'standards-compliance',
    severity: 'high',
    pattern: /jetton|token.*transfer/i,
    antiPattern: /transfer_notification|0x7362d09c/,
    description: 'Jetton transfer without transfer_notification (TEP-74 violation). Receiving contracts will not be notified.',
    recommendation: 'Send transfer_notification (op 0x7362d09c) to the destination after transfer.',
  },
  {
    id: 'INTEGER_OVERFLOW',
    category: 'arithmetic',
    severity: 'high',
    pattern: /\+\s*(?:amount|value|balance|quantity)/,
    antiPattern: /require.*[<>]|throw_if|throw_unless|assert/,
    description: 'Arithmetic operation on balance/amount without overflow check. TVM exit code 4 on 257-bit overflow.',
    recommendation: 'Add bounds checking before arithmetic operations on user-supplied values.',
  },
];

// ---------------------------------------------------------------------------
// Baseline Agent
// ---------------------------------------------------------------------------

export class BaselineAgent implements Agent {
  name = 'tvmbench-baseline';
  version = '0.1.0';

  async execute(task: AgentTask): Promise<AgentResponse> {
    if (task.mode !== 'detect') {
      // Baseline only supports detect mode
      return { mode: 'detect', findings: [] } as DetectResponse;
    }

    const source = task.contractSource;
    const findings: VulnerabilityFinding[] = [];

    for (const rule of RULES) {
      if (!rule.pattern.test(source)) continue;
      if (rule.antiPattern && rule.antiPattern.test(source)) continue;

      // Find approximate line number
      const match = source.match(rule.pattern);
      const line = match?.index != null
        ? source.substring(0, match.index).split('\n').length
        : undefined;

      findings.push({
        id: rule.id,
        category: rule.category,
        severity: rule.severity,
        line,
        description: rule.description,
        recommendation: rule.recommendation,
        confidence: 0.5, // Pattern matching = moderate confidence
      });
    }

    return { mode: 'detect', findings } as DetectResponse;
  }
}

export function createAgent(): Agent {
  return new BaselineAgent();
}
