import { describe, expect, it } from "bun:test";
import {
  clusterTopicForItem,
  consolidateClusterDeterministic,
  findConsolidationClusters,
  MIN_CLUSTER_SIZE,
} from "../src/memory/consolidator";
import type { MemoryItem } from "../src/db/schema/memory";
import { MemoryStatus } from "../src/models/memory";

function mem(partial: Partial<MemoryItem> & { id: number }): MemoryItem {
  return {
    userId: "test-user",
    content: partial.value || partial.content || "",
    type: "preference",
    topicKey: "",
    subject: "user",
    predicate: "",
    value: "",
    scope: "user",
    confidence: 0.9,
    importance: 0.8,
    stability: 0.85,
    freshness: 1,
    informationGain: 0.9,
    sourceMessageIdsJson: "[]",
    supersedesId: null,
    contradictsIdsJson: "[]",
    relatedMemoryIdsJson: "[]",
    relationship: null,
    status: MemoryStatus.ACTIVE,
    version: 1,
    validFrom: null,
    validUntil: null,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    ...partial,
  };
}

describe("Memory Consolidation Engine", () => {
  it("assigns tech_stack cluster topics for stack preferences", () => {
    expect(
      clusterTopicForItem(
        mem({
          id: 1,
          predicate: "preferred_language",
          value: "TypeScript",
          topicKey: "preference:language",
        })
      )
    ).toBe("user.tech_stack");
    expect(
      clusterTopicForItem(
        mem({
          id: 2,
          predicate: "favorite_color",
          value: "red",
          topicKey: "preference:favorite_color",
        })
      )
    ).toBeNull();
  });

  it("finds a cluster when ≥3 related stack memories exist", () => {
    const items = [
      mem({ id: 1, predicate: "preferred_language", value: "TypeScript", topicKey: "preference:language" }),
      mem({ id: 2, predicate: "preferred_database", value: "Neon", topicKey: "preference:database" }),
      mem({ id: 3, predicate: "preferred_runtime", value: "Cloudflare Workers", topicKey: "preference:runtime" }),
      mem({ id: 4, predicate: "preferred_framework", value: "Hono", topicKey: "preference:framework" }),
    ];
    const clusters = findConsolidationClusters(items, MIN_CLUSTER_SIZE);
    expect(clusters).toHaveLength(1);
    expect(clusters[0].topic).toBe("user.tech_stack");
    expect(clusters[0].items.length).toBe(4);
  });

  it("does not cluster below the minimum size", () => {
    const items = [
      mem({ id: 1, predicate: "language", value: "TypeScript", topicKey: "preference:language" }),
      mem({ id: 2, predicate: "database", value: "Neon", topicKey: "preference:database" }),
    ];
    expect(findConsolidationClusters(items)).toHaveLength(0);
  });

  it("merges stack preferences into one ARCHITECTURE memory", () => {
    const items = [
      mem({ id: 1, predicate: "preferred_language", value: "TypeScript", confidence: 0.9, topicKey: "preference:language" }),
      mem({ id: 2, predicate: "preferred_database", value: "Neon", confidence: 0.85, topicKey: "preference:database" }),
      mem({ id: 3, predicate: "preferred_runtime", value: "Cloudflare Workers", confidence: 0.9, topicKey: "preference:runtime" }),
      mem({ id: 4, predicate: "preferred_framework", value: "Hono", confidence: 0.8, topicKey: "preference:framework" }),
      mem({ id: 5, predicate: "preferred_language", value: "JavaScript", confidence: 0.4, topicKey: "preference:language" }),
    ];

    const result = consolidateClusterDeterministic("user.tech_stack", items);
    expect(result.consolidated).toHaveLength(1);
    const c = result.consolidated[0];
    expect(c.type).toBe("ARCHITECTURE");
    expect(c.predicate).toBe("tech_stack");
    expect(c.topicKey).toBe("user.tech_stack");
    expect(typeof c.value).toBe("object");
    const value = c.value as Record<string, string>;
    expect(value.language).toBe("TypeScript");
    expect(value.database).toBe("Neon");
    expect(value.runtime).toBe("Cloudflare Workers");
    expect(value.framework).toBe("Hono");
    expect(result.superseded_ids).toContain("1");
    expect(result.superseded_ids).toContain("5");
    expect(result.conflicts_detected.length).toBeGreaterThanOrEqual(1);
    expect(result.conflicts_detected[0].description).toContain("TypeScript");
    expect(result.conflicts_detected[0].resolution.toLowerCase()).toContain("typescript");
  });
});
