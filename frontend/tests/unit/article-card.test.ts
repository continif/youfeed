// Test del componente ArticleCard: rendering, fallback immagini, topic colors,
// formattazione date e descrizione (strip HTML + truncate).

import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import ArticleCard from "@/components/articles/ArticleCard.vue";
import type { ArticleListItem } from "@/types/api";

function makeItem(overrides: Partial<ArticleListItem> = {}): ArticleListItem {
  return {
    id: 1,
    url_canonical: "https://x.com/a",
    title: "Titolo articolo",
    description: null,
    image_url: null,
    image_local_url: null,
    image_width: null,
    image_height: null,
    author: null,
    published_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(), // 1h fa
    source: { id: 1, title: "Source X", favicon_url: null, url_site: null },
    topics: [],
    ...overrides,
  };
}

describe("ArticleCard", () => {
  it("renders title with anchor to canonical URL", () => {
    const w = mount(ArticleCard, { props: { item: makeItem() } });
    const a = w.find("h2 a");
    expect(a.attributes("href")).toBe("https://x.com/a");
    expect(a.attributes("target")).toBe("_blank");
    expect(a.attributes("rel")).toContain("noopener");
    expect(a.text()).toBe("Titolo articolo");
  });

  it("does not render <picture> when no image", () => {
    const w = mount(ArticleCard, { props: { item: makeItem() } });
    expect(w.find("picture").exists()).toBe(false);
  });

  it("uses image_local_url when present (mobile srcset replaces _d.webp with _m.webp)", () => {
    const item = makeItem({
      image_local_url: "/images/ab/cd/abcd_d.webp",
      image_width: 1200,
      image_height: 800,
    });
    const w = mount(ArticleCard, { props: { item } });
    expect(w.find("picture").exists()).toBe(true);
    const source = w.find("source");
    expect(source.attributes("media")).toBe("(max-width: 599px)");
    expect(source.attributes("srcset")).toBe("/images/ab/cd/abcd_m.webp");
    const img = w.find("img");
    expect(img.attributes("src")).toBe("/images/ab/cd/abcd_d.webp");
    expect(img.attributes("width")).toBe("1200");
    expect(img.attributes("height")).toBe("800");
  });

  it("falls back to image_url when image_local_url is missing", () => {
    const item = makeItem({ image_url: "https://cdn.x.com/orig.jpg" });
    const w = mount(ArticleCard, { props: { item } });
    expect(w.find("img").attributes("src")).toBe("https://cdn.x.com/orig.jpg");
    expect(w.find("source").exists()).toBe(false); // niente local: niente <source>
  });

  it("strips HTML and truncates the description to ~180 chars", () => {
    const long = "abc ".repeat(80); // 320 char
    const item = makeItem({ description: `<p><strong>${long}</strong></p>` });
    const w = mount(ArticleCard, { props: { item } });
    const desc = w.find("p.text-sm").text();
    expect(desc).not.toContain("<strong>");
    expect(desc.length).toBeLessThanOrEqual(180);
    expect(desc.endsWith("…")).toBe(true);
  });

  it("renders a relative time in Italian", () => {
    const w = mount(ArticleCard, { props: { item: makeItem() } });
    const t = w.find("time").text();
    // 'circa 1 ora fa' o variante: deve contenere 'fa'
    expect(t).toMatch(/fa$/);
  });

  it("renders topics with type-specific styling", () => {
    const item = makeItem({
      topics: [
        { id: 1, slug: "ferrari", display_name: "Ferrari", type: "brand" },
        { id: 2, slug: "papa", display_name: "Papa", type: "person" },
        { id: 3, slug: "ai", display_name: "AI", type: "subject" },
      ],
    });
    const w = mount(ArticleCard, { props: { item } });
    const lis = w.findAll("ul li");
    expect(lis).toHaveLength(3);
    expect(lis[0].classes().some((c) => c.includes("red"))).toBe(true);
    expect(lis[1].classes().some((c) => c.includes("blue"))).toBe(true);
    expect(lis[2].classes().some((c) => c.includes("emerald"))).toBe(true);
  });

  it("hides image after a load error (graceful fallback)", async () => {
    const item = makeItem({ image_url: "https://broken/img.jpg" });
    const w = mount(ArticleCard, { props: { item } });
    expect(w.find("picture").exists()).toBe(true);
    await w.find("img").trigger("error");
    expect(w.find("picture").exists()).toBe(false);
  });
});
