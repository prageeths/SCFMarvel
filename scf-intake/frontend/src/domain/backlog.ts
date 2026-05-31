// Synthetic intake backlog used for prioritization comparison (PRD §16.2).
// No real customer / account / PII data — synthetic only.

import type { BacklogItem } from "./types";

export const SEED_BACKLOG: BacklogItem[] = [
  {
    requestId: "SCF-INTK-000101",
    title: "Real-time supplier early-payment APR transparency",
    org: "Business line",
    roiScore: 84,
    band: "P0",
  },
  {
    requestId: "SCF-INTK-000102",
    title: "OFAC sanctioned-party screening on counterparty onboarding",
    org: "Risk & Compliance",
    roiScore: 81,
    band: "P0",
  },
  {
    requestId: "SCF-INTK-000103",
    title: "Basel III RWA reporting field for receivables financing",
    org: "Regulatory",
    roiScore: 78,
    band: "P1",
  },
  {
    requestId: "SCF-INTK-000104",
    title: "Automated reconciliation of buyer remittance files",
    org: "Accounting",
    roiScore: 71,
    band: "P1",
  },
  {
    requestId: "SCF-INTK-000105",
    title: "Dynamic discounting offer engine for mid-market buyers",
    org: "Leadership",
    roiScore: 68,
    band: "P1",
  },
  {
    requestId: "SCF-INTK-000106",
    title: "Decommission COBOL FX-rate batch feed (legacy LIMITS)",
    org: "Legacy platform",
    roiScore: 57,
    band: "P2",
  },
  {
    requestId: "SCF-INTK-000107",
    title: "Multi-currency invoice upload via CSV template",
    org: "Business line",
    roiScore: 52,
    band: "P2",
  },
  {
    requestId: "SCF-INTK-000108",
    title: "Configurable email cadence for program utilization alerts",
    org: "Business line",
    roiScore: 44,
    band: "P3",
  },
  {
    requestId: "SCF-INTK-000109",
    title: "Dark-mode theme for the relationship-manager console",
    org: "Business line",
    roiScore: 28,
    band: "Defer",
  },
  {
    requestId: "SCF-INTK-000110",
    title: "Custom emoji reactions on agent decision feed",
    org: "Business line",
    roiScore: 16,
    band: "Defer",
  },
];
