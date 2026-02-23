/**
 * Tonsurance Insurability Rating Mapper
 *
 * Maps TVMBench composite scores to insurance tiers (AAA through C).
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type InsurabilityRating = 'AAA' | 'AA' | 'A' | 'BB' | 'B' | 'C';

export interface InsurabilityResult {
  rating: InsurabilityRating;
  score: number;
  premiumMultiplier: number;
  tier: string;
  eligible: boolean;
}

// ---------------------------------------------------------------------------
// Rating Table
// ---------------------------------------------------------------------------

interface RatingTier {
  min: number;
  max: number;
  rating: InsurabilityRating;
  tier: string;
  premiumMultiplier: number;
}

const RATING_TABLE: RatingTier[] = [
  { min: 900, max: 1000, rating: 'AAA', tier: 'Preferred',    premiumMultiplier: 0.5 },
  { min: 750, max: 899,  rating: 'AA',  tier: 'Standard',     premiumMultiplier: 1.0 },
  { min: 600, max: 749,  rating: 'A',   tier: 'Elevated',     premiumMultiplier: 1.5 },
  { min: 400, max: 599,  rating: 'BB',  tier: 'High Risk',    premiumMultiplier: 2.5 },
  { min: 200, max: 399,  rating: 'B',   tier: 'Very High',    premiumMultiplier: 4.0 },
  { min: 0,   max: 199,  rating: 'C',   tier: 'Uninsurable',  premiumMultiplier: Infinity },
];

// ---------------------------------------------------------------------------
// Mapper
// ---------------------------------------------------------------------------

export class InsurabilityMapper {
  /**
   * Map a TVMBench composite score (0–1000) to an insurability result.
   */
  static rate(score: number): InsurabilityResult {
    const clamped = Math.max(0, Math.min(1000, Math.round(score)));

    for (const tier of RATING_TABLE) {
      if (clamped >= tier.min && clamped <= tier.max) {
        return {
          rating: tier.rating,
          score: clamped,
          premiumMultiplier: tier.premiumMultiplier,
          tier: tier.tier,
          eligible: tier.rating !== 'C',
        };
      }
    }

    // Fallback (shouldn't reach)
    return {
      rating: 'C',
      score: clamped,
      premiumMultiplier: Infinity,
      tier: 'Uninsurable',
      eligible: false,
    };
  }
}
