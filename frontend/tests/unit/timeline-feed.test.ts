// Test del componente TimelineFeed: load iniziale, paginazione cursor,
// gestione errori, slot empty.

import { describe, it, expect, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { HTTPError } from "ky";
import TimelineFeed from "@/components/articles/TimelineFeed.vue";
import type { ArticleListOut } from "@/types/api";

function fakeItem(id: number) {
  return {
    id,
    url_canonical: `https://x.com/${id}`,
    title: `T${id}`,
    description: null,
    image_url: null,
    image_local_url: null,
    image_width: null,
    image_height: null,
    author: null,
    published_at: "2026-05-06T10:00:00Z",
    source: { id: 1, title: "S", favicon_url: null, url_site: null },
    topics: [],
  };
}

function makeFetcher(pages: ArticleListOut[]) {
  let i = 0;
  return vi.fn(async (_cursor?: string): Promise<ArticleListOut> => {
    return pages[Math.min(i++, pages.length - 1)];
  });
}

describe("TimelineFeed", () => {
  it("loads initial page on mount", async () => {
    const fetcher = makeFetcher([
      { items: [fakeItem(1), fakeItem(2)], next_cursor: null },
    ]);
    const w = mount(TimelineFeed, { props: { fetcher } });
    await flushPromises();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledWith(undefined);
    expect(w.findAllComponents({ name: "ArticleCard" })).toHaveLength(2);
    expect(w.find("button").exists()).toBe(false); // no cursor: niente "Carica altri"
  });

  it("appends items on load more (cursor pagination)", async () => {
    const fetcher = makeFetcher([
      { items: [fakeItem(1), fakeItem(2)], next_cursor: "c1" },
      { items: [fakeItem(3)], next_cursor: null },
    ]);
    const w = mount(TimelineFeed, { props: { fetcher } });
    await flushPromises();

    expect(w.findAllComponents({ name: "ArticleCard" })).toHaveLength(2);
    expect(w.find("button").text()).toContain("Carica altri");

    await w.find("button").trigger("click");
    await flushPromises();

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher).toHaveBeenLastCalledWith("c1");
    expect(w.findAllComponents({ name: "ArticleCard" })).toHaveLength(3);
    expect(w.find("button").exists()).toBe(false);
  });

  it("renders the empty slot when there are no items", async () => {
    const fetcher = makeFetcher([{ items: [], next_cursor: null }]);
    const w = mount(TimelineFeed, {
      props: { fetcher },
      slots: { empty: "Nessun articolo (custom)" },
    });
    await flushPromises();
    expect(w.text()).toContain("Nessun articolo (custom)");
  });

  it("shows error message on fetch failure", async () => {
    const errResp = new Response(
      JSON.stringify({ error: { code: "boom", message: "API down" } }),
      { status: 500, headers: { "content-type": "application/json" } },
    );
    const httpErr = new HTTPError(errResp, new Request("http://x/"), {} as never);
    const fetcher = vi.fn(async () => {
      throw httpErr;
    });
    const w = mount(TimelineFeed, { props: { fetcher } });
    await flushPromises();
    expect(w.text()).toContain("API down");
  });

  it("exposes a reload method that refetches from scratch", async () => {
    const fetcher = makeFetcher([
      { items: [fakeItem(1)], next_cursor: null },
      { items: [fakeItem(2)], next_cursor: null },
    ]);
    const w = mount(TimelineFeed, { props: { fetcher } });
    await flushPromises();
    expect(w.findAllComponents({ name: "ArticleCard" })).toHaveLength(1);

    // reload non passa cursor (riparte da capo, sostituisce items)
    (w.vm as unknown as { reload: () => Promise<void> }).reload();
    await flushPromises();

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher).toHaveBeenLastCalledWith(undefined);
    // Solo l'ultimo fetch è visibile (sostituisce, non appende)
    expect(w.findAllComponents({ name: "ArticleCard" })).toHaveLength(1);
  });
});
