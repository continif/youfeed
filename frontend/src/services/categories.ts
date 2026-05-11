import { api } from "@/services/api";
import type { CategoryOut, CategoryTreeOut } from "@/types/api";

export async function fetchCategoryTree(): Promise<CategoryTreeOut> {
  return api.get("yf_me/categories").json<CategoryTreeOut>();
}

export async function createCategory(
  name: string,
  parentId: number | null = null,
  color: string | null = null,
): Promise<CategoryOut> {
  return api
    .post("yf_me/categories", {
      json: { name, parent_id: parentId, color },
    })
    .json<CategoryOut>();
}

export async function updateCategory(
  id: number,
  patch: { name?: string; color?: string | null; position?: number; is_public?: boolean },
): Promise<CategoryOut> {
  return api.patch(`yf_me/categories/${id}`, { json: patch }).json<CategoryOut>();
}

export async function deleteCategory(id: number): Promise<void> {
  await api.delete(`yf_me/categories/${id}`);
}

/** Appiattisce l'albero in [{id, name, depth}] per i select dei form. */
export function flattenTree(
  tree: CategoryTreeOut,
): Array<{ id: number; name: string; depth: number }> {
  const out: Array<{ id: number; name: string; depth: number }> = [];
  function walk(nodes: CategoryTreeOut["tree"], depth: number): void {
    for (const n of nodes) {
      out.push({ id: n.id, name: n.name, depth });
      if (n.children?.length) walk(n.children, depth + 1);
    }
  }
  walk(tree.tree, 0);
  return out;
}
