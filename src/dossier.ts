// src/dossier.ts — token-radar dossier writer (Day 3).
//
// There is no vendor dossier file for this bounty (see DAY2-NOTES.md:
// no makefun-board.ts exists anywhere, and the token-radar requirements
// never mention a dossier schema), so Day 3 writes its own, modelled on
// the cooking-game kit's makefun/dossier/v1 pattern: canonical JSON
// (sorted keys, no spaces) with sha256 + bytes of every shipped output,
// the board summary, and the model summary. main.ts calls buildDossier
// after writing board.json and copying dashboard/ + screenshots/ into
// the output dir, so the grader's run reproduces the handed-in output:
// board.json is regenerated, dashboard/ + screenshots/ are copied
// byte-for-byte, and dossier.json is regenerated from those same files.

import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

/** This entry's dossier schema (our own; the bounty defines none). */
export const DOSSIER_SCHEMA = "token-radar/dossier/v1";

/** Code-unit order, the same on every machine (localeCompare is not). */
const byCodeUnit = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

const sha256Hex = (bytes: Buffer): string =>
  createHash("sha256").update(bytes).digest("hex");

/**
 * JSON with every object's keys in code-unit order and no whitespace:
 * one spelling per value. Takes null, booleans, finite numbers,
 * strings, arrays and plain objects; throws TypeError on anything else.
 */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new TypeError(`canonicalJson: ${value} is not a finite number`);
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((v) => canonicalJson(v)).join(",")}]`;
  }
  if (typeof value === "object") {
    const proto = Object.getPrototypeOf(value);
    if (proto !== Object.prototype && proto !== null) {
      throw new TypeError("canonicalJson: only plain objects and arrays");
    }
    const o = value as Record<string, unknown>;
    return `{${Object.keys(o)
      .sort(byCodeUnit)
      .map((k) => `${JSON.stringify(k)}:${canonicalJson(o[k])}`)
      .join(",")}}`;
  }
  throw new TypeError(`canonicalJson: a ${typeof value} has no JSON form`);
}

export interface DossierFile {
  path: string;
  bytes: number;
  sha256: string;
}

/** Every file under `dir`, by path relative to `base`, in code-unit order. */
function listFiles(dir: string, base: string): DossierFile[] {
  const out: DossierFile[] = [];
  const walk = (rel: string): void => {
    const full = rel === "" ? dir : join(dir, rel);
    for (const entry of readdirSync(full, { withFileTypes: true }).sort((a, b) =>
      byCodeUnit(a.name, b.name),
    )) {
      const path = rel === "" ? entry.name : `${rel}/${entry.name}`;
      if (entry.isDirectory()) {
        walk(path);
      } else if (entry.isFile()) {
        const bytes = readFileSync(join(dir, path));
        out.push({ path: `${base}/${path}`, bytes: bytes.length, sha256: sha256Hex(bytes) });
      } else {
        throw new Error(`dossier: ${base}/${path}: not a plain file`);
      }
    }
  };
  walk("");
  out.sort((a, b) => byCodeUnit(a.path, b.path));
  return out;
}

/** The model summary, fixed constants from MODEL_CARD.md (Day 1 fit). */
const MODEL_SUMMARY = {
  conformal_80_factor: 10.2,
  conformal_80_log: 2.32,
  cv_median_ratio: 3.43,
  launch_odds_auc: 0.7,
  launch_odds_brier: 0.221,
  walk_forward_median_ratio: 3.2,
};

/**
 * The dossier (token-radar/dossier/v1) of an output directory, as
 * canonical JSON bytes. `outDir` must already hold board.json (written
 * by main.ts just before) and the copied dashboard/ + screenshots/
 * directories. The screenshots are the PNG files under screenshots/,
 * in name order, the first the cover. Throws on a missing board,
 * a missing dashboard, or no screenshots.
 */
export function buildDossier(outDir: string): Uint8Array {
  let board: {
    generatedAt?: string;
    snapshotProtocols?: number;
    families?: number;
    tokenedFamilies?: number;
    reviewItems?: number;
    watchlist?: number;
    rows?: { rank: number; name: string; expectedValueUsd: number }[];
  };
  try {
    board = JSON.parse(readFileSync(join(outDir, "board.json"), "utf8"));
  } catch {
    throw new Error("buildDossier: no board.json in the output dir (main.ts writes it first)");
  }
  if (!Array.isArray(board.rows) || board.rows.length === 0) {
    throw new Error("buildDossier: board.json holds no rows");
  }
  let dashboardFiles: DossierFile[];
  try {
    dashboardFiles = listFiles(join(outDir, "dashboard"), "dashboard");
  } catch {
    throw new Error("buildDossier: no dashboard/ in the output dir (main.ts copies it first)");
  }
  if (dashboardFiles.length === 0) {
    throw new Error("buildDossier: dashboard/ is empty");
  }
  let screenshotFiles: DossierFile[];
  try {
    screenshotFiles = listFiles(join(outDir, "screenshots"), "screenshots").filter((f) =>
      /\.png$/i.test(f.path) || /\.jpe?g$/i.test(f.path),
    );
  } catch {
    throw new Error("buildDossier: no screenshots/ in the output dir (main.ts copies it first)");
  }
  if (screenshotFiles.length === 0) {
    throw new Error("buildDossier: screenshots/ holds no PNG or JPEG image");
  }
  const dossier = {
    board: {
      families: board.families,
      review_items: board.reviewItems,
      rows: board.rows.length,
      snapshot_date: board.generatedAt ?? "2026-11-26",
      snapshot_protocols: board.snapshotProtocols,
      tokened_families_excluded: board.tokenedFamilies,
      top_3: board.rows.slice(0, 3).map((r) => ({
        expected_value_usd: r.expectedValueUsd,
        name: r.name,
        rank: r.rank,
      })),
      watchlist: board.watchlist,
    },
    dashboard: {
      files: dashboardFiles,
      total_bytes: dashboardFiles.reduce((n, f) => n + f.bytes, 0),
    },
    model: MODEL_SUMMARY,
    schema: DOSSIER_SCHEMA,
    screenshots: {
      cover: screenshotFiles[0]!.path,
      images: screenshotFiles,
    },
  };
  return new TextEncoder().encode(canonicalJson(dossier));
}
