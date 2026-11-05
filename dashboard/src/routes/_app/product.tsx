import { createFileRoute } from "@tanstack/react-router";

// Temporary, for showing customers the product. To remove it: delete this file, the menu entry
// in app-shell.tsx, and public/demo/. The page is a copy of demo/product-3d/index.html.
export const Route = createFileRoute("/_app/product")({
  head: () => ({ meta: [{ title: "3D model - Prins" }] }),
  component: ProductPage,
});

function ProductPage() {
  return (
    <iframe
      src="/demo/product-3d.html?app=1"
      title="Interactive 3D model of the Prins device. Concept design."
      className="rise-in min-h-[32rem] w-full flex-1 rounded-3xl border bg-[#0a0807]"
    />
  );
}
