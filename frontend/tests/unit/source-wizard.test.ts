// Test del SourceWizard: navigazione 3-step, presetFromFeatured, errori discovery.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount, flushPromises } from "@vue/test-utils";

vi.mock("@/services/sources", () => ({
  discoverUrl: vi.fn(),
  linkSource: vi.fn(),
}));
vi.mock("@/services/categories", () => ({
  fetchCategoryTree: vi.fn(),
  createCategory: vi.fn(),
  flattenTree: (t: { tree: Array<{ id: number; name: string }> }) =>
    t.tree.map((n) => ({ id: n.id, name: n.name, depth: 0 })),
}));

import * as sourcesApi from "@/services/sources";
import * as catsApi from "@/services/categories";
import SourceWizard from "@/components/sources/SourceWizard.vue";
import type { DiscoveryOut, FeaturedSourceItem } from "@/types/api";

const mocked = {
  discoverUrl: vi.mocked(sourcesApi.discoverUrl),
  linkSource: vi.mocked(sourcesApi.linkSource),
  fetchCategoryTree: vi.mocked(catsApi.fetchCategoryTree),
  createCategory: vi.mocked(catsApi.createCategory),
};

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
  mocked.fetchCategoryTree.mockResolvedValue({
    tree: [
      { id: 1, name: "News", slug: "news", parent_id: null, position: 0, color: null, is_public: true, children: [] },
    ],
  });
});

const VALID_DISCOVERY: DiscoveryOut = {
  kind: "rss",
  source_id: 99,
  url_site: "https://example.com",
  url_feed: "https://example.com/feed.xml",
  wp_api_root: null,
  candidates: [
    {
      url_feed: "https://example.com/feed.xml",
      title: "Example Feed",
      sample_articles: [
        { title: "A", url: "https://example.com/a", published_at: "2026-01-01" },
      ],
    },
  ],
  og: {
    title: "Example",
    description: null,
    image: null,
    site_name: null,
    favicon: null,
  },
  reason: null,
};

describe("SourceWizard", () => {
  it("starts on step 1 (URL input)", () => {
    const w = mount(SourceWizard);
    expect(w.find("input[type='url']").exists()).toBe(true);
    expect(w.find("button[type='submit']").text()).toContain("Analizza");
  });

  it("calls discoverUrl on submit and advances to step 2 on success", async () => {
    mocked.discoverUrl.mockResolvedValueOnce(VALID_DISCOVERY);
    const w = mount(SourceWizard);
    await flushPromises();

    await w.find("input[type='url']").setValue("https://example.com");
    await w.find("form").trigger("submit");
    await flushPromises();

    expect(mocked.discoverUrl).toHaveBeenCalledWith("https://example.com");
    expect(w.text()).toContain("Continua");
  });

  it("shows reason when discovery returns kind=invalid", async () => {
    mocked.discoverUrl.mockResolvedValueOnce({
      ...VALID_DISCOVERY,
      kind: "invalid",
      source_id: null,
      reason: "Nessun feed trovato.",
    });

    const w = mount(SourceWizard);
    await flushPromises();
    await w.find("input[type='url']").setValue("https://x.com");
    await w.find("form").trigger("submit");
    await flushPromises();

    expect(w.text()).toContain("Nessun feed trovato.");
    // Resta su step 1 (form input visibile)
    expect(w.find("input[type='url']").exists()).toBe(true);
  });

  it("step 3: linkSource called with source_id + categoryId, then emits 'added'", async () => {
    mocked.discoverUrl.mockResolvedValueOnce(VALID_DISCOVERY);
    mocked.linkSource.mockResolvedValueOnce({
      id: 555,
      category_id: 1,
      custom_title: null,
      added_at: "2026-05-06T10:00:00Z",
      source: {
        id: 99,
        kind: "rss",
        url_site: "https://example.com",
        url_feed: "https://example.com/feed.xml",
        wp_api_root: null,
        title: "Example",
        favicon_url: null,
        status: "active",
      },
    });

    const w = mount(SourceWizard);
    await flushPromises();
    await w.find("input[type='url']").setValue("https://example.com");
    await w.find("form").trigger("submit");
    await flushPromises();

    // Step 2 -> Continua
    const continueBtn = w
      .findAll("button")
      .find((b) => b.text().includes("Continua"));
    expect(continueBtn).toBeTruthy();
    await continueBtn!.trigger("click");
    await flushPromises();

    // Step 3 -> seleziona categoria
    const select = w.find("select");
    await select.setValue("1");
    const confirmBtn = w
      .findAll("button")
      .find((b) => b.text().includes("Aggiungi"));
    await confirmBtn!.trigger("click");
    await flushPromises();

    expect(mocked.linkSource).toHaveBeenCalledWith(99, 1);
    const events = w.emitted("added");
    expect(events).toBeTruthy();
    expect(events?.[0]?.[0]).toBe(555);
  });

  it("presetFromFeatured() jumps directly to step 3", async () => {
    const w = mount(SourceWizard);
    await flushPromises();

    const featured: FeaturedSourceItem = {
      source_id: 42,
      display_name: "Featured Source",
      description: "Desc",
      position: 1,
      source: {
        id: 42,
        kind: "rss",
        url_site: "https://feat.com",
        url_feed: "https://feat.com/rss.xml",
        wp_api_root: null,
        title: "Featured",
        favicon_url: null,
        status: "active",
      },
    };
    (w.vm as unknown as {
      presetFromFeatured: (i: FeaturedSourceItem) => void;
    }).presetFromFeatured(featured);
    await flushPromises();

    // Step 3 -> select visibile
    expect(w.find("select").exists()).toBe(true);
  });
});
