import { describe, expect, it } from "bun:test";
import { parseCorrection, stripCorrectionPrefix } from "../src/memory/correction";
import { parseRevocation } from "../src/memory/revocation";

describe("Correction & Revocation Parsing (FIX.md §3 & §4)", () => {
  it("strips correction prefixes", () => {
    const [stripped, had] = stripCorrectionPrefix("Actually, we use PostgreSQL");
    expect(had).toBe(true);
    expect(stripped).toBe("we use PostgreSQL");
  });

  it("parses explicit structured corrections", () => {
    const corr1 = parseCorrection("Cloudisy changed from Neon to self-hosted PostgreSQL");
    expect(corr1).not.toBeNull();
    expect(corr1?.target).toBe("Cloudisy");
    expect(corr1?.oldValue).toBe("Neon");
    expect(corr1?.newValue).toBe("self-hosted PostgreSQL");

    const corr2 = parseCorrection("The database was changed to self-hosted PostgreSQL");
    expect(corr2).not.toBeNull();
    expect(corr2?.target).toBe("database");
    expect(corr2?.newValue).toBe("self-hosted PostgreSQL");
  });

  it("parses revocation and reset statements", () => {
    const rev1 = parseRevocation("The temporary password was reset; ignore temp1234");
    expect(rev1).not.toBeNull();
    expect(rev1?.target).toBe("temporary password");
    expect(rev1?.value).toBe("temp1234");

    const rev2 = parseRevocation("Ignore the previous password");
    expect(rev2).not.toBeNull();
    expect(rev2?.target).toBe("password");
  });
});
